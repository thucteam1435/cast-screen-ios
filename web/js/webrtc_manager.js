/**
 * Cast Screen WebRTC manager.
 *
 * PeerJS is used only for rendezvous/control. Media is configured with no
 * STUN/TURN servers so WebRTC prefers direct LAN host candidates.
 * One host + one client per room, with host heartbeat and two-way media.
 */
class WebRTCManager {
    constructor(options = {}) {
        this.role = options.role === 'host' ? 'host' : 'client';
        this.isHost = this.role === 'host';
        this.roomId = String(options.roomId || '').replace(/[^a-zA-Z0-9_-]/g, '').slice(0, 40);
        if (!this.roomId) throw new Error('roomId is required');

        this.onStream = options.onStream || null;
        this.onStreamEnded = options.onStreamEnded || null;
        this.onStatusChange = options.onStatusChange || null;
        this.onMetrics = options.onMetrics || null;
        this.onPeerCountChange = options.onPeerCountChange || null;

        this.peer = null;
        this.peerId = '';
        this.control = null;
        this.remotePeerId = '';
        this.outgoingCall = null;
        this.incomingCalls = new Set();
        this.localStream = null;
        this.remoteStreams = new Map();
        this.statsTimer = null;
        this.heartbeatTimer = null;
        this.clientWatchdog = null;
        this.lastHeartbeat = 0;
        this.closed = false;
        this.clientConnected = false;
        this.roomReady = false;

        this.rtcConfig = {
            iceServers: [],
            iceCandidatePoolSize: 0,
            sdpSemantics: 'unified-plan'
        };
    }

    get hostPeerId() {
        return `castscreen-room-${this.roomId}-host`;
    }

    get hasPeer() {
        return !!(this.control?.open && this.remotePeerId);
    }

    // Compatibility with existing room pages.
    connectSignaling() {
        return this.connect();
    }

    connect() {
        if (this.closed) return;
        if (typeof window.Peer !== 'function') {
            this._setStatus('FAILED', 'Không tải được PeerJS — hãy tải lại trang');
            return;
        }
        this._setStatus('CONNECTING', this.isHost ? 'Đang tạo phòng…' : 'Đang kiểm tra phòng…');
        if (this.isHost) this._createHostPeer();
        else this._createClientPeer();
    }

    _createHostPeer() {
        this._destroyPeerOnly();
        const peer = new Peer(this.hostPeerId, { config: this.rtcConfig, debug: 0 });
        this.peer = peer;
        this.peerId = this.hostPeerId;

        peer.on('open', id => {
            if (this.closed) return;
            this.peerId = id || this.hostPeerId;
            this.roomReady = true;
            this._setStatus('WAITING', 'Phòng đã sẵn sàng — đang chờ thiết bị thứ hai');
        });
        peer.on('connection', conn => this._acceptClient(conn));
        peer.on('call', call => this._handleIncomingCall(call));
        peer.on('error', err => {
            if (this.closed) return;
            console.warn('[CastScreen][Host]', err?.type || err);
            this._setStatus('FAILED', err?.type === 'unavailable-id' ? 'Mã phòng đang được sử dụng' : 'Không thể tạo phòng');
        });
        peer.on('disconnected', () => {
            if (!this.closed) this._setStatus('FAILED', 'Mất kết nối dịch vụ điều phối');
        });
    }

    _createClientPeer() {
        this._destroyPeerOnly();
        const id = `castscreen-client-${Math.random().toString(36).slice(2, 11)}`;
        const peer = new Peer(id, { config: this.rtcConfig, debug: 0 });
        this.peer = peer;
        this.peerId = id;

        peer.on('open', () => this._connectToHost());
        peer.on('call', call => this._handleIncomingCall(call));
        peer.on('error', err => {
            if (this.closed) return;
            console.warn('[CastScreen][Client]', err?.type || err);
            if (err?.type === 'peer-unavailable' || err?.type === 'unavailable-id') {
                this._setStatus('ROOM_NOT_FOUND', 'Phòng không tồn tại hoặc đã đóng');
            } else {
                this._setStatus('FAILED', 'Không thể tham gia phòng');
            }
        });
        peer.on('disconnected', () => {
            if (!this.closed) this._setStatus('HOST_GONE', 'Mất kết nối với chủ phòng');
        });
    }

    _acceptClient(conn) {
        if (this.control?.open || this.clientConnected) {
            try { conn.send({ type: 'room-full' }); } catch (_) {}
            try { conn.close(); } catch (_) {}
            return;
        }
        this.control = conn;
        this.remotePeerId = conn.peer;
        conn.on('open', () => {
            if (this.closed) return;
            this.clientConnected = true;
            this.roomReady = true;
            try { conn.send({ type: 'host-ready', roomId: this.roomId, hostPeerId: this.peerId }); } catch (_) {}
            this._startHeartbeat();
            this._notifyPeerCount(2);
            this._setStatus('CONNECTED', 'Đã kết nối thiết bị thứ hai');
            this._maybeSendLocalStream();
        });
        conn.on('data', data => {
            if (data?.type === 'client-hello') this._setStatus('CONNECTED', 'Đã kết nối thiết bị thứ hai');
        });
        conn.on('close', () => this._handleClientGone());
        conn.on('error', () => this._handleClientGone());
    }

