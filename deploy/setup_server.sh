#!/usr/bin/env bash
# Server setup script for Linux VM (Ubuntu / Debian / RHEL)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$SCRIPT_DIR"

echo "=================================================="
echo "Cleantech Invoice Automation - Server Setup"
echo "=================================================="

# 1. Check Python version
if ! command -v python3 >/dev/null 2>&1; then
    echo "Error: Python 3 is not installed. Please install python3 and python3-venv." >&2
    exit 1
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo "[✓] Found Python $PYTHON_VERSION"

# 2. Setup Virtual Environment
if [ ! -d ".venv" ]; then
    echo "[*] Creating virtual environment (.venv)..."
    python3 -m venv .venv
else
    echo "[✓] Virtual environment already exists (.venv)"
fi

# 3. Install Dependencies
echo "[*] Installing dependencies..."
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
echo "[✓] Dependencies installed."

# 4. Check .env configuration
if [ ! -f ".env" ]; then
    echo "[!] .env file not found. Copying from .env.example..."
    cp .env.example .env
    echo "[!] Please configure your .env file with Microsoft Entra & SharePoint credentials."
else
    echo "[✓] .env file detected."
fi

# 5. Make helper scripts executable
chmod +x start.sh stop.sh status.sh

echo ""
echo "=================================================="
echo "Setup Complete!"
echo "=================================================="
echo "You can now run without Docker using:"
echo "  1. Background process: ./start.sh"
echo "  2. Interactive run:    .venv/bin/python -m src.main"
echo "  3. Single check test:  .venv/bin/python -m src.main --once"
echo "  4. Check status:       ./status.sh"
echo "  5. Stop service:       ./stop.sh"
echo "=================================================="
