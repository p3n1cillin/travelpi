#!/usr/bin/env bash
set -euo pipefail

PI_HOST="${PI_HOST:-pwned@100.119.216.79}"
SSH_KEY="${SSH_KEY:-$HOME/.ssh/id_ed25519}"

ssh -i "$SSH_KEY" -o BatchMode=yes "$PI_HOST" '
  export PATH=/usr/sbin:/sbin:$PATH
  echo "== host =="
  hostname
  hostname -I
  echo
  echo "== services =="
  systemctl is-active tailscaled hostapd dnsmasq travel-ap-net firestick-remote 2>/dev/null || true
  echo
  echo "== ap =="
  iw dev wlan0 info 2>/dev/null | grep -E "ssid|channel" || true
  sudo iw dev wlan0 station dump 2>/dev/null | egrep "Station|signal:|tx bitrate|rx bitrate" || true
  echo
  echo "== leases =="
  cat /var/lib/misc/dnsmasq.leases 2>/dev/null || true
  echo
  echo "== firestick remote =="
  curl -fsS --max-time 4 http://127.0.0.1:8787/api/health || true
  echo
'
