"""Outlook operations via Microsoft Graph API."""

import base64
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Generator, List, Optional, Tuple

from src.graph.graph_client import GraphClient, GraphResourceNotFoundError

logger = logging.getLogger("invoice_automation.outlook")


class OutlookClient:
    """Handles mailbox monitoring, email inspection, and attachment retrieval."""

    def __init__(
        self,
        graph_client: GraphClient,
        processing_mailbox: str,
        invoice_group_address: str,
        timezone_name: str = "Asia/Kolkata",
    ):
        self.graph = graph_client
        self.processing_mailbox = processing_mailbox.strip().lower()
        self.invoice_group_address = invoice_group_address.strip().lower()
        self.timezone_name = timezone_name

    def calculate_cutoff_date(
        self,
        start_date: Optional[str] = None,
        today_only: bool = False,
        lookback_days: int = 30,
    ) -> str:
        """Calculate the UTC cutoff ISO string for email queries based on timezone."""
        try:
            from zoneinfo import ZoneInfo
            tz = ZoneInfo(self.timezone_name)
        except Exception:
            tz = datetime.now().astimezone().tzinfo or timezone.utc

        if start_date:
            clean_start = start_date.strip()
            if len(clean_start) == 10:  # Format YYYY-MM-DD
                dt = datetime.strptime(clean_start, "%Y-%m-%d").replace(tzinfo=tz)
                return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            else:
                try:
                    dt = datetime.fromisoformat(clean_start.replace("Z", "+00:00"))
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=tz)
                    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                except Exception:
                    return clean_start
        elif today_only:
            # Midnight today in configured timezone converted to UTC ISO format
            local_now = datetime.now(tz)
            midnight_today_local = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
            cutoff_utc = midnight_today_local.astimezone(timezone.utc)
            return cutoff_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
        else:
            return (datetime.now(timezone.utc) - timedelta(days=lookback_days)).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            )

    def check_mailbox_access(self) -> Tuple[bool, bool, Optional[str]]:
        """Verify that the processing mailbox is accessible and messages endpoint responds.

        Returns:
            Tuple of (mailbox_lookup_ok, messages_endpoint_ok, error_details)
        """
        # Test 1: Messages endpoint test (returns top 1 message or empty list)
        try:
            endpoint = f"users/{self.processing_mailbox}/messages"
            resp = self.graph.get(endpoint, params={"$top": "1", "$select": "id"})
            if resp.status_code == 200:
                return True, True, None
            return False, False, f"HTTP {resp.status_code}: {resp.text}"
        except GraphResourceNotFoundError as exc:
            return False, False, f"HTTP 404: Resource not found at users/{self.processing_mailbox}/messages"
        except Exception as exc:
            return False, False, str(exc)

    def get_messages(
        self,
        lookback_days: int = 30,
        top: int = 50,
        only_unread: bool = False,
        today_only: bool = False,
        start_date: Optional[str] = None,
    ) -> Generator[Dict[str, Any], None, None]:
        """Fetch incoming emails from the user's processing mailbox using query optimization.

        Yields messages matching the filter criteria.
        """
        endpoint = f"users/{self.processing_mailbox}/messages"

        # Calculate cutoff date
        cutoff_date = self.calculate_cutoff_date(
            start_date=start_date,
            today_only=today_only,
            lookback_days=lookback_days,
        )

        filter_clauses = [f"receivedDateTime ge {cutoff_date}"]
        if only_unread:
            filter_clauses.append("isRead eq false")

        params = {
            "$select": "id,internetMessageId,subject,receivedDateTime,from,toRecipients,ccRecipients,hasAttachments",
            "$filter": " and ".join(filter_clauses),
            "$orderby": "receivedDateTime desc",
            "$top": str(top),
        }

        logger.info(
            "Querying messages for processing mailbox %s (Filter: %s)",
            self.processing_mailbox,
            params["$filter"],
        )

        for message in self.graph.paginate(endpoint, params=params):
            # Defensive check: ensure message receivedDateTime is on or after cutoff
            msg_received = message.get("receivedDateTime")
            if msg_received and cutoff_date and msg_received < cutoff_date:
                logger.debug(
                    "Skipping message %s received at %s (prior to cutoff %s)",
                    message.get("id"),
                    msg_received,
                    cutoff_date,
                )
                continue
            yield message

    def is_target_recipient(self, message: Dict[str, Any]) -> bool:
        """Validate whether the invoice group address appears in 'To' or 'CC' list.

        Case-insensitive and whitespace tolerant.
        """
        target = self.invoice_group_address.strip().lower()
        if not target:
            return False

        # Check To Recipients
        to_recipients = message.get("toRecipients", [])
        for recipient in to_recipients:
            addr = recipient.get("emailAddress", {}).get("address", "").strip().lower()
            if addr == target:
                return True

        # Check CC Recipients
        cc_recipients = message.get("ccRecipients", [])
        for recipient in cc_recipients:
            addr = recipient.get("emailAddress", {}).get("address", "").strip().lower()
            if addr == target:
                return True

        return False

    def get_attachments(self, message_id: str) -> List[Dict[str, Any]]:
        """Retrieve all attachment metadata for a given message from processing mailbox."""
        endpoint = f"users/{self.processing_mailbox}/messages/{message_id}/attachments"
        resp = self.graph.get(endpoint)
        data = resp.json()
        return data.get("value", [])

    def download_attachment_bytes(self, message_id: str, attachment: Dict[str, Any]) -> bytes:
        """Download binary content of an email attachment from processing mailbox.

        Extracts from base64 contentBytes if present, otherwise requests /$value.
        """
        # If contentBytes is already embedded in the attachment object
        if "contentBytes" in attachment and attachment["contentBytes"]:
            return base64.b64decode(attachment["contentBytes"])

        attachment_id = attachment.get("id")
        if not attachment_id:
            raise ValueError(f"Attachment has no valid ID: {attachment}")

        # Fallback to direct raw content download
        endpoint = f"users/{self.processing_mailbox}/messages/{message_id}/attachments/{attachment_id}/$value"
        resp = self.graph.get(endpoint)
        return resp.content
