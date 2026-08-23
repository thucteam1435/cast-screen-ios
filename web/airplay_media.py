from __future__ import annotations

import queue
import socket
import struct
import threading
import time
from typing import Generator, Optional

VIDEO_PORT = 5000
AUDIO_PORT = 5002


def _parse_rtp(data: bytes):
    if len(data) < 12:
        return None
    b0, b1, seq, ts, ssrc = struct.unpack('!BBHII', data[:12])
    version = b0 >> 6
    if version != 2:
        return None
    cc = b0 & 0x0F
    has_ext = bool(b0 & 0x10)
    marker = bool(b1 & 0x80)
    pt = b1 & 0x7F
    off = 12 + cc * 4
    if len(data) < off:
        return None
    if has_ext:
        if len(data) < off + 4:
            return None
        _, words = struct.unpack('!HH', data[off:off+4])
        off += 4 + words * 4
    if b0 & 0x20:
        if not data:
            return None
        pad = data[-1]
        if pad <= len(data) - off:
            data = data[:-pad]
    return seq, ts, marker, pt, data[off:]


class _H264Assembler:
    def __init__(self, emit):
        self.emit = emit
        self.ts: Optional[int] = None
        self.parts: list[bytes] = []
        self.fu: Optional[bytearray] = None
        self.sps: Optional[bytes] = None
        self.pps: Optional[bytes] = None
        self.key = False

    def _nal(self, nal: bytes):
        if not nal:
            return
        typ = nal[0] & 0x1F
        if typ == 7:
            self.sps = nal
        elif typ == 8:
            self.pps = nal
        elif typ == 5:
            self.key = True
        self.parts.append(b'\x00\x00\x00\x01' + nal)

    def push(self, ts: int, marker: bool, payload: bytes):
        if self.ts is None:
            self.ts = ts
        if ts != self.ts:
            self.flush()
            self.ts = ts
        if not payload:
            return
        typ = payload[0] & 0x1F
        if 1 <= typ <= 23:
            self._nal(payload)
        elif typ == 24:  # STAP-A
            i = 1
            while i + 2 <= len(payload):
                n = struct.unpack('!H', payload[i:i+2])[0]
                i += 2
                if i + n > len(payload):
                    break
                self._nal(payload[i:i+n])
                i += n
        elif typ == 28 and len(payload) >= 2:  # FU-A
            fu_ind = payload[0]
            fu_hdr = payload[1]
            start = bool(fu_hdr & 0x80)
            end = bool(fu_hdr & 0x40)
            ntype = fu_hdr & 0x1F
            if start:
                self.fu = bytearray([fu_ind & 0xE0 | ntype])
                self.fu.extend(payload[2:])
                if ntype == 5:
                    self.key = True
            elif self.fu is not None:
                self.fu.extend(payload[2:])
            if end and self.fu is not None:
                self._nal(bytes(self.fu))
                self.fu = None
        if marker:
            self.flush()

    def flush(self):
        if self.fu is not None:
            self.fu = None
        if self.parts and self.ts is not None:
            parts = list(self.parts)
            if self.key and self.sps and self.pps:
                prefix = [b'\x00\x00\x00\x01' + self.sps, b'\x00\x00\x00\x01' + self.pps]
                parts = prefix + parts
            payload = b''.join(parts)
            pts_us = int(self.ts * 1_000_000 / 90000)
            self.emit(payload, pts_us, self.key)
        self.parts.clear()
        self.key = False


