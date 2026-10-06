"""Vercel Serverless Function & Local Development WSGI Handler with Live UI Dashboard."""

import html
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Safe environment overrides for serverless
if os.environ.get("VERCEL") or os.environ.get("AWS_LAMBDA_FUNCTION_NAME"):
    os.environ["DATABASE_PATH"] = "/tmp/invoice_automation.db"
    os.environ["LOG_FILE_PATH"] = "/tmp/invoice_automation.log"

from src.config import settings
from src.database.db import DatabaseManager
from src.services.invoice_service import InvoiceAutomationService

logger = logging.getLogger("invoice_automation.api")


def app(environ, start_response):
    """Standard WSGI application interface for Vercel and local development."""
    path = environ.get("PATH_INFO", "/")
    query_string = environ.get("QUERY_STRING", "")
    method = environ.get("REQUEST_METHOD", "GET")
    accept_header = environ.get("HTTP_ACCEPT", "")
    params = parse_qs(query_string)

    # Health check endpoint
    if path.rstrip("/") in ("/health", "/api/health"):
        data = {
            "status": "healthy",
            "service": "Cleantech Invoice Automation",
            "timezone": settings.app_timezone,
            "filter_start_date": settings.filter_start_date,
            "process_today_only": settings.process_today_only,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        return _json_response(200, data, start_response)

    dry_run = params.get("dry_run", ["false"])[0].lower() in ("1", "true", "yes")
    force_html = params.get("format", [""])[0].lower() == "html"
    force_json = params.get("format", [""])[0].lower() == "json"
    is_browser_request = (force_html or "text/html" in accept_header) and not force_json
    should_run_cycle = params.get("run", ["true"])[0].lower() in ("1", "true", "yes")

    # Verify critical environment variables
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
        config_data = {
            "status": "configuration_required",
            "service": "Cleantech Invoice Automation",
            "message": "Service is deployed, but required environment variables are not configured.",
            "missing_variables": missing_vars,
            "instructions": "Please configure these in Vercel Project Settings (Settings -> Environment Variables) and redeploy.",
        }
        if not is_browser_request:
            return _json_response(200, config_data, start_response)
        return _html_response(200, _render_config_needed_html(config_data), start_response)

    stats = {}
    error_msg = None
    recent_records = []

    try:
        if dry_run:
            settings.dry_run = True

        service = InvoiceAutomationService(config=settings)

        if should_run_cycle:
            stats = service.process_cycle()

        # Retrieve recent processed records for UI
        try:
            recent_records = service.db.get_recent_emails(limit=25)
        except Exception:
            recent_records = []

        response_data = {
            "status": "success",
            "message": "Cleantech invoice automation cycle completed",
            "dry_run": settings.dry_run,
            "mailbox": settings.processing_mailbox,
            "invoice_group": settings.invoice_group_address,
            "sharepoint_target": f"{settings.sharepoint_library_name}/{settings.sharepoint_root_folder}",
            "date_filter": (
                f"From {settings.filter_start_date} onwards ({settings.app_timezone})"
                if settings.filter_start_date
                else f"Today only ({settings.app_timezone})"
            ),
            "results": stats,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        if not is_browser_request:
            return _json_response(200, response_data, start_response)

        html_content = _render_dashboard_html(response_data, recent_records)
        return _html_response(200, html_content, start_response)

    except Exception as exc:
        logger.error("Error executing serverless request: %s", exc, exc_info=True)
        err_data = {
            "status": "error",
            "error": str(exc),
            "type": exc.__class__.__name__,
            "mailbox": settings.processing_mailbox,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        if not is_browser_request:
            return _json_response(500, err_data, start_response)
        return _html_response(500, _render_error_html(err_data), start_response)


def _json_response(status_code: int, data: dict, start_response):
    status_text = {
        200: "200 OK",
        400: "400 Bad Request",
        404: "404 Not Found",
        500: "500 Internal Server Error",
    }.get(status_code, f"{status_code} Unknown")

    body = json.dumps(data, indent=2).encode("utf-8")
    headers = [
        ("Content-Type", "application/json; charset=utf-8"),
        ("Content-Length", str(len(body))),
        ("Access-Control-Allow-Origin", "*"),
    ]
    start_response(status_text, headers)
    return [body]


def _html_response(status_code: int, html_str: str, start_response):
    status_text = {
        200: "200 OK",
        400: "400 Bad Request",
        500: "500 Internal Server Error",
    }.get(status_code, f"{status_code} Unknown")

    body = html_str.encode("utf-8")
    headers = [
        ("Content-Type", "text/html; charset=utf-8"),
        ("Content-Length", str(len(body))),
        ("Access-Control-Allow-Origin", "*"),
    ]
    start_response(status_text, headers)
    return [body]


def _render_dashboard_html(data: dict, recent_records: list) -> str:
    """Render a premium, modern status and monitoring dashboard."""
    stats = data.get("results", {})
    success_cnt = stats.get("SUCCESS", 0)
    skipped_cnt = stats.get("SKIPPED_RECIPIENT", 0) + stats.get("SKIPPED_SUBJECT", 0)
    duplicate_cnt = stats.get("DUPLICATE", 0)
    already_cnt = stats.get("ALREADY_PROCESSED", 0)
    total_eval = sum(stats.values()) if stats else 0

    rows_html = ""
    if recent_records:
        for r in recent_records:
            status_val = r.get("status", "UNKNOWN")
            badge_class = "badge-success" if status_val == "SUCCESS" else (
                "badge-duplicate" if status_val == "DUPLICATE" else "badge-skipped"
            )
            subj = html.escape(r.get("subject") or "No Subject")
            om = html.escape(r.get("om_code") or "—")
            client = html.escape(r.get("client_name") or "—")
            target = html.escape(r.get("saved_filename") or r.get("attachment_name") or "—")
            dt = r.get("received_datetime") or r.get("created_at") or ""
            dt_display = dt[:19].replace("T", " ") if dt else "—"

            rows_html += f"""
            <tr>
                <td><code>{om}</code></td>
                <td><strong>{client}</strong></td>
                <td class="filename-cell" title="{html.escape(r.get('sharepoint_path') or '')}">{target}</td>
                <td><span class="badge {badge_class}">{status_val}</span></td>
                <td class="date-cell">{dt_display}</td>
            </tr>
            """
    else:
        rows_html = """
        <tr>
            <td colspan="5" style="text-align:center; padding: 2.5rem; color: #94a3b8;">
                No recent processed emails recorded in this session.
            </td>
        </tr>
        """

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Cleantech Invoice Automation - Live Monitor</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
    <style>
        :root {{
            --bg-base: #0b0f19;
            --bg-card: #111827;
            --bg-card-hover: #1f2937;
            --border-color: rgba(255, 255, 255, 0.08);
            --accent-primary: #38bdf8;
            --accent-success: #10b981;
            --accent-warning: #f59e0b;
            --text-main: #f8fafc;
            --text-muted: #94a3b8;
            --font-stack: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
        }}
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        body {{
            background-color: var(--bg-base);
            color: var(--text-main);
            font-family: var(--font-stack);
            line-height: 1.5;
            min-height: 100vh;
            padding: 2rem 1.5rem;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
        }}
        /* Header Banner */
        .header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 1.25rem;
            margin-bottom: 2rem;
            padding-bottom: 1.5rem;
            border-bottom: 1px solid var(--border-color);
        }}
        .header-title {{
            display: flex;
            align-items: center;
            gap: 1rem;
        }}
        .logo-icon {{
            width: 44px;
            height: 44px;
            background: linear-gradient(135deg, #0284c7, #06b6d4);
            border-radius: 12px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 1.5rem;
            box-shadow: 0 8px 16px rgba(6, 182, 212, 0.25);
        }}
        .header-title h1 {{
            font-size: 1.5rem;
            font-weight: 700;
            letter-spacing: -0.02em;
            color: #ffffff;
        }}
        .header-title p {{
            font-size: 0.875rem;
            color: var(--text-muted);
        }}
        .status-pill {{
            display: inline-flex;
            align-items: center;
            gap: 0.5rem;
            padding: 0.4rem 0.9rem;
            border-radius: 9999px;
            background: rgba(16, 185, 129, 0.12);
            border: 1px solid rgba(16, 185, 129, 0.3);
            color: #34d399;
            font-size: 0.8125rem;
            font-weight: 600;
            letter-spacing: 0.02em;
        }}
        .pulse-dot {{
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background-color: #10b981;
            box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.7);
            animation: pulse 1.8s infinite;
        }}
        @keyframes pulse {{
            0% {{ box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.7); }}
            70% {{ box-shadow: 0 0 0 8px rgba(16, 185, 129, 0); }}
            100% {{ box-shadow: 0 0 0 0 rgba(16, 185, 129, 0); }}
        }}

        /* Action Bar */
        .action-bar {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            flex-wrap: wrap;
            gap: 1rem;
            margin-bottom: 2rem;
            background: rgba(17, 24, 39, 0.7);
            padding: 1rem 1.25rem;
            border-radius: 12px;
            border: 1px solid var(--border-color);
            backdrop-filter: blur(8px);
        }}
        .btn {{
            display: inline-flex;
            align-items: center;
            gap: 0.5rem;
            padding: 0.625rem 1.25rem;
            font-size: 0.875rem;
            font-weight: 600;
            border-radius: 8px;
            cursor: pointer;
            text-decoration: none;
            transition: all 0.2s ease;
            border: none;
        }}
        .btn-primary {{
            background: linear-gradient(135deg, #0284c7, #2563eb);
            color: #ffffff;
            box-shadow: 0 4px 12px rgba(37, 99, 235, 0.3);
        }}
        .btn-primary:hover {{
            background: linear-gradient(135deg, #0369a1, #1d4ed8);
            transform: translateY(-1px);
        }}
        .btn-secondary {{
            background: rgba(255, 255, 255, 0.06);
            color: var(--text-main);
            border: 1px solid var(--border-color);
        }}
        .btn-secondary:hover {{
            background: rgba(255, 255, 255, 0.1);
        }}

        /* Metrics Grid */
        .metrics-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
            gap: 1.25rem;
            margin-bottom: 2rem;
        }}
        .metric-card {{
            background: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: 14px;
            padding: 1.25rem;
            transition: border-color 0.2s, transform 0.2s;
        }}
        .metric-card:hover {{
            border-color: rgba(255, 255, 255, 0.18);
            transform: translateY(-2px);
        }}
        .metric-label {{
            font-size: 0.8125rem;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 0.05em;
            margin-bottom: 0.35rem;
        }}
        .metric-value {{
            font-size: 1.5rem;
            font-weight: 700;
            color: #ffffff;
            word-break: break-all;
        }}
        .metric-sub {{
            font-size: 0.75rem;
            color: #64748b;
            margin-top: 0.35rem;
        }}

        /* Table Card */
        .card {{
            background: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: 14px;
            overflow: hidden;
            margin-bottom: 2rem;
        }}
        .card-header {{
            padding: 1.25rem 1.5rem;
            border-bottom: 1px solid var(--border-color);
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        .card-header h2 {{
            font-size: 1.125rem;
            font-weight: 600;
        }}
        .table-responsive {{
            overflow-x: auto;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            text-align: left;
            font-size: 0.875rem;
        }}
        th {{
            padding: 0.875rem 1.5rem;
            background: rgba(255, 255, 255, 0.02);
            color: var(--text-muted);
            font-weight: 600;
            border-bottom: 1px solid var(--border-color);
            text-transform: uppercase;
            font-size: 0.75rem;
            letter-spacing: 0.05em;
        }}
        td {{
            padding: 1rem 1.5rem;
            border-bottom: 1px solid var(--border-color);
        }}
        tr:last-child td {{
            border-bottom: none;
        }}
        tr:hover td {{
            background: rgba(255, 255, 255, 0.02);
        }}
        code {{
            background: rgba(255, 255, 255, 0.08);
            padding: 0.2rem 0.45rem;
            border-radius: 4px;
            font-size: 0.8125rem;
            color: #38bdf8;
            font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
        }}
        .badge {{
            display: inline-block;
            padding: 0.25rem 0.6rem;
            border-radius: 6px;
            font-size: 0.75rem;
            font-weight: 600;
            text-transform: uppercase;
        }}
        .badge-success {{
            background: rgba(16, 185, 129, 0.15);
            color: #34d399;
            border: 1px solid rgba(16, 185, 129, 0.3);
        }}
        .badge-duplicate {{
            background: rgba(56, 189, 248, 0.15);
            color: #38bdf8;
            border: 1px solid rgba(56, 189, 248, 0.3);
        }}
        .badge-skipped {{
            background: rgba(148, 163, 184, 0.12);
            color: #94a3b8;
            border: 1px solid rgba(148, 163, 184, 0.2);
        }}
        .filename-cell {{
            max-width: 300px;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
            color: #cbd5e1;
        }}
        .date-cell {{
            color: #64748b;
            font-size: 0.8125rem;
            white-space: nowrap;
        }}
        .footer {{
            text-align: center;
            font-size: 0.8125rem;
            color: #64748b;
            margin-top: 2.5rem;
        }}
    </style>
</head>
<body>
    <div class="container">
        <!-- Top Header -->
        <header class="header">
            <div class="header-title">
                <div class="logo-icon">⚡</div>
                <div>
                    <h1>Cleantech Invoice Automation</h1>
                    <p>Microsoft 365 Mailbox &rarr; SharePoint Filing Monitor</p>
                </div>
            </div>
            <div>
                <span class="status-pill">
                    <span class="pulse-dot"></span>
                    SERVICE ACTIVE &bull; MONITORING
                </span>
            </div>
        </header>

        <!-- Action / Control Bar -->
        <div class="action-bar">
            <div>
                <strong>Active Mailbox:</strong> <span style="color: #38bdf8;">{html.escape(data.get("mailbox", ""))}</span>
                &bull;
                <strong>Invoice Group:</strong> <span style="color: #cbd5e1;">{html.escape(data.get("invoice_group", ""))}</span>
            </div>
            <div style="display: flex; gap: 0.75rem;">
                <button class="btn btn-primary" onclick="triggerRun(false)">
                    &orarr; Run Sync Cycle Now
                </button>
                <a href="/?format=json" target="_blank" class="btn btn-secondary">
                    View JSON
                </a>
            </div>
        </div>

        <!-- Metrics Cards -->
        <div class="metrics-grid">
            <div class="metric-card">
                <div class="metric-label">Cycle Status</div>
                <div class="metric-value" style="color: #10b981;">HEALTHY</div>
                <div class="metric-sub">Evaluated: {total_eval} emails in last cycle</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">New Invoices Saved</div>
                <div class="metric-value">{success_cnt}</div>
                <div class="metric-sub">Uploaded to SharePoint</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">SharePoint Destination</div>
                <div class="metric-value" style="font-size: 1.125rem; padding-top: 0.25rem;">{html.escape(data.get("sharepoint_target", ""))}</div>
                <div class="metric-sub">Auto-creates /YYYY/YYMM/IN-xxx/</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Date Filter</div>
                <div class="metric-value" style="font-size: 1rem; padding-top: 0.35rem;">{html.escape(data.get("date_filter", ""))}</div>
                <div class="metric-sub">Duplicates detected: {duplicate_cnt}</div>
            </div>
        </div>

        <!-- Recent Invoices Table -->
        <div class="card">
            <div class="card-header">
                <h2>Audit Log & Processed Invoices</h2>
                <span style="font-size: 0.8125rem; color: var(--text-muted);">Auto-updating from database</span>
            </div>
            <div class="table-responsive">
                <table>
                    <thead>
                        <tr>
                            <th>O&amp;M Code</th>
                            <th>Client Name</th>
                            <th>Invoice File</th>
                            <th>Status</th>
                            <th>Date Processed</th>
                        </tr>
                    </thead>
                    <tbody>
                        {rows_html}
                    </tbody>
                </table>
            </div>
        </div>

        <footer class="footer">
            Cleantech Solar &bull; Automated Invoice Filing Service &bull; Deployed on Vercel
        </footer>
    </div>

    <script>
        function triggerRun(dryRun) {{
            const btn = document.querySelector('.btn-primary');
            const originalText = btn.innerHTML;
            btn.innerHTML = '&#9203; Running Check...';
            btn.style.opacity = '0.7';
            btn.disabled = true;

            const url = dryRun ? '/?dry_run=true&format=json' : '/?run=true&format=json';
            fetch(url)
                .then(res => res.json())
                .then(data => {{
                    window.location.reload();
                }})
                .catch(err => {{
                    alert('Error executing sync cycle: ' + err);
                    btn.innerHTML = originalText;
                    btn.disabled = false;
                    btn.style.opacity = '1';
                }});
        }}
    </script>
</body>
</html>
"""


def _render_config_needed_html(data: dict) -> str:
    """Render helpful HTML when environment variables need to be set in Vercel."""
    missing_items = "".join(f"<li><code>{html.escape(v)}</code></li>" for v in data.get("missing_variables", []))
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Cleantech Invoice Automation - Configuration Required</title>
    <style>
        body {{
            background: #0f172a;
            color: #f8fafc;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            display: flex;
            align-items: center;
            justify-content: center;
            min-height: 100vh;
            padding: 1.5rem;
        }}
        .card {{
            background: #1e293b;
            border: 1px solid #334155;
            border-radius: 12px;
            padding: 2.5rem;
            max-width: 600px;
            box-shadow: 0 10px 25px rgba(0,0,0,0.4);
        }}
        h1 {{ color: #f59e0b; margin-bottom: 1rem; font-size: 1.5rem; }}
        ul {{ margin: 1.25rem 0; padding-left: 1.5rem; }}
        li {{ margin-bottom: 0.5rem; }}
        code {{ background: #0f172a; padding: 0.2rem 0.5rem; border-radius: 4px; color: #38bdf8; }}
        p {{ color: #cbd5e1; line-height: 1.6; }}
    </style>
</head>
<body>
    <div class="card">
        <h1>Configuration Required</h1>
        <p>The service is deployed, but required Microsoft Azure credentials have not been configured in Vercel Environment Variables:</p>
        <ul>{missing_items}</ul>
        <p>Please navigate to your <strong>Vercel Project Settings &rarr; Environment Variables</strong>, add the values from your <code>.env</code> file, and redeploy.</p>
    </div>
</body>
</html>
"""


def _render_error_html(data: dict) -> str:
    """Render error page with clear diagnostic details."""
    err_str = html.escape(str(data.get("error", "Unknown error")))
    err_type = html.escape(str(data.get("type", "Error")))
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Cleantech Invoice Automation - Error</title>
    <style>
        body {{
            background: #0f172a;
            color: #f8fafc;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            display: flex;
            align-items: center;
            justify-content: center;
            min-height: 100vh;
            padding: 1.5rem;
        }}
        .card {{
            background: #1e293b;
            border: 1px solid #ef4444;
            border-radius: 12px;
            padding: 2.5rem;
            max-width: 650px;
            box-shadow: 0 10px 25px rgba(0,0,0,0.4);
        }}
        h1 {{ color: #ef4444; margin-bottom: 1rem; font-size: 1.5rem; }}
        pre {{ background: #0f172a; padding: 1rem; border-radius: 8px; overflow-x: auto; color: #fca5a5; font-size: 0.875rem; }}
        .btn {{ display: inline-block; margin-top: 1.5rem; padding: 0.6rem 1.25rem; background: #3b82f6; color: white; text-decoration: none; border-radius: 6px; }}
    </style>
</head>
<body>
    <div class="card">
        <h1>Operation Error ({err_type})</h1>
        <p style="color: #94a3b8; margin-bottom: 1rem;">An issue occurred while executing the invoice processing cycle:</p>
        <pre>{err_str}</pre>
        <a href="/" class="btn">&larr; Return to Dashboard</a>
    </div>
</body>
</html>
"""


# Aliases for various deployment runners
handler = app
application = app


if __name__ == "__main__":
    from wsgiref.simple_server import make_server

    port = int(os.environ.get("PORT", 8000))
    print("=" * 60)
    print("Cleantech Invoice Automation - Web Server")
    print("=" * 60)
    print(f"Local Server running at: http://localhost:{port}")
    print(f"Health Check URL:        http://localhost:{port}/health")
    print("=" * 60)
    with make_server("0.0.0.0", port, app) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nServer stopped.")
