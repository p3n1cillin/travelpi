#!/usr/bin/env bash
set -euo pipefail

PI_HOST="${PI_HOST:-pwned@100.119.216.79}"
SSH_KEY="${SSH_KEY:-$HOME/.ssh/id_ed25519}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "This installs TravelPi AP config templates. Review configs/hostapd.conf.example first."
echo "Set WIFI_PASSPHRASE before running, or edit /etc/hostapd/hostapd.conf manually on the Pi."
: "${WIFI_PASSPHRASE:?WIFI_PASSPHRASE is required}"
if (( ${#WIFI_PASSPHRASE} < 8 || ${#WIFI_PASSPHRASE} > 63 )); then
  echo "WIFI_PASSPHRASE must be 8-63 characters for WPA2-PSK." >&2
  exit 1
fi

tmpdir="$(mktemp -d)"
trap 'rm -rf "$tmpdir"' EXIT

cp "$ROOT_DIR/configs/hostapd.conf.example" "$tmpdir/hostapd.conf"
python3 - "$tmpdir/hostapd.conf" "$WIFI_PASSPHRASE" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
password = sys.argv[2]
text = path.read_text(encoding="utf-8")
text = text.replace("wpa_passphrase=CHANGE_ME", f"wpa_passphrase={password}")
path.write_text(text, encoding="utf-8")
PY

scp -i "$SSH_KEY" "$tmpdir/hostapd.conf" "$ROOT_DIR/configs/dnsmasq-travel-ap.conf" \
  "$ROOT_DIR/configs/travel-ap.nft" "$ROOT_DIR/configs/travel-ap-net.service" \
  "$ROOT_DIR/configs/99-unmanage-ap.conf" "$ROOT_DIR/configs/99-travelap.conf" \
  "$PI_HOST:/tmp/"

ssh -i "$SSH_KEY" -o BatchMode=yes "$PI_HOST" '
  set -e
  stamp="$(date +%Y%m%d-%H%M%S)"
  sudo mkdir -p /root/travelpi-config-backups/"$stamp"
  for path in \
    /etc/hostapd/hostapd.conf \
    /etc/dnsmasq.d/travel-ap.conf \
    /etc/travel-ap.nft \
    /etc/systemd/system/travel-ap-net.service \
    /etc/NetworkManager/conf.d/99-unmanage-ap.conf \
    /etc/sysctl.d/99-travelap.conf
  do
    if [ -e "$path" ]; then
      sudo cp -a "$path" /root/travelpi-config-backups/"$stamp"/
    fi
  done
  sudo cp /tmp/hostapd.conf /etc/hostapd/hostapd.conf
  sudo cp /tmp/dnsmasq-travel-ap.conf /etc/dnsmasq.d/travel-ap.conf
  sudo cp /tmp/travel-ap.nft /etc/travel-ap.nft
  sudo cp /tmp/travel-ap-net.service /etc/systemd/system/travel-ap-net.service
  sudo cp /tmp/99-unmanage-ap.conf /etc/NetworkManager/conf.d/99-unmanage-ap.conf
  sudo cp /tmp/99-travelap.conf /etc/sysctl.d/99-travelap.conf
  sudo systemctl daemon-reload
  sudo systemctl enable travel-ap-net hostapd dnsmasq
  echo "Backups, if any, are in /root/travelpi-config-backups/$stamp"
  echo "Configs installed. Reboot the Pi to apply AP changes safely."
'
