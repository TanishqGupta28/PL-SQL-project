"""
fd_calculator.py - Fixed Deposit Calculation & Formatting Engine
Handles compound interest calculations, maturity date projections,
status classification, and Indian financial formatting (INR/DD-MM-YYYY).
"""

from datetime import date, datetime
import calendar
from typing import Optional, Tuple, Union

# Disclaimer regarding academic calculation estimates
DISCLAIMER_TEXT = (
    "Disclaimer: All maturity and interest values are estimates for academic demonstration "
    "based on standard compounding formulas. Actual bank payouts may vary due to bank-specific "
    "day-count conventions, premature withdrawals, TDS/taxation, and deposit terms. "
    "This application is a portfolio tracking and educational DBMS tool, not a banking transaction system."
)

# Compounding frequency multiplier mapping
COMPOUNDING_FREQUENCIES = {
    "Quarterly": 4,
    "Monthly": 12,
    "Half-Yearly": 2,
    "Annually": 1,
}


def calculate_maturity_amount(
    principal: float,
    annual_rate: float,
    tenure_months: int,
    frequency: str = "Quarterly",
) -> Tuple[float, float]:
    """
    Calculate estimated maturity amount and interest earned using compound interest.

    Formula:
        A = P * (1 + r / (100 * n))^(n * t)
    Where:
        P = principal amount
        r = annual interest rate in percent (e.g., 7.25)
        n = compounding periods per year (4 for Quarterly, 12 for Monthly, etc.)
        t = tenure in years (tenure_months / 12.0)
        A = estimated maturity amount

    Returns:
        (maturity_amount, estimated_interest) rounded to 2 decimal places.
    """
    if principal <= 0:
        raise ValueError("Principal amount must be positive.")
    if annual_rate <= 0 or annual_rate > 30:
        raise ValueError("Annual interest rate must be between 0.01% and 30.00%.")
    if tenure_months <= 0:
        raise ValueError("Tenure months must be a positive integer.")

    n = COMPOUNDING_FREQUENCIES.get(frequency, 4)
    t = tenure_months / 12.0

    # A = P * (1 + r / (100 * n)) ^ (n * t)
    rate_factor = 1.0 + (annual_rate / (100.0 * n))
    exponent = n * t
    maturity_amount = principal * (rate_factor ** exponent)

    maturity_amount = round(maturity_amount, 2)
    estimated_interest = round(maturity_amount - principal, 2)

    return maturity_amount, estimated_interest