    _connectToHost() {
        if (this.closed || !this.peer || this.peer.destroyed) return;
        const conn = this.peer.connect(this.hostPeerId, { reliable: true, serialization: 'json' });
        this.control = conn;
        let opened = false;
        conn.on('open', () => {
            if (this.closed) return;
            opened = true;
            this.remotePeerId = this.hostPeerId;
            this.clientConnected = true;
            this.roomReady = true;
            this.lastHeartbeat = performance.now();
            try { conn.send({ type: 'client-hello', roomId: this.roomId, peerId: this.peerId }); } catch (_) {}
            this._startClientWatchdog();
            this._notifyPeerCount(2);
            this._setStatus('CONNECTED', 'Đã vào phòng');
            this._maybeSendLocalStream();
        });
        conn.on('data', data => {
            if (data?.type === 'host-ready') this.remotePeerId = data.hostPeerId || this.hostPeerId;
            else if (data?.type === 'room-full') {
                this._setStatus('ROOM_FULL', 'Phòng đã đủ 2 thiết bị');
                try { conn.close(); } catch (_) {}
            } else if (data?.type === 'host-heartbeat') {
                this.lastHeartbeat = performance.now();
                try { conn.send({ type: 'heartbeat-ack', t: data.t }); } catch (_) {}
            }
        });
        conn.on('close', () => this._handleHostGone());
        conn.on('error', () => this._handleHostGone());
        setTimeout(() => {
            if (!opened && !this.closed && !this.roomReady) this._setStatus('ROOM_NOT_FOUND', 'Phòng không tồn tại hoặc đã đóng');
        }, 5500);
    }

    _handleIncomingCall(call) {
        if (this.closed) {
            try { call.close(); } catch (_) {}
            return;
        }
        this.remotePeerId = call.peer;
        this.incomingCalls.add(call);
        try { call.answer(this.localStream || undefined); } catch (_) { try { call.answer(); } catch (__) {} }
        call.on('stream', stream => {
            this.remoteStreams.set(call, stream);
            if (this.onStream) this.onStream(stream, stream.getVideoTracks()[0] || null);
            this._startStats();
        });
        const cleanup = () => {
            this.incomingCalls.delete(call);
            this.remoteStreams.delete(call);
            if (this.onStreamEnded) this.onStreamEnded();
        };
        call.on('close', cleanup);
        call.on('error', cleanup);
    }

    async startScreenCapture(stream) {
        if (!stream) throw new Error('Không có luồng màn hình');
        this.stopScreenCapture(false);
        this.localStream = stream;
        for (const track of stream.getTracks()) {
            if (track.kind === 'video') track.contentHint = 'motion';
            track.addEventListener('ended', () => {
                if (this.localStream === stream) this.stopScreenCapture(true);
            }, { once: true });
        }
        if (!this.hasPeer) {
            this._setStatus('WAITING', 'Đang chờ thiết bị thứ hai…');
            return;
        }
        this._makeOutgoingCall();
    }

    stopScreenCapture(updateStatus = true) {
        if (this.localStream) {
            for (const track of this.localStream.getTracks()) { try { track.stop(); } catch (_) {} }
            this.localStream = null;
        }
        if (this.outgoingCall) { try { this.outgoingCall.close(); } catch (_) {} this.outgoingCall = null; }
        if (updateStatus && this.hasPeer) this._setStatus('CONNECTED', 'Đã kết nối thiết bị thứ hai');
    }

    _maybeSendLocalStream() {
        if (this.localStream && this.hasPeer) this._makeOutgoingCall();
    }

    _makeOutgoingCall() {
        if (!this.localStream || !this.remotePeerId || !this.peer || this.peer.destroyed || this.closed) return;
        if (this.outgoingCall) { try { this.outgoingCall.close(); } catch (_) {} this.outgoingCall = null; }
        try {
            const call = this.peer.call(this.remotePeerId, this.localStream, {
                metadata: { roomId: this.roomId, lanOnly: true }
            });
            this.outgoingCall = call;
            call.on('stream', stream => {
                this.remoteStreams.set(call, stream);
                if (this.onStream) this.onStream(stream, stream.getVideoTracks()[0] || null);
                this._startStats();
            });
            const cleanup = () => { if (this.outgoingCall === call) this.outgoingCall = null; };
            call.on('close', cleanup);
            call.on('error', cleanup);
        } catch (err) { console.warn('[CastScreen] outgoing call failed', err); }
    }

