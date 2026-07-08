#!/usr/bin/env bash
set -euo pipefail

PI_HOST="${PI_HOST:-pwned@100.119.216.79}"
SSH_KEY="${SSH_KEY:-$HOME/.ssh/id_ed25519}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

tar --exclude='__pycache__' --exclude='.git' -C "$ROOT_DIR/firestick-remote-web" -czf - . |
  ssh -i "$SSH_KEY" -o BatchMode=yes "$PI_HOST" '
    set -e
    sudo rm -rf /opt/firestick-remote-web
    sudo mkdir -p /opt/firestick-remote-web
    sudo tar -xzf - -C /opt/firestick-remote-web
    sudo chown -R pwned:pwned /opt/firestick-remote-web
    sudo cp /opt/firestick-remote-web/systemd/firestick-remote.service /etc/systemd/system/firestick-remote.service
    sudo systemctl daemon-reload
    sudo systemctl enable --now firestick-remote.service
    systemctl --no-pager --full status firestick-remote.service | sed -n "1,16p"
  '
