"""
Zero-Dependency Local Development & Testing Server for Cast Screen Web
Serves static assets and provides lightweight HTTP/SSE Signaling using only Python standard library.
"""
import os
import sys
import json
import socket
import time
import threading
from http.server import SimpleHTTPRequestHandler, HTTPServer, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

WEB_DIR = os.path.dirname(os.path.abspath(__file__))

# In-memory message queues for room signaling: roomId -> list of messages
rooms = {}
rooms_lock = threading.Lock()

def _cleanup_rooms():
    """Background thread: remove stale messages and empty rooms every 60 seconds.
    This prevents memory growth when many users create rooms without cleaning up."""
    while True:
        time.sleep(60)
        now = time.time()
        with rooms_lock:
            stale_rooms = []
            for room_id, msgs in rooms.items():
                # Drop messages older than 60 seconds
                rooms[room_id] = [m for m in msgs if now - m["ts"] < 60]
                # Mark empty rooms for deletion
                if not rooms[room_id]:
                    stale_rooms.append(room_id)
            for room_id in stale_rooms:
                del rooms[room_id]

_cleanup_thread = threading.Thread(target=_cleanup_rooms, daemon=True)
_cleanup_thread.start()

class CastScreenWebHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=WEB_DIR, **kwargs)

    def do_GET(self):
        parsed = urlparse(self.path)
        
        # 1. Long-polling / Event Stream Signaling (/signal/poll)
        if parsed.path == "/signal/poll":
            params = parse_qs(parsed.query)
            room_id = params.get("room", ["default"])[0]
            role = params.get("role", ["receiver"])[0]
            since = float(params.get("since", [0])[0])

            # Wait up to 5 seconds for new messages
            deadline = time.time() + 5.0
            new_msgs = []
            
            while time.time() < deadline:
                with rooms_lock:
                    room_list = rooms.get(room_id, [])
                    new_msgs = [m for m in room_list if m["ts"] > since and m["from"] != role]
                if new_msgs:
                    break
                time.sleep(0.1)

            resp_data = json.dumps(new_msgs).encode("utf-8")
            try:
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(resp_data)))
                self.end_headers()
                self.wfile.write(resp_data)
            except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
                pass
            return

        # Fallback to standard static file serving
        return super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        
        # 2. Post signaling message (/signal/send)
        if parsed.path == "/signal/send":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            try:
                data = json.loads(body.decode("utf-8"))
                room_id = data.get("roomId", "default")
                role = data.get("from", "receiver")
                
                with rooms_lock:
                    if room_id not in rooms:
                        rooms[room_id] = []
                    # Add message with timestamp
                    rooms[room_id].append({
                        "data": data,
                        "from": role,
                        "ts": time.time()
                    })
                    # Keep at most last 50 messages per room
                    if len(rooms[room_id]) > 50:
                        rooms[room_id] = rooms[room_id][-50:]

                resp_data = b'{"status":"ok"}'
                try:
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.send_header("Content-Length", str(len(resp_data)))
                    self.end_headers()
                    self.wfile.write(resp_data)
                except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
                    pass
            except Exception as e:
                err_data = str(e).encode("utf-8")
                try:
                    self.send_response(400)
                    self.send_header("Content-Type", "text/plain; charset=utf-8")
                    self.send_header("Content-Length", str(len(err_data)))
                    self.end_headers()
                    self.wfile.write(err_data)
                except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
                    pass
            return

        self.send_response(404)
        self.end_headers()

    def do_OPTIONS(self):
        """Handle CORS preflight — must respond immediately with 200 and Content-Length 0."""
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Requested-With")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def end_headers(self):
        """Inject CORS + no-cache headers automatically so clients always get fresh code."""
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()

def get_all_ips():
    ips = []
    try:
        import psutil
        for iface, addrs in psutil.net_if_addrs().items():
            for addr in addrs:
                if addr.family == socket.AF_INET and not addr.address.startswith(("127.", "169.254.")):
                    ips.append((iface, addr.address))
    except Exception:
        pass
    if not ips:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ips.append(("Mạng", s.getsockname()[0]))
            s.close()
        except Exception:
            ips.append(("Local", "127.0.0.1"))
    return ips

def ensure_ssl_cert():
    cert_file = os.path.join(WEB_DIR, "cert.pem")
    key_file = os.path.join(WEB_DIR, "key.pem")
    if os.path.exists(cert_file) and os.path.exists(key_file):
        return cert_file, key_file
    try:
        from cryptography import x509
        from cryptography.x509.oid import NameOID
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        import datetime, ipaddress

        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        subject = issuer = x509.Name([
            x509.NameAttribute(NameOID.COUNTRY_NAME, 'VN'),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, 'CastScreen'),
            x509.NameAttribute(NameOID.COMMON_NAME, 'CastScreen Local'),
        ])

        # ISSUE-03 FIX: Dynamically detect all local IPs instead of hard-coding
        # two specific addresses. This ensures the cert is valid on any network.
        san_entries = [
            x509.DNSName('localhost'),
            x509.IPAddress(ipaddress.IPv4Address('127.0.0.1')),
        ]
        for _, ip_addr in get_all_ips():
            try:
                san_entries.append(x509.IPAddress(ipaddress.IPv4Address(ip_addr)))
            except Exception:
                pass

        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(datetime.datetime.utcnow())
            .not_valid_after(datetime.datetime.utcnow() + datetime.timedelta(days=365))
            .add_extension(
                x509.SubjectAlternativeName(san_entries),
                critical=False,
            )
            .sign(key, hashes.SHA256())
        )
        with open(key_file, 'wb') as f:
            f.write(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL, serialization.NoEncryption()))
        with open(cert_file, 'wb') as f:
            f.write(cert.public_bytes(serialization.Encoding.PEM))
        return cert_file, key_file
    except Exception as e:
        print('[SSL] Cannot auto-generate cert:', e)
        return None, None

def run_server(port=8080, enable_ssl=False):
    import ssl
    all_ips = get_all_ips()
    # FIX: Use ThreadingHTTPServer so long-poll /signal/poll does NOT block
    # the entire server. Without threading, sender's /signal/send can never
    # be processed while receiver is waiting in a 5-second long-poll.
    server = ThreadingHTTPServer(("0.0.0.0", port), CastScreenWebHandler)
    use_https = False
    
    if enable_ssl:
        cert_file, key_file = ensure_ssl_cert()
        if cert_file and key_file:
            try:
                ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
                ctx.load_cert_chain(certfile=cert_file, keyfile=key_file)
                server.socket = ctx.wrap_socket(server.socket, server_side=True)
                use_https = True
            except Exception as e:
                print('[SSL] Failed to wrap HTTPS socket:', e)

    proto = "https" if use_https else "http"

    print("=" * 68)
    print(f"🚀 CAST SCREEN PRO — WEB PLATFORM ({proto.upper()} SERVER)")
    print("=" * 68)
    print(f"💻 Trên MÁY TÍNH (Mở trình duyệt):")
    print(f"   👉 {proto}://localhost:{port}")
    print()
    print(f"📱 Trên ĐIỆN THOẠI (iPhone / Android cùng Wi-Fi):")
    for name, ip in all_ips:
        print(f"   👉 {proto}://{ip}:{port}")
    print("=" * 68)
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nĐã dừng Web Server.")

if __name__ == "__main__":
    use_ssl = "--ssl" in sys.argv
    port = 8443 if use_ssl else (int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 8080)
    run_server(port, enable_ssl=use_ssl)
