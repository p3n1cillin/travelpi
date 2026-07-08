# TravelPi

Raspberry Pi travel router setup for streaming home Jellyfin to a Firestick while away.

The Pi takes Ethernet from the local router, advertises its own WiFi AP for the Firestick,
and routes AP clients over normal internet plus Tailscale back to the home Jellyfin subnet.

## What Is In This Repo

- Firestick remote web app source and static UI.
- Systemd units for the AP network setup and remote app.
- Sanitized `hostapd`, `dnsmasq`, `nftables`, NetworkManager, and sysctl configs.
- Scripts to install prerequisites, deploy the remote app, install AP configs, and check status.
- Safety notes for applying AP changes without disrupting the existing Tailscale setup.

## What Is Not In This Repo

- Raspberry Pi OS image, boot EEPROM, kernel, or device firmware blobs.
- Tailscale authentication state, node keys, or auth keys.
- The real WiFi passphrase for the AP.
- Router-specific DHCP reservations or home-router port forwarding.
- Firestick ADB authorization state. Each Firestick still has to approve ADB once.

## Current Live Addresses

- Pi AP gateway: `192.168.50.1`
- Remote web app on Pi AP: `http://192.168.50.1:8787/`
- Tailscale address: `100.119.216.79`
- Remote web app on Tailscale: `http://100.119.216.79:8787/`
- mDNS when available: `http://wifipi.local:8787/`

The Ethernet/router-side address is DHCP by design and can change per router. Do not hard-code
it for travel use; use the AP address or Tailscale address instead.

## Layout

- `firestick-remote-web/` - local web remote for Fire TV devices using ADB.
- `configs/` - sanitized TravelPi service/config templates.
- `scripts/` - deploy and status helpers.

## Fresh Setup From Clone

Start with Raspberry Pi OS on a Pi that has:

- Ethernet as the uplink to the local router.
- A WiFi adapter intended for the travel AP as `wlan0`.
- SSH enabled.
- A user account that can run `sudo`.

Clone this repo on your laptop or admin machine:

```bash
git clone git@github.com:p3nicillin/travelpi.git
cd travelpi
```

Set the target Pi details if they differ from the live TravelPi:

```bash
export PI_HOST=pwned@100.119.216.79
export SSH_KEY="$HOME/.ssh/id_ed25519"
export PI_SERVICE_USER=pwned
```

Install Pi packages:

```bash
./scripts/install-prereqs.sh
```

If Tailscale is not already installed on a fresh Pi, install it too:

```bash
INSTALL_TAILSCALE=1 ./scripts/install-prereqs.sh
```

Then SSH to the Pi and authenticate Tailscale:

```bash
sudo tailscale up
```

Install the AP configs. This intentionally requires the AP password as an environment variable so the secret is not committed:

```bash
WIFI_PASSPHRASE='change-this-password' ./scripts/install-travel-ap-configs.sh
```

Reboot the Pi to apply AP changes safely:

```bash
ssh -i "$SSH_KEY" "$PI_HOST" 'sudo reboot'
```

After the Pi comes back, deploy the remote app:

```bash
./scripts/deploy-firestick-remote.sh
```

Check everything:

```bash
./scripts/status.sh
```

## Important Safety Note

Do not run a live `systemctl restart hostapd` on this Pi. The USB WiFi/Ethernet bus can wedge.
Apply AP config changes by writing the config and rebooting. Use an auto-revert guard for risky
AP changes.

## Firestick Remote

The remote service runs as `firestick-remote.service` and listens on port `8787`.

From a device connected to the Pi AP:

```bash
http://192.168.50.1:8787/
```

From a Tailscale device:

```bash
http://100.119.216.79:8787/
```

## Deploy Remote App

```bash
./scripts/deploy-firestick-remote.sh
```

## Check Status

```bash
./scripts/status.sh
```

## Firestick Setup

Connect the Firestick to the TravelPi AP, currently `Living Room`, then enable ADB debugging on the Firestick.
Open the remote app from a phone or laptop on the AP:

```bash
http://192.168.50.1:8787/
```

The app discovers ADB devices from connected ADB sessions and the Pi DHCP leases. If the Firestick is not in
the dropdown yet, connect it manually once from the Pi:

```bash
adb connect FIRESTICK_IP:5555
```

Approve the prompt on the Firestick. After that, the web app should find it.

## Reproducibility Notes

This repo is enough to recreate the TravelPi application and service configuration on a normal Raspberry Pi OS
install without wiping Tailscale. A clone cannot fully recreate external state: the base OS image, Tailscale login,
WiFi password, home network routes, and Firestick ADB pairing still have to be supplied by the person setting it up.
