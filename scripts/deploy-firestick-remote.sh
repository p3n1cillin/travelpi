#!/usr/bin/env bash
set -euo pipefail

PI_HOST="${PI_HOST:-pwned@100.119.216.79}"
PI_SERVICE_USER="${PI_SERVICE_USER:-pwned}"
SSH_KEY="${SSH_KEY:-$HOME/.ssh/id_ed25519}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

tmpdir="$(mktemp -d)"
trap 'rm -rf "$tmpdir"' EXIT

cp "$ROOT_DIR/firestick-remote-web/systemd/firestick-remote.service" "$tmpdir/firestick-remote.service"
python3 - "$tmpdir/firestick-remote.service" "$PI_SERVICE_USER" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
user = sys.argv[2]
text = path.read_text(encoding="utf-8")
text = text.replace("User=pwned", f"User={user}")
path.write_text(text, encoding="utf-8")
PY

tar --exclude='__pycache__' --exclude='.git' -C "$ROOT_DIR/firestick-remote-web" -czf - . |
  ssh -i "$SSH_KEY" -o BatchMode=yes "$PI_HOST" '
    set -e
    sudo rm -rf /opt/firestick-remote-web
    sudo mkdir -p /opt/firestick-remote-web
    sudo tar -xzf - -C /opt/firestick-remote-web
    sudo chown -R '"$PI_SERVICE_USER:$PI_SERVICE_USER"' /opt/firestick-remote-web
  '

scp -i "$SSH_KEY" "$tmpdir/firestick-remote.service" "$PI_HOST:/tmp/firestick-remote.service"

ssh -i "$SSH_KEY" -o BatchMode=yes "$PI_HOST" '
    set -e
    sudo cp /tmp/firestick-remote.service /etc/systemd/system/firestick-remote.service
    sudo systemctl daemon-reload
    sudo systemctl enable --now firestick-remote.service
    systemctl --no-pager --full status firestick-remote.service | sed -n "1,16p"
  '