def calculate_maturity_date(
    start_date: Union[str, date],
    tenure_months: int,
) -> str:
    """
    Calculate maturity date from start date and tenure in months.
    Safely clamps to the last day of the target month when start day exceeds it
    (e.g., Jan 31 + 1 month -> Feb 28/29).

    Accepts:
        start_date: ISO string 'YYYY-MM-DD' or datetime.date object.
        tenure_months: Positive integer.

    Returns:
        ISO formatted date string 'YYYY-MM-DD'.
    """
    if isinstance(start_date, str):
        # Support both YYYY-MM-DD and DD-MM-YYYY inputs
        clean_date_str = start_date.strip()
        if "-" in clean_date_str:
            parts = clean_date_str.split("-")
            if len(parts[0]) == 4:
                d = datetime.strptime(clean_date_str, "%Y-%m-%d").date()
            else:
                d = datetime.strptime(clean_date_str, "%d-%m-%Y").date()
        else:
            raise ValueError(f"Unrecognized date format: '{start_date}'. Use DD-MM-YYYY or YYYY-MM-DD.")
    elif isinstance(start_date, date):
        d = start_date
    else:
        raise TypeError("start_date must be a date object or string.")

    if tenure_months <= 0:
        raise ValueError("tenure_months must be greater than zero.")

    total_months = d.month - 1 + tenure_months
    target_year = d.year + (total_months // 12)
    target_month = (total_months % 12) + 1

    # Clamp day if target month has fewer days than source day
    max_days_in_target_month = calendar.monthrange(target_year, target_month)[1]
    target_day = min(d.day, max_days_in_target_month)

    maturity_d = date(target_year, target_month, target_day)
    return maturity_d.strftime("%Y-%m-%d")


def determine_status(
    maturity_date: Union[str, date],
    current_status: Optional[str] = None,
    as_of_date: Optional[date] = None,
) -> str:
    """
    Classify deposit status:
      - 'Closed' if manually marked closed (never overwritten).
      - 'Matured' if maturity_date <= as_of_date (default: today).
      - 'Active' if maturity_date > as_of_date.
    """
    if current_status == "Closed":
        return "Closed"

    if as_of_date is None:
        as_of_date = date.today()

    if isinstance(maturity_date, str):
        clean_date_str = maturity_date.strip()
        if len(clean_date_str.split("-")[0]) == 4:
            mat_d = datetime.strptime(clean_date_str, "%Y-%m-%d").date()
        else:
            mat_d = datetime.strptime(clean_date_str, "%d-%m-%Y").date()
    elif isinstance(maturity_date, date):
        mat_d = maturity_date
    else:
        raise TypeError("maturity_date must be a date object or string.")

    if mat_d <= as_of_date:
        return "Matured"
    return "Active"


def format_inr(amount: Union[float, int], include_symbol: bool = True) -> str:
    """
    Format a number using the Indian Numbering System (e.g., 1,50,000.00).
    Adds ₹ prefix if include_symbol is True.
    """
    try:
        val = float(amount)
    except (ValueError, TypeError):
        return "₹0.00" if include_symbol else "0.00"

    is_negative = val < 0
    val = abs(val)

    # Split into integer and fractional parts
    int_part = int(val)
    decimal_part = f"{val - int_part:.2f}"[1:]  # e.g., ".50"

    s = str(int_part)
    if len(s) <= 3:
        formatted_int = s
    else:
        # Last 3 digits
        last_three = s[-3:]
        remaining = s[:-3]
        # Group remaining digits in pairs from right to left
        groups = []
        while remaining:
            groups.insert(0, remaining[-2:])
            remaining = remaining[:-2]
        formatted_int = ",".join(groups) + "," + last_three

    result = f"{'-' if is_negative else ''}{formatted_int}{decimal_part}"
    if include_symbol:
        return f"₹{result}"
    return result


def format_date_display(iso_date_str: Optional[str]) -> str:
    """
    Convert ISO date 'YYYY-MM-DD' to user-facing 'DD-MM-YYYY'.
    Handles None and fallback gracefully.
    """
    if not iso_date_str:
        return ""
    clean = iso_date_str.strip()
    try:
        if "-" in clean:
            parts = clean.split("-")
            if len(parts[0]) == 4:  # YYYY-MM-DD
                d = datetime.strptime(clean, "%Y-%m-%d").date()
                return d.strftime("%d-%m-%Y")
            elif len(parts[2]) == 4:  # Already DD-MM-YYYY
                return clean
        return clean
    except Exception:
        return clean


def parse_date_input(date_str: str) -> str:
    """
    Validate and convert user date input (DD-MM-YYYY or YYYY-MM-DD)
    into standard ISO format 'YYYY-MM-DD' for SQLite storage.
    Raises ValueError with a clear message if invalid.
    """
    if not date_str or not date_str.strip():
        raise ValueError("Date cannot be empty.")

    clean = date_str.strip()
    try:
        if "-" in clean:
            parts = clean.split("-")
            if len(parts) == 3:
                if len(parts[0]) == 4:  # YYYY-MM-DD
                    d = datetime.strptime(clean, "%Y-%m-%d").date()
                    return d.strftime("%Y-%m-%d")
                elif len(parts[2]) == 4:  # DD-MM-YYYY
                    d = datetime.strptime(clean, "%d-%m-%Y").date()
                    return d.strftime("%Y-%m-%d")
        elif "/" in clean:
            parts = clean.split("/")
            if len(parts) == 3:
                if len(parts[2]) == 4:  # DD/MM/YYYY
                    d = datetime.strptime(clean, "%d/%m/%Y").date()
                    return d.strftime("%Y-%m-%d")
        raise ValueError
    except (ValueError, Exception):
        raise ValueError(f"Invalid date '{date_str}'. Please use DD-MM-YYYY format (e.g. 15-08-2024).")
