"""High-level SharePoint filing service."""

import logging
from typing import Any, Dict, Optional, Tuple

from src.graph.sharepoint_client import SharePointClient

logger = logging.getLogger("invoice_automation.sharepoint_service")


class SharePointService:
    """Orchestrates folder hierarchy resolution, duplicate detection, and file uploads."""

    def __init__(self, sharepoint_client: SharePointClient, dry_run: bool = False):
        self.client = sharepoint_client
        self.dry_run = dry_run

    def resolve_target_folder(
        self,
        month_folder: str,
        om_code: str,
        invoice_year: Optional[int] = None,
    ) -> Tuple[Optional[str], Optional[str], str]:
        """Ensure year folder (YYYY), month folder (YYMM) and O&M folder (IN-xxx) exist under root Invoices.

        Returns:
            Tuple of (drive_id, om_folder_id, sharepoint_full_path)
            In dry-run mode, om_folder_id may be None if folders do not exist.
        """
        # Determine 4-digit year for year folder (e.g. 2026)
        year_str = str(invoice_year) if invoice_year else None
        if not year_str and len(month_folder) == 4 and month_folder[:2].isdigit():
            year_str = f"20{month_folder[:2]}"

        if year_str:
            full_path = f"{self.client.library_name}/{self.client.root_folder}/{year_str}/{month_folder}/{om_code}"
        else:
            full_path = f"{self.client.library_name}/{self.client.root_folder}/{month_folder}/{om_code}"

        if self.dry_run:
            logger.info("DRY RUN: Target SharePoint folder would be: %s", full_path)
            try:
                drive_id = self.client.get_drive_id()
                root_id = self.client.get_root_invoices_folder_id()

                parent_id = root_id
                # Check year folder if applicable
                if year_str:
                    year_item = self.client.get_child_folder(drive_id, parent_id, year_str)
                    if not year_item:
                        logger.info("DRY RUN: Would create folder: %s", year_str)
                        logger.info("DRY RUN: Would create folder: %s", month_folder)
                        logger.info("DRY RUN: Would create folder: %s", om_code)
                        return drive_id, None, full_path
                    parent_id = year_item["id"]

                # Check month folder
                month_item = self.client.get_child_folder(drive_id, parent_id, month_folder)
                if not month_item:
                    logger.info("DRY RUN: Would create folder: %s", month_folder)
                    logger.info("DRY RUN: Would create folder: %s", om_code)
                    return drive_id, None, full_path

                logger.info("DRY RUN: Month folder '%s' exists", month_folder)
                om_item = self.client.get_child_folder(drive_id, month_item["id"], om_code)
                if not om_item:
                    logger.info("DRY RUN: Would create folder: %s", om_code)
                    return drive_id, None, full_path

                logger.info("DRY RUN: O&M folder '%s' exists", om_code)
                return drive_id, om_item["id"], full_path
            except Exception as exc:
                logger.warning("DRY RUN: SharePoint inspection skipped or failed (%s). Continuing dry run...", exc)
                return None, None, full_path

        # Live run: resolve drive and root invoices folder
        drive_id = self.client.get_drive_id()
        root_id = self.client.get_root_invoices_folder_id()

        parent_id = root_id
        # Step 1: Ensure Year folder (YYYY) exists if year is provided
        if year_str:
            year_item = self.client.ensure_folder(drive_id, parent_id, year_str)
            parent_id = year_item["id"]

        # Step 2: Ensure month folder (YYMM) exists inside year folder
        month_item = self.client.ensure_folder(drive_id, parent_id, month_folder)
        month_id = month_item["id"]

        # Step 3: Ensure O&M folder exists inside month folder
        om_item = self.client.ensure_folder(drive_id, month_id, om_code)
        om_folder_id = om_item["id"]

        return drive_id, om_folder_id, full_path

    def check_duplicate_file(
        self,
        drive_id: Optional[str],
        folder_id: Optional[str],
        filename: str,
    ) -> bool:
        """Check if filename already exists in the target folder."""
        if not drive_id or not folder_id:
            return False
        return self.client.file_exists_in_folder(drive_id, folder_id, filename)

    def upload_invoice_pdf(
        self,
        drive_id: Optional[str],
        folder_id: Optional[str],
        filename: str,
        pdf_bytes: bytes,
        target_path: str,
    ) -> Optional[Dict[str, Any]]:
        """Upload invoice PDF to the designated SharePoint folder."""
        if self.dry_run:
            logger.info("DRY RUN: Would upload:\n%s to %s", filename, target_path)
            return {"dry_run": True, "filename": filename, "path": target_path}

        if not drive_id or not folder_id:
            raise ValueError("Cannot upload file: drive_id or folder_id is missing")

        return self.client.upload_file(drive_id, folder_id, filename, pdf_bytes)
