"""
auth.py - Authentication and Role-Based Authorization
Implements salted PBKDF2-HMAC-SHA256 password hashing, user authentication,
role checks (Admin vs Customer), and session state with strict customer data isolation.
"""

import hashlib
import os
import secrets
from typing import Any, Dict, Optional

from database import get_db_connection


def hash_password(plain_password: str) -> str:
    """
    Hash a plain-text password using PBKDF2-HMAC-SHA256 with a cryptographically
    secure 16-byte random salt and 100,000 iterations.
    Format stored: salt_hex$hash_hex
    """
    if not plain_password:
        raise ValueError("Password cannot be empty.")
    salt = secrets.token_bytes(16)
    key = hashlib.pbkdf2_hmac("sha256", plain_password.encode("utf-8"), salt, 100_000)
    return f"{salt.hex()}${key.hex()}"


def verify_password(plain_password: str, stored_hash: str) -> bool:
    """
    Verify a plain-text password against a stored salt_hex$hash_hex string.
    Uses constant-time comparison to prevent timing attacks.
    """
    if not plain_password or not stored_hash or "$" not in stored_hash:
        return False
    try:
        salt_hex, key_hex = stored_hash.split("$", 1)
        salt = bytes.fromhex(salt_hex)
        expected_key = bytes.fromhex(key_hex)
        key = hashlib.pbkdf2_hmac("sha256", plain_password.encode("utf-8"), salt, 100_000)
        return secrets.compare_digest(key, expected_key)
    except Exception:
        return False


def authenticate_user(
    username: str,
    plain_password: str,
    db_path: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Authenticate a user by username and password.
    Returns user dict with joined customer details if valid and active, else None.
    """
    if not username or not plain_password:
        return None

    query = """
        SELECT u.user_id, u.username, u.password_hash, u.role, u.customer_id, u.is_active,
               c.full_name, c.email, c.city
        FROM Users u
        LEFT JOIN Customers c ON u.customer_id = c.customer_id
        WHERE u.username = ?;
    """
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(query, (username.strip(),))
        row = cursor.fetchone()
        if not row:
            return None

        user = dict(row)
        if not user["is_active"]:
            return None

        if verify_password(plain_password, user["password_hash"]):
            # Do not leak the password hash in the return dict
            user.pop("password_hash", None)
            return user
        return None


def create_user(
    username: str,
    plain_password: str,
    role: str,
    customer_id: Optional[str] = None,
    db_path: Optional[str] = None,
) -> int:
    """
    Create a new user with securely hashed password.
    Enforces role constraints ('admin' or 'customer').
    """
    if role not in ("admin", "customer"):
        raise ValueError(f"Invalid role: '{role}'. Must be 'admin' or 'customer'.")

    if role == "customer" and not customer_id:
        raise ValueError("Customer account must be associated with a valid customer_id.")

    p_hash = hash_password(plain_password)

    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO Users (username, password_hash, role, customer_id, is_active)
            VALUES (?, ?, ?, ?, 1);
        """, (username.strip().lower(), p_hash, role, customer_id))
        return cursor.lastrowid


def get_user_by_username(username: str, db_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Fetch user record by username."""
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM Users WHERE username = ?;", (username.strip().lower(),))
        row = cursor.fetchone()
        return dict(row) if row else None


def get_user_by_customer_id(customer_id: str, db_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Fetch user record associated with a given customer_id."""
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM Users WHERE customer_id = ?;", (customer_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


class CurrentSession:
    """
    Singleton-style session tracker for the currently authenticated user.
    Enforces customer isolation and role-based permissions.
    """
    def __init__(self):
        self.user_id: Optional[int] = None
        self.username: Optional[str] = None
        self.role: Optional[str] = None
        self.customer_id: Optional[str] = None
        self.full_name: Optional[str] = None
        self.is_authenticated: bool = False

    def login(self, user_dict: Dict[str, Any]) -> None:
        self.user_id = user_dict.get("user_id")
        self.username = user_dict.get("username")
        self.role = user_dict.get("role")
        self.customer_id = user_dict.get("customer_id")
        self.full_name = user_dict.get("full_name") or user_dict.get("username")
        self.is_authenticated = True

    def logout(self) -> None:
        self.user_id = None
        self.username = None
        self.role = None
        self.customer_id = None
        self.full_name = None
        self.is_authenticated = False

    def is_admin(self) -> bool:
        return self.is_authenticated and self.role == "admin"

    def is_customer(self) -> bool:
        return self.is_authenticated and self.role == "customer"

    def can_access_customer(self, target_customer_id: str) -> bool:
        """
        Authorization check: Admin can access any customer,
        Customer can ONLY access their own customer_id.
        """
        if not self.is_authenticated:
            return False
        if self.role == "admin":
            return True
        return self.role == "customer" and self.customer_id == target_customer_id


# Global active session instance
session = CurrentSession()
