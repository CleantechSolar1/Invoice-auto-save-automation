"""Unit tests for filename generation and sanitization."""

from src.utils.filename import (
    generate_invoice_filename,
    is_pdf_filename,
    is_valid_pdf_bytes,
    sanitize_sharepoint_name,
)


def test_standard_filename_generation():
    """Verify standard filename formatting per Section 18."""
    assert (
        generate_invoice_filename("GRUPO ANTOLIN INDIA - CHENNAI", "August", 2026)
        == "GRUPO ANTOLIN INDIA - CHENNAI August 2026.pdf"
    )
    assert (
        generate_invoice_filename("ABC INDIA", "September", 2026)
        == "ABC INDIA September 2026.pdf"
    )
    assert (
        generate_invoice_filename("XYZ", "July", 2026)
        == "XYZ July 2026.pdf"
    )


def test_month_title_casing():
    """Verify month is always Title Cased regardless of input casing."""
    assert (
        generate_invoice_filename("CLIENT", "AUGUST", 2026)
        == "CLIENT August 2026.pdf"
    )
    assert (
        generate_invoice_filename("CLIENT", "august", 2026)
        == "CLIENT August 2026.pdf"
    )
    assert (
        generate_invoice_filename("CLIENT", "aUgUsT", 2026)
        == "CLIENT August 2026.pdf"
    )


def test_forbidden_characters_sanitization():
    """Verify SharePoint illegal characters are cleanly stripped (Section 19)."""
    # Illegal chars: " * : < > ? / \ |
    dirty_name = 'Client "Acme*Corp" : Tech <Pvt> ? / \\ | Ltd.'
    sanitized = sanitize_sharepoint_name(dirty_name)
    assert '"' not in sanitized
    assert '*' not in sanitized
    assert ':' not in sanitized
    assert '<' not in sanitized
    assert '>' not in sanitized
    assert '?' not in sanitized
    assert '/' not in sanitized
    assert '\\' not in sanitized
    assert '|' not in sanitized


def test_safe_characters_preserved():
    """Ensure standard characters (- & . ( )) are preserved."""
    safe_name = "ABC & Sons (India) - Solar Tech Pvt. Ltd."
    sanitized = sanitize_sharepoint_name(safe_name)
    assert "&" in sanitized
    assert "(" in sanitized and ")" in sanitized
    assert "-" in sanitized


def test_is_pdf_filename():
    """Verify case-insensitive PDF file extension check (Section 16)."""
    assert is_pdf_filename("invoice.pdf")
    assert is_pdf_filename("Invoice.PDF")
    assert is_pdf_filename("INVOICE.Pdf")
    assert not is_pdf_filename("invoice.xlsx")
    assert not is_pdf_filename("invoice.docx")
    assert not is_pdf_filename("invoice.png")
    assert not is_pdf_filename("invoice.zip")
    assert not is_pdf_filename("")


def test_is_valid_pdf_bytes():
    """Verify binary PDF header validation (%PDF-)."""
    valid_pdf_header = b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n"
    assert is_valid_pdf_bytes(valid_pdf_header)

    invalid_content = b"<html><body>Not a PDF</body></html>"
    assert not is_valid_pdf_bytes(invalid_content)
    assert not is_valid_pdf_bytes(b"")
