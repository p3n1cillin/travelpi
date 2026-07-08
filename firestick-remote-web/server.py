from __future__ import annotations

import argparse
import json
import mimetypes
import os
import shutil
import socket
import subprocess
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

ROOT = Path(__file__).parent.resolve()
WEB_ROOT = ROOT / "web"

KEYS = {
    "up": "KEYCODE_DPAD_UP",
    "down": "KEYCODE_DPAD_DOWN",
    "left": "KEYCODE_DPAD_LEFT",
    "right": "KEYCODE_DPAD_RIGHT",
    "select": "KEYCODE_DPAD_CENTER",
    "back": "KEYCODE_BACK",
    "home": "KEYCODE_HOME",
    "menu": "KEYCODE_MENU",
    "play_pause": "KEYCODE_MEDIA_PLAY_PAUSE",
    "play": "KEYCODE_MEDIA_PLAY",
    "pause": "KEYCODE_MEDIA_PAUSE",
    "stop": "KEYCODE_MEDIA_STOP",
    "rewind": "KEYCODE_MEDIA_REWIND",
    "fast_forward": "KEYCODE_MEDIA_FAST_FORWARD",
    "previous": "KEYCODE_MEDIA_PREVIOUS",
    "next": "KEYCODE_MEDIA_NEXT",
    "volume_up": "KEYCODE_VOLUME_UP",
    "volume_down": "KEYCODE_VOLUME_DOWN",
    "mute": "KEYCODE_VOLUME_MUTE",
    "power": "KEYCODE_POWER",
    "search": "KEYCODE_SEARCH",
    "settings": "KEYCODE_SETTINGS",
    "recents": "KEYCODE_APP_SWITCH",
    "info": "KEYCODE_INFO",
    "captions": "KEYCODE_CAPTIONS",
    "channel_up": "KEYCODE_CHANNEL_UP",
    "channel_down": "KEYCODE_CHANNEL_DOWN",
    "page_up": "KEYCODE_PAGE_UP",
    "page_down": "KEYCODE_PAGE_DOWN",
    "delete": "KEYCODE_DEL",
    "enter": "KEYCODE_ENTER",
}


