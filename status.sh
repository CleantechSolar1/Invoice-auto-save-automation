#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_FILE="$SCRIPT_DIR/invoicing.pid"
LOG_FILE="$SCRIPT_DIR/logs/invoice_automation.log"

if [ -f "$PID_FILE" ]; then
    PID="$(cat "$PID_FILE")"
    if kill -0 "$PID" 2>/dev/null; then
        echo "[✓] Cleantech Invoice Automation is RUNNING (PID: $PID)"
        if command -v ps >/dev/null 2>&1; then
            ps -p "$PID" -o pid,stat,time,command 2>/dev/null || true
        fi
    else
        echo "[✗] Service is STOPPED (stale PID file: $PID)"
    fi
else
    echo "[✗] Service is STOPPED (no PID file found)"
fi

if [ -f "$LOG_FILE" ]; then
    echo ""
    echo "--- Last 15 lines of log ($LOG_FILE) ---"
    tail -n 15 "$LOG_FILE"
fi
