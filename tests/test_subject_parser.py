"""Unit tests for invoice email subject parsing."""

import pytest
from src.parsers.invoice_subject_parser import (
    InvoicePeriodError,
    OMCodeNotFoundError,
    SubjectValidationError,
    extract_client_name,
    extract_om_code,
    extract_period,
    is_valid_invoice_subject,
    parse_invoice_subject,
)


def test_standard_test_case():
    """Test the exact standard test case specified in Section 30."""
    subject = "GRUPO ANTOLIN INDIA - CHENNAI IN1821191 - IN-091 - | Invoice for the month of AUGUST 2026"
    result = parse_invoice_subject(subject)

    assert result["client_name"] == "GRUPO ANTOLIN INDIA - CHENNAI"
    assert result["om_code"] == "IN-091"
    assert result["invoice_month"] == "August"
    assert result["invoice_year"] == 2026
    assert result["month_folder"] == "2608"


def test_additional_valid_subjects():
    """Test various additional valid subject variations from the specification."""
    # Test case 2
    subject2 = "ABC INDIA - IN-125 - Invoice for the month of September 2026"
    res2 = parse_invoice_subject(subject2)
    assert res2["client_name"] == "ABC INDIA"
    assert res2["om_code"] == "IN-125"
    assert res2["invoice_month"] == "September"
    assert res2["invoice_year"] == 2026
    assert res2["month_folder"] == "2609"

    # Test case 3
    subject3 = "XYZ - IN-045 - Invoice for the month of JULY 2026"
    res3 = parse_invoice_subject(subject3)
    assert res3["client_name"] == "XYZ"
    assert res3["om_code"] == "IN-045"
    assert res3["invoice_month"] == "July"
    assert res3["invoice_year"] == 2026
    assert res3["month_folder"] == "2607"


def test_month_folder_conversions():
    """Test required month folder conversions from Section 30."""
    cases = [
        ("ABC - IN-001 - Invoice for the month of September 2026", "2609"),
        ("ABC - IN-001 - Invoice for the month of July 2026", "2607"),
        ("ABC - IN-001 - Invoice for the month of December 2026", "2612"),
        ("ABC - IN-001 - Invoice for the month of January 2027", "2701"),
        ("ABC - IN-001 - Invoice for the month of February 2028", "2802"),
    ]
    for subject, expected_folder in cases:
        res = parse_invoice_subject(subject)
        assert res["month_folder"] == expected_folder


def test_case_insensitivity_of_period():
    """Test mixed casing of the invoice period as specified in Section 30."""
    variations = [
        "GRUPO ANTOLIN - IN-091 - Invoice for the month of august 2026",
        "GRUPO ANTOLIN - IN-091 - Invoice for the month of August 2026",
        "GRUPO ANTOLIN - IN-091 - Invoice for the month of AUGUST 2026",
        "GRUPO ANTOLIN - IN-091 - Invoice for the month of AuGuSt 2026",
    ]
    for subject in variations:
        res = parse_invoice_subject(subject)
        assert res["invoice_month"] == "August"
        assert res["invoice_year"] == 2026
        assert res["month_folder"] == "2608"


def test_all_twelve_months():
    """Verify all 12 calendar months map to their expected 2-digit representation."""
    months = [
        ("January", "2601"),
        ("February", "2602"),
        ("March", "2603"),
        ("April", "2604"),
        ("May", "2605"),
        ("June", "2606"),
        ("July", "2607"),
        ("August", "2608"),
        ("September", "2609"),
        ("October", "2610"),
        ("November", "2611"),
        ("December", "2612"),
    ]
    for month_name, expected_code in months:
        subject = f"TEST CORP - IN-001 - Invoice for the month of {month_name} 2026"
        res = parse_invoice_subject(subject)
        assert res["month_folder"] == expected_code
        assert res["invoice_month"] == month_name


def test_om_code_precision():
    """Ensure IN1821191 is not mistakenly picked up when IN-091 is present or absent."""
    subject = "GRUPO ANTOLIN INDIA - CHENNAI IN1821191 - IN-091 - | Invoice for the month of AUGUST 2026"
    assert extract_om_code(subject) == "IN-091"

    # When no hyphenated code exists, must fail
    with pytest.raises(OMCodeNotFoundError):
        extract_om_code("GRUPO ANTOLIN INDIA - CHENNAI IN1821191 | Invoice for the month of AUGUST 2026")


def test_invalid_subject_no_phrase():
    """Test subjects lacking 'Invoice for the month of' (Section 31)."""
    invalid_subjects = [
        "GRUPO ANTOLIN INDIA - IN-091 - Payment Reminder",
        "Payment Reminder",
        "Invoice",
        "Invoice Generated",
        "Monthly Billing",
    ]
    for s in invalid_subjects:
        assert not is_valid_invoice_subject(s)
        with pytest.raises(SubjectValidationError):
            parse_invoice_subject(s)


def test_missing_om_code():
    """Test subject missing O&M code (Section 31)."""
    subject = "GRUPO ANTOLIN INDIA | Invoice for the month of August 2026"
    with pytest.raises(OMCodeNotFoundError):
        parse_invoice_subject(subject)


def test_invalid_period_month():
    """Test invalid month name (Section 31)."""
    subject = "GRUPO ANTOLIN INDIA - IN-091 | Invoice for the month of ABC 2026"
    with pytest.raises(InvoicePeriodError):
        parse_invoice_subject(subject)


def test_invalid_period_year():
    """Test invalid 2-digit year (Section 31)."""
    subject = "GRUPO ANTOLIN INDIA - IN-091 | Invoice for the month of August 26"
    with pytest.raises(InvoicePeriodError):
        parse_invoice_subject(subject)
