"""Unit tests for SQLite database manager."""

import tempfile
from pathlib import Path
from src.database.db import DatabaseManager
from src.database.models import ProcessedEmailRecord, ProcessingStatus


def test_database_lifecycle():
    """Verify table creation, insertion, queries, and idempotent updates."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_file = str(Path(tmpdir) / "test.db")
        db = DatabaseManager(db_path=db_file)

        msg_id = "msg-12345"
        assert not db.is_message_processed(msg_id)

        # Record email
        record = ProcessedEmailRecord(
            message_id=msg_id,
            internet_message_id="<abc@cleantechsolar.com>",
            received_datetime="2026-09-03T10:00:00Z",
            sender="vendor@example.com",
            subject="GRUPO ANTOLIN INDIA - IN-091 - | Invoice for the month of AUGUST 2026",
            client_name="GRUPO ANTOLIN INDIA",
            om_code="IN-091",
            invoice_month="August",
            invoice_year=2026,
            month_folder="2608",
            attachment_name="Invoice_123.pdf",
            saved_filename="GRUPO ANTOLIN INDIA August 2026.pdf",
            sharepoint_path="Customer Invoicing/Invoices/2608/IN-091/GRUPO ANTOLIN INDIA August 2026.pdf",
            status=ProcessingStatus.PROCESSED.value,
        )
        db.record_email(record)

        assert db.is_message_processed(msg_id)

        # Retrieve
        fetched = db.get_processed_email(msg_id)
        assert fetched is not None
        assert fetched["message_id"] == msg_id
        assert fetched["status"] == "PROCESSED"
        assert fetched["om_code"] == "IN-091"
        assert fetched["month_folder"] == "2608"

        # Update status
        record.status = ProcessingStatus.DUPLICATE.value
        db.record_email(record)

        fetched2 = db.get_processed_email(msg_id)
        assert fetched2["status"] == "DUPLICATE"

        # Count by status
        counts = db.count_by_status()
        assert counts.get("DUPLICATE") == 1