class _RtpThread(threading.Thread):
    def __init__(self, port: int, callback, stop_event: threading.Event, audio=False):
        super().__init__(daemon=True)
        self.port = port
        self.callback = callback
        self.stop_event = stop_event
        self.audio = audio
        self.sock: Optional[socket.socket] = None

    def run(self):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(('127.0.0.1', self.port))
            s.settimeout(0.5)
            self.sock = s
            if self.audio:
                self._audio_loop(s)
            else:
                asm = _H264Assembler(self.callback)
                while not self.stop_event.is_set():
                    try:
                        data, _ = s.recvfrom(65536)
                    except socket.timeout:
                        continue
                    pkt = _parse_rtp(data)
                    if not pkt:
                        continue
                    _, ts, marker, _, payload = pkt
                    asm.push(ts, marker, payload)
                asm.flush()
        finally:
            try:
                if self.sock:
                    self.sock.close()
            except Exception:
                pass

    def _audio_loop(self, s: socket.socket):
        # UxPlay -artp sends L16, 44.1kHz stereo, S16BE.
        for_ = self.callback
        while not self.stop_event.is_set():
            try:
                data, _ = s.recvfrom(65536)
            except socket.timeout:
                continue
            pkt = _parse_rtp(data)
            if not pkt:
                continue
            _, ts, _, _, payload = pkt
            if payload:
                for_(payload, int(ts * 1_000_000 / 44100))


class AirplayMediaHub:
    def __init__(self, video_port: int = VIDEO_PORT, audio_port: int = AUDIO_PORT):
        self.video_port = video_port
        self.audio_port = audio_port
        self.stop_event = threading.Event()
        self.video_thread: Optional[_RtpThread] = None
        self.audio_thread: Optional[_RtpThread] = None
        self.video_clients: set[queue.Queue] = set()
        self.audio_clients: set[queue.Queue] = set()
        self.lock = threading.Lock()
        self.running = False
        self.video_bytes = 0
        self.video_frames = 0
        self.started_at = 0.0

    def start(self):
        if self.running:
            return
        self.stop_event.clear()
        self.running = True
        self.started_at = time.time()
        self.video_thread = _RtpThread(self.video_port, self._video_emit, self.stop_event, audio=False)
        self.audio_thread = _RtpThread(self.audio_port, self._audio_emit, self.stop_event, audio=True)
        self.video_thread.start()
        self.audio_thread.start()

    def stop(self):
        self.stop_event.set()
        with self.lock:
            clients = list(self.video_clients) + list(self.audio_clients)
            self.video_clients.clear()
            self.audio_clients.clear()
        for q in clients:
            try:
                q.put_nowait(None)
            except Exception:
                pass
        self.running = False

    def subscribe_video(self):
        q: queue.Queue = queue.Queue(maxsize=30)
        with self.lock:
            self.video_clients.add(q)
        return q

    def unsubscribe_video(self, q):
        with self.lock:
            self.video_clients.discard(q)

    def subscribe_audio(self):
        q: queue.Queue = queue.Queue(maxsize=60)
        with self.lock:
            self.audio_clients.add(q)
        return q

    def unsubscribe_audio(self, q):
        with self.lock:
            self.audio_clients.discard(q)

    def _video_emit(self, payload: bytes, pts_us: int, key: bool):
        # Frame: uint32 length + uint64 pts + uint8 flags + payload.
        body = struct.pack('!Q B', pts_us, 1 if key else 0) + payload
        packet = struct.pack('!I', len(body)) + body
        self.video_bytes += len(payload)
        self.video_frames += 1
        with self.lock:
            clients = list(self.video_clients)
        for q in clients:
            try:
                q.put_nowait(packet)
            except queue.Full:
                try:
                    q.get_nowait()
                except Exception:
                    pass
                try:
                    q.put_nowait(packet)
                except Exception:
                    pass

    def _audio_emit(self, payload: bytes, pts_us: int):
        body = struct.pack('!Q', pts_us) + payload
        packet = struct.pack('!I', len(body)) + body
        with self.lock:
            clients = list(self.audio_clients)
        for q in clients:
            try:
                q.put_nowait(packet)
            except queue.Full:
                try:
                    q.get_nowait()
                except Exception:
                    pass
                try:
                    q.put_nowait(packet)
                except Exception:
                    pass

    def stats(self):
        age = max(0.001, time.time() - self.started_at) if self.started_at else 0
        return {
            'running': self.running,
            'videoFrames': self.video_frames,
            'videoBytes': self.video_bytes,
            'avgVideoMbps': (self.video_bytes * 8 / age / 1e6) if age else 0,
        }
