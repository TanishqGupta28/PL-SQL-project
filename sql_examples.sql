-- ============================================================================
-- FD MANAGER SYSTEM - SQL DEMONSTRATION SCRIPT
-- Subject: Database Management Systems (DBMS)
-- Backend: SQLite 3 Relational Database Engine
--
-- This script contains documented SQL queries implemented in the application,
-- demonstrating relational concepts: DDL, DML, Constraints, Indexes, JOINs,
-- Aggregations, GROUP BY, Transactions, Referential Integrity, and Data Access.
-- ============================================================================

-- Enable Foreign Key constraints in SQLite
PRAGMA foreign_keys = ON;

-- ============================================================================
-- 1. DATA DEFINITION LANGUAGE (DDL) - SCHEMA DESIGN & CONSTRAINTS
-- ============================================================================

-- Table 1: Customers
-- Demonstrates: Primary Key, NOT NULL, DEFAULT values, CHECK constraints.
CREATE TABLE IF NOT EXISTS Customers (
    customer_id TEXT PRIMARY KEY,
    full_name TEXT NOT NULL,
    phone TEXT NOT NULL,
    email TEXT NOT NULL,
    city TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1 CHECK(is_active IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

-- Table 2: Users (Authentication & Role-Based Access Control)
-- Demonstrates: Foreign Key (one-to-one with Customers for customers), UNIQUE constraints.
CREATE TABLE IF NOT EXISTS Users (
    user_id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('admin', 'customer')),
    customer_id TEXT UNIQUE REFERENCES Customers(customer_id) ON DELETE SET NULL,
    is_active INTEGER NOT NULL DEFAULT 1 CHECK(is_active IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

-- Table 3: Banks
-- Demonstrates: Auto-increment Primary Key, UNIQUE bank name.
CREATE TABLE IF NOT EXISTS Banks (
    bank_id INTEGER PRIMARY KEY AUTOINCREMENT,
    bank_name TEXT UNIQUE NOT NULL,
    branch_name TEXT NOT NULL,
    rate_source_note TEXT
);

-- Table 4: FixedDeposits
-- Demonstrates: One-to-Many relationships, Foreign Keys with ON DELETE RESTRICT,
-- multiple CHECK constraints for positive principal, rate ranges, and valid statuses.
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

-- Indexes for performance optimization on frequently filtered/joined columns
CREATE INDEX IF NOT EXISTS idx_fd_customer_id ON FixedDeposits(customer_id);
CREATE INDEX IF NOT EXISTS idx_fd_bank_id ON FixedDeposits(bank_id);
CREATE INDEX IF NOT EXISTS idx_fd_maturity_date ON FixedDeposits(maturity_date);
CREATE INDEX IF NOT EXISTS idx_fd_status ON FixedDeposits(status);
CREATE INDEX IF NOT EXISTS idx_cust_city ON Customers(city);
CREATE INDEX IF NOT EXISTS idx_cust_active ON Customers(is_active);

-- ============================================================================
-- 2. DATA MANIPULATION LANGUAGE (DML) - CRUD OPERATIONS
-- ============================================================================

-- Insert sample bank
INSERT OR IGNORE INTO Banks (bank_name, branch_name, rate_source_note)
VALUES ('State Bank of India (SBI)', 'Nariman Point Branch, Mumbai', 'Sample rate assumption 6.50% - 7.10% (Academic demo)');

-- Insert sample customer
INSERT OR IGNORE INTO Customers (customer_id, full_name, phone, email, city, is_active)
VALUES ('CUST001', 'Aarav Sharma', '+91 98110 20001', 'aarav.sharma@demo-fd.in', 'Delhi', 1);

-- Insert sample Fixed Deposit
INSERT OR IGNORE INTO FixedDeposits (
    fd_id, customer_id, bank_id, principal_amount, annual_interest_rate,
    tenure_months, compounding_frequency, start_date, maturity_date, status
) VALUES (
    'FD1001', 'CUST001', 1, 150000.00, 7.10, 12, 'Quarterly', '2025-11-05', '2026-11-05', 'Active'
);

-- Update customer profile
UPDATE Customers
SET phone = '+91 98110 99999', city = 'New Delhi'
WHERE customer_id = 'CUST001';

-- Explicitly close an FD (historical preservation: status update instead of physical deletion)
UPDATE FixedDeposits
SET status = 'Closed', updated_at = datetime('now', 'localtime')
WHERE fd_id = 'FD1006';

-- ============================================================================
-- 3. RELATIONAL JOINS (INNER JOIN & LEFT JOIN)
-- ============================================================================

-- Query: Retrieve all Fixed Deposits with Customer & Bank details (3-Table JOIN)
SELECT
    fd.fd_id,
    c.customer_id,
    c.full_name AS customer_name,
    c.city,
    b.bank_name,
    b.branch_name,
    fd.principal_amount,
    fd.annual_interest_rate,
    fd.tenure_months,
    fd.compounding_frequency,
    fd.start_date,
    fd.maturity_date,
    fd.status
FROM FixedDeposits fd
INNER JOIN Customers c ON fd.customer_id = c.customer_id
INNER JOIN Banks b ON fd.bank_id = b.bank_id
ORDER BY fd.maturity_date ASC;

-- Query: Customer Directory with Left Joined Deposit Counts and Totals
SELECT
    c.customer_id,
    c.full_name,
    c.city,
    c.is_active,
    COUNT(fd.fd_id) AS total_deposits,
    COALESCE(SUM(fd.principal_amount), 0.0) AS total_invested
FROM Customers c
LEFT JOIN FixedDeposits fd ON c.customer_id = fd.customer_id
GROUP BY c.customer_id
ORDER BY c.customer_id ASC;

-- ============================================================================
-- 4. AGGREGATE FUNCTIONS & GROUP BY CLAUSES
-- ============================================================================

-- Bank-wise Investment Distribution Report
SELECT
    b.bank_name,
    COUNT(fd.fd_id) AS total_fds,
    COALESCE(SUM(fd.principal_amount), 0.0) AS total_principal_invested,
    COALESCE(AVG(fd.annual_interest_rate), 0.0) AS avg_interest_rate,
    COALESCE(MIN(fd.principal_amount), 0.0) AS min_fd_amount,
    COALESCE(MAX(fd.principal_amount), 0.0) AS max_fd_amount
FROM Banks b
LEFT JOIN FixedDeposits fd ON b.bank_id = fd.bank_id
GROUP BY b.bank_id, b.bank_name
ORDER BY total_principal_invested DESC;

-- FD Portfolio Status Distribution
SELECT
    status,
    COUNT(*) AS count_of_deposits,
    SUM(principal_amount) AS total_amount,
    ROUND(AVG(annual_interest_rate), 2) AS avg_rate
FROM FixedDeposits
GROUP BY status;

-- ============================================================================
-- 5. UPCOMING MATURITIES & DATE FILTERING
-- ============================================================================

-- Find Active Fixed Deposits maturing in the next 30 days
SELECT
    fd.fd_id,
    c.full_name AS customer_name,
    c.phone,
    b.bank_name,
    fd.principal_amount,
    fd.maturity_date
FROM FixedDeposits fd
JOIN Customers c ON fd.customer_id = c.customer_id
JOIN Banks b ON fd.bank_id = b.bank_id
WHERE fd.status = 'Active'
  AND fd.maturity_date >= date('now', 'localtime')
  AND fd.maturity_date <= date('now', 'localtime', '+30 days')
ORDER BY fd.maturity_date ASC;

-- ============================================================================
-- 6. ROLE-BASED ACCESS CONTROL & CUSTOMER DATA ISOLATION
-- ============================================================================

-- Strict Customer Query (Customer CUST001 can only view their own records)
SELECT
    fd.fd_id,
    b.bank_name,
    fd.principal_amount,
    fd.annual_interest_rate,
    fd.tenure_months,
    fd.start_date,
    fd.maturity_date,
    fd.status
FROM FixedDeposits fd
JOIN Banks b ON fd.bank_id = b.bank_id
WHERE fd.customer_id = 'CUST001'
ORDER BY fd.maturity_date ASC;

-- ============================================================================
-- 7. DATABASE TRANSACTIONS & ROLLBACK DEMONSTRATION
-- ============================================================================

-- Multi-table creation transaction: Customer + User account creation
BEGIN TRANSACTION;

INSERT INTO Customers (customer_id, full_name, phone, email, city, is_active)
VALUES ('CUST021', 'Vikas Sharma', '+91 98110 20021', 'vikas.sharma@demo-fd.in', 'Gurugram', 1);

INSERT INTO Users (username, password_hash, role, customer_id, is_active)
VALUES ('cust021', 'sample_salt$sample_hash_pbkdf2', 'customer', 'CUST021', 1);

-- If any constraint fails, the transaction is safely rolled back:
-- ROLLBACK;
-- Otherwise:
COMMIT;

-- ============================================================================
-- 8. REFERENTIAL INTEGRITY DEMONSTRATION
-- ============================================================================

-- Attempting to delete a Customer with active Fixed Deposits will FAIL
-- because ON DELETE RESTRICT is enforced:
-- DELETE FROM Customers WHERE customer_id = 'CUST001';
-- Result: [FOREIGN KEY constraint failed]

-- ============================================================================
-- NOTE ON DATABASE ENGINE & PL/SQL:
-- This application is built with Python and SQLite 3.
-- SQLite is an embedded relational database supporting standard SQL (DDL, DML,
-- JOINs, Aggregates, Indexes, Constraints, and ACID Transactions).
-- SQLite does not execute proprietary Oracle PL/SQL procedural blocks (such as
-- Oracle-specific packages, triggers, or stored procedures).
-- Business logic and compounding math are implemented in Python application code.
-- ============================================================================
