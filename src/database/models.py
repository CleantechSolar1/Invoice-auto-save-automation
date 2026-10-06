"""Data models and status enums for invoice processing."""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class ProcessingStatus(str, Enum):
    """Standardized processing statuses for audited email processing."""

    PROCESSED = "PROCESSED"
    SUCCESS = "SUCCESS"
    DUPLICATE = "DUPLICATE"
    SKIPPED = "SKIPPED"
    SKIPPED_RECIPIENT = "SKIPPED_RECIPIENT"
    SKIPPED_SUBJECT = "SKIPPED_SUBJECT"
    FAILED = "FAILED"
    INVALID_PERIOD = "INVALID_PERIOD"
    INVALID_OM_CODE = "INVALID_OM_CODE"
    NO_PDF = "NO_PDF"
    SHAREPOINT_ERROR = "SHAREPOINT_ERROR"
    AUTHENTICATION_ERROR = "AUTHENTICATION_ERROR"
    PROCESSING_ERROR = "PROCESSING_ERROR"


@dataclass
class ProcessedEmailRecord:
    """Represents a row in the processed_emails table."""

    message_id: str
    status: str
    internet_message_id: Optional[str] = None
    received_datetime: Optional[str] = None
    sender: Optional[str] = None
    subject: Optional[str] = None
    invoice_group_address: Optional[str] = None
    client_name: Optional[str] = None
    om_code: Optional[str] = None
    invoice_month: Optional[str] = None
    invoice_year: Optional[int] = None
    month_folder: Optional[str] = None
    attachment_name: Optional[str] = None
    saved_filename: Optional[str] = None
    target_filename: Optional[str] = None
    sharepoint_path: Optional[str] = None
    error_message: Optional[str] = None
    processed_at: Optional[str] = None
    created_at: Optional[str] = None
    id: Optional[int] = None
