#!/usr/bin/env bash
# Install a boot/on-connect ntfy announcement of TravelPi's addresses, so the
# portal and Firestick remote are never "lost" even though the LAN IP is DHCP.
# The AP (192.168.50.1) and Tailscale (100.x) addresses are already static/stable;
# this also publishes the variable eth0 LAN IP whenever the Pi comes online.
set -euo pipefail

echo "== announce script =="
sudo tee /usr/local/sbin/travelpi-announce.sh >/dev/null <<'EOF'
#!/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
NOTIFY=/usr/local/bin/notify.sh
LAST=/run/travelpi-announce.last
force=0; [ "${1:-}" = "--force" ] && force=1

eth=$(ip -4 -o addr show eth0 2>/dev/null | awk '{print $4}' | cut -d/ -f1)
w1=$(ip -4 -o addr show wlan1 2>/dev/null | awk '{print $4}' | cut -d/ -f1)
ts=$(tailscale ip -4 2>/dev/null | head -1)

key="${eth}|${w1}|${ts}"
if [ "$force" != 1 ] && [ -f "$LAST" ] && [ "$(cat "$LAST" 2>/dev/null)" = "$key" ]; then
  exit 0
fi

msg="Portal: http://192.168.50.1/
Remote (WiFi): http://192.168.50.1:8787/
Remote (Tailscale): http://${ts:-?}:8787/
LAN IP (DHCP): ${eth:-none}${eth:+ -> http://$eth:8787/}
Upstream WiFi: ${w1:-not connected}"

# ntfy needs internet; if online, publish and remember what we sent.
if ping -c1 -W2 1.1.1.1 >/dev/null 2>&1 && [ -x "$NOTIFY" ]; then
  "$NOTIFY" default "TravelPi addresses" "$msg" && echo "$key" > "$LAST"
fi
EOF
sudo chmod +x /usr/local/sbin/travelpi-announce.sh

echo "== boot announce service =="
sudo tee /etc/systemd/system/travelpi-announce.service >/dev/null <<'EOF'
[Unit]
Description=Announce TravelPi addresses to ntfy on boot
After=network-online.target tailscaled.target tailscaled.service
Wants=network-online.target
[Service]
Type=oneshot
ExecStartPre=/bin/sleep 20
ExecStart=/usr/local/sbin/travelpi-announce.sh --force
[Install]
WantedBy=multi-user.target
EOF

echo "== NetworkManager dispatcher (re-announce when a WAN comes up/changes) =="
sudo tee /etc/NetworkManager/dispatcher.d/90-travelpi-announce >/dev/null <<'EOF'
#!/bin/sh
IFACE="$1"; ACTION="$2"
case "$IFACE" in eth0|wlan1) ;; *) exit 0;; esac
case "$ACTION" in up|dhcp4-change|connectivity-change)
  (sleep 5; /usr/local/sbin/travelpi-announce.sh) &
  ;;
esac
exit 0
EOF
sudo chmod +x /etc/NetworkManager/dispatcher.d/90-travelpi-announce

sudo systemctl daemon-reload
sudo systemctl enable travelpi-announce.service >/dev/null 2>&1
echo "== test announce now (--force) =="
sudo /usr/local/sbin/travelpi-announce.sh --force && echo "announce sent"
