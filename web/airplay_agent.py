import json
import os
import queue
import secrets
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from engine.airplay_server import AirPlayServer
from web.airplay_media import AirplayMediaHub

HOST = "127.0.0.1"
PORT = int(os.environ.get("CASTSCREEN_AIRPLAY_PORT", "8765"))
DENY_COOLDOWN_SECONDS = 12
LEASE_TIMEOUT_SECONDS = 7
ALLOWED_RESOLUTIONS = {"1280x720", "1920x1080"}
ALLOWED_FPS = {30, 60}

state_lock = threading.Lock()
state = {
    "running": False,
    "airplay_connected": False,
    "device": None,
    "pending_approval": False,
    "approved": False,
    "last_event": 0.0,
    "last_error": None,
    "denied_until": 0.0,
    "lease_active": False,
    "last_lease": 0.0,
    "room_active": False,
    "resolution": "1920x1080",
    "fps": 60,
    "sharpen": 0,
}

agent_token = secrets.token_urlsafe(24)
airplay = AirPlayServer()
media = AirplayMediaHub(video_port=5000, audio_port=5002)


def _set_event(device=None, connected=False, pending=False):
    with state_lock:
        state["airplay_connected"] = bool(connected)
        state["device"] = device
        state["pending_approval"] = bool(pending)
        state["last_event"] = time.time()


def _on_connected(device):
    name = device or "iPhone / iPad"
    now = time.time()
    with state_lock:
        approved = bool(state["approved"])
        denied_until = float(state.get("denied_until", 0))
    if approved:
        _set_event(name, connected=True, pending=False)
    elif now < denied_until:
        _set_event(name, connected=True, pending=False)
    else:
        _set_event(name, connected=True, pending=True)


def _on_disconnected():
    with state_lock:
        state["approved"] = False
    _set_event(None, connected=False, pending=False)


airplay.on_client_connected = _on_connected
airplay.on_client_disconnected = _on_disconnected


def _normalize_config(data: dict | None = None):
    data = data or {}
    resolution = str(data.get("resolution", "1920x1080"))
    if resolution not in ALLOWED_RESOLUTIONS:
        resolution = "1920x1080"
    try:
        fps = int(data.get("fps", 60))
    except (TypeError, ValueError):
        fps = 60
    if fps not in ALLOWED_FPS:
        fps = 60
    try:
        sharpen = int(float(data.get("sharpen", 0)))
    except (TypeError, ValueError):
        sharpen = 0
    sharpen = max(0, min(100, sharpen))
    return {"resolution": resolution, "fps": fps, "sharpen": sharpen}


def _web_uxplay_command(config: dict):
    """Headless UxPlay command: AirPlay -> local RTP -> browser media hub."""
    exe_path = airplay.find_executable()
    if not exe_path:
        raise FileNotFoundError("Không tìm thấy uxplay-windows.exe trong engine/bin")
    resolution = config["resolution"]
    fps = config["fps"]
    return [
        exe_path,
        "-n", "CastScreen-PC",
        "-fps", str(fps),
        "-nohold",
        "-reset", "3",
        "-nofreeze",
        "-s", f"{resolution}@{fps}",
        "-vd", "d3d11h264dec",
        "-vc", "d3d11convert",
        "-vs", "0",
        "-vsync", "no",
        "-vrtp", "config-interval=1 ! udpsink host=127.0.0.1 port=5000 sync=false async=false",
        "-artp", "udpsink host=127.0.0.1 port=5002 sync=false async=false",
    ]


# Replace the legacy arguments.txt-only command construction for the web receiver.
airplay.build_command = _web_uxplay_command
# Do not generate legacy renderer arguments that could reintroduce a visible UxPlay window.
airplay.sync_appdata_config = lambda config: None


def _touch_lease_locked():
    state["lease_active"] = True
    state["last_lease"] = time.time()


def start_airplay(config: dict | None = None):
    cfg = _normalize_config(config)
    with state_lock:
        state["room_active"] = True
        state["resolution"] = cfg["resolution"]
        state["fps"] = cfg["fps"]
        state["sharpen"] = cfg["sharpen"]
        _touch_lease_locked()

    if airplay.is_running:
        # Quality changes require a restart of the UxPlay process so its source mode changes apply.
        try:
            airplay.stop()
        except Exception:
            pass

    try:
        media.stop()
        media.start()
    except Exception as exc:
        with state_lock:
            state["last_error"] = f"Không thể khởi động media hub: {exc}"
        return False

    ok = airplay.start({
        "server_name": "CastScreen-PC",
        "resolution": cfg["resolution"],
        "fps": cfg["fps"],
        "ultra_low_latency": True,
        "enable_audio": True,
    })
    with state_lock:
        state["running"] = bool(ok)
        state["last_error"] = None if ok else "Không thể khởi động UxPlay/AirPlay"
        if not ok:
            state["room_active"] = False
            state["lease_active"] = False
            state["last_lease"] = 0.0
            media.stop()
    return ok


def stop_airplay(clear_room=True):
    try:
        airplay.stop()
    finally:
        media.stop()
        with state_lock:
            state["running"] = False
            state["approved"] = False
            state["airplay_connected"] = False
            state["pending_approval"] = False
            state["device"] = None
            state["last_event"] = time.time()
            if clear_room:
                state["room_active"] = False
                state["lease_active"] = False
                state["last_lease"] = 0.0


def touch_lease():
    with state_lock:
        if not state["room_active"]:
            return {"ok": False, "leaseTimeoutSeconds": LEASE_TIMEOUT_SECONDS, "roomActive": False}
        _touch_lease_locked()
    return {"ok": True, "leaseTimeoutSeconds": LEASE_TIMEOUT_SECONDS, "roomActive": True}


