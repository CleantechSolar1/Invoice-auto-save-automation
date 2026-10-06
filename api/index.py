"""Vercel Serverless Function & Local Development WSGI Handler."""

import json
import logging
import os
import sys
from pathlib import Path
from urllib.parse import parse_qs

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import settings
from src.services.invoice_service import InvoiceAutomationService

logger = logging.getLogger("invoice_automation.api")


def app(environ, start_response):
    """Standard WSGI application interface for Vercel and WSGI servers."""
    path = environ.get("PATH_INFO", "/")
    query_string = environ.get("QUERY_STRING", "")
    method = environ.get("REQUEST_METHOD", "GET")
    params = parse_qs(query_string)

    # Health check endpoint
    if path.rstrip("/") in ("/health", "/api/health"):
        data = {
            "status": "healthy",
            "service": "Cleantech Invoice Automation",
            "timezone": settings.app_timezone,
            "filter_start_date": settings.filter_start_date,
            "process_today_only": settings.process_today_only,
        }
        return _json_response(200, data, start_response)

    dry_run = params.get("dry_run", ["false"])[0].lower() in ("1", "true", "yes")

    try:
        # Check for missing required environment variables on serverless environments
        missing_vars = []
        if not settings.tenant_id:
            missing_vars.append("TENANT_ID")
        if not settings.client_id:
            missing_vars.append("CLIENT_ID")
        if not settings.client_secret:
            missing_vars.append("CLIENT_SECRET")
        if not settings.processing_mailbox:
            missing_vars.append("PROCESSING_MAILBOX")
        if not settings.invoice_group_address:
            missing_vars.append("INVOICE_GROUP_ADDRESS")

        if missing_vars and not dry_run:
            data = {
                "status": "configuration_required",
                "service": "Cleantech Invoice Automation",
                "message": "Service is deployed, but required environment variables are not configured in Vercel.",
                "missing_variables": missing_vars,
                "instructions": "Please configure these environment variables in your Vercel Project Settings (Settings -> Environment Variables) and redeploy.",
            }
            return _json_response(200, data, start_response)

        if dry_run:
            settings.dry_run = True

        # Execute single processing cycle
        service = InvoiceAutomationService(config=settings)
        stats = service.process_cycle()

        response_data = {
            "status": "success",
            "message": "Cleantech invoice automation cycle completed",
            "dry_run": settings.dry_run,
            "mailbox": settings.processing_mailbox,
            "invoice_group": settings.invoice_group_address,
            "date_filter": (
                f"From {settings.filter_start_date} onwards ({settings.app_timezone})"
                if settings.filter_start_date
                else f"Today only ({settings.app_timezone})"
            ),
            "results": stats,
        }
        return _json_response(200, response_data, start_response)

    except Exception as exc:
        logger.error("Error executing serverless request: %s", exc, exc_info=True)
        data = {
            "status": "error",
            "error": str(exc),
            "type": exc.__class__.__name__,
        }
        return _json_response(500, data, start_response)


def _json_response(status_code: int, data: dict, start_response):
    status_text = {
        200: "200 OK",
        400: "400 Bad Request",
        404: "404 Not Found",
        500: "500 Internal Server Error",
    }.get(status_code, f"{status_code} Unknown")

    body = json.dumps(data, indent=2).encode("utf-8")
    headers = [
        ("Content-Type", "application/json"),
        ("Content-Length", str(len(body))),
        ("Access-Control-Allow-Origin", "*"),
    ]
    start_response(status_text, headers)
    return [body]


# Aliases for various deployment runners
handler = app
application = app


if __name__ == "__main__":
    from wsgiref.simple_server import make_server

    port = int(os.environ.get("PORT", 8000))
    print("=" * 60)
    print("Cleantech Invoice Automation - Local Web Server")
    print("=" * 60)
    print(f"Local Server running at: http://localhost:{port}")
    print(f"Health Check URL:        http://localhost:{port}/health")
    print(f"Run Cycle URL:           http://localhost:{port}/")
    print(f"Dry-Run Cycle URL:       http://localhost:{port}/?dry_run=true")
    print("=" * 60)
    with make_server("0.0.0.0", port, app) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nServer stopped.")
