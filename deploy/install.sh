#!/usr/bin/env bash
# Install lensmind on Raspberry Pi OS Lite. Run from the repository: sudo deploy/install.sh
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_USER="${SUDO_USER:-}"

if [[ $EUID -ne 0 || -z "$RUN_USER" || "$RUN_USER" == "root" ]]; then
  echo "Run it with sudo from the user that will run lensmind: sudo deploy/install.sh" >&2
  exit 1
fi

apt-get update
apt-get install -y python3-venv python3-dev build-essential pkg-config libgphoto2-dev gphoto2

sudo -u "$RUN_USER" python3 -m venv "$REPO_DIR/.venv"
sudo -u "$RUN_USER" "$REPO_DIR/.venv/bin/pip" install --upgrade pip
sudo -u "$RUN_USER" "$REPO_DIR/.venv/bin/pip" install -e "$REPO_DIR[pi]"

# Access to the camera's USB device without root.
usermod -aG plugdev "$RUN_USER"

if [[ ! -f /etc/lensmind.env ]]; then
  cat > /etc/lensmind.env <<'ENV'
LENSMIND_PORT=80
LENSMIND_LANGUAGE=it
ENV
fi

sed -e "s|@USER@|$RUN_USER|g" -e "s|@REPO@|$REPO_DIR|g" \
  "$REPO_DIR/deploy/lensmind.service" > /etc/systemd/system/lensmind.service
systemctl daemon-reload
systemctl enable --now lensmind.service

echo "lensmind is running: http://$(hostname).local/"
