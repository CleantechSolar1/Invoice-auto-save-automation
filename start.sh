#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

PID_FILE="$SCRIPT_DIR/invoicing.pid"
LOG_DIR="$SCRIPT_DIR/logs"
LOG_FILE="$LOG_DIR/invoice_automation.log"

mkdir -p "$LOG_DIR"

# Check if already running
if [ -f "$PID_FILE" ]; then
    PID="$(cat "$PID_FILE")"
    if kill -0 "$PID" 2>/dev/null; then
        echo "[!] Cleantech Invoice Automation is already running (PID: $PID)."
        exit 0
    else
        echo "[*] Removing stale PID file..."
        rm -f "$PID_FILE"
    fi
fi

# Determine Python binary
if [ -f "$SCRIPT_DIR/.venv/bin/python" ]; then
    PYTHON_BIN="$SCRIPT_DIR/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="python3"
else
    echo "Error: Python 3 not found." >&2
    exit 1
fi

echo "[*] Starting Cleantech Invoice Automation in background..."
echo "[*] Python executable: $PYTHON_BIN"
echo "[*] Log file: $LOG_FILE"

nohup "$PYTHON_BIN" -m src.main > "$LOG_DIR/stdout.log" 2>&1 &
NEW_PID=$!
echo "$NEW_PID" > "$PID_FILE"

# Verify startup
sleep 2
if kill -0 "$NEW_PID" 2>/dev/null; then
    echo "[✓] Cleantech Invoice Automation started successfully (PID: $NEW_PID)."
    echo "[✓] View live logs: tail -f \"$LOG_FILE\""
    echo "[✓] Check status:   ./status.sh"
    echo "[✓] Stop service:   ./stop.sh"
else
    echo "[✗] Failed to start service. Check logs at: $LOG_FILE" >&2
    rm -f "$PID_FILE"
    exit 1
fi