    _startHeartbeat() {
        clearInterval(this.heartbeatTimer);
        this.heartbeatTimer = setInterval(() => {
            if (!this.isHost || !this.control?.open || this.closed) return;
            try { this.control.send({ type: 'host-heartbeat', t: Date.now() }); } catch (_) {}
        }, 2000);
    }

    _startClientWatchdog() {
        clearInterval(this.clientWatchdog);
        this.clientWatchdog = setInterval(() => {
            if (this.isHost || this.closed || !this.roomReady) return;
            if (performance.now() - this.lastHeartbeat > 6500) this._handleHostGone();
        }, 1000);
    }

    _handleClientGone() {
        if (this.closed) return;
        this.clientConnected = false;
        this.remotePeerId = '';
        clearInterval(this.heartbeatTimer);
        this._closeMediaCalls();
        this._notifyPeerCount(1);
        this._setStatus('WAITING', 'Thiết bị thứ hai đã rời phòng');
    }

    _handleHostGone() {
        if (this.isHost || this.closed) return;
        this.closed = true;
        clearInterval(this.clientWatchdog);
        this.remotePeerId = '';
        this._closeMediaCalls();
        this._notifyPeerCount(0);
        this._setStatus('HOST_GONE', 'Chủ phòng đã thoát — phòng đã đóng');
        this._destroyPeerOnly();
    }

    _closeMediaCalls() {
        if (this.outgoingCall) { try { this.outgoingCall.close(); } catch (_) {} this.outgoingCall = null; }
        for (const call of this.incomingCalls) { try { call.close(); } catch (_) {} }
        this.incomingCalls.clear();
        this.remoteStreams.clear();
        if (this.onStreamEnded) this.onStreamEnded();
    }

    _notifyPeerCount(count) { if (this.onPeerCountChange) this.onPeerCountChange(count); }

    _startStats() {
        if (this.statsTimer) return;
        this.statsTimer = setInterval(async () => {
            try {
                const calls = [this.outgoingCall, ...this.incomingCalls].filter(Boolean);
                if (!calls.length) return;
                let fps = 0, rtt = 0, jitter = 0, decode = 0, localType = '', remoteType = '';
                for (const call of calls) {
                    if (!call.peerConnection) continue;
                    const stats = await call.peerConnection.getStats();
                    stats.forEach(report => {
                        if (report.type === 'inbound-rtp' && (report.kind === 'video' || report.mediaType === 'video')) {
                            if (Number.isFinite(report.framesPerSecond)) fps = Math.max(fps, report.framesPerSecond);
                            if (Number.isFinite(report.jitter)) jitter = Math.max(jitter, report.jitter * 1000);
                            if (Number.isFinite(report.totalDecodeTime) && report.framesDecoded > 0) decode = Math.max(decode, report.totalDecodeTime / report.framesDecoded * 1000);
                        }
                        if (report.type === 'candidate-pair' && report.state === 'succeeded') {
                            if (Number.isFinite(report.currentRoundTripTime)) rtt = Math.max(rtt, report.currentRoundTripTime * 1000);
                            if (report.localCandidateId) { const c = stats.get(report.localCandidateId); if (c?.candidateType) localType = c.candidateType; }
                            if (report.remoteCandidateId) { const c = stats.get(report.remoteCandidateId); if (c?.candidateType) remoteType = c.candidateType; }
                        }
                    });
                }
                if (this.onMetrics) {
                    this.onMetrics({
                        fps: Math.round(fps || 0),
                        rtt: Math.round(rtt || 0),
                        ping: Math.round(rtt || 0),
                        pipelineMs: Math.round(Math.max(0, rtt + jitter + decode)),
                        localCandidateType: localType,
                        remoteCandidateType: remoteType,
                        lan: localType === 'host' && remoteType === 'host'
                    });
                }
            } catch (_) {}
        }, 500);
    }

    _setStatus(code, label) { if (this.onStatusChange) this.onStatusChange(code, label); }

    _destroyPeerOnly() {
        clearInterval(this.heartbeatTimer);
        clearInterval(this.clientWatchdog);
        this.heartbeatTimer = null;
        this.clientWatchdog = null;
        if (this.control) { try { this.control.close(); } catch (_) {} this.control = null; }
        this._closeMediaCalls();
        if (this.peer) { try { this.peer.destroy(); } catch (_) {} this.peer = null; }
        this.remotePeerId = '';
    }

    close() {
        if (this.closed) return;
        this.closed = true;
        this._destroyPeerOnly();
        this.stopScreenCapture(false);
        clearInterval(this.statsTimer);
        this.statsTimer = null;
        this.roomReady = false;
        this.clientConnected = false;
    }
}

window.WebRTCManager = WebRTCManager;
