"""End-to-end integration simulation matching Section 38 of the specification."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock

from src.database.db import DatabaseManager
from src.database.models import ProcessingStatus
from src.parsers.invoice_subject_parser import parse_invoice_subject
from src.services.email_processor import EmailProcessor
from src.utils.filename import generate_invoice_filename


def test_section_38_complete_workflow():
    """Execute and verify Section 38's exact scenario:

    Input email:
      To: india.invoicing@cleantechsolar.com
      Subject: GRUPO ANTOLIN INDIA - CHENNAI IN1821191 - IN-091 - | Invoice for the month of AUGUST 2026
      Attachment: Invoice_12345.pdf

    Expected:
      Recipient: VALID
      Subject: VALID
      Client: GRUPO ANTOLIN INDIA - CHENNAI
      O&M: IN-091
      Month: August
      Year: 2026
      SharePoint Month Folder: 2608
      Final Filename: GRUPO ANTOLIN INDIA - CHENNAI August 2026.pdf
      Customer Invoicing/Invoices/2608 -> created
      Customer Invoicing/Invoices/2608/IN-091 -> created
      Upload -> Customer Invoicing/Invoices/2608/IN-091/
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        db = DatabaseManager(db_path=str(Path(tmpdir) / "sim.db"))

        subject = "GRUPO ANTOLIN INDIA - CHENNAI IN1821191 - IN-091 - | Invoice for the month of AUGUST 2026"

        # 1. Subject parser step verification
        parsed = parse_invoice_subject(subject)
        assert parsed["client_name"] == "GRUPO ANTOLIN INDIA - CHENNAI"
        assert parsed["om_code"] == "IN-091"
        assert parsed["invoice_month"] == "August"
        assert parsed["invoice_year"] == 2026
        assert parsed["month_folder"] == "2608"

        # 2. Filename generator verification
        final_filename = generate_invoice_filename(
            parsed["client_name"], parsed["invoice_month"], parsed["invoice_year"]
        )
        assert final_filename == "GRUPO ANTOLIN INDIA - CHENNAI August 2026.pdf"

        # 3. Email Processor orchestration verification
        mock_outlook = MagicMock()
        mock_outlook.invoice_group_address = "india.invoicing@cleantechsolar.com"
        mock_outlook.is_target_recipient.return_value = True
        mock_outlook.get_attachments.return_value = [
            {"name": "Invoice_12345.pdf", "id": "att-123"}
        ]
        pdf_content = b"%PDF-1.5 \x00 Sample Invoice Content"
        mock_outlook.download_attachment_bytes.return_value = pdf_content

        mock_sharepoint = MagicMock()
        mock_sharepoint.dry_run = False
        mock_sharepoint.resolve_target_folder.return_value = (
            "drive-cleantech-om",
            "folder-in091-id",
            "Customer Invoicing/Invoices/2608/IN-091",
        )
        mock_sharepoint.check_duplicate_file.return_value = False

        processor = EmailProcessor(
            outlook_client=mock_outlook,
            sharepoint_service=mock_sharepoint,
            db_manager=db,
        )

        sample_message = {
            "id": "AAMkAGI2AA...",
            "internetMessageId": "<invoice-aug2026@cleantechsolar.com>",
            "receivedDateTime": "2026-09-03T08:30:00Z",
            "from": {"emailAddress": {"address": "billing@grupoantolin.com"}},
            "toRecipients": [{"emailAddress": {"address": "india.invoicing@cleantechsolar.com"}}],
            "ccRecipients": [],
            "subject": subject,
        }

        status = processor.process_message(sample_message)
        assert status in (ProcessingStatus.SUCCESS.value, ProcessingStatus.PROCESSED.value)

        # Confirm target folder resolution was invoked with 2608, IN-091, and year 2026
        mock_sharepoint.resolve_target_folder.assert_called_once_with(
            month_folder="2608",
            om_code="IN-091",
            invoice_year=2026,
        )

        # Confirm upload was invoked with correct parameters
        mock_sharepoint.upload_invoice_pdf.assert_called_once_with(
            drive_id="drive-cleantech-om",
            folder_id="folder-in091-id",
            filename="GRUPO ANTOLIN INDIA - CHENNAI August 2026.pdf",
            pdf_bytes=pdf_content,
            target_path="Customer Invoicing/Invoices/2608/IN-091",
        )

        # Confirm record written in DB
        db_record = db.get_processed_email("AAMkAGI2AA...")
        assert db_record is not None
        assert db_record["status"] in ("SUCCESS", "PROCESSED")
        assert db_record["client_name"] == "GRUPO ANTOLIN INDIA - CHENNAI"
        assert db_record["om_code"] == "IN-091"
        assert db_record["invoice_month"] == "August"
        assert db_record["invoice_year"] == 2026
        assert db_record["month_folder"] == "2608"
        assert db_record["saved_filename"] == "GRUPO ANTOLIN INDIA - CHENNAI August 2026.pdf"
        assert db_record["sharepoint_path"] == "Customer Invoicing/Invoices/2608/IN-091/GRUPO ANTOLIN INDIA - CHENNAI August 2026.pdf"
        assert db_record["invoice_group_address"] == "india.invoicing@cleantechsolar.com"
