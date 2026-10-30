"""
seed_data.py - Synthetic Demonstration Data Seeder for FD Manager System
Preloads 20 fictional Indian customers, 4 sample banks, admin and customer login
credentials, and 38 realistic Fixed Deposit records across active, matured, and closed states.
Ensures idempotency on repeated execution.
"""

from datetime import date, timedelta
from typing import Optional

from auth import create_user, get_user_by_username
from database import (
    add_bank,
    add_customer,
    add_fixed_deposit,
    get_all_banks,
    get_customers,
    get_db_connection,
    init_db,
    sync_fd_statuses,
)
from fd_calculator import calculate_maturity_date

# Synthetic Demo Customers specified in requirements
DEMO_CUSTOMERS = [
    ("CUST001", "Aarav Sharma", "Delhi", "+91 98110 20001", "aarav.sharma@demo-fd.in"),
    ("CUST002", "Priya Verma", "Lucknow", "+91 98110 20002", "priya.verma@demo-fd.in"),
    ("CUST003", "Rahul Gupta", "Jaipur", "+91 98110 20003", "rahul.gupta@demo-fd.in"),
    ("CUST004", "Neha Singh", "Chandigarh", "+91 98110 20004", "neha.singh@demo-fd.in"),
    ("CUST005", "Arjun Patel", "Ahmedabad", "+91 98110 20005", "arjun.patel@demo-fd.in"),
    ("CUST006", "Ananya Mishra", "Varanasi", "+91 98110 20006", "ananya.mishra@demo-fd.in"),
    ("CUST007", "Rohan Kumar", "Patna", "+91 98110 20007", "rohan.kumar@demo-fd.in"),
    ("CUST008", "Sneha Yadav", "Kanpur", "+91 98110 20008", "sneha.yadav@demo-fd.in"),
    ("CUST009", "Vikram Mehta", "Mumbai", "+91 98110 20009", "vikram.mehta@demo-fd.in"),
    ("CUST010", "Pooja Agarwal", "Agra", "+91 98110 20010", "pooja.agarwal@demo-fd.in"),
    ("CUST011", "Aditya Joshi", "Pune", "+91 98110 20011", "aditya.joshi@demo-fd.in"),
    ("CUST012", "Kavya Reddy", "Hyderabad", "+91 98110 20012", "kavya.reddy@demo-fd.in"),
    ("CUST013", "Karan Malhotra", "Amritsar", "+91 98110 20013", "karan.malhotra@demo-fd.in"),
    ("CUST014", "Simran Kaur", "Ludhiana", "+91 98110 20014", "simran.kaur@demo-fd.in"),
    ("CUST015", "Aman Tiwari", "Bhopal", "+91 98110 20015", "aman.tiwari@demo-fd.in"),
    ("CUST016", "Isha Kapoor", "Noida", "+91 98110 20016", "isha.kapoor@demo-fd.in"),
    ("CUST017", "Suresh Nair", "Kochi", "+91 98110 20017", "suresh.nair@demo-fd.in"),
    ("CUST018", "Meera Desai", "Surat", "+91 98110 20018", "meera.desai@demo-fd.in"),
    ("CUST019", "Deepak Choudhary", "Jodhpur", "+91 98110 20019", "deepak.choudhary@demo-fd.in"),
    ("CUST020", "Riya Saxena", "Dehradun", "+91 98110 20020", "riya.saxena@demo-fd.in"),
]

# Sample Banks with illustrative rates for academic demonstration
DEMO_BANKS = [
    ("State Bank of India (SBI)", "Nariman Point Branch, Mumbai", "Sample rate assumption: 6.50% - 7.10% (Academic demo)"),
    ("HDFC Bank", "Connaught Place Branch, New Delhi", "Sample rate assumption: 6.60% - 7.25% (Academic demo)"),
    ("ICICI Bank", "Bandra-Kurla Complex Branch, Mumbai", "Sample rate assumption: 6.70% - 7.20% (Academic demo)"),
    ("Punjab National Bank (PNB)", "Sector 17 Branch, Chandigarh", "Sample rate assumption: 6.50% - 7.30% (Academic demo)"),
]

