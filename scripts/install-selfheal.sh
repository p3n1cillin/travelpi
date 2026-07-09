#!/usr/bin/env bash
# Install TravelPi self-healing, error-checking, auto-update and push alerts.
# Run ON the Pi (it writes to /usr/local, /etc/systemd). Idempotent.
#   - travelpi-selfheal : every 10 min + 2 min after boot; restarts failed
#     services, re-asserts AP IP / tailscale / protective route; alerts if stuck.
#   - travelpi-update   : weekly (catch-up on boot via Persistent); apt full
#     upgrade when online; alerts on result.
#   - notify.sh         : ntfy push (same topic as the rest of the homelab).
set -euo pipefail
NTFY_TOPIC="pve-lab1-3ef6648a2e7b"

echo "== notify.sh (ntfy) =="
sudo tee /usr/local/bin/notify.sh >/dev/null <<EOF
#!/bin/bash
# Push a notification to the private ntfy topic. Best-effort (needs internet).
NTFY_URL="https://ntfy.sh/${NTFY_TOPIC}"
prio="\${1:-default}"; title="\${2:-travelpi}"; shift 2 2>/dev/null; msg="\$*"
case "\$prio" in high|urgent) tags="warning,travelpi";; *) tags="white_check_mark,travelpi";; esac
curl -fsS --max-time 12 -H "Title: \$title" -H "Priority: \$prio" -H "Tags: \$tags" \
  -d "\${msg:-no message}" "\$NTFY_URL" >/dev/null 2>&1 || true
EOF
sudo chmod +x /usr/local/bin/notify.sh

echo "== self-heal script =="
sudo tee /usr/local/sbin/travelpi-selfheal.sh >/dev/null <<'EOF'
#!/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
LOG=/var/log/travelpi-selfheal.log
NOTIFY=/usr/local/bin/notify.sh
exec >>"$LOG" 2>&1
ISSUES=()
log(){ echo "$(date '+%F %T') $*"; }

# 1) core services back up if they died
for s in tailscaled hostapd dnsmasq travel-ap-net firestick-remote travelpi-portal; do
  systemctl list-unit-files "$s.service" >/dev/null 2>&1 || continue
  if ! systemctl is-active --quiet "$s"; then
    log "restart $s"; systemctl restart "$s" 2>/dev/null; sleep 2
    systemctl is-active --quiet "$s" || ISSUES+=("$s down")
  fi
done

# 2) AP address present on wlan0
if ! ip -4 addr show wlan0 2>/dev/null | grep -q '192.168.50.1'; then
  log "AP IP missing -> restart travel-ap-net"; systemctl restart travel-ap-net 2>/dev/null; sleep 1
  ip -4 addr show wlan0 2>/dev/null | grep -q '192.168.50.1' || ISSUES+=("AP IP missing")
fi

# 3) tailscale connected
if ! tailscale status >/dev/null 2>&1; then
  log "tailscale down -> up"
  tailscale up --accept-routes --accept-dns=false --hostname travelpi >/dev/null 2>&1 || true
  tailscale status >/dev/null 2>&1 || ISSUES+=("tailscale down")
fi

# 4) protective route (keep Pi's own home-LAN traffic on eth0, not the tunnel)
ip rule list | grep -q '192.168.0.0/24 lookup main' || \
  ip rule add iif lo to 192.168.0.0/24 lookup main priority 50 2>/dev/null || true

# 5) forwarding on
[ "$(cat /proc/sys/net/ipv4/ip_forward 2>/dev/null)" = "1" ] || sysctl -w net.ipv4.ip_forward=1 >/dev/null 2>&1

if [ "${#ISSUES[@]}" -gt 0 ]; then
  log "UNRESOLVED: ${ISSUES[*]}"
  if ping -c1 -W2 1.1.1.1 >/dev/null 2>&1 && [ -x "$NOTIFY" ]; then
    "$NOTIFY" high "TravelPi: ${#ISSUES[@]} issue(s)" "${ISSUES[*]}"
  fi
fi
tail -n 500 "$LOG" > "$LOG.tmp" 2>/dev/null && mv "$LOG.tmp" "$LOG" 2>/dev/null || true
EOF
sudo chmod +x /usr/local/sbin/travelpi-selfheal.sh

echo "== auto-update script =="
sudo tee /usr/local/sbin/travelpi-update.sh >/dev/null <<'EOF'
#!/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
LOG=/var/log/travelpi-update.log
NOTIFY=/usr/local/bin/notify.sh
export DEBIAN_FRONTEND=noninteractive
exec >>"$LOG" 2>&1
ping -c1 -W3 1.1.1.1 >/dev/null 2>&1 || { echo "$(date '+%F %T') offline, skip"; exit 0; }
echo "=== update $(date '+%F %T') ==="
fail=0
apt-get update -qq || fail=1
apt-get -y -o Dpkg::Options::=--force-confold full-upgrade || fail=1
apt-get -y autoremove --purge || true
apt-get -y clean || true
if [ -x "$NOTIFY" ]; then
  if [ "$fail" = 0 ]; then "$NOTIFY" default "TravelPi updated OK" "$(date '+%F %T')"
  else "$NOTIFY" high "TravelPi update FAILED" "check travelpi-update.log"; fi
fi
tail -n 800 "$LOG" > "$LOG.tmp" 2>/dev/null && mv "$LOG.tmp" "$LOG" 2>/dev/null || true
EOF
sudo chmod +x /usr/local/sbin/travelpi-update.sh

echo "== systemd units + timers =="
sudo tee /etc/systemd/system/travelpi-selfheal.service >/dev/null <<'EOF'
[Unit]
Description=TravelPi self-heal (services, AP, tailscale, routing)
[Service]
Type=oneshot
ExecStart=/usr/local/sbin/travelpi-selfheal.sh
EOF
sudo tee /etc/systemd/system/travelpi-selfheal.timer >/dev/null <<'EOF'
[Unit]
Description=Run TravelPi self-heal after boot and every 10 min
[Timer]
OnBootSec=2min
OnUnitActiveSec=10min
[Install]
WantedBy=timers.target
EOF
sudo tee /etc/systemd/system/travelpi-update.service >/dev/null <<'EOF'
[Unit]
Description=TravelPi weekly apt full-upgrade (when online)
[Service]
Type=oneshot
ExecStart=/usr/local/sbin/travelpi-update.sh
EOF
sudo tee /etc/systemd/system/travelpi-update.timer >/dev/null <<'EOF'
[Unit]
Description=Weekly TravelPi update (catches up on next boot if missed)
[Timer]
OnCalendar=Sun 04:00
Persistent=true
[Install]
WantedBy=timers.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now travelpi-selfheal.timer travelpi-update.timer >/dev/null 2>&1
echo "== enabled timers =="
systemctl list-timers travelpi-* --no-pager 2>/dev/null | grep travelpi || true
echo "== run one self-heal pass now =="
sudo /usr/local/sbin/travelpi-selfheal.sh && echo "selfheal ran OK"
