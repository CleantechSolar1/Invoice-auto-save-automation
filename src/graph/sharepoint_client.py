"""SharePoint operations via Microsoft Graph API."""

import io
import logging
from typing import Any, Dict, List, Optional

from src.graph.graph_client import GraphAPIError, GraphClient, GraphResourceNotFoundError
from src.utils.filename import sanitize_sharepoint_name

logger = logging.getLogger("invoice_automation.sharepoint")


class SharePointClient:
    """Manages SharePoint site, library, folder hierarchy resolution, and file uploads."""

    def __init__(
        self,
        graph_client: GraphClient,
        hostname: str,
        site_path: str,
        library_name: str,
        root_folder: str = "Invoices",
    ):
        self.graph = graph_client
        self.hostname = hostname.strip().lower()
        self.site_path = site_path.strip()
        if not self.site_path.startswith("/"):
            self.site_path = "/" + self.site_path
        self.library_name = library_name.strip()
        self.root_folder = sanitize_sharepoint_name(root_folder.strip())

        # Cached resolved IDs
        self._site_id: Optional[str] = None
        self._drive_id: Optional[str] = None
        self._root_folder_id: Optional[str] = None

    def get_site(self) -> Dict[str, Any]:
        """Resolve SharePoint site using hostname and site path.

        Endpoint: /v1.0/sites/{hostname}:{site_path}
        """
        endpoint = f"sites/{self.hostname}:{self.site_path}"
        logger.debug("Resolving SharePoint site at %s", endpoint)
        resp = self.graph.get(endpoint)
        site_data = resp.json()
        self._site_id = site_data.get("id")
        logger.info("Resolved SharePoint Site ID: %s", self._site_id)
        return site_data

    def get_site_id(self) -> str:
        """Return cached site ID or resolve dynamically."""
        if not self._site_id:
            self.get_site()
        return self._site_id  # type: ignore

    def get_drive(self) -> Dict[str, Any]:
        """Resolve Document Library (Drive) by name inside the site.

        Endpoint: /v1.0/sites/{site_id}/drives
        """
        site_id = self.get_site_id()
        endpoint = f"sites/{site_id}/drives"
        logger.debug("Searching for document library '%s' in site %s", self.library_name, site_id)

        target_name = self.library_name.lower()
        for drive in self.graph.paginate(endpoint):
            if drive.get("name", "").strip().lower() == target_name:
                self._drive_id = drive.get("id")
                logger.info(
                    "Resolved Document Library '%s' -> Drive ID: %s",
                    self.library_name,
                    self._drive_id,
                )
                return drive

        raise GraphAPIError(
            f"Document library '{self.library_name}' not found on SharePoint site {self.hostname}:{self.site_path}"
        )

    def get_drive_id(self) -> str:
        """Return cached drive ID or resolve dynamically."""
        if not self._drive_id:
            self.get_drive()
        return self._drive_id  # type: ignore

    def get_item_by_path(self, drive_id: str, item_path: str) -> Optional[Dict[str, Any]]:
        """Retrieve a driveItem by its relative path within the drive."""
        clean_path = item_path.strip("/")
        endpoint = f"drives/{drive_id}/root:/{clean_path}:"
        try:
            resp = self.graph.get(endpoint)
            return resp.json()
        except GraphResourceNotFoundError:
            return None

    def get_root_invoices_folder(self) -> Dict[str, Any]:
        """Resolve or create the root Invoices folder in the document library."""
        drive_id = self.get_drive_id()
        folder = self.get_item_by_path(drive_id, self.root_folder)
        if folder:
            self._root_folder_id = folder.get("id")
            return folder

        # Create root folder if missing
        logger.info("Root folder '%s' not found. Creating it...", self.root_folder)
        folder = self.create_folder_under_parent(drive_id, parent_item_id="root", folder_name=self.root_folder)
        self._root_folder_id = folder.get("id")
        return folder

    def get_root_invoices_folder_id(self) -> str:
        """Return cached root Invoices folder ID or resolve."""
        if not self._root_folder_id:
            self.get_root_invoices_folder()
        return self._root_folder_id  # type: ignore

    def get_child_folder(self, drive_id: str, parent_item_id: str, folder_name: str) -> Optional[Dict[str, Any]]:
        """Check if a subfolder exists directly under a parent item."""
        clean_name = sanitize_sharepoint_name(folder_name).lower()
        endpoint = f"drives/{drive_id}/items/{parent_item_id}/children"
        for item in self.graph.paginate(endpoint):
            if "folder" in item and item.get("name", "").strip().lower() == clean_name:
                return item
        return None

    def create_folder_under_parent(
        self,
        drive_id: str,
        parent_item_id: str,
        folder_name: str,
    ) -> Dict[str, Any]:
        """Create a folder under a parent item.

        Idempotent: if created concurrently or already exists, returns existing folder.
        """
        clean_name = sanitize_sharepoint_name(folder_name)
        endpoint = f"drives/{drive_id}/items/{parent_item_id}/children"
        body = {
            "name": clean_name,
            "folder": {},
            "@microsoft.graph.conflictBehavior": "fail",
        }

        try:
            resp = self.graph.post(endpoint, json_data=body)
            created = resp.json()
            logger.info("Created folder '%s' (ID: %s) under %s", clean_name, created.get("id"), parent_item_id)
            return created
        except GraphAPIError as exc:
            # Check if failure is due to conflict (already exists)
            if exc.status_code == 409 or (exc.response_body and "nameAlreadyExists" in exc.response_body):
                logger.info("Folder '%s' already exists under %s (concurrency handled)", clean_name, parent_item_id)
                existing = self.get_child_folder(drive_id, parent_item_id, clean_name)
                if existing:
                    return existing
            raise

    def ensure_folder(
        self,
        drive_id: str,
        parent_item_id: str,
        folder_name: str,
    ) -> Dict[str, Any]:
        """Ensure a folder exists under parent. If it exists, returns it; otherwise creates it."""
        clean_name = sanitize_sharepoint_name(folder_name)
        existing = self.get_child_folder(drive_id, parent_item_id, clean_name)
        if existing:
            return existing
        return self.create_folder_under_parent(drive_id, parent_item_id, clean_name)

    def file_exists_in_folder(self, drive_id: str, folder_id: str, filename: str) -> bool:
        """Check if a file with the given name exists in the specified folder."""
        clean_name = sanitize_sharepoint_name(filename).lower()
        endpoint = f"drives/{drive_id}/items/{folder_id}/children"
        for item in self.graph.paginate(endpoint):
            if "file" in item and item.get("name", "").strip().lower() == clean_name:
                return True
        return False

    def upload_file(
        self,
        drive_id: str,
        folder_id: str,
        filename: str,
        file_bytes: bytes,
    ) -> Dict[str, Any]:
        """Upload file content into the target folder.

        Uses simple PUT for files <= 4MB, and upload session for larger files.
        """
        import urllib.parse

        clean_name = sanitize_sharepoint_name(filename)
        encoded_name = urllib.parse.quote(clean_name)
        size = len(file_bytes)

        # Simple upload for files <= 4MB (4 * 1024 * 1024 bytes)
        if size <= 4 * 1024 * 1024:
            endpoint = f"drives/{drive_id}/items/{folder_id}:/{encoded_name}:/content?@microsoft.graph.conflictBehavior=fail"
            headers = {
                "Content-Type": "application/pdf",
            }
            resp = self.graph.put(endpoint, data=file_bytes, headers=headers)
            uploaded_item = resp.json()
            logger.info("Uploaded '%s' (%d bytes) successfully. Item ID: %s", clean_name, size, uploaded_item.get("id"))
            return uploaded_item

        # Large file chunked upload via Upload Session
        logger.info("File '%s' size is %d bytes (>4MB). Creating upload session...", clean_name, size)
        session_endpoint = f"drives/{drive_id}/items/{folder_id}:/{encoded_name}:/createUploadSession"
        session_body = {
            "item": {
                "@microsoft.graph.conflictBehavior": "fail",
                "name": clean_name,
            }
        }
        session_resp = self.graph.post(session_endpoint, json_data=session_body)
        upload_url = session_resp.json().get("uploadUrl")
        if not upload_url:
            raise GraphAPIError(f"Failed to create upload session for {clean_name}")

        chunk_size = 320 * 1024 * 10  # 3.2 MB chunks (must be multiple of 320 KiB)
        bytes_io = io.BytesIO(file_bytes)
        offset = 0

        while offset < size:
            chunk = bytes_io.read(chunk_size)
            chunk_length = len(chunk)
            range_header = f"bytes {offset}-{offset + chunk_length - 1}/{size}"
            headers = {
                "Content-Range": range_header,
                "Content-Length": str(chunk_length),
            }
            chunk_resp = self.graph.put(upload_url, data=chunk, headers=headers)
            offset += chunk_length
            if chunk_resp.status_code in (200, 201):
                logger.info("Upload session completed for '%s'.", clean_name)
                return chunk_resp.json()

        raise GraphAPIError(f"Upload session ended unexpectedly for {clean_name}")