class RemoteError(Exception):
    def __init__(self, status: HTTPStatus, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


class FirestickRemote:
    def __init__(
        self,
        target: str = "",
        *,
        mock: bool = False,
        timeout: float = 8.0,
        port: int = 8787,
    ) -> None:
        self.target = target.strip()
        self.mock = mock
        self.timeout = timeout
        self.port = port
        self._connected = False
        self._shell: subprocess.Popen[str] | None = None
        self._shell_lock = threading.Lock()

    def health(self) -> dict[str, Any]:
        devices = self.devices()
        if self._connected and not self.mock:
            try:
                self._start_shell()
            except RemoteError:
                self._connected = False
        return {
            "ok": True,
            "mock": self.mock,
            "adb": shutil.which("adb") or "",
            "target": self.target,
            "devices": devices,
            "network": self.network(),
        }

    def network(self) -> dict[str, Any]:
        ips = self._local_ips()
        urls = []
        for ip in ips:
            if ip == "192.168.50.1":
                label = "Pi AP"
            elif ip.startswith("100."):
                label = "Tailscale"
            elif ip.startswith(("10.", "172.", "192.168.")):
                label = "Router LAN"
            else:
                label = "Network"
            urls.append({"label": label, "url": f"http://{ip}:{self.port}/", "ip": ip})
        hostname = socket.gethostname()
        urls.append({"label": "Local hostname", "url": f"http://{hostname}.local:{self.port}/", "ip": ""})
        return {"hostname": hostname, "ips": ips, "urls": urls}

    def discover(self) -> list[dict[str, str]]:
        found: dict[str, dict[str, str]] = {}
        for device in self.devices():
            serial = device["serial"]
            if ":" not in serial:
                continue
            found[serial] = {
                "target": serial,
                "label": self._device_label(serial, device),
                "state": device["state"],
                "source": "adb",
            }
        for lease in self._leases():
            target = f"{lease['ip']}:5555"
            if target in found or not self._tcp_open(lease["ip"], 5555):
                continue
            name = lease["name"] if lease["name"] != "*" else "Fire TV"
            found[target] = {
                "target": target,
                "label": f"{name} ({target})",
                "state": "available",
                "source": "network",
            }
        if self.target and self.target not in found:
            found[self.target] = {
                "target": self.target,
                "label": f"Configured Fire TV ({self.target})",
                "state": "configured",
                "source": "configured",
            }
        return sorted(
            found.values(),
            key=lambda item: (
                item["state"] != "device",
                item["source"] != "network",
                item["target"],
            ),
        )

    def devices(self) -> list[dict[str, str]]:
        if self.mock:
            return [
                {
                    "serial": self.target or "mock-firestick:5555",
                    "state": "device",
                    "model": "Fire_TV",
                }
            ]
        result = self._adb("devices")
        rows: list[dict[str, str]] = []
        for line in result["stdout"].splitlines()[1:]:
            parts = line.split()
            if len(parts) >= 2:
                row = {"serial": parts[0], "state": parts[1]}
                for item in parts[2:]:
                    if ":" in item:
                        key, value = item.split(":", 1)
                        row[key] = value
                rows.append(row)
        self._connected = bool(
            self.target and any(row["serial"] == self.target and row["state"] == "device" for row in rows)
        )
        return rows

    @staticmethod
    def _device_label(serial: str, device: dict[str, str]) -> str:
        model = device.get("model", "Fire_TV").replace("_", " ")
        return f"{model} ({serial})"

    @staticmethod
    def _leases() -> list[dict[str, str]]:
        leases: list[dict[str, str]] = []
        paths = (
            Path("/var/lib/misc/dnsmasq.leases"),
            Path("/var/lib/NetworkManager/dnsmasq.leases"),
        )
        for path in paths:
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except OSError:
                continue
            for line in lines:
                parts = line.split()
                if len(parts) >= 4:
                    leases.append({"mac": parts[1], "ip": parts[2], "name": parts[3]})
        return leases

    @staticmethod
    def _tcp_open(host: str, port: int, timeout: float = 0.18) -> bool:
        try:
            with socket.create_connection((host, port), timeout=timeout):
                return True
        except OSError:
            return False

    @staticmethod
    def _local_ips() -> list[str]:
        try:
            output = subprocess.run(
                ["hostname", "-I"],
                check=False,
                capture_output=True,
                text=True,
                timeout=2,
            ).stdout
        except (OSError, subprocess.TimeoutExpired):
            return []
        return [item for item in output.split() if "." in item and not item.startswith("127.")]

    def connect(self, target: str | None = None) -> dict[str, Any]:
        if target is not None:
            self.target = target.strip()
        if not self.target:
            raise RemoteError(HTTPStatus.BAD_REQUEST, "Firestick target is required")
        self._close_shell()
        result = self._adb("connect", self.target, include_target=False)
        output = f"{result['stdout']}\n{result['stderr']}".casefold()
        self._connected = "connected" in output or "already connected" in output
        if "unauthorized" in output:
            raise RemoteError(HTTPStatus.FORBIDDEN, "Firestick is waiting for ADB authorization")
        if not self._connected:
            raise RemoteError(HTTPStatus.BAD_GATEWAY, (result["stdout"] or result["stderr"]).strip())
        self._start_shell()
        return result

    def key(self, name: str, *, longpress: bool = False) -> dict[str, Any]:
        keycode = KEYS.get(name)
        if not keycode:
            raise RemoteError(HTTPStatus.BAD_REQUEST, f"Unknown remote button: {name}")
        option = " --longpress" if longpress else ""
        return self._shell_command(f"input keyevent{option} {keycode}", label=keycode)

    def text(self, value: str) -> dict[str, Any]:
        text = value.strip()
        if not text:
            raise RemoteError(HTTPStatus.BAD_REQUEST, "Text is required")
        escaped = text.replace("%", "%25").replace(" ", "%s")
        return self._shell_command(f"input text {escaped}", label="text")

    def launch(self, package: str) -> dict[str, Any]:
        package = package.strip()
        if not package:
            raise RemoteError(HTTPStatus.BAD_REQUEST, "Package name is required")
        self._ensure_connected()
        return self._adb("shell", "monkey", "-p", package, "-c", "android.intent.category.LAUNCHER", "1")

    def apps(self) -> list[dict[str, str]]:
        defaults = [
            {"name": "Jellyfin", "package": "org.jellyfin.androidtv"},
            {"name": "Prime Video", "package": "com.amazon.amazonvideo.livingroom"},
            {"name": "Netflix", "package": "com.netflix.ninja"},
            {"name": "YouTube", "package": "com.google.android.youtube.tv"},
            {"name": "Disney+", "package": "com.disney.disneyplus"},
            {"name": "Fire TV Home", "package": "com.amazon.tv.launcher"},
        ]
        if self.mock:
            return defaults
        try:
            result = self._adb("shell", "pm", "list", "packages")
        except RemoteError:
            return defaults
        installed = {line.partition(":")[2].strip() for line in result["stdout"].splitlines()}
        return [app for app in defaults if app["package"] in installed] or defaults

    def warm(self) -> None:
        if self.mock or not self.target:
            return
        try:
            self.connect()
        except RemoteError:
            self._connected = False

    def _ensure_connected(self) -> None:
        if self.target and not self._connected:
            self.connect()

    def _shell_command(self, command: str, *, label: str) -> dict[str, Any]:
        if self.mock:
            return {"command": ["adb", "-s", self.target, "shell"], "stdin": command, "returncode": 0}
        self._ensure_connected()
        for attempt in range(2):
            with self._shell_lock:
                self._start_shell_locked()
                assert self._shell is not None and self._shell.stdin is not None
                try:
                    self._shell.stdin.write(f"{command}\n")
                    self._shell.stdin.flush()
                    break
                except (BrokenPipeError, OSError):
                    self._close_shell_locked()
                    self._connected = False
            if attempt == 0:
                self._ensure_connected()
            else:
                raise RemoteError(HTTPStatus.BAD_GATEWAY, "ADB shell is not accepting commands")
        else:
            raise RemoteError(HTTPStatus.BAD_GATEWAY, "ADB shell is not accepting commands")
        return {
            "command": ["adb", "-s", self.target, "shell"],
            "stdin": command,
            "label": label,
            "returncode": 0,
        }

    def _start_shell(self) -> None:
        with self._shell_lock:
            self._start_shell_locked()

    def _start_shell_locked(self) -> None:
        if not self.target:
            raise RemoteError(HTTPStatus.BAD_REQUEST, "Firestick target is required")
        if shutil.which("adb") is None:
            raise RemoteError(HTTPStatus.SERVICE_UNAVAILABLE, "adb is not installed")
        if self._shell and self._shell.poll() is None:
            return
        self._shell = subprocess.Popen(
            ["adb", "-s", self.target, "shell"],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
            bufsize=1,
        )

    def _close_shell(self) -> None:
        with self._shell_lock:
            self._close_shell_locked()

    def _close_shell_locked(self) -> None:
        if self._shell and self._shell.poll() is None:
            self._shell.terminate()
        self._shell = None

    def _adb(self, *args: str, include_target: bool = True) -> dict[str, Any]:
        command = ["adb"]
        if include_target and self.target:
            command.extend(["-s", self.target])
        command.extend(args)
        if self.mock:
            return {"command": command, "stdout": "mock ok\n", "stderr": "", "returncode": 0}
        if shutil.which("adb") is None:
            raise RemoteError(HTTPStatus.SERVICE_UNAVAILABLE, "adb is not installed")
        try:
            result = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )
        except subprocess.TimeoutExpired as exc:
            raise RemoteError(HTTPStatus.GATEWAY_TIMEOUT, "adb command timed out") from exc
        payload = {
            "command": command,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode,
        }
        if result.returncode != 0:
            message = (result.stderr or result.stdout or "adb command failed").strip()
            raise RemoteError(HTTPStatus.BAD_GATEWAY, message)
        return payload


