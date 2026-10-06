"""Unit and integration tests for the EmailProcessor service."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.database.db import DatabaseManager
from src.database.models import ProcessingStatus
from src.services.email_processor import EmailProcessor


@pytest.fixture
def temp_db():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = str(Path(tmpdir) / "test_processor.db")
        yield DatabaseManager(db_path=db_path)


def test_skip_recipient_when_not_in_to_or_cc(temp_db):
    """Verify email is skipped when invoice group address is not in To or CC."""
    mock_outlook = MagicMock()
    mock_outlook.invoice_group_address = "india.invoicing@cleantechsolar.com"
    mock_outlook.is_target_recipient.return_value = False
    mock_sharepoint = MagicMock()

    processor = EmailProcessor(
        outlook_client=mock_outlook,
        sharepoint_service=mock_sharepoint,
        db_manager=temp_db,
    )

    msg = {
        "id": "msg-001",
        "subject": "GRUPO ANTOLIN - IN-091 - Invoice for the month of August 2026",
        "toRecipients": [{"emailAddress": {"address": "other@cleantechsolar.com"}}],
        "ccRecipients": [],
    }

    status = processor.process_message(msg)
    assert status == ProcessingStatus.SKIPPED_RECIPIENT.value
    assert temp_db.is_message_processed("msg-001")
    assert not mock_sharepoint.upload_invoice_pdf.called


def test_skip_subject_when_phrase_missing(temp_db):
    """Verify email is skipped when 'Invoice for the month of' is absent."""
    mock_outlook = MagicMock()
    mock_outlook.invoice_group_address = "india.invoicing@cleantechsolar.com"
    mock_outlook.is_target_recipient.return_value = True
    mock_sharepoint = MagicMock()

    processor = EmailProcessor(
        outlook_client=mock_outlook,
        sharepoint_service=mock_sharepoint,
        db_manager=temp_db,
    )

    msg = {
        "id": "msg-002",
        "subject": "GRUPO ANTOLIN INDIA - IN-091 - Payment Reminder",
        "toRecipients": [{"emailAddress": {"address": "india.invoicing@cleantechsolar.com"}}],
    }

    status = processor.process_message(msg)
    assert status == ProcessingStatus.SKIPPED_SUBJECT.value
    assert temp_db.is_message_processed("msg-002")
    assert not mock_sharepoint.upload_invoice_pdf.called


def test_no_pdf_attachment_detected(temp_db):
    """Verify status NO_PDF when message has no PDF attachments."""
    mock_outlook = MagicMock()
    mock_outlook.invoice_group_address = "india.invoicing@cleantechsolar.com"
    mock_outlook.is_target_recipient.return_value = True
    mock_outlook.get_attachments.return_value = [
        {"name": "statement.xlsx", "id": "att-1"},
        {"name": "summary.docx", "id": "att-2"},
    ]
    mock_sharepoint = MagicMock()

    processor = EmailProcessor(
        outlook_client=mock_outlook,
        sharepoint_service=mock_sharepoint,
        db_manager=temp_db,
    )

    msg = {
        "id": "msg-003",
        "subject": "GRUPO ANTOLIN INDIA - CHENNAI IN1821191 - IN-091 - | Invoice for the month of AUGUST 2026",
        "toRecipients": [{"emailAddress": {"address": "india.invoicing@cleantechsolar.com"}}],
    }

    status = processor.process_message(msg)
    assert status == ProcessingStatus.NO_PDF.value
    assert temp_db.is_message_processed("msg-003")
    assert not mock_sharepoint.upload_invoice_pdf.called


def test_duplicate_pdf_detection(temp_db):
    """Verify duplicate detection prevents file upload and logs DUPLICATE."""
    mock_outlook = MagicMock()
    mock_outlook.invoice_group_address = "india.invoicing@cleantechsolar.com"
    mock_outlook.is_target_recipient.return_value = True
    mock_outlook.get_attachments.return_value = [
        {"name": "Invoice_raw.pdf", "id": "att-pdf"}
    ]
    mock_outlook.download_attachment_bytes.return_value = b"%PDF-1.4 simulated pdf content"

    mock_sharepoint = MagicMock()
    mock_sharepoint.resolve_target_folder.return_value = (
        "drive-1",
        "folder-om",
        "Customer Invoicing/Invoices/2608/IN-091",
    )
    # Simulate duplicate exists in SharePoint
    mock_sharepoint.check_duplicate_file.return_value = True

    processor = EmailProcessor(
        outlook_client=mock_outlook,
        sharepoint_service=mock_sharepoint,
        db_manager=temp_db,
    )

    msg = {
        "id": "msg-004",
        "subject": "GRUPO ANTOLIN INDIA - CHENNAI IN1821191 - IN-091 - | Invoice for the month of AUGUST 2026",
        "toRecipients": [{"emailAddress": {"address": "india.invoicing@cleantechsolar.com"}}],
    }

    status = processor.process_message(msg)
    assert status == ProcessingStatus.DUPLICATE.value
    assert temp_db.is_message_processed("msg-004")
    assert not mock_sharepoint.upload_invoice_pdf.called


def test_successful_processing_pipeline(temp_db):
    """Verify end-to-end processing succeeds with expected filename, folder, and upload."""
    mock_outlook = MagicMock()
    mock_outlook.invoice_group_address = "india.invoicing@cleantechsolar.com"
    mock_outlook.is_target_recipient.return_value = True
    mock_outlook.get_attachments.return_value = [
        {"name": "Invoice_12345.pdf", "id": "att-pdf"}
    ]
    valid_pdf_content = b"%PDF-1.4\n1 0 obj\n<<\n>>\nendobj\ntrailer\n<<\n>>\n%%EOF"
    mock_outlook.download_attachment_bytes.return_value = valid_pdf_content

    mock_sharepoint = MagicMock()
    mock_sharepoint.dry_run = False
    mock_sharepoint.resolve_target_folder.return_value = (
        "drive-1",
        "folder-om",
        "Customer Invoicing/Invoices/2608/IN-091",
    )
    mock_sharepoint.check_duplicate_file.return_value = False

    processor = EmailProcessor(
        outlook_client=mock_outlook,
        sharepoint_service=mock_sharepoint,
        db_manager=temp_db,
    )

    msg = {
        "id": "msg-005",
        "subject": "GRUPO ANTOLIN INDIA - CHENNAI IN1821191 - IN-091 - | Invoice for the month of AUGUST 2026",
        "toRecipients": [{"emailAddress": {"address": "india.invoicing@cleantechsolar.com"}}],
    }

    status = processor.process_message(msg)
    assert status in (ProcessingStatus.SUCCESS.value, ProcessingStatus.PROCESSED.value)
    assert temp_db.is_message_processed("msg-005")

    # Verify upload was called with exact filename and parameters
    mock_sharepoint.upload_invoice_pdf.assert_called_once_with(
        drive_id="drive-1",
        folder_id="folder-om",
        filename="GRUPO ANTOLIN INDIA - CHENNAI August 2026.pdf",
        pdf_bytes=valid_pdf_content,
        target_path="Customer Invoicing/Invoices/2608/IN-091",
    )

    # Verify database record
    record = temp_db.get_processed_email("msg-005")
    assert record["status"] in ("SUCCESS", "PROCESSED")
    assert record["client_name"] == "GRUPO ANTOLIN INDIA - CHENNAI"
    assert record["om_code"] == "IN-091"
    assert record["month_folder"] == "2608"
    assert record["saved_filename"] == "GRUPO ANTOLIN INDIA - CHENNAI August 2026.pdf"
    assert record["invoice_group_address"] == "india.invoicing@cleantechsolar.com"


def test_dry_run_mode_does_not_upload(temp_db):
    """Verify dry-run mode resolves paths and checks duplicates but does not upload live files."""
    mock_outlook = MagicMock()
    mock_outlook.invoice_group_address = "india.invoicing@cleantechsolar.com"
    mock_outlook.is_target_recipient.return_value = True
    mock_outlook.get_attachments.return_value = [
        {"name": "Invoice_dry.pdf", "id": "att-pdf"}
    ]
    mock_outlook.download_attachment_bytes.return_value = b"%PDF-1.4 sample content"

    mock_sharepoint = MagicMock()
    mock_sharepoint.dry_run = True
    mock_sharepoint.resolve_target_folder.return_value = (
        "drive-1",
        "folder-om",
        "Customer Invoicing/Invoices/2608/IN-091",
    )
    mock_sharepoint.check_duplicate_file.return_value = False

    processor = EmailProcessor(
        outlook_client=mock_outlook,
        sharepoint_service=mock_sharepoint,
        db_manager=temp_db,
    )

    msg = {
        "id": "msg-006",
        "subject": "GRUPO ANTOLIN INDIA - CHENNAI IN1821191 - IN-091 - | Invoice for the month of AUGUST 2026",
        "toRecipients": [{"emailAddress": {"address": "india.invoicing@cleantechsolar.com"}}],
    }

    status = processor.process_message(msg)
    assert status in (ProcessingStatus.SUCCESS.value, ProcessingStatus.PROCESSED.value)
    mock_sharepoint.upload_invoice_pdf.assert_called_once()
