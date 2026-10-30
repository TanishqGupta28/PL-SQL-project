"""
database.py - Database Layer for FD Manager System
Implements SQLite schema, foreign key enforcement, indexes, CHECK constraints,
parameterized queries, transaction helpers, and CRUD/aggregate operations.
"""

import os
import sqlite3
from contextlib import contextmanager
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

from fd_calculator import (
    calculate_maturity_amount,
    calculate_maturity_date,
    determine_status,
)

DEFAULT_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fd_manager.db")


def get_db_path() -> str:
    """Get the active database file path from environment or default."""
    return os.environ.get("FD_MANAGER_DB", DEFAULT_DB_PATH)


@contextmanager
def get_db_connection(db_path: Optional[str] = None):
    """
    Context manager for SQLite connection with PRAGMA foreign_keys = ON.
    Automatically commits on success or rolls back on exception.
    """
    path = db_path or get_db_path()
    conn = sqlite3.connect(path, timeout=10.0)
    conn.row_factory = sqlite3.Row
    # Enforce foreign key constraints
    conn.execute("PRAGMA foreign_keys = ON;")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(db_path: Optional[str] = None) -> None:
    """
    Initialize relational tables, constraints, and indexes.
    Idempotent: uses CREATE TABLE IF NOT EXISTS.
    """
    path = db_path or get_db_path()
    with get_db_connection(path) as conn:
        cursor = conn.cursor()

        # 1. Customers Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS Customers (
                customer_id TEXT PRIMARY KEY,
                full_name TEXT NOT NULL,
                phone TEXT NOT NULL,
                email TEXT NOT NULL,
                city TEXT NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 1 CHECK(is_active IN (0, 1)),
                created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
            );
        """)

        # 2. Users Table (Authentication & Role-Based Access)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS Users (
                user_id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('admin', 'customer')),
                customer_id TEXT UNIQUE REFERENCES Customers(customer_id) ON DELETE SET NULL,
                is_active INTEGER NOT NULL DEFAULT 1 CHECK(is_active IN (0, 1)),
                created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
            );
        """)

        # 3. Banks Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS Banks (
                bank_id INTEGER PRIMARY KEY AUTOINCREMENT,
                bank_name TEXT UNIQUE NOT NULL,
                branch_name TEXT NOT NULL,
                rate_source_note TEXT
            );
        """)

        # 4. Fixed Deposits Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS FixedDeposits (
                fd_id TEXT PRIMARY KEY,
                customer_id TEXT NOT NULL REFERENCES Customers(customer_id) ON DELETE RESTRICT,
                bank_id INTEGER NOT NULL REFERENCES Banks(bank_id) ON DELETE RESTRICT,
                principal_amount REAL NOT NULL CHECK(principal_amount > 0),
                annual_interest_rate REAL NOT NULL CHECK(annual_interest_rate > 0 AND annual_interest_rate <= 30),
                tenure_months INTEGER NOT NULL CHECK(tenure_months > 0),
                compounding_frequency TEXT NOT NULL CHECK(compounding_frequency IN ('Quarterly', 'Monthly', 'Half-Yearly', 'Annually')),
                start_date TEXT NOT NULL,
                maturity_date TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('Active', 'Matured', 'Closed')),
                created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
            );
        """)

        # Indexes for query optimization
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_fd_customer_id ON FixedDeposits(customer_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_fd_bank_id ON FixedDeposits(bank_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_fd_maturity_date ON FixedDeposits(maturity_date);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_fd_status ON FixedDeposits(status);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_cust_city ON Customers(city);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_cust_active ON Customers(is_active);")


def sync_fd_statuses(db_path: Optional[str] = None) -> int:
    """
    Sync FD status: update 'Active' to 'Matured' if maturity_date has arrived/passed.
    Guarantees: 'Closed' deposits are preserved and never overwritten.
    Returns the count of updated rows.
    """
    path = db_path or get_db_path()
    today_str = date.today().strftime("%Y-%m-%d")
    with get_db_connection(path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE FixedDeposits
            SET status = 'Matured',
                updated_at = datetime('now', 'localtime')
            WHERE status = 'Active'
              AND maturity_date <= ?;
        """, (today_str,))
        return cursor.rowcount


# ============================================================================
# Customer Operations
# ============================================================================

def generate_next_customer_id(db_path: Optional[str] = None) -> str:
    """Generate next sequential customer ID, e.g., CUST021."""
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT customer_id FROM Customers WHERE customer_id LIKE 'CUST%' ORDER BY customer_id DESC LIMIT 1;")
        row = cursor.fetchone()
        if not row:
            return "CUST001"
        try:
            curr_num = int(row["customer_id"].replace("CUST", ""))
            return f"CUST{curr_num + 1:03d}"
        except Exception:
            return f"CUST{len(get_customers(db_path=db_path)) + 1:03d}"


def get_customers(
    search_query: Optional[str] = None,
    status_filter: Optional[str] = None,
    db_path: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Retrieve customers with optional search by Name, ID, Phone, City
    and filter by active status ('Active', 'Deactivated', or 'All').
    """
    query = """
        SELECT c.customer_id, c.full_name, c.phone, c.email, c.city, c.is_active, c.created_at,
               COUNT(fd.fd_id) AS total_fds,
               COALESCE(SUM(fd.principal_amount), 0.0) AS total_principal
        FROM Customers c
        LEFT JOIN FixedDeposits fd ON c.customer_id = fd.customer_id
        WHERE 1=1
    """
    params: List[Any] = []

    if status_filter == "Active":
        query += " AND c.is_active = 1"
    elif status_filter == "Deactivated":
        query += " AND c.is_active = 0"

    if search_query and search_query.strip():
        term = f"%{search_query.strip()}%"
        query += " AND (c.full_name LIKE ? OR c.customer_id LIKE ? OR c.phone LIKE ? OR c.city LIKE ?)"
        params.extend([term, term, term, term])

    query += " GROUP BY c.customer_id ORDER BY c.customer_id ASC"

    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]


def get_customer_by_id(customer_id: str, db_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Retrieve a single customer profile by customer_id."""
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM Customers WHERE customer_id = ?;", (customer_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def add_customer(
    customer_id: str,
    full_name: str,
    phone: str,
    email: str,
    city: str,
    db_path: Optional[str] = None,
) -> None:
    """Insert a new customer."""
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO Customers (customer_id, full_name, phone, email, city, is_active)
            VALUES (?, ?, ?, ?, ?, 1);
        """, (customer_id.strip(), full_name.strip(), phone.strip(), email.strip(), city.strip()))


def update_customer(
    customer_id: str,
    full_name: str,
    phone: str,
    email: str,
    city: str,
    db_path: Optional[str] = None,
) -> None:
    """Update customer contact and personal details."""
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE Customers
            SET full_name = ?, phone = ?, email = ?, city = ?
            WHERE customer_id = ?;
        """, (full_name.strip(), phone.strip(), email.strip(), city.strip(), customer_id))


def set_customer_status(customer_id: str, is_active: int, db_path: Optional[str] = None) -> None:
    """Activate or deactivate a customer account."""
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE Customers SET is_active = ? WHERE customer_id = ?;", (is_active, customer_id))
        # Keep user login status in sync
        cursor.execute("UPDATE Users SET is_active = ? WHERE customer_id = ?;", (is_active, customer_id))


# ============================================================================
# Bank Operations
# ============================================================================

def get_all_banks(db_path: Optional[str] = None) -> List[Dict[str, Any]]:
    """List all registered banks."""
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM Banks ORDER BY bank_name ASC;")
        return [dict(row) for row in cursor.fetchall()]


def get_bank_by_id(bank_id: int, db_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Fetch bank by ID."""
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM Banks WHERE bank_id = ?;", (bank_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def add_bank(bank_name: str, branch_name: str, rate_source_note: str = "", db_path: Optional[str] = None) -> int:
    """Add a new bank record."""
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO Banks (bank_name, branch_name, rate_source_note)
            VALUES (?, ?, ?);
        """, (bank_name.strip(), branch_name.strip(), rate_source_note.strip()))
        return cursor.lastrowid


# ============================================================================
# Fixed Deposit Operations
# ============================================================================

def generate_next_fd_id(db_path: Optional[str] = None) -> str:
    """Generate next sequential FD ID, e.g., FD1001, FD1002."""
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT fd_id FROM FixedDeposits WHERE fd_id LIKE 'FD%' ORDER BY fd_id DESC LIMIT 1;")
        row = cursor.fetchone()
        if not row:
            return "FD1001"
        try:
            curr_num = int(row["fd_id"].replace("FD", ""))
            return f"FD{curr_num + 1}"
        except Exception:
            return f"FD{1000 + len(get_fixed_deposits(db_path=db_path)) + 1}"


def get_fixed_deposits(
    customer_id: Optional[str] = None,
    bank_id: Optional[int] = None,
    status: Optional[str] = None,
    search_query: Optional[str] = None,
    order_by: str = "fd.maturity_date ASC",
    db_path: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Search, filter, and fetch Fixed Deposits with joined customer and bank info.
    Dynamically computes estimated maturity amount and interest earned.
    """
    query = """
        SELECT fd.fd_id, fd.customer_id, fd.bank_id, fd.principal_amount,
               fd.annual_interest_rate, fd.tenure_months, fd.compounding_frequency,
               fd.start_date, fd.maturity_date, fd.status, fd.created_at, fd.updated_at,
               c.full_name AS customer_name, c.city AS customer_city, c.phone AS customer_phone,
               b.bank_name, b.branch_name
        FROM FixedDeposits fd
        JOIN Customers c ON fd.customer_id = c.customer_id
        JOIN Banks b ON fd.bank_id = b.bank_id
        WHERE 1=1
    """
    params: List[Any] = []

    if customer_id:
        query += " AND fd.customer_id = ?"
        params.append(customer_id)

    if bank_id:
        query += " AND fd.bank_id = ?"
        params.append(bank_id)

    if status and status != "All":
        query += " AND fd.status = ?"
        params.append(status)

    if search_query and search_query.strip():
        term = f"%{search_query.strip()}%"
        query += " AND (fd.fd_id LIKE ? OR c.full_name LIKE ? OR c.customer_id LIKE ? OR b.bank_name LIKE ?)"
        params.extend([term, term, term, term])

    # Allowable order by clauses
    valid_order_bys = {
        "maturity_asc": "fd.maturity_date ASC",
        "maturity_desc": "fd.maturity_date DESC",
        "principal_desc": "fd.principal_amount DESC",
        "principal_asc": "fd.principal_amount ASC",
        "fd_id_asc": "fd.fd_id ASC",
        "fd_id_desc": "fd.fd_id DESC",
    }
    safe_order_clause = valid_order_bys.get(order_by, "fd.maturity_date ASC")
    query += f" ORDER BY {safe_order_clause}"

    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        records = []
        for row in cursor.fetchall():
            d = dict(row)
            # Calculate estimated returns dynamically using calculation engine
            mat_amt, est_int = calculate_maturity_amount(
                principal=d["principal_amount"],
                annual_rate=d["annual_interest_rate"],
                tenure_months=d["tenure_months"],
                frequency=d["compounding_frequency"],
            )
            d["estimated_maturity_amount"] = mat_amt
            d["estimated_interest"] = est_int
            records.append(d)
        return records


def get_fd_by_id(fd_id: str, db_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Retrieve a single FD with joined customer and bank data."""
    results = get_fixed_deposits(search_query=fd_id, db_path=db_path)
    for r in results:
        if r["fd_id"] == fd_id:
            return r
    return None


def add_fixed_deposit(
    fd_id: str,
    customer_id: str,
    bank_id: int,
    principal_amount: float,
    annual_interest_rate: float,
    tenure_months: int,
    compounding_frequency: str,
    start_date: str,
    maturity_date: Optional[str] = None,
    status: Optional[str] = None,
    db_path: Optional[str] = None,
) -> None:
    """
    Insert a new fixed deposit. If maturity_date or status are not provided,
    calculates them automatically using the calculation engine.
    """
    if maturity_date is None:
        maturity_date = calculate_maturity_date(start_date, tenure_months)

    if status is None:
        status = determine_status(maturity_date)

    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO FixedDeposits (
                fd_id, customer_id, bank_id, principal_amount, annual_interest_rate,
                tenure_months, compounding_frequency, start_date, maturity_date, status,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now', 'localtime'), datetime('now', 'localtime'));
        """, (
            fd_id.strip(),
            customer_id.strip(),
            int(bank_id),
            float(principal_amount),
            float(annual_interest_rate),
            int(tenure_months),
            compounding_frequency,
            start_date,
            maturity_date,
            status,
        ))


def update_fixed_deposit(
    fd_id: str,
    bank_id: int,
    principal_amount: float,
    annual_interest_rate: float,
    tenure_months: int,
    compounding_frequency: str,
    start_date: str,
    maturity_date: Optional[str] = None,
    status: Optional[str] = None,
    db_path: Optional[str] = None,
) -> None:
    """
    Update fixed deposit attributes. If status is provided, it is updated;
    otherwise existing closed status is preserved, or active/matured re-evaluated.
    """
    existing = get_fd_by_id(fd_id, db_path=db_path)
    if not existing:
        raise ValueError(f"FD with ID {fd_id} not found.")

    if maturity_date is None:
        maturity_date = calculate_maturity_date(start_date, tenure_months)

    if status is None:
        status = determine_status(maturity_date, current_status=existing["status"])

    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE FixedDeposits
            SET bank_id = ?,
                principal_amount = ?,
                annual_interest_rate = ?,
                tenure_months = ?,
                compounding_frequency = ?,
                start_date = ?,
                maturity_date = ?,
                status = ?,
                updated_at = datetime('now', 'localtime')
            WHERE fd_id = ?;
        """, (
            int(bank_id),
            float(principal_amount),
            float(annual_interest_rate),
            int(tenure_months),
            compounding_frequency,
            start_date,
            maturity_date,
            status,
            fd_id,
        ))


def close_fixed_deposit(fd_id: str, db_path: Optional[str] = None) -> None:
    """
    Explicitly close a fixed deposit. Preserves history by updating status to 'Closed'.
    """
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE FixedDeposits
            SET status = 'Closed',
                updated_at = datetime('now', 'localtime')
            WHERE fd_id = ?;
        """, (fd_id,))


# ============================================================================
# Dashboard Statistics & Aggregations
# ============================================================================

def get_admin_dashboard_stats(db_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Calculate comprehensive dashboard statistics directly from SQL queries:
      - Total customers
      - Total active FDs
      - Total principal invested
      - Total estimated maturity value & interest
      - Number of matured deposits
      - Number of deposits maturing within the next 30 days
      - Bank-wise investment distribution
      - FD status distribution
      - Recent registrations
    """
    sync_fd_statuses(db_path)
    path = db_path or get_db_path()

    with get_db_connection(path) as conn:
        cursor = conn.cursor()

        # Customer count
        cursor.execute("SELECT COUNT(*) AS total_customers FROM Customers WHERE is_active = 1;")
        total_customers = cursor.fetchone()["total_customers"]

        # Deposit counts by status
        cursor.execute("""
            SELECT status, COUNT(*) AS count, COALESCE(SUM(principal_amount), 0.0) AS principal_sum
            FROM FixedDeposits
            GROUP BY status;
        """)
        status_rows = cursor.fetchall()
        status_counts = {"Active": 0, "Matured": 0, "Closed": 0}
        for row in status_rows:
            status_counts[row["status"]] = row["count"]

        # Total principal across all deposits
        cursor.execute("SELECT COALESCE(SUM(principal_amount), 0.0) AS total_principal FROM FixedDeposits;")
        total_principal = cursor.fetchone()["total_principal"]

        # Active principal
        cursor.execute("SELECT COALESCE(SUM(principal_amount), 0.0) AS active_principal FROM FixedDeposits WHERE status = 'Active';")
        active_principal = cursor.fetchone()["active_principal"]

        # Deposits maturing in next 30 days (Active only)
        cursor.execute("""
            SELECT COUNT(*) AS upcoming_30d
            FROM FixedDeposits
            WHERE status = 'Active'
              AND maturity_date >= date('now', 'localtime')
              AND maturity_date <= date('now', 'localtime', '+30 days');
        """)
        upcoming_30d = cursor.fetchone()["upcoming_30d"]

        # Bank-wise distribution
        cursor.execute("""
            SELECT b.bank_name,
                   COUNT(fd.fd_id) AS fd_count,
                   COALESCE(SUM(fd.principal_amount), 0.0) AS total_principal
            FROM Banks b
            LEFT JOIN FixedDeposits fd ON b.bank_id = fd.bank_id
            GROUP BY b.bank_id, b.bank_name
            ORDER BY total_principal DESC;
        """)
        bank_distribution = [dict(row) for row in cursor.fetchall()]

        # Recent FD registrations
        cursor.execute("""
            SELECT fd.fd_id, c.full_name AS customer_name, b.bank_name,
                   fd.principal_amount, fd.annual_interest_rate, fd.maturity_date, fd.status
            FROM FixedDeposits fd
            JOIN Customers c ON fd.customer_id = c.customer_id
            JOIN Banks b ON fd.bank_id = b.bank_id
            ORDER BY fd.created_at DESC, fd.fd_id DESC
            LIMIT 5;
        """)
        recent_fds = [dict(row) for row in cursor.fetchall()]

    # Calculate overall estimated maturity & interest using calculation engine
    all_fds = get_fixed_deposits(db_path=path)
    total_maturity = sum(fd["estimated_maturity_amount"] for fd in all_fds)
    total_interest = sum(fd["estimated_interest"] for fd in all_fds)

    return {
        "total_customers": total_customers,
        "active_fds": status_counts["Active"],
        "matured_fds": status_counts["Matured"],
        "closed_fds": status_counts["Closed"],
        "total_fds": len(all_fds),
        "total_principal": total_principal,
        "active_principal": active_principal,
        "total_maturity_value": total_maturity,
        "total_interest": total_interest,
        "upcoming_30d": upcoming_30d,
        "bank_distribution": bank_distribution,
        "status_counts": status_counts,
        "recent_fds": recent_fds,
    }


def get_customer_portfolio_summary(customer_id: str, db_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Get portfolio metrics strictly for a single customer.
    Enforces customer isolation.
    """
    sync_fd_statuses(db_path)
    fds = get_fixed_deposits(customer_id=customer_id, db_path=db_path)

    total_principal = sum(fd["principal_amount"] for fd in fds)
    total_maturity = sum(fd["estimated_maturity_amount"] for fd in fds)
    total_interest = sum(fd["estimated_interest"] for fd in fds)

    active_count = sum(1 for fd in fds if fd["status"] == "Active")
    matured_count = sum(1 for fd in fds if fd["status"] == "Matured")
    closed_count = sum(1 for fd in fds if fd["status"] == "Closed")

    # Upcoming within 30 days
    today_str = date.today().strftime("%Y-%m-%d")
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT COUNT(*) AS upcoming
            FROM FixedDeposits
            WHERE customer_id = ?
              AND status = 'Active'
              AND maturity_date >= ?
              AND maturity_date <= date(?, '+30 days');
        """, (customer_id, today_str, today_str))
        upcoming_count = cursor.fetchone()["upcoming"]

    return {
        "customer_id": customer_id,
        "total_fds": len(fds),
        "total_principal": total_principal,
        "total_maturity_value": total_maturity,
        "total_interest": total_interest,
        "active_count": active_count,
        "matured_count": matured_count,
        "closed_count": closed_count,
        "upcoming_count": upcoming_count,
        "deposits": fds,
    }


# ============================================================================
# Comprehensive Reporting Engine (10 Standard Reports & CSV Export)
# ============================================================================

import csv


def export_data_to_csv(filepath: str, headers: List[str], rows: List[List[Any]]) -> None:
    """
    Export tabular data to CSV with UTF-8-SIG encoding for flawless
    Excel compatibility on Windows (properly renders ₹ and symbols).
    """
    with open(filepath, mode="w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        for row in rows:
            writer.writerow(row)


def get_report_customer_directory(db_path: Optional[str] = None) -> Tuple[List[str], List[List[Any]]]:
    """1. Complete customer directory report."""
    customers = get_customers(db_path=db_path)
    headers = ["Customer ID", "Full Name", "Phone", "Email", "City", "Account Status", "Total FDs", "Total Principal (INR)", "Registered On"]
    rows = []
    for c in customers:
        status_label = "Active" if c["is_active"] == 1 else "Deactivated"
        rows.append([
            c["customer_id"],
            c["full_name"],
            c["phone"],
            c["email"],
            c["city"],
            status_label,
            c["total_fds"],
            f"{c['total_principal']:.2f}",
            c["created_at"],
        ])
    return headers, rows


def get_report_customer_portfolio(customer_id: Optional[str] = None, db_path: Optional[str] = None) -> Tuple[List[str], List[List[Any]]]:
    """2. Customer-wise FD portfolio report."""
    fds = get_fixed_deposits(customer_id=customer_id, db_path=db_path)
    headers = [
        "Customer ID", "Customer Name", "City", "FD ID", "Bank Name",
        "Principal (INR)", "Rate (%)", "Tenure (Mo)", "Compounding",
        "Start Date", "Maturity Date", "Status", "Est. Interest (INR)", "Est. Maturity (INR)"
    ]
    rows = []
    for fd in fds:
        rows.append([
            fd["customer_id"],
            fd["customer_name"],
            fd["customer_city"],
            fd["fd_id"],
            fd["bank_name"],
            f"{fd['principal_amount']:.2f}",
            f"{fd['annual_interest_rate']:.2f}%",
            fd["tenure_months"],
            fd["compounding_frequency"],
            fd["start_date"],
            fd["maturity_date"],
            fd["status"],
            f"{fd['estimated_interest']:.2f}",
            f"{fd['estimated_maturity_amount']:.2f}",
        ])
    return headers, rows


def get_report_bank_investments(db_path: Optional[str] = None) -> Tuple[List[str], List[List[Any]]]:
    """3. Bank-wise investment report."""
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT b.bank_id, b.bank_name, b.branch_name, b.rate_source_note,
                   COUNT(fd.fd_id) AS total_fds,
                   COALESCE(SUM(fd.principal_amount), 0.0) AS total_principal,
                   COALESCE(SUM(CASE WHEN fd.status = 'Active' THEN 1 ELSE 0 END), 0) AS active_count,
                   COALESCE(SUM(CASE WHEN fd.status = 'Matured' THEN 1 ELSE 0 END), 0) AS matured_count,
                   COALESCE(SUM(CASE WHEN fd.status = 'Closed' THEN 1 ELSE 0 END), 0) AS closed_count
            FROM Banks b
            LEFT JOIN FixedDeposits fd ON b.bank_id = fd.bank_id
            GROUP BY b.bank_id
            ORDER BY total_principal DESC;
        """)
        banks = cursor.fetchall()

    all_fds = get_fixed_deposits(db_path=db_path)
    # Calculate bank-wise estimated maturity sum
    bank_mat_map = {}
    for fd in all_fds:
        bid = fd["bank_id"]
        bank_mat_map[bid] = bank_mat_map.get(bid, 0.0) + fd["estimated_maturity_amount"]

    headers = ["Bank ID", "Bank Name", "Branch", "Total FDs", "Active", "Matured", "Closed", "Total Principal (INR)", "Est. Maturity Value (INR)", "Rate Note"]
    rows = []
    for b in banks:
        bid = b["bank_id"]
        rows.append([
            bid,
            b["bank_name"],
            b["branch_name"],
            b["total_fds"],
            b["active_count"],
            b["matured_count"],
            b["closed_count"],
            f"{b['total_principal']:.2f}",
            f"{bank_mat_map.get(bid, 0.0):.2f}",
            b["rate_source_note"] or "N/A",
        ])
    return headers, rows


def get_report_fds_by_status(status: str, customer_id: Optional[str] = None, db_path: Optional[str] = None) -> Tuple[List[str], List[List[Any]]]:
    """4, 5, 6. Active, Matured, or Closed FD reports."""
    fds = get_fixed_deposits(customer_id=customer_id, status=status, db_path=db_path)
    headers = [
        "FD ID", "Customer ID", "Customer Name", "Bank Name", "Principal (INR)",
        "Rate (%)", "Tenure (Mo)", "Start Date", "Maturity Date", "Status",
        "Est. Interest (INR)", "Est. Maturity (INR)"
    ]
    rows = []
    for fd in fds:
        rows.append([
            fd["fd_id"],
            fd["customer_id"],
            fd["customer_name"],
            fd["bank_name"],
            f"{fd['principal_amount']:.2f}",
            f"{fd['annual_interest_rate']:.2f}%",
            fd["tenure_months"],
            fd["start_date"],
            fd["maturity_date"],
            fd["status"],
            f"{fd['estimated_interest']:.2f}",
            f"{fd['estimated_maturity_amount']:.2f}",
        ])
    return headers, rows


def get_report_upcoming_maturities(days: int = 30, customer_id: Optional[str] = None, db_path: Optional[str] = None) -> Tuple[List[str], List[List[Any]]]:
    """7. Upcoming maturity report (within N days)."""
    sync_fd_statuses(db_path)
    today_str = date.today().strftime("%Y-%m-%d")
    all_fds = get_fixed_deposits(customer_id=customer_id, status="Active", db_path=db_path)

    headers = [
        "FD ID", "Customer Name", "Phone", "Bank Name", "Principal (INR)",
        "Rate (%)", "Start Date", "Maturity Date", "Days Remaining", "Est. Maturity (INR)"
    ]
    rows = []
    today_dt = date.today()
    for fd in all_fds:
        try:
            m_dt = date.fromisoformat(fd["maturity_date"])
            diff = (m_dt - today_dt).days
            if 0 <= diff <= days:
                rows.append([
                    fd["fd_id"],
                    fd["customer_name"],
                    fd["customer_phone"],
                    fd["bank_name"],
                    f"{fd['principal_amount']:.2f}",
                    f"{fd['annual_interest_rate']:.2f}%",
                    fd["start_date"],
                    fd["maturity_date"],
                    f"{diff} day(s)",
                    f"{fd['estimated_maturity_amount']:.2f}",
                ])
        except Exception:
            continue

    rows.sort(key=lambda r: int(r[8].split()[0]))
    return headers, rows


def get_report_date_range_maturities(
    from_date: str,
    to_date: str,
    customer_id: Optional[str] = None,
    db_path: Optional[str] = None,
) -> Tuple[List[str], List[List[Any]]]:
    """8. Date-range maturity report."""
    sync_fd_statuses(db_path)
    all_fds = get_fixed_deposits(customer_id=customer_id, db_path=db_path)
    headers = [
        "FD ID", "Customer Name", "Bank Name", "Principal (INR)",
        "Rate (%)", "Tenure (Mo)", "Start Date", "Maturity Date", "Status", "Est. Maturity (INR)"
    ]
    rows = []
    for fd in all_fds:
        if from_date <= fd["maturity_date"] <= to_date:
            rows.append([
                fd["fd_id"],
                fd["customer_name"],
                fd["bank_name"],
                f"{fd['principal_amount']:.2f}",
                f"{fd['annual_interest_rate']:.2f}%",
                fd["tenure_months"],
                fd["start_date"],
                fd["maturity_date"],
                fd["status"],
                f"{fd['estimated_maturity_amount']:.2f}",
            ])
    return headers, rows


def get_report_investment_summary(customer_id: Optional[str] = None, db_path: Optional[str] = None) -> Tuple[List[str], List[List[Any]]]:
    """9. High-level portfolio investment summary report."""
    fds = get_fixed_deposits(customer_id=customer_id, db_path=db_path)
    headers = ["Metric Description", "Value"]

    total_fds = len(fds)
    total_principal = sum(f["principal_amount"] for f in fds)
    active_principal = sum(f["principal_amount"] for f in fds if f["status"] == "Active")
    matured_principal = sum(f["principal_amount"] for f in fds if f["status"] == "Matured")
    closed_principal = sum(f["principal_amount"] for f in fds if f["status"] == "Closed")
    total_est_maturity = sum(f["estimated_maturity_amount"] for f in fds)
    total_est_interest = sum(f["estimated_interest"] for f in fds)
    avg_rate = (sum(f["annual_interest_rate"] for f in fds) / total_fds) if total_fds else 0.0

    rows = [
        ["Total Deposit Accounts", str(total_fds)],
        ["Active Deposits Count", str(sum(1 for f in fds if f['status'] == 'Active'))],
        ["Matured Deposits Count", str(sum(1 for f in fds if f['status'] == 'Matured'))],
        ["Closed Deposits Count", str(sum(1 for f in fds if f['status'] == 'Closed'))],
        ["Total Principal Invested (INR)", f"{total_principal:.2f}"],
        ["Active Principal (INR)", f"{active_principal:.2f}"],
        ["Matured Principal (INR)", f"{matured_principal:.2f}"],
        ["Closed Principal (INR)", f"{closed_principal:.2f}"],
        ["Estimated Total Maturity Value (INR)", f"{total_est_maturity:.2f}"],
        ["Estimated Total Interest Return (INR)", f"{total_est_interest:.2f}"],
        ["Portfolio Average Interest Rate", f"{avg_rate:.2f}%"],
    ]
    return headers, rows


def get_report_estimated_returns_summary(customer_id: Optional[str] = None, db_path: Optional[str] = None) -> Tuple[List[str], List[List[Any]]]:
    """10. Estimated returns summary: tenure bucket distribution."""
    fds = get_fixed_deposits(customer_id=customer_id, db_path=db_path)
    headers = ["Tenure Bucket", "FD Count", "Total Principal (INR)", "Est. Interest Return (INR)", "Est. Maturity Value (INR)", "Avg Return Rate (%)"]

    buckets = {
        "Short-Term (<= 12 Months)": {"count": 0, "principal": 0.0, "interest": 0.0, "maturity": 0.0},
        "Medium-Term (13 - 24 Months)": {"count": 0, "principal": 0.0, "interest": 0.0, "maturity": 0.0},
        "Long-Term (25 - 36 Months)": {"count": 0, "principal": 0.0, "interest": 0.0, "maturity": 0.0},
        "Extended (> 36 Months)": {"count": 0, "principal": 0.0, "interest": 0.0, "maturity": 0.0},
    }

    for fd in fds:
        m = fd["tenure_months"]
        if m <= 12:
            key = "Short-Term (<= 12 Months)"
        elif m <= 24:
            key = "Medium-Term (13 - 24 Months)"
        elif m <= 36:
            key = "Long-Term (25 - 36 Months)"
        else:
            key = "Extended (> 36 Months)"

        b = buckets[key]
        b["count"] += 1
        b["principal"] += fd["principal_amount"]
        b["interest"] += fd["estimated_interest"]
        b["maturity"] += fd["estimated_maturity_amount"]

    rows = []
    for label, b in buckets.items():
        avg_ret = ((b["interest"] / b["principal"]) * 100.0) if b["principal"] > 0 else 0.0
        rows.append([
            label,
            b["count"],
            f"{b['principal']:.2f}",
            f"{b['interest']:.2f}",
            f"{b['maturity']:.2f}",
            f"{avg_ret:.2f}%",
        ])
    return headers, rows

