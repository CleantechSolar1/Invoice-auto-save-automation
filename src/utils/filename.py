"""Filename generation and sanitization for SharePoint compatibility."""

import re

# Characters strictly forbidden in SharePoint and OneDrive file and folder names:
# " * : < > ? / \ |
# Also tabs, newlines, and control characters
SHAREPOINT_FORBIDDEN_CHARS_REGEX = re.compile(r'["*:<>?/\\|\x00-\x1f]')


def sanitize_sharepoint_name(name: str) -> str:
    """Sanitize a file or folder name for SharePoint compatibility.

    - Removes forbidden characters: " * : < > ? / \\ |
    - Preserves safe characters: - & . ( )
    - Collapses consecutive whitespace to a single space
    - Strips leading and trailing whitespace and periods (SharePoint disallows names ending in a dot)
    """
    if not name:
        return ""

    # Replace forbidden characters with empty string (or space if embedded)
    sanitized = SHAREPOINT_FORBIDDEN_CHARS_REGEX.sub("", name)

    # Collapse multiple spaces into one
    sanitized = re.sub(r"\s+", " ", sanitized).strip()

    # SharePoint filenames cannot end with a period or space
    sanitized = sanitized.rstrip(". ")

    return sanitized


def generate_invoice_filename(client_name: str, invoice_month: str, invoice_year: int) -> str:
    """Generate the standardized invoice PDF filename.

    Format: <Client Name> <Month> <Year>.pdf
    Example: GRUPO ANTOLIN INDIA - CHENNAI August 2026.pdf
    Month is formatted in standard Title Case.
    """
    clean_client = sanitize_sharepoint_name(client_name)
    title_month = invoice_month.strip().capitalize()
    base_name = f"{clean_client} {title_month} {invoice_year}"
    clean_base = sanitize_sharepoint_name(base_name)
    return f"{clean_base}.pdf"


def is_pdf_filename(filename: str) -> bool:
    """Check if the filename has a .pdf extension (case-insensitive)."""
    if not filename:
        return False
    return filename.strip().lower().endswith(".pdf")


def is_valid_pdf_bytes(content: bytes) -> bool:
    """Check if the binary data starts with the standard PDF magic header (%PDF-)."""
    if not content or len(content) < 5:
        return False
    # Standard PDF header is %PDF-
    return content[:1024].lstrip().startswith(b"%PDF-")
