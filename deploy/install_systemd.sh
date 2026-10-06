#!/usr/bin/env bash
# Install Cleantech Invoice Automation as a systemd service (Ubuntu / Debian / RHEL)
set -euo pipefail

if [ "$EUID" -ne 0 ]; then
    echo "Error: Please run as root (e.g. sudo bash deploy/install_systemd.sh)" >&2
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVICE_SRC="$SCRIPT_DIR/deploy/cleantech-invoicing.service"
SERVICE_DEST="/etc/systemd/system/cleantech-invoicing.service"

echo "[*] Installing systemd service..."

# Adjust WorkingDirectory, ExecStart, and EnvironmentFile to match current location
sed -e "s|/opt/invoicing-automation|$SCRIPT_DIR|g" "$SERVICE_SRC" > "$SERVICE_DEST"

# Ensure log directory exists
mkdir -p /var/log
touch /var/log/invoicing-automation.stdout.log /var/log/invoicing-automation.stderr.log
chmod 644 /var/log/invoicing-automation.stdout.log /var/log/invoicing-automation.stderr.log

systemctl daemon-reload
systemctl enable cleantech-invoicing.service
systemctl restart cleantech-invoicing.service

echo "[✓] Service installed and started!"
echo "[✓] Status: sudo systemctl status cleantech-invoicing.service"
echo "[✓] Logs:   sudo journalctl -u cleantech-invoicing.service -f"
