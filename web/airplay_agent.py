import json
import os
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

HOST = "127.0.0.1"
PORT = int(os.environ.get("CASTSCREEN_AIRPLAY_PORT", "8765"))
DENY_COOLDOWN_SECONDS = 12
LEASE_TIMEOUT_SECONDS = 7

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
}
agent_token = secrets.token_urlsafe(24)
airplay = AirPlayServer()


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


def _touch_lease_locked():
    state["lease_active"] = True
    state["last_lease"] = time.time()


def start_airplay():
    with state_lock:
        state["room_active"] = True
        # Start the lease immediately. The Host room's /status polling keeps it alive.
        _touch_lease_locked()

    if airplay.is_running:
        with state_lock:
            state["running"] = True
        return True

    config = {
        "server_name": "CastScreen-PC",
        "resolution": "1920x1080",
        "fps": 60,
        "ultra_low_latency": True,
        "enable_audio": True,
    }
    ok = airplay.start(config)
    with state_lock:
        state["running"] = bool(ok)
        state["last_error"] = None if ok else "Không thể khởi động UxPlay/AirPlay"
        if not ok:
            state["room_active"] = False
            state["lease_active"] = False
            state["last_lease"] = 0.0
    return ok


def stop_airplay(clear_room=True):
    try:
        # AirPlayServer.stop() tears down UxPlay AND the mDNS advertisement.
        airplay.stop()
    finally:
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
            start_airplay()
        with state_lock:
            state["device"] = device
    return {"ok": True, "allowed": bool(allow)}


class Handler(BaseHTTPRequestHandler):
    server_version = "CastScreenAirPlayAgent/1.6"

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
        return not token or secrets.compare_digest(token, agent_token)

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/airplay/status":
            with state_lock:
                # The Host room already polls /airplay/status. Treat that poll as
                # the room heartbeat so closing the page automatically expires
                # the AirPlay receiver without requiring page-unload reliability.
                if state["room_active"]:
                    _touch_lease_locked()
                payload = dict(state)
            payload["token"] = agent_token
            payload["port"] = PORT
            payload["host"] = HOST
            payload["leaseTimeoutSeconds"] = LEASE_TIMEOUT_SECONDS
            self._json(200, payload)
            return
        if parsed.path == "/health":
            self._json(200, {"ok": True, "service": "airplay-agent", "version": "1.6"})
            return
        self._json(404, {"ok": False, "error": "not-found"})

    def do_POST(self):
        if not self._authorized():
            self._json(403, {"ok": False, "error": "forbidden"})
            return
        parsed = urlparse(self.path)
        if parsed.path == "/airplay/start":
            self._json(200, {"ok": start_airplay()})
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
    print("CAST SCREEN PRO — LOCAL AIRPLAY AGENT")
    print(f"Control API: http://{HOST}:{PORT}")
    print("AirPlay + mDNS: starts only while a Cast Screen Host room is active")
    print("Room heartbeat timeout: %ss" % LEASE_TIMEOUT_SECONDS)
    print("When the room closes or the browser disappears, UxPlay and mDNS stop automatically.")
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
