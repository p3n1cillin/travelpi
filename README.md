# TravelPi

Raspberry Pi travel router setup for streaming home Jellyfin to a Firestick while away.

The Pi takes Ethernet from the local router, advertises its own WiFi AP for the Firestick,
and routes AP clients over normal internet plus Tailscale back to the home Jellyfin subnet.

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

