"""Email processing pipeline for sales invoice emails."""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from src.database.db import DatabaseManager
from src.database.models import ProcessedEmailRecord, ProcessingStatus
from src.graph.outlook_client import OutlookClient
from src.parsers.invoice_subject_parser import (
    InvoicePeriodError,
    OMCodeNotFoundError,
    SubjectParserError,
    SubjectValidationError,
    is_valid_invoice_subject,
    parse_invoice_subject,
)
from src.services.sharepoint_service import SharePointService
from src.utils.filename import (
    generate_invoice_filename,
    is_pdf_filename,
    is_valid_pdf_bytes,
)

logger = logging.getLogger("invoice_automation.processor")


class EmailProcessor:
    """Processes single email messages according to business rules and policies."""

    def __init__(
        self,
        outlook_client: OutlookClient,
        sharepoint_service: SharePointService,
        db_manager: DatabaseManager,
    ):
        self.outlook = outlook_client
        self.sharepoint = sharepoint_service
        self.db = db_manager

    def process_message(self, message: Dict[str, Any]) -> str:
        """Process an incoming email message through the full pipeline.

        Returns:
            The resulting ProcessingStatus string.
        """
        message_id = message.get("id", "")
        internet_message_id = message.get("internetMessageId")
        received_datetime = message.get("receivedDateTime")
        sender_info = message.get("from", {}).get("emailAddress", {})
        sender = sender_info.get("address", "")
        subject = message.get("subject") or ""

        logger.info("Email received: %s (Subject: '%s')", message_id, subject)

        # Step 0: Check database to prevent duplicate processing
        if self.db.is_message_processed(message_id):
            logger.info("Email %s was previously processed. Skipping.", message_id)
            return "ALREADY_PROCESSED"

        base_record = ProcessedEmailRecord(
            message_id=message_id,
            internet_message_id=internet_message_id,
            received_datetime=received_datetime,
            sender=sender,
            subject=subject,
            invoice_group_address=self.outlook.invoice_group_address,
            status=ProcessingStatus.PROCESSING_ERROR.value,
        )

        # Step 1: Check Condition #1 - Recipient (To or CC contains INVOICE_GROUP_ADDRESS)
        if not self.outlook.is_target_recipient(message):
            logger.info(
                "Recipient validation skipped: invoice group '%s' not in To or CC for message %s. Skipping.",
                self.outlook.invoice_group_address,
                message_id,
            )
            base_record.status = ProcessingStatus.SKIPPED_RECIPIENT.value
            self.db.record_email(base_record)
            return ProcessingStatus.SKIPPED_RECIPIENT.value

        logger.info("Recipient validation passed (matched invoice group: %s)", self.outlook.invoice_group_address)

        # Step 2: Check Condition #2 - Subject Validation
        if not is_valid_invoice_subject(subject):
            logger.info("Subject validation failed: missing 'Invoice for the month of'. Skipping.")
            base_record.status = ProcessingStatus.SKIPPED_SUBJECT.value
            self.db.record_email(base_record)
            return ProcessingStatus.SKIPPED_SUBJECT.value

        logger.info("Subject validation passed")

        # Step 3: Parse Subject Metadata
        try:
            parsed = parse_invoice_subject(subject)
        except InvoicePeriodError as exc:
            logger.error("Invalid invoice period in subject: %s", exc)
            base_record.status = ProcessingStatus.INVALID_PERIOD.value
            base_record.error_message = str(exc)
            self.db.record_email(base_record)
            return ProcessingStatus.INVALID_PERIOD.value
        except OMCodeNotFoundError as exc:
            logger.error("Invalid or missing O&M code in subject: %s", exc)
            base_record.status = ProcessingStatus.INVALID_OM_CODE.value
            base_record.error_message = str(exc)
            self.db.record_email(base_record)
            return ProcessingStatus.INVALID_OM_CODE.value
        except SubjectParserError as exc:
            logger.error("Subject parsing error: %s", exc)
            base_record.status = ProcessingStatus.PROCESSING_ERROR.value
            base_record.error_message = str(exc)
            self.db.record_email(base_record)
            return ProcessingStatus.PROCESSING_ERROR.value

        client_name = parsed["client_name"]
        om_code = parsed["om_code"]
        invoice_month = parsed["invoice_month"]
        invoice_year = parsed["invoice_year"]
        month_folder = parsed["month_folder"]

        logger.info("Client: %s", client_name)
        logger.info("O&M Code: %s", om_code)
        logger.info("Invoice Period: %s %d", invoice_month, invoice_year)
        logger.info("Month Folder: %s", month_folder)

        base_record.client_name = client_name
        base_record.om_code = om_code
        base_record.invoice_month = invoice_month
        base_record.invoice_year = invoice_year
        base_record.month_folder = month_folder

        # Step 4: Identify PDF Attachment
        try:
            attachments = self.outlook.get_attachments(message_id)
        except Exception as exc:
            logger.error("Failed to retrieve attachments for email %s: %s", message_id, exc)
            base_record.status = ProcessingStatus.PROCESSING_ERROR.value
            base_record.error_message = f"Failed to retrieve attachments: {exc}"
            self.db.record_email(base_record)
            return ProcessingStatus.PROCESSING_ERROR.value

        pdf_attachment: Optional[Dict[str, Any]] = None
        for att in attachments:
            att_name = att.get("name", "")
            logger.debug("Found attachment: %s", att_name)
            if is_pdf_filename(att_name):
                pdf_attachment = att
                break

        if not pdf_attachment:
            logger.warning("No PDF invoice attachment found for message: %s", message_id)
            base_record.status = ProcessingStatus.NO_PDF.value
            base_record.error_message = "No PDF invoice attachment found"
            self.db.record_email(base_record)
            return ProcessingStatus.NO_PDF.value

        original_attachment_name = pdf_attachment.get("name", "")
        base_record.attachment_name = original_attachment_name
        logger.info("PDF attachment identified: %s", original_attachment_name)

        # Step 5: Download & Validate PDF Content
        try:
            pdf_bytes = self.outlook.download_attachment_bytes(message_id, pdf_attachment)
        except Exception as exc:
            logger.error("Unable to download attachment %s: %s", original_attachment_name, exc)
            base_record.status = ProcessingStatus.PROCESSING_ERROR.value
            base_record.error_message = f"Unable to download attachment: {exc}"
            self.db.record_email(base_record)
            return ProcessingStatus.PROCESSING_ERROR.value

        if not is_valid_pdf_bytes(pdf_bytes):
            logger.error("Attachment '%s' is not a valid PDF file (missing %%PDF- header)", original_attachment_name)
            base_record.status = ProcessingStatus.PROCESSING_ERROR.value
            base_record.error_message = "Attachment content is not a valid PDF file"
            self.db.record_email(base_record)
            return ProcessingStatus.PROCESSING_ERROR.value

        # Step 6: Generate Sanitized Final Filename
        final_filename = generate_invoice_filename(client_name, invoice_month, invoice_year)
        base_record.saved_filename = final_filename
        base_record.target_filename = final_filename

        # Step 7: SharePoint Hierarchy Resolution & Duplicate Check
        try:
            drive_id, om_folder_id, target_path = self.sharepoint.resolve_target_folder(
                month_folder=month_folder,
                om_code=om_code,
                invoice_year=invoice_year,
            )
            base_record.sharepoint_path = f"{target_path}/{final_filename}"

            # Duplicate Check
            if om_folder_id and self.sharepoint.check_duplicate_file(drive_id, om_folder_id, final_filename):
                logger.info("DUPLICATE:\nInvoice file already exists:\n%s", final_filename)
                base_record.status = ProcessingStatus.DUPLICATE.value
                self.db.record_email(base_record)
                return ProcessingStatus.DUPLICATE.value

            logger.info("Duplicate check passed")

            # Step 8: Upload File
            self.sharepoint.upload_invoice_pdf(
                drive_id=drive_id,
                folder_id=om_folder_id,
                filename=final_filename,
                pdf_bytes=pdf_bytes,
                target_path=target_path,
            )

            if not self.sharepoint.dry_run:
                logger.info("Invoice uploaded successfully to %s", target_path)

            base_record.status = ProcessingStatus.SUCCESS.value
            base_record.processed_at = datetime.now(timezone.utc).isoformat()
            self.db.record_email(base_record)
            return ProcessingStatus.SUCCESS.value

        except Exception as exc:
            logger.error("SharePoint operation failed: %s", exc)
            base_record.status = ProcessingStatus.SHAREPOINT_ERROR.value
            base_record.error_message = str(exc)
            self.db.record_email(base_record)
            return ProcessingStatus.SHAREPOINT_ERROR.value
