"""Invoice email subject parsing and metadata extraction."""

import re
from typing import Any, Dict, Optional, Tuple

# Mapping of month names to their 2-digit numerical string
MONTH_NAME_TO_NUMBER = {
    "january": "01",
    "february": "02",
    "march": "03",
    "april": "04",
    "may": "05",
    "june": "06",
    "july": "07",
    "august": "08",
    "september": "09",
    "october": "10",
    "november": "11",
    "december": "12",
}

# Regex for matching the required subject phrase and period
# Requires exact 4-digit year: \b\d{4}\b
PERIOD_REGEX = re.compile(
    r"Invoice\s+for\s+the\s+month\s+of\s+([A-Za-z]+)\s+(\d+)\b",
    re.IGNORECASE,
)

# Regex for O&M Code (starts with IN- followed by digits)
OM_CODE_REGEX = re.compile(r"\bIN-\d+\b", re.IGNORECASE)

# Regex for reference / invoice numbers that might follow client name
# Examples: IN1821191, INV12345, 1821191
INVOICE_REF_REGEX = re.compile(
    r"(?:[\s\-_|]+)(?:[A-Z]{1,4})?\d{5,}(?:[\s\-_|]+|$)",
    re.IGNORECASE,
)


class SubjectParserError(Exception):
    """Base exception for subject parsing errors."""
    pass


class SubjectValidationError(SubjectParserError):
    """Raised when subject does not contain 'Invoice for the month of'."""
    pass


class OMCodeNotFoundError(SubjectParserError):
    """Raised when no valid IN-xxx O&M code is present in the subject."""
    pass


class InvoicePeriodError(SubjectParserError):
    """Raised when the invoice month or year is invalid or missing."""
    pass


class ClientNameNotFoundError(SubjectParserError):
    """Raised when client name cannot be extracted from the subject."""
    pass


def is_valid_invoice_subject(subject: Optional[str]) -> bool:
    """Check whether subject contains the required phrase 'Invoice for the month of'."""
    if not subject:
        return False
    return "invoice for the month of" in subject.lower()


def extract_period(subject: str) -> Tuple[str, int, str]:
    """Extract month, year, and calculate SharePoint month folder (YYMM).

    Returns:
        Tuple of (month_title_case, year_int, yymm_folder)

    Raises:
        SubjectValidationError: If 'Invoice for the month of' is missing.
        InvoicePeriodError: If month name is unknown or year is not 4 digits.
    """
    if not is_valid_invoice_subject(subject):
        raise SubjectValidationError(
            f"Subject does not contain 'Invoice for the month of': '{subject}'"
        )

    match = PERIOD_REGEX.search(subject)
    if not match:
        raise InvoicePeriodError(
            f"Could not parse month and year after 'Invoice for the month of' in: '{subject}'"
        )

    raw_month = match.group(1).strip()
    raw_year = match.group(2).strip()

    month_key = raw_month.lower()
    if month_key not in MONTH_NAME_TO_NUMBER:
        raise InvoicePeriodError(
            f"Invalid month name '{raw_month}'. Expected full month (e.g. January..December)."
        )

    if len(raw_year) != 4 or not raw_year.isdigit():
        raise InvoicePeriodError(
            f"Invalid year '{raw_year}'. Expected exactly 4 digits (e.g. 2026)."
        )

    year_int = int(raw_year)
    month_title = raw_month.capitalize()
    month_num = MONTH_NAME_TO_NUMBER[month_key]
    yy = str(year_int)[-2:]
    month_folder = f"{yy}{month_num}"

    return month_title, year_int, month_folder


def extract_om_code(subject: str) -> str:
    """Extract O&M code matching regex \\bIN-\\d+\\b.

    Raises:
        OMCodeNotFoundError: If no valid IN-xxx pattern is found.
    """
    match = OM_CODE_REGEX.search(subject)
    if not match:
        raise OMCodeNotFoundError(
            f"O&M code matching 'IN-\\d+' not found in subject: '{subject}'"
        )
    return match.group(0).upper()


def extract_client_name(subject: str, om_code: str) -> str:
    """Extract the client name portion before invoice/reference number and O&M code.

    Examples:
        'GRUPO ANTOLIN INDIA - CHENNAI IN1821191 - IN-091 - | Invoice for the month of AUGUST 2026'
        -> 'GRUPO ANTOLIN INDIA - CHENNAI'

        'ABC INDIA - IN-125 - Invoice for the month of September 2026'
        -> 'ABC INDIA'

        'XYZ - IN-045 - Invoice for the month of JULY 2026'
        -> 'XYZ'
    """
    # Split at 'Invoice for the month of'
    period_match = re.search(r"Invoice\s+for\s+the\s+month\s+of", subject, re.IGNORECASE)
    if not period_match:
        raise SubjectValidationError("Cannot extract client: subject missing required phrase.")

    prefix = subject[: period_match.start()].strip()

    # Remove trailing/leading pipes and dashes from prefix
    prefix = re.sub(r"\|.*$", "", prefix).strip()
    prefix = prefix.rstrip("- \t|")

    # Remove O&M code and surrounding separators
    if om_code:
        om_pattern = rf"[\s\-_|]*\b{re.escape(om_code)}\b[\s\-_|]*"
        prefix = re.sub(om_pattern, " ", prefix, flags=re.IGNORECASE).strip()

    # Remove reference numbers like IN1821191 or numbers of 5+ digits
    # Only remove if it looks like an invoice/reference number (e.g. IN1821191)
    prefix = re.sub(r"[\s\-_|]*\b(?:IN|INV|REF)?[0-9]{5,}\b[\s\-_|]*", " ", prefix, flags=re.IGNORECASE).strip()

    # Clean up trailing/leading dashes, spaces, pipes
    client_name = re.sub(r"\s+", " ", prefix).strip("- \t|")

    if not client_name:
        raise ClientNameNotFoundError(f"Could not extract a valid client name from: '{subject}'")

    return client_name


def parse_invoice_subject(subject: str) -> Dict[str, Any]:
    """Parse complete invoice email subject into structured data.

    Returns:
        dict:
            client_name: str
            om_code: str
            invoice_month: str (Title Case, e.g. 'August')
            invoice_year: int (e.g. 2026)
            month_folder: str (YYMM, e.g. '2608')

    Raises:
        SubjectValidationError: If required subject phrase is missing.
        OMCodeNotFoundError: If O&M code is missing.
        InvoicePeriodError: If month/year is missing or invalid.
        ClientNameNotFoundError: If client name cannot be extracted.
    """
    month_title, year_int, month_folder = extract_period(subject)
    om_code = extract_om_code(subject)
    client_name = extract_client_name(subject, om_code)

    return {
        "client_name": client_name,
        "om_code": om_code,
        "invoice_month": month_title,
        "invoice_year": year_int,
        "month_folder": month_folder,
    }
