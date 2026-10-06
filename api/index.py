"""Vercel Serverless Function & Local Development HTTP Handler."""

import json
import logging
import os
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import settings
from src.services.invoice_service import InvoiceAutomationService

logger = logging.getLogger("invoice_automation.api")


class handler(BaseHTTPRequestHandler):
    """Vercel serverless HTTP request handler."""

    def do_GET(self):
        parsed_url = urlparse(self.path)
        params = parse_qs(parsed_url.query)
        path = parsed_url.path

        # Health check endpoint
        if path.rstrip("/") in ("/health", "/api/health"):
            self._send_json(200, {
                "status": "healthy",
                "service": "Cleantech Invoice Automation",
                "timezone": settings.app_timezone,
                "filter_start_date": settings.filter_start_date,
                "process_today_only": settings.process_today_only,
            })
            return

        # Determine dry_run from query parameter
        dry_run = params.get("dry_run", ["false"])[0].lower() in ("1", "true", "yes")

        try:
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
            self._send_json(200, response_data)

        except Exception as exc:
            self._send_json(500, {
                "status": "error",
                "error": str(exc),
            })

    def do_POST(self):
        """Handle POST triggers (e.g. webhooks, GitHub Actions, or cron callers)."""
        self.do_GET()

    def _send_json(self, status_code: int, data: dict):
        body = json.dumps(data, indent=2).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        # Clean logging output
        sys.stderr.write(f"[{self.log_date_time_string()}] {format % args}\n")


# Alias app and application for WSGI/ASGI platform inspectors
app = handler
application = handler


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    print("=" * 60)
    print("Cleantech Invoice Automation - Local Web Server")
    print("=" * 60)
    print(f"Local Server running at: http://localhost:{port}")
    print(f"Health Check URL:        http://localhost:{port}/health")
    print(f"Run Cycle URL:           http://localhost:{port}/")
    print(f"Dry-Run Cycle URL:       http://localhost:{port}/?dry_run=true")
    print("=" * 60)
    server = HTTPServer(("0.0.0.0", port), handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")
