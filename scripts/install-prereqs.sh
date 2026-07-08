#!/usr/bin/env bash
set -euo pipefail

PI_HOST="${PI_HOST:-pwned@100.119.216.79}"
SSH_KEY="${SSH_KEY:-$HOME/.ssh/id_ed25519}"
INSTALL_TAILSCALE="${INSTALL_TAILSCALE:-0}"

ssh -i "$SSH_KEY" -o BatchMode=yes "$PI_HOST" '
  set -e
  export DEBIAN_FRONTEND=noninteractive

  sudo apt-get update
  sudo apt-get install -y \
    android-tools-adb \
    avahi-daemon \
    curl \
    dnsmasq \
    hostapd \
    iproute2 \
    iw \
    network-manager \
    nftables \
    rfkill \
    wireless-tools

  sudo systemctl unmask hostapd || true
  sudo systemctl enable avahi-daemon nftables
'

if [[ "$INSTALL_TAILSCALE" == "1" ]]; then
  ssh -i "$SSH_KEY" -o BatchMode=yes "$PI_HOST" '
    set -e
    if ! command -v tailscale >/dev/null 2>&1; then
      curl -fsSL https://tailscale.com/install.sh | sh
    fi
    sudo systemctl enable --now tailscaled
    echo "Run: sudo tailscale up --advertise-routes=<home-subnet>/24"
  '
fi