# Default credentials for demonstration
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "AdminPassword@123"
CUSTOMER_DEFAULT_PASSWORD = "Customer@123"


def seed_database(db_path: Optional[str] = None, force_reset: bool = False) -> None:
    """
    Idempotent seeding routine.
    If database already has >= 20 customers, skip to prevent duplicates.
    """
    init_db(db_path)

    existing_customers = get_customers(db_path=db_path)
    if len(existing_customers) >= 20 and not force_reset:
        # Already seeded
        sync_fd_statuses(db_path)
        return

    # Seed Banks
    existing_banks = get_all_banks(db_path=db_path)
    bank_map = {}
    if not existing_banks:
        for bank_name, branch, note in DEMO_BANKS:
            b_id = add_bank(bank_name, branch, note, db_path=db_path)
            bank_map[bank_name] = b_id
    else:
        for b in existing_banks:
            bank_map[b["bank_name"]] = b["bank_id"]

    # Bank IDs: SBI=1, HDFC=2, ICICI=3, PNB=4 (approx)
    b_sbi = bank_map.get("State Bank of India (SBI)", 1)
    b_hdfc = bank_map.get("HDFC Bank", 2)
    b_icici = bank_map.get("ICICI Bank", 3)
    b_pnb = bank_map.get("Punjab National Bank (PNB)", 4)

    # Seed Admin User
    if not get_user_by_username(ADMIN_USERNAME, db_path=db_path):
        create_user(ADMIN_USERNAME, ADMIN_PASSWORD, role="admin", customer_id=None, db_path=db_path)

    # Seed Customers and Customer User Logins
    for cid, name, city, phone, email in DEMO_CUSTOMERS:
        # Check if customer exists
        with get_db_connection(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT customer_id FROM Customers WHERE customer_id = ?;", (cid,))
            if not cursor.fetchone():
                add_customer(cid, name, phone, email, city, db_path=db_path)

        # Create user account e.g., cust001
        username = cid.lower()
        if not get_user_by_username(username, db_path=db_path):
            create_user(username, CUSTOMER_DEFAULT_PASSWORD, role="customer", customer_id=cid, db_path=db_path)

    # Calculate dynamic dates relative to current date (e.g., 2026-10-30)
    today = date.today()

    # Pre-calculated dates for demonstration:
    # 1. Past dates (matured / closed)
    start_2023_01 = (today - timedelta(days=700)).strftime("%Y-%m-%d")
    start_2024_03 = (today - timedelta(days=500)).strftime("%Y-%m-%d")
    start_2024_08 = (today - timedelta(days=300)).strftime("%Y-%m-%d")

    # 2. Upcoming maturities in the next 30 days (critical requirement)
    # Start date set so that maturity falls in 8 days, 15 days, 22 days, 28 days
    start_upcoming_1 = (today - timedelta(days=357)).strftime("%Y-%m-%d")  # 12 mo -> matures in ~8 days
    mat_upcoming_1 = (today + timedelta(days=8)).strftime("%Y-%m-%d")

    start_upcoming_2 = (today - timedelta(days=715)).strftime("%Y-%m-%d")  # 24 mo -> matures in ~15 days
    mat_upcoming_2 = (today + timedelta(days=15)).strftime("%Y-%m-%d")

    start_upcoming_3 = (today - timedelta(days=162)).strftime("%Y-%m-%d")  # 6 mo -> matures in ~20 days
    mat_upcoming_3 = (today + timedelta(days=20)).strftime("%Y-%m-%d")

    start_upcoming_4 = (today - timedelta(days=337)).strftime("%Y-%m-%d")  # 12 mo -> matures in ~28 days
    mat_upcoming_4 = (today + timedelta(days=28)).strftime("%Y-%m-%d")

    # 3. Active long-term deposits (maturing 6-36 months in future)
    start_recent = (today - timedelta(days=60)).strftime("%Y-%m-%d")
    start_active_1yr = (today - timedelta(days=90)).strftime("%Y-%m-%d")

    # Fixed Deposit Seed Records (38 comprehensive records covering all 20 customers)
    sample_fds = [
        # CUST001 - Aarav Sharma (Delhi) - 2 FDs
        ("FD1001", "CUST001", b_sbi, 150000.0, 7.10, 12, "Quarterly", start_upcoming_1, mat_upcoming_1, "Active"),
        ("FD1002", "CUST001", b_hdfc, 300000.0, 7.25, 24, "Quarterly", start_active_1yr, None, "Active"),

        # CUST002 - Priya Verma (Lucknow) - 2 FDs
        ("FD1003", "CUST002", b_hdfc, 200000.0, 7.00, 12, "Quarterly", start_2023_01, None, "Matured"),
        ("FD1004", "CUST002", b_icici, 500000.0, 7.20, 36, "Quarterly", start_recent, None, "Active"),

        # CUST003 - Rahul Gupta (Jaipur) - 2 FDs
        ("FD1005", "CUST003", b_sbi, 100000.0, 6.80, 12, "Quarterly", start_upcoming_2, mat_upcoming_2, "Active"),
        ("FD1006", "CUST003", b_pnb, 75000.0, 6.75, 6, "Monthly", start_2024_03, None, "Closed"),

        # CUST004 - Neha Singh (Chandigarh) - 2 FDs
        ("FD1007", "CUST004", b_pnb, 250000.0, 7.30, 24, "Quarterly", start_active_1yr, None, "Active"),
        ("FD1008", "CUST004", b_hdfc, 100000.0, 6.90, 12, "Quarterly", start_2023_01, None, "Matured"),

        # CUST005 - Arjun Patel (Ahmedabad) - 2 FDs
        ("FD1009", "CUST005", b_icici, 1000000.0, 7.20, 36, "Quarterly", start_recent, None, "Active"),
        ("FD1010", "CUST005", b_sbi, 200000.0, 6.50, 6, "Quarterly", start_upcoming_3, mat_upcoming_3, "Active"),

        # CUST006 - Ananya Mishra (Varanasi) - 2 FDs
        ("FD1011", "CUST006", b_sbi, 50000.0, 6.90, 12, "Half-Yearly", start_2024_08, None, "Active"),
        ("FD1012", "CUST006", b_pnb, 120000.0, 7.00, 18, "Quarterly", start_2023_01, None, "Matured"),

        # CUST007 - Rohan Kumar (Patna) - 2 FDs
        ("FD1013", "CUST007", b_hdfc, 180000.0, 7.15, 24, "Quarterly", start_recent, None, "Active"),
        ("FD1014", "CUST007", b_sbi, 60000.0, 6.60, 12, "Quarterly", start_2023_01, None, "Closed"),

        # CUST008 - Sneha Yadav (Kanpur) - 2 FDs
        ("FD1015", "CUST008", b_pnb, 350000.0, 7.25, 36, "Quarterly", start_active_1yr, None, "Active"),
        ("FD1016", "CUST008", b_icici, 150000.0, 6.85, 12, "Monthly", start_upcoming_4, mat_upcoming_4, "Active"),

        # CUST009 - Vikram Mehta (Mumbai) - 3 FDs
        ("FD1017", "CUST009", b_hdfc, 750000.0, 7.25, 24, "Quarterly", start_recent, None, "Active"),
        ("FD1018", "CUST009", b_icici, 500000.0, 7.10, 12, "Quarterly", start_2023_01, None, "Matured"),
        ("FD1019", "CUST009", b_sbi, 250000.0, 6.75, 12, "Quarterly", start_2024_03, None, "Closed"),

        # CUST010 - Pooja Agarwal (Agra) - 2 FDs
        ("FD1020", "CUST010", b_sbi, 125000.0, 7.00, 18, "Quarterly", start_active_1yr, None, "Active"),
        ("FD1021", "CUST010", b_pnb, 80000.0, 6.80, 12, "Quarterly", start_2023_01, None, "Matured"),

        # CUST011 - Aditya Joshi (Pune) - 2 FDs
        ("FD1022", "CUST011", b_icici, 400000.0, 7.20, 24, "Quarterly", start_recent, None, "Active"),
        ("FD1023", "CUST011", b_hdfc, 150000.0, 7.00, 12, "Quarterly", start_2024_03, None, "Closed"),

        # CUST012 - Kavya Reddy (Hyderabad) - 2 FDs
        ("FD1024", "CUST012", b_sbi, 600000.0, 7.15, 36, "Quarterly", start_active_1yr, None, "Active"),
        ("FD1025", "CUST012", b_icici, 200000.0, 6.90, 12, "Quarterly", start_2023_01, None, "Matured"),

        # CUST013 - Karan Malhotra (Amritsar) - 2 FDs
        ("FD1026", "CUST013", b_pnb, 300000.0, 7.30, 24, "Quarterly", start_recent, None, "Active"),
        ("FD1027", "CUST013", b_sbi, 100000.0, 6.75, 12, "Quarterly", start_2023_01, None, "Matured"),

        # CUST014 - Simran Kaur (Ludhiana) - 2 FDs
        ("FD1028", "CUST014", b_hdfc, 250000.0, 7.10, 18, "Quarterly", start_active_1yr, None, "Active"),
        ("FD1029", "CUST014", b_pnb, 150000.0, 6.95, 12, "Monthly", start_recent, None, "Active"),

        # CUST015 - Aman Tiwari (Bhopal) - 2 FDs
        ("FD1030", "CUST015", b_sbi, 175000.0, 7.05, 12, "Quarterly", start_2024_08, None, "Active"),
        ("FD1031", "CUST015", b_icici, 75000.0, 6.50, 6, "Quarterly", start_2023_01, None, "Matured"),

        # CUST016 - Isha Kapoor (Noida) - 2 FDs
        ("FD1032", "CUST016", b_hdfc, 450000.0, 7.25, 24, "Quarterly", start_recent, None, "Active"),
        ("FD1033", "CUST016", b_sbi, 100000.0, 6.70, 12, "Quarterly", start_2024_03, None, "Closed"),

        # CUST017 - Suresh Nair (Kochi) - 2 FDs
        ("FD1034", "CUST017", b_sbi, 500000.0, 7.10, 36, "Quarterly", start_active_1yr, None, "Active"),
        ("FD1035", "CUST017", b_icici, 200000.0, 6.85, 12, "Quarterly", start_2023_01, None, "Matured"),

        # CUST018 - Meera Desai (Surat) - 1 FD
        ("FD1036", "CUST018", b_hdfc, 800000.0, 7.20, 24, "Quarterly", start_recent, None, "Active"),

        # CUST019 - Deepak Choudhary (Jodhpur) - 1 FD
        ("FD1037", "CUST019", b_pnb, 220000.0, 7.15, 18, "Quarterly", start_active_1yr, None, "Active"),

        # CUST020 - Riya Saxena (Dehradun) - 1 FD
        ("FD1038", "CUST020", b_icici, 350000.0, 7.20, 24, "Quarterly", start_recent, None, "Active"),
    ]

    for fd_id, cid, bid, principal, rate, tenure, freq, s_date, m_date, status in sample_fds:
        with get_db_connection(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT fd_id FROM FixedDeposits WHERE fd_id = ?;", (fd_id,))
            if not cursor.fetchone():
                add_fixed_deposit(
                    fd_id=fd_id,
                    customer_id=cid,
                    bank_id=bid,
                    principal_amount=principal,
                    annual_interest_rate=rate,
                    tenure_months=tenure,
                    compounding_frequency=freq,
                    start_date=s_date,
                    maturity_date=m_date,
                    status=status,
                    db_path=db_path,
                )

    sync_fd_statuses(db_path)


if __name__ == "__main__":
    seed_database()
    print("Database seeding completed successfully.")