class Application:
    def __init__(self, remote: FirestickRemote) -> None:
        self.remote = remote

    def handle(self, method: str, raw_path: str, body: bytes = b"") -> tuple[int, str, bytes]:
        parsed = urlparse(raw_path)
        path = parsed.path.rstrip("/") or "/"
        try:
            if path.startswith("/api"):
                return self._json(self._api(method, path, body))
            if method != "GET":
                raise RemoteError(HTTPStatus.METHOD_NOT_ALLOWED, "Only GET is supported here")
            return self._static(path)
        except RemoteError as exc:
            return self._json({"error": exc.message}, exc.status)
        except Exception as exc:
            return self._json({"error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def _api(self, method: str, path: str, body: bytes) -> Any:
        if path == "/api/health" and method == "GET":
            return self.remote.health()
        if path == "/api/discover" and method == "GET":
            return self.remote.discover()
        if path == "/api/network" and method == "GET":
            return self.remote.network()
        if path == "/api/apps" and method == "GET":
            return self.remote.apps()
        if path == "/api/key" and method == "POST":
            payload = self._payload(body)
            return self.remote.key(str(payload.get("key", "")), longpress=bool(payload.get("long")))
        if path == "/api/text" and method == "POST":
            return self.remote.text(str(self._payload(body).get("text", "")))
        if path == "/api/connect" and method == "POST":
            return self.remote.connect(str(self._payload(body).get("target", "")))
        if path == "/api/launch" and method == "POST":
            return self.remote.launch(str(self._payload(body).get("package", "")))
        raise RemoteError(HTTPStatus.NOT_FOUND, f"No route for {method} {path}")

    @staticmethod
    def _payload(body: bytes) -> dict[str, Any]:
        if not body:
            return {}
        try:
            payload = json.loads(body.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise RemoteError(HTTPStatus.BAD_REQUEST, "Request body must be valid JSON") from exc
        if not isinstance(payload, dict):
            raise RemoteError(HTTPStatus.BAD_REQUEST, "Request body must be a JSON object")
        return payload

    @staticmethod
    def _json(payload: Any, status: HTTPStatus = HTTPStatus.OK) -> tuple[int, str, bytes]:
        return (
            int(status),
            "application/json; charset=utf-8",
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
        )

    def _static(self, path: str) -> tuple[int, str, bytes]:
        relative = "index.html" if path == "/" else unquote(path.lstrip("/"))
        target = (WEB_ROOT / relative).resolve()
        if WEB_ROOT not in target.parents or not target.is_file():
            target = WEB_ROOT / "index.html"
        content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        return HTTPStatus.OK, content_type, target.read_bytes()


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    application: Application

    def setup(self) -> None:
        super().setup()
        self.connection.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

    def do_GET(self) -> None:
        self._handle()

    def do_POST(self) -> None:
        self._handle()

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _handle(self) -> None:
        parsed = urlparse(self.path)
        if self.command == "GET" and parsed.path.startswith("/k/"):
            try:
                key = unquote(parsed.path.removeprefix("/k/"))
                longpress = parsed.query in {"long=1", "long=true"}
                self.application.remote.key(key, longpress=longpress)
                self.send_response(HTTPStatus.NO_CONTENT)
                self.send_header("Content-Length", "0")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Connection", "keep-alive")
                self.end_headers()
            except RemoteError as exc:
                payload = json.dumps({"error": exc.message}, separators=(",", ":")).encode()
                self.send_response(exc.status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(payload)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(payload)
            return
        length = int(self.headers.get("content-length", "0") or "0")
        body = self.rfile.read(length) if length else b""
        status, content_type, payload = self.application.handle(self.command, self.path, body)
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Connection", "keep-alive")
        self.end_headers()
        self.wfile.write(payload)


def build_server(host: str, port: int, remote: FirestickRemote) -> ThreadingHTTPServer:
    Handler.application = Application(remote)
    return ThreadingHTTPServer((host, port), Handler)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the Firestick remote web app")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--target", default=os.environ.get("FIRESTICK_TARGET", ""))
    parser.add_argument("--mock", action="store_true", default=os.environ.get("FIRESTICK_REMOTE_MOCK") == "1")
    args = parser.parse_args()
    remote = FirestickRemote(args.target, mock=args.mock, port=args.port)
    threading.Thread(target=remote.warm, daemon=True, name="adb-warmup").start()
    server = build_server(args.host, args.port, remote)
    print(f"Firestick remote listening on http://{args.host}:{server.server_port}/")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
