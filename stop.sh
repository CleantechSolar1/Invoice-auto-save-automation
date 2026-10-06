#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_FILE="$SCRIPT_DIR/invoicing.pid"

if [ ! -f "$PID_FILE" ]; then
    echo "[*] No PID file found. Service is not running."
    exit 0
fi

PID="$(cat "$PID_FILE")"

if kill -0 "$PID" 2>/dev/null; then
    echo "[*] Stopping Cleantech Invoice Automation (PID: $PID)..."
    kill -15 "$PID" 2>/dev/null || true

    # Wait for process to shut down gracefully
    for i in {1..10}; do
        if ! kill -0 "$PID" 2>/dev/null; then
            break
        fi
        sleep 1
    done

    if kill -0 "$PID" 2>/dev/null; then
        echo "[!] Process did not exit gracefully, sending SIGKILL..."
        kill -9 "$PID" 2>/dev/null || true
    fi

    rm -f "$PID_FILE"
    echo "[✓] Service stopped."
else
    echo "[*] Process (PID: $PID) was not running. Cleaning stale PID file."
    rm -f "$PID_FILE"
fi
