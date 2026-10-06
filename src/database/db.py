"""SQLite database management and persistence layer."""

import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.database.models import ProcessedEmailRecord, ProcessingStatus


class DatabaseManager:
    """Thread-safe SQLite database manager for tracking processed invoice emails."""

    def __init__(self, db_path: str = "invoice_automation.db"):
        self.db_path = db_path
        self._lock = threading.Lock()
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        """Create and return a configured SQLite connection."""
        parent_dir = Path(self.db_path).parent
        if str(parent_dir) not in ("", "."):
            parent_dir.mkdir(parents=True, exist_ok=True)

        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        # Enable WAL mode for high concurrency and robustness
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        return conn

    def _init_db(self) -> None:
        """Initialize the database schema if not present and run migrations."""
        with self._lock:
            with self._get_connection() as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS processed_emails (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        message_id TEXT UNIQUE NOT NULL,
                        internet_message_id TEXT,
                        received_datetime TEXT,
                        sender TEXT,
                        subject TEXT,
                        invoice_group_address TEXT,
                        client_name TEXT,
                        om_code TEXT,
                        invoice_month TEXT,
                        invoice_year INTEGER,
                        month_folder TEXT,
                        attachment_name TEXT,
                        saved_filename TEXT,
                        target_filename TEXT,
                        sharepoint_path TEXT,
                        status TEXT NOT NULL,
                        error_message TEXT,
                        processed_at TEXT,
                        created_at TEXT NOT NULL
                    );
                    """
                )
                # Check for columns if table already existed without invoice_group_address
                cursor = conn.execute("PRAGMA table_info(processed_emails);")
                columns = {row["name"] for row in cursor.fetchall()}
                if "invoice_group_address" not in columns:
                    conn.execute("ALTER TABLE processed_emails ADD COLUMN invoice_group_address TEXT;")
                if "target_filename" not in columns:
                    conn.execute("ALTER TABLE processed_emails ADD COLUMN target_filename TEXT;")

                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_processed_emails_message_id ON processed_emails(message_id);"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_processed_emails_status ON processed_emails(status);"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_processed_emails_received ON processed_emails(received_datetime);"
                )
                conn.commit()

    def is_message_processed(self, message_id: str) -> bool:
        """Check if message_id has already been successfully processed or skipped.

        Messages that failed with SHAREPOINT_ERROR, PROCESSING_ERROR, or FAILED
        are allowed to be retried on subsequent cycles.
        """
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.execute(
                    """
                    SELECT id FROM processed_emails 
                    WHERE message_id = ? 
                    AND status NOT IN ('SHAREPOINT_ERROR', 'PROCESSING_ERROR', 'AUTHENTICATION_ERROR', 'FAILED')
                    """,
                    (message_id,),
                )
                return cursor.fetchone() is not None

    def record_email(self, record: ProcessedEmailRecord) -> None:
        """Insert or replace email processing record."""
        now_utc = datetime.now(timezone.utc).isoformat()
        processed_at = record.processed_at or now_utc
        created_at = record.created_at or now_utc
        target_file = record.target_filename or record.saved_filename
        saved_file = record.saved_filename or record.target_filename

        with self._lock:
            with self._get_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO processed_emails (
                        message_id, internet_message_id, received_datetime, sender,
                        subject, invoice_group_address, client_name, om_code,
                        invoice_month, invoice_year, month_folder, attachment_name,
                        saved_filename, target_filename, sharepoint_path,
                        status, error_message, processed_at, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(message_id) DO UPDATE SET
                        status = excluded.status,
                        invoice_group_address = coalesce(excluded.invoice_group_address, processed_emails.invoice_group_address),
                        client_name = coalesce(excluded.client_name, processed_emails.client_name),
                        om_code = coalesce(excluded.om_code, processed_emails.om_code),
                        invoice_month = coalesce(excluded.invoice_month, processed_emails.invoice_month),
                        invoice_year = coalesce(excluded.invoice_year, processed_emails.invoice_year),
                        month_folder = coalesce(excluded.month_folder, processed_emails.month_folder),
                        attachment_name = coalesce(excluded.attachment_name, processed_emails.attachment_name),
                        saved_filename = coalesce(excluded.saved_filename, processed_emails.saved_filename),
                        target_filename = coalesce(excluded.target_filename, processed_emails.target_filename),
                        sharepoint_path = coalesce(excluded.sharepoint_path, processed_emails.sharepoint_path),
                        error_message = excluded.error_message,
                        processed_at = excluded.processed_at;
                    """,
                    (
                        record.message_id,
                        record.internet_message_id,
                        record.received_datetime,
                        record.sender,
                        record.subject,
                        record.invoice_group_address,
                        record.client_name,
                        record.om_code,
                        record.invoice_month,
                        record.invoice_year,
                        record.month_folder,
                        record.attachment_name,
                        saved_file,
                        target_file,
                        record.sharepoint_path,
                        str(record.status),
                        record.error_message,
                        processed_at,
                        created_at,
                    ),
                )
                conn.commit()

    def get_processed_email(self, message_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a processed email record by message_id."""
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.execute(
                    "SELECT * FROM processed_emails WHERE message_id = ?",
                    (message_id,),
                )
                row = cursor.fetchone()
                return dict(row) if row else None

    def get_recent_emails(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get the most recently processed emails."""
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.execute(
                    "SELECT * FROM processed_emails ORDER BY id DESC LIMIT ?",
                    (limit,),
                )
                return [dict(row) for row in cursor.fetchall()]

    def count_by_status(self) -> Dict[str, int]:
        """Return counts of processed emails grouped by status."""
        with self._lock:
            with self._get_connection() as conn:
                cursor = conn.execute(
                    "SELECT status, COUNT(*) as cnt FROM processed_emails GROUP BY status"
                )
                return {row["status"]: row["cnt"] for row in cursor.fetchall()}
