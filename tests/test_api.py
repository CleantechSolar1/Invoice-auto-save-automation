"""Test Vercel serverless HTTP handler."""

import json
from io import BytesIO
from unittest.mock import MagicMock, patch

from api.index import handler


def test_api_health_endpoint():
    """Verify /health endpoint returns HTTP 200 with JSON status."""
    mock_request = MagicMock()
    mock_request.makefile.return_value = BytesIO(b"GET /health HTTP/1.1\r\nHost: localhost\r\n\r\n")

    wfile = BytesIO()

    with patch.object(handler, "setup"):
        with patch.object(handler, "finish"):
            h = handler.__new__(handler)
            h.requestline = "GET /health HTTP/1.1"
            h.command = "GET"
            h.path = "/health"
            h.request_version = "HTTP/1.1"
            h.headers = {}
            h.rfile = BytesIO()
            h.wfile = wfile

            h.do_GET()

    output = wfile.getvalue().decode("utf-8")
    assert "200 OK" in output or "status" in output
    assert "healthy" in output


@patch("api.index.InvoiceAutomationService")
def test_api_run_cycle_endpoint(mock_service_class):
    """Verify default endpoint triggers process_cycle and returns JSON."""
    mock_service_instance = MagicMock()
    mock_service_instance.process_cycle.return_value = {"SUCCESS": 1}
    mock_service_class.return_value = mock_service_instance

    wfile = BytesIO()

    h = handler.__new__(handler)
    h.requestline = "GET /?dry_run=true HTTP/1.1"
    h.command = "GET"
    h.path = "/?dry_run=true"
    h.request_version = "HTTP/1.1"
    h.headers = {}
    h.rfile = BytesIO()
    h.wfile = wfile

    h.do_GET()

    output = wfile.getvalue().decode("utf-8")
    assert "success" in output
    assert "SUCCESS" in output