def revoke_lease():
    with state_lock:
        state["lease_active"] = False
        state["last_lease"] = 0.0
    stop_airplay(clear_room=True)
    return {"ok": True, "airplayActive": False, "roomActive": False}


def _lease_watchdog():
    while True:
        time.sleep(1.0)
        with state_lock:
            active = bool(state["lease_active"])
            last = float(state["last_lease"] or 0.0)
        if active and last and time.time() - last > LEASE_TIMEOUT_SECONDS:
            print("[CastScreen AirPlay Agent] Host room heartbeat expired; stopping AirPlay and mDNS advertisement.")
            revoke_lease()


def authorize(allow: bool):
    with state_lock:
        connected = bool(state["airplay_connected"])
        device = state.get("device") or "iPhone / iPad"
        state["approved"] = bool(allow)
        state["pending_approval"] = False
        if not allow:
            state["denied_until"] = time.time() + DENY_COOLDOWN_SECONDS
    if not allow and connected:
        with state_lock:
            room_active = bool(state["room_active"])
        stop_airplay(clear_room=False)
        if room_active:
            start_airplay({"resolution": state["resolution"], "fps": state["fps"], "sharpen": state["sharpen"]})
        with state_lock:
            state["device"] = device
    return {"ok": True, "allowed": bool(allow)}


def _stream_queue(handler, q, content_type):
    handler.send_response(200)
    handler._cors()
    handler.send_header("Content-Type", content_type)
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("Connection", "close")
    handler.send_header("Transfer-Encoding", "chunked")
    handler.end_headers()
    try:
        while True:
            try:
                packet = q.get(timeout=1.0)
            except queue.Empty:
                with state_lock:
                    active = state["room_active"] and state["running"]
                if not active:
                    break
                continue
            if packet is None:
                break
            chunk_head = f"{len(packet):X}\r\n".encode("ascii")
            handler.wfile.write(chunk_head)
            handler.wfile.write(packet)
            handler.wfile.write(b"\r\n")
            handler.wfile.flush()
    except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
        pass


class Handler(BaseHTTPRequestHandler):
    server_version = "CastScreenAirPlayAgent/2.0"
    protocol_version = "HTTP/1.1"

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-CastScreen-Agent-Token")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Private-Network", "true")
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")

    def _json(self, status, payload):
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self._cors()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _authorized(self):
        token = self.headers.get("X-CastScreen-Agent-Token", "")
        return bool(token) and secrets.compare_digest(token, agent_token)

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/airplay/status":
            with state_lock:
                if state["room_active"]:
                    _touch_lease_locked()
                payload = dict(state)
            payload["token"] = agent_token
            payload["port"] = PORT
            payload["host"] = HOST
            payload["leaseTimeoutSeconds"] = LEASE_TIMEOUT_SECONDS
            payload["media"] = media.stats()
            self._json(200, payload)
            return
        if parsed.path == "/health":
            self._json(200, {"ok": True, "service": "airplay-agent", "version": "2.0", "media": media.stats()})
            return
        if parsed.path in ("/airplay/video", "/airplay/audio"):
            if not self._authorized():
                self._json(403, {"ok": False, "error": "forbidden"})
                return
            with state_lock:
                active = bool(state["room_active"] and state["running"])
            if not active:
                self._json(409, {"ok": False, "error": "room-inactive"})
                return
            q = media.subscribe_video() if parsed.path.endswith("/video") else media.subscribe_audio()
            try:
                _stream_queue(self, q, "application/octet-stream")
            finally:
                if parsed.path.endswith("/video"):
                    media.unsubscribe_video(q)
                else:
                    media.unsubscribe_audio(q)
            return
        self._json(404, {"ok": False, "error": "not-found"})

    def do_POST(self):
        if not self._authorized():
            self._json(403, {"ok": False, "error": "forbidden"})
            return
        parsed = urlparse(self.path)
        if parsed.path == "/airplay/start":
            length = int(self.headers.get("Content-Length", "0") or 0)
            body = self.rfile.read(length) if length else b"{}"
            try:
                data = json.loads(body.decode("utf-8"))
            except Exception:
                data = {}
            self._json(200, {"ok": start_airplay(data)})
            return
        if parsed.path == "/airplay/stop":
            self._json(200, revoke_lease())
            return
        if parsed.path == "/airplay/lease":
            self._json(200, touch_lease())
            return
        if parsed.path == "/airplay/authorize":
            length = int(self.headers.get("Content-Length", "0") or 0)
            body = self.rfile.read(length) if length else b"{}"
            try:
                data = json.loads(body.decode("utf-8"))
            except Exception:
                data = {}
            self._json(200, authorize(bool(data.get("allow"))))
            return
        self._json(404, {"ok": False, "error": "not-found"})

    def log_message(self, fmt, *args):
        print("[CastScreen AirPlay Agent] " + fmt % args)


def main():
    threading.Thread(target=_lease_watchdog, daemon=True).start()
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print("=" * 64)
    print("CAST SCREEN PRO — LOCAL AIRPLAY AGENT 2.0")
    print(f"Control API: http://{HOST}:{PORT}")
    print("AirPlay + mDNS: starts only while a Cast Screen Host room is active")
    print("Headless RTP media: video=127.0.0.1:5000, audio=127.0.0.1:5002")
    print("Room heartbeat timeout: %ss" % LEASE_TIMEOUT_SECONDS)
    print("When the room closes or the browser disappears, UxPlay, RTP and mDNS stop automatically.")
    print("Packaged mode: no Python is required on the user's PC.")
    print("=" * 64)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        revoke_lease()
        server.server_close()


if __name__ == "__main__":
    main()
