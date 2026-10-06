"""Unit tests for SharePoint YYMM month folder generation."""

from src.parsers.invoice_subject_parser import extract_period


def test_month_folder_generation_all_months():
    """Verify all 12 months in 2026 produce the exact expected YYMM string."""
    expected_mapping = [
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

    for month_name, expected_code in expected_mapping:
        subject = f"CLIENT - IN-001 - Invoice for the month of {month_name} 2026"
        month_title, year_int, month_folder = extract_period(subject)
        assert month_folder == expected_code
        assert month_title == month_name
        assert year_int == 2026


def test_folder_derived_from_subject_not_received_date():
    """Verify folder is derived strictly from subject period (Section 10)."""
    # Scenario: received in September 2026, but invoice is for August 2026
    subject = "GRUPO ANTOLIN INDIA - IN-091 - Invoice for the month of AUGUST 2026"
    _, _, month_folder = extract_period(subject)
    assert month_folder == "2608"
    assert month_folder != "2609"


def test_cross_year_folder_generation():
    """Verify transition across years produces accurate YYMM."""
    subject = "CLIENT - IN-001 - Invoice for the month of January 2027"
    _, year, folder = extract_period(subject)
    assert year == 2027
    assert folder == "2701"

    subject = "CLIENT - IN-001 - Invoice for the month of December 2029"
    _, year, folder = extract_period(subject)
    assert year == 2029
    assert folder == "2912"
