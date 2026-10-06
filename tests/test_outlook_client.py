"""Unit tests for Outlook client with separate processing mailbox and invoice group."""

from unittest.mock import MagicMock
from src.graph.outlook_client import OutlookClient


def test_graph_endpoint_uses_processing_mailbox_not_invoice_group():
    """Verify Graph calls users/{PROCESSING_MAILBOX}/messages and never the group address."""
    mock_graph = MagicMock()
    mock_graph.paginate.return_value = iter([])

    client = OutlookClient(
        graph_client=mock_graph,
        processing_mailbox="surojit@cleantechsolar.com",
        invoice_group_address="india.invoicing@cleantechsolar.com",
    )

    list(client.get_messages(lookback_days=10))

    mock_graph.paginate.assert_called_once()
    called_endpoint = mock_graph.paginate.call_args[0][0]

    # Verify endpoint is Surojit's mailbox
    assert called_endpoint == "users/surojit@cleantechsolar.com/messages"
    assert "india.invoicing@cleantechsolar.com" not in called_endpoint


def test_recipient_validation_in_to():
    """Verify target address in To field is accepted with varied casing and whitespace."""
    mock_graph = MagicMock()
    client = OutlookClient(
        mock_graph,
        processing_mailbox="surojit@cleantechsolar.com",
        invoice_group_address="india.invoicing@cleantechsolar.com",
    )

    # Lowercase
    msg1 = {"toRecipients": [{"emailAddress": {"address": "india.invoicing@cleantechsolar.com"}}]}
    assert client.is_target_recipient(msg1)

    # Title Case
    msg2 = {"toRecipients": [{"emailAddress": {"address": "India.Invoicing@cleantechsolar.com"}}]}
    assert client.is_target_recipient(msg2)

    # Upper Case
    msg3 = {"toRecipients": [{"emailAddress": {"address": "INDIA.INVOICING@CLEANTECHSOLAR.COM"}}]}
    assert client.is_target_recipient(msg3)

    # Mixed Case
    msg4 = {"toRecipients": [{"emailAddress": {"address": "India.Invoicing@CleantechSolar.com"}}]}
    assert client.is_target_recipient(msg4)

    # Whitespace padded
    msg5 = {"toRecipients": [{"emailAddress": {"address": "  india.invoicing@cleantechsolar.com  "}}]}
    assert client.is_target_recipient(msg5)


def test_recipient_validation_in_cc():
    """Verify target address in CC field is accepted."""
    mock_graph = MagicMock()
    client = OutlookClient(
        mock_graph,
        processing_mailbox="surojit@cleantechsolar.com",
        invoice_group_address="india.invoicing@cleantechsolar.com",
    )

    msg = {
        "toRecipients": [{"emailAddress": {"address": "surojit@cleantechsolar.com"}}],
        "ccRecipients": [{"emailAddress": {"address": "india.invoicing@cleantechsolar.com"}}],
    }
    assert client.is_target_recipient(msg)


def test_recipient_validation_skipped_when_absent():
    """Verify when target invoice group address is not present in To/CC, returns False."""
    mock_graph = MagicMock()
    client = OutlookClient(
        mock_graph,
        processing_mailbox="surojit@cleantechsolar.com",
        invoice_group_address="india.invoicing@cleantechsolar.com",
    )

    msg = {
        "toRecipients": [{"emailAddress": {"address": "another@example.com"}}],
        "ccRecipients": [{"emailAddress": {"address": "another@example.com"}}],
    }
    assert not client.is_target_recipient(msg)


def test_get_messages_today_only_filter():
    """Verify today_only generates a filter matching today's midnight timestamp."""
    from datetime import datetime
    mock_graph = MagicMock()
    mock_graph.paginate.return_value = iter([])

    client = OutlookClient(
        mock_graph,
        processing_mailbox="surojit@cleantechsolar.com",
        invoice_group_address="india.invoicing@cleantechsolar.com",
    )

    list(client.get_messages(today_only=True))

    mock_graph.paginate.assert_called_once()
    called_params = mock_graph.paginate.call_args[1]["params"]
    filter_expr = called_params["$filter"]

    assert "receivedDateTime ge" in filter_expr
    # Verify current year is in the filter expression
    current_year = str(datetime.now().year)
    assert current_year in filter_expr


def test_calculate_cutoff_date_start_date_asia_kolkata():
    """Verify start_date '2026-10-06' maps to 2026-10-05T18:30:00Z in Asia/Kolkata."""
    mock_graph = MagicMock()
    client = OutlookClient(
        mock_graph,
        processing_mailbox="surojit@cleantechsolar.com",
        invoice_group_address="india.invoicing@cleantechsolar.com",
        timezone_name="Asia/Kolkata",
    )
    cutoff = client.calculate_cutoff_date(start_date="2026-10-06")
    assert cutoff == "2026-10-05T18:30:00Z"


def test_defensive_cutoff_filtering_in_get_messages():
    """Verify messages prior to cutoff date are defensively skipped."""
    mock_graph = MagicMock()
    # Message 1 is yesterday (5th Oct 2026), Message 2 is today (6th Oct 2026)
    mock_graph.paginate.return_value = iter([
        {"id": "msg-yesterday", "receivedDateTime": "2026-10-05T11:58:24Z"},
        {"id": "msg-today", "receivedDateTime": "2026-10-06T06:00:00Z"},
    ])

    client = OutlookClient(
        mock_graph,
        processing_mailbox="surojit@cleantechsolar.com",
        invoice_group_address="india.invoicing@cleantechsolar.com",
        timezone_name="Asia/Kolkata",
    )

    results = list(client.get_messages(start_date="2026-10-06"))
    assert len(results) == 1
    assert results[0]["id"] == "msg-today"

