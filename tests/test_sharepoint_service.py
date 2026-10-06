"""Unit tests for SharePoint service and folder resolution."""

from unittest.mock import MagicMock
from src.services.sharepoint_service import SharePointService


def test_resolve_target_folder_hierarchy():
    """Verify year, month, and O&M folders are ensured in live mode."""
    mock_client = MagicMock()
    mock_client.library_name = "Customer Invoicing"
    mock_client.root_folder = "Invoices"
    mock_client.get_drive_id.return_value = "drive-123"
    mock_client.get_root_invoices_folder_id.return_value = "root-folder-id"

    # Mock ensure_folder calls for year, month, and O&M folders
    mock_client.ensure_folder.side_effect = [
        {"id": "year-2026-id", "name": "2026"},
        {"id": "month-2608-id", "name": "2608"},
        {"id": "om-in091-id", "name": "IN-091"},
    ]

    service = SharePointService(mock_client, dry_run=False)
    drive_id, om_folder_id, full_path = service.resolve_target_folder(
        month_folder="2608",
        om_code="IN-091",
        invoice_year=2026,
    )

    assert drive_id == "drive-123"
    assert om_folder_id == "om-in091-id"
    assert full_path == "Customer Invoicing/Invoices/2026/2608/IN-091"

    # Ensure ensure_folder was called 3 times (year, month, om)
    assert mock_client.ensure_folder.call_count == 3
