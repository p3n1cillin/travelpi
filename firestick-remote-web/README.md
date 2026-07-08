# Firestick Remote Web

Local web remote for a Fire TV / Firestick, designed to run on the TravelPi Raspberry Pi.

The app serves a phone-friendly remote UI and sends Android TV key events through `adb`.

## Local Run

```bash
python3 server.py --mock --host 127.0.0.1 --port 8787
```

Open `http://127.0.0.1:8787/`.

## TravelPi Run

The TravelPi can run this with system Python and `android-tools-adb`.

```bash
python3 server.py --host 0.0.0.0 --port 8787 --target FIRESTICK_IP:5555
```

If the Firestick has network ADB enabled, the server will run `adb connect` for the configured target before sending commands.

Useful environment variables:

- `FIRESTICK_TARGET`: default ADB target, such as `192.168.50.23:5555`.
- `FIRESTICK_REMOTE_MOCK=1`: return success without executing `adb`, for local testing.

## Safety Notes

This app only sends local ADB remote-control commands. It does not expose a public service and should stay on the TravelPi/AP LAN or Tailscale. If hosting beyond that boundary later, add authentication first.
