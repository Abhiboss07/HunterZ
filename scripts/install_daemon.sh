#!/bin/bash
# ==============================================================================
# HunterZ Daemon Installer: Auto-Start on System Boot
# ==============================================================================
set -e

SERVICE_NAME="hunterz"
SYSTEMD_USER_DIR="$HOME/.config/systemd/user"
SERVICE_SRC="$(dirname "$0")/hunterz.service"
SERVICE_DEST="$SYSTEMD_USER_DIR/${SERVICE_NAME}.service"

echo "⚡ [HunterZ] Setting up background daemon to run automatically on system boot..."

# 1. Create systemd user service directory
mkdir -p "$SYSTEMD_USER_DIR"

# 2. Copy and configure service file
cp "$SERVICE_SRC" "$SERVICE_DEST"

# 3. Reload systemd daemon
systemctl --user daemon-reload

# 4. Enable service to start on boot
systemctl --user enable "${SERVICE_NAME}.service"

# 5. Start service immediately
systemctl --user restart "${SERVICE_NAME}.service"

echo "✔ [HunterZ] Background daemon is now ACTIVE and will automatically run whenever your system starts!"
echo "  • Status: systemctl --user status ${SERVICE_NAME}"
echo "  • Logs:   journalctl --user -u ${SERVICE_NAME} -f"
echo "  • Stop:   systemctl --user stop ${SERVICE_NAME}"
