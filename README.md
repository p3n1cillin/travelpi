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

- Pi AP SSID: `travelpi`
- Pi AP gateway: `192.168.50.1`
- **WiFi selection portal (hotel WiFi picker): `http://192.168.50.1/`** (port 80, always on)
- Remote web app on Pi AP: `http://192.168.50.1:8787/`
- Tailscale address: `100.119.216.79`
- Remote web app on Tailscale: `http://100.119.216.79:8787/`
- mDNS when available: `http://wifipi.local:8787/`

Interfaces: `eth0` = wired uplink, `wlan0` = Archer T3U access point (the `travelpi`
SSID), `wlan1` = client dongle used to join upstream WiFi (hotels).

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

Connect the Firestick to the TravelPi AP, currently `travelpi`, then enable ADB debugging on the Firestick.
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

## Hotel WiFi (no router access)

When there is no Ethernet to plug into, the Pi joins the venue WiFi on the **client dongle
`wlan1`** and keeps hosting the `travelpi` AP on `wlan0`. Because you can't reach a router
you don't control, there is an **always-on web GUI on the AP itself** to pick the network:

1. Connect a phone/laptop to the `travelpi` AP.
2. Open `http://192.168.50.1/` (the WiFi portal — served on port 80, works with no internet yet).
3. Tap **Scan**, choose the venue WiFi, enter its password, **Connect**.
4. Once it shows "Online", the Firestick has internet + the Tailscale path home.

The portal is `wifi-portal/app.py` (Flask, runs as root via `travelpi-portal.service`) and
drives `nmcli` on `wlan1`. NAT masquerades AP traffic out whichever WAN is active — `eth0`,
`wlan1`, or `tailscale0` (see `configs/travel-ap.nft`). Deploy with:

```bash
# copy wifi-portal/app.py to /opt/travelpi-portal/app.py and install the unit
sudo install -D wifi-portal/app.py /opt/travelpi-portal/app.py
sudo cp wifi-portal/travelpi-portal.service /etc/systemd/system/
sudo systemctl enable --now travelpi-portal.service
```

## Split-tunnel routing (important)

Tailscale runs with `--accept-routes` so the Pi can reach the home `192.168.0.0/24` subnet
(advertised by the home Tailscale subnet router). A protective policy rule keeps the Pi's
**own** traffic to that subnet on `eth0` while only **forwarded** Firestick traffic is
tunnelled — without it, at home the Pi would route its own LAN traffic through the tunnel and
become unreachable on the LAN. Installed as a drop-in on `travel-ap-net.service`
(`configs/10-protect-own-lan.conf`):

```
ip rule add iif lo to 192.168.0.0/24 lookup main priority 50
```

## Self-healing, error-checking and auto-update

`scripts/install-selfheal.sh` (run on the Pi) installs:

- **`travelpi-selfheal.timer`** — 2 min after boot and every 10 min: restarts any dead core
  service (`tailscaled`, `hostapd`, `dnsmasq`, `travel-ap-net`, `firestick-remote`,
  `travelpi-portal`), re-asserts the AP address, tailscale connection, protective route and IP
  forwarding, and pushes an alert if something can't be recovered.
- **`travelpi-update.timer`** — weekly `apt` full-upgrade when online, `Persistent=true` so a
  missed run (Pi off/away) catches up on next boot.
- **`notify.sh`** — ntfy push alerts (same private topic as the rest of the homelab) for update
  results and unrecoverable self-heal issues.

Everything needed for the Firestick to work is enabled on boot: `tailscaled`, `hostapd`,
`dnsmasq`, `travel-ap-net`, `firestick-remote`, `travelpi-portal`.

### Never lose the portal / remote (addresses)

The access addresses are already **static/stable** — the AP is a hard-coded static
`192.168.50.1`, and the Tailscale address `100.x` never changes:

- Portal: `http://192.168.50.1/`
- Firestick remote (WiFi): `http://192.168.50.1:8787/`
- Firestick remote (Tailscale): `http://100.119.216.79:8787/`

Only the `eth0` LAN IP is DHCP. `scripts/install-announce.sh` adds a boot service +
NetworkManager dispatcher (`travelpi-announce`) that **pushes all current addresses to ntfy**
whenever the Pi comes online or its WAN IP changes, so the LAN URL is always known too.

## Performance / no double-NAT

Fast remote streaming needs a **direct** Tailscale path (not a DERP relay). That requires the
home side to be a single NAT with working port-mapping. With the Deco plugged straight into the
ONT (no ISP-router NAT in front), `tailscale netcheck` on the home node reports
`PortMapping: UPnP, NAT-PMP` and `MappingVariesByDestIP: false` ("easy" NAT), and peers connect
`direct` instead of via a relay. Confirm any time with:

```bash
tailscale netcheck          # want UPnP/NAT-PMP + MappingVariesByDestIP:false
tailscale status            # the home peer line should say "direct ...", not "relay"
```

## Change log

- **2026-07-09** — AP renamed `Living Room` -> `travelpi` (was clashing with the home SSID; the
  known-good backup `hostapd.conf.good` was updated too). Added the hotel WiFi client mode on
  `wlan1` + the always-on WiFi selection portal. Added `wlan1` to the NAT masquerade set. Added
  the split-tunnel protective route. Added self-heal + weekly auto-update + ntfy alerts.
  Verified the Tailscale path home is now **direct** after the double-NAT was removed.
