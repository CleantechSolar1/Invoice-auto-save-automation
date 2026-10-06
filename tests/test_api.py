"""Test Vercel serverless WSGI HTTP handler."""

import json
from unittest.mock import MagicMock, patch

from api.index import app


def test_api_health_endpoint():
    """Verify /health endpoint returns HTTP 200 with JSON status."""
    environ = {
        "PATH_INFO": "/health",
        "REQUEST_METHOD": "GET",
        "QUERY_STRING": "",
    }
    status_captured = []
    headers_captured = []

    def start_response(status, headers):
        status_captured.append(status)
        headers_captured.append(headers)

    response = app(environ, start_response)
    body = b"".join(response).decode("utf-8")
    data = json.loads(body)

    assert status_captured[0] == "200 OK"
    assert data["status"] == "healthy"
    assert data["service"] == "Cleantech Invoice Automation"


@patch("api.index.InvoiceAutomationService")
def test_api_run_cycle_endpoint(mock_service_class):
    """Verify default endpoint triggers process_cycle and returns JSON."""
    mock_service_instance = MagicMock()
    mock_service_instance.process_cycle.return_value = {"SUCCESS": 1}
    mock_service_class.return_value = mock_service_instance

    environ = {
        "PATH_INFO": "/",
        "REQUEST_METHOD": "GET",
        "QUERY_STRING": "dry_run=true",
    }
    status_captured = []
    headers_captured = []

    def start_response(status, headers):
        status_captured.append(status)
        headers_captured.append(headers)

    response = app(environ, start_response)
    body = b"".join(response).decode("utf-8")
    data = json.loads(body)

    assert status_captured[0] == "200 OK"
    assert data["status"] == "success"
    assert data["results"]["SUCCESS"] == 1
