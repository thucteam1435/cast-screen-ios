/**
 * LAN-first WebRTC manager for Cast Screen Web.
 *
 * Host owns room lifetime. A room has at most one client.
 * PeerJS is signaling/discovery only; media uses direct host candidates.
 * No STUN/TURN servers are configured.
 */
class WebRTCManager {
    constructor(options = {}) {
        this.role = options.role || 'client';
        this.isHost = options.isHost === true || this.role === 'host';
        this.roomId = String(options.roomId || 'default').replace(/[^a-zA-Z0-9_-]/g, '').slice(0, 40) || 'default';
        this.onStream = options.onStream || null;
        this.onStatusChange = options.onStatusChange || null;
        this.onMetrics = options.onMetrics || null;
        this.onSignalingReady = options.onSignalingReady || null;

        this.peer = null;
        this.peerId = '';
        this.remotePeerId = '';
        this.hubConnection = null;
        this.incomingCall = null;
        this.outgoingCall = null;
        this.localStream = null;
        this.remoteStream = null;
        this.statsInterval = null;
        this.heartbeatTimer = null;
        this.hostWatchdog = null;
        this.lastHostPulse = 0;
        this._closed = false;
        this._signalingReady = false;

        this.rtcConfig = {
            iceServers: [],
            iceTransportPolicy: 'all',
            sdpSemantics: 'unified-plan',
            iceCandidatePoolSize: 0
        };
    }

    get hubId() {
        return `castscreen-room-${this.roomId}-host`;
    }

    connectSignaling() {
        this._closed = false;
        if (this.isHost) {
            this._updateStatus('CONNECTING_SIGNALING', 'Đang tạo phòng...');
            this._createHost();
        } else {
            this._updateStatus('CONNECTING_SIGNALING', 'Đang kiểm tra phòng...');
            this._createClient();
        }
    }

    _createHost() {
        if (this._closed) return;
        this._destroyPeerOnly();
        const peer = new Peer(this.hubId, { config: this.rtcConfig, debug: 0 });
        this.peer = peer;

        peer.on('open', (id) => {
            this.peerId = id;
            console.log('[LAN] HOST active:', id);
            this._updateStatus('SIGNALING_READY', 'Phòng đã sẵn sàng');
            this._notifySignalingReady();
        });

        peer.on('connection', (conn) => this._acceptHostConnection(conn));
        peer.on('call', (call) => this._handleIncomingCall(call));

        peer.on('error', (err) => {
            console.warn('[LAN] Host error:', err?.type || err);
            if (!this._closed && err?.type === 'unavailable-id') {
                this._updateStatus('FAILED', 'Mã phòng đã được sử dụng');
            }
        });
        peer.on('disconnected', () => {
            if (!this._closed) this._updateStatus('FAILED', 'Mất kết nối máy chủ signaling');
        });
        peer.on('close', () => {
            if (!this._closed) this._updateStatus('FAILED', 'Phòng đã đóng');
        });
    }

    _createClient() {
        if (this._closed) return;
        this._destroyPeerOnly();
        const nodeId = `castscreen-client-${Math.random().toString(36).slice(2, 10)}`;
        const peer = new Peer(nodeId, { config: this.rtcConfig, debug: 0 });
        this.peer = peer;

        peer.on('open', () => this._connectToHost());
        peer.on('call', (call) => this._handleIncomingCall(call));
        peer.on('error', (err) => {
            console.warn('[LAN] Client peer error:', err?.type || err);
            if (!this._closed && (err?.type === 'peer-unavailable' || err?.type === 'not-found')) {
                this._handleRoomNotFound();
            }
        });
        peer.on('disconnected', () => {
            if (!this._closed) this._handleHostGone('Mất kết nối tới máy chủ phòng');
        });
        peer.on('close', () => {
            if (!this._closed) this._handleHostGone('Máy chủ phòng đã đóng');
        });
    }

    _acceptHostConnection(conn) {
        // Exactly one client per room.
        if (this.remotePeerId && this.remotePeerId !== conn.peer) {
            try { conn.send({ type: 'room-full' }); } catch (_) {}
            try { conn.close(); } catch (_) {}
            return;
        }

        this.hubConnection = conn;
        this.remotePeerId = conn.peer;

        conn.on('open', () => {
            conn.send({ type: 'host-ready', peerId: this.peerId, roomId: this.roomId });
            this._startHostHeartbeat();
            this._updateStatus('CONNECTED', 'Thiết bị đã tham gia phòng');
            this._notifySignalingReady();
            this._callRemoteIfPossible();
        });
        conn.on('data', (data) => {
            if (data?.type === 'client-pulse') {
                // Connection itself is enough; pulse is useful for diagnostics.
                return;
            }
            if (data?.type === 'client-goodbye') {
                this._handleClientGone();
            }
        });
        conn.on('close', () => this._handleClientGone());
        conn.on('error', () => this._handleClientGone());
    }

    _connectToHost() {
        if (!this.peer || this.peer.destroyed || this._closed) return;
        const conn = this.peer.connect(this.hubId, { reliable: true, serialization: 'json' });
        this.hubConnection = conn;

        conn.on('open', () => {
            this.remotePeerId = this.hubId;
            this.lastHostPulse = Date.now();
            this.hostWatchdog = setInterval(() => {
                if (this._closed) return;
                if (Date.now() - this.lastHostPulse > 7000) {
                    this._handleHostGone('Máy chủ phòng đã ngắt kết nối');
                }
            }, 2000);
            conn.send({ type: 'client-hello', peerId: this.peerId, roomId: this.roomId });
            this._updateStatus('CONNECTED', 'Đã vào phòng');
            this._notifySignalingReady();
            this._callRemoteIfPossible();
        });
        conn.on('data', (data) => {
            this.lastHostPulse = Date.now();
            if (data?.type === 'host-ready') {
                this.remotePeerId = data.peerId || this.hubId;
                this._updateStatus('CONNECTED', 'Đã vào phòng');
                this._notifySignalingReady();
                this._callRemoteIfPossible();
            } else if (data?.type === 'host-pulse') {
                try { conn.send({ type: 'client-pulse' }); } catch (_) {}
            } else if (data?.type === 'room-full') {
                this._handleRoomFull();
            }
        });
        conn.on('close', () => this._handleHostGone('Máy chủ phòng đã đóng'));
        conn.on('error', (err) => {
            if (err?.type === 'peer-unavailable' || err?.type === 'network') {
                this._handleRoomNotFound();
            } else {
                this._handleHostGone('Không thể kết nối máy chủ phòng');
            }
        });
    }

    _startHostHeartbeat() {
        if (this.heartbeatTimer) clearInterval(this.heartbeatTimer);
        this.heartbeatTimer = setInterval(() => {
            if (!this.hubConnection || this._closed) return;
            try { this.hubConnection.send({ type: 'host-pulse', ts: Date.now() }); } catch (_) {}
        }, 2000);
    }

    _handleIncomingCall(call) {
        // Only accept media from the one client in this room.
        if (this.remotePeerId && call.peer !== this.remotePeerId) {
            try { call.close(); } catch (_) {}
            return;
        }
        this.remotePeerId = call.peer;
        try { call.answer(this.localStream || undefined); } catch (_) { try { call.answer(); } catch (__) {} }
        this.incomingCall = call;

        call.on('stream', (stream) => {
            this.remoteStream = stream;
            this._bindRemoteStream(stream);
            this._updateStatus('CONNECTED', 'Đang nhận màn hình qua LAN');
            this._startStatsMonitoring();
        });
        call.on('close', () => {
            if (this.incomingCall === call) this.incomingCall = null;
        });
        call.on('error', () => {
            if (this.incomingCall === call) this.incomingCall = null;
        });
    }

    _bindRemoteStream(stream) {
        if (this.onStream) this.onStream(stream, stream.getVideoTracks()[0] || null);
    }

    _callRemoteIfPossible() {
        if (this._closed || !this.localStream || !this.remotePeerId || !this.peer || this.peer.destroyed) return;
        if (this.outgoingCall) return;

        try {
            const call = this.peer.call(this.remotePeerId, this.localStream, {
                metadata: { roomId: this.roomId, lanOnly: true }
            });
            this.outgoingCall = call;
            call.on('stream', (stream) => {
                this.remoteStream = stream;
                this._bindRemoteStream(stream);
                this._startStatsMonitoring();
            });
            call.on('close', () => {
                if (this.outgoingCall === call) this.outgoingCall = null;
            });
            call.on('error', () => {
                if (this.outgoingCall === call) this.outgoingCall = null;
            });
        } catch (e) {
            console.warn('[LAN] Outgoing media call failed:', e);
        }
    }

    async startScreenCapture(stream) {
        if (!stream) throw new Error('Không có MediaStream để chia sẻ.');
        this.localStream = stream;
        stream.getTracks().forEach(track => {
            if (track.kind === 'video') track.contentHint = 'motion';
            track.onended = () => {
                if (this.localStream === stream) this.stopScreenCapture();
            };
        });
        this._callRemoteIfPossible();
    }

    stopScreenCapture() {
        if (!this.localStream) return;
        this.localStream.getTracks().forEach(track => { try { track.stop(); } catch (_) {} });
        this.localStream = null;
        if (this.outgoingCall) {
            try { this.outgoingCall.close(); } catch (_) {}
            this.outgoingCall = null;
        }
        if (this.remotePeerId) {
            this._updateStatus('CONNECTED', this.isHost ? 'Đang chờ thiết bị...' : 'Đã vào phòng');
        }
    }

    _handleRoomNotFound() {
        if (this._closed) return;
        this._closed = true;
        this._stopTimers();
        this._destroyPeerOnly();
        this._updateStatus('ROOM_NOT_FOUND', 'Phòng không tồn tại');
    }

    _handleRoomFull() {
        if (this._closed) return;
        this._closed = true;
        this._stopTimers();
        this._destroyPeerOnly();
        this._updateStatus('ROOM_FULL', 'Phòng đã đủ 2 thiết bị');
    }

    _handleHostGone(message = 'Máy chủ phòng đã ngắt kết nối') {
        if (this.isHost || this._closed) return;
        this._closed = true;
        this._stopTimers();
        this._destroyPeerOnly();
        this._updateStatus('HOST_GONE', message);
    }

    _handleClientGone() {
        if (!this.isHost || this._closed) return;
        this._stopHostHeartbeat();
        this.remotePeerId = '';
        this._stopMediaCalls();
        this._updateStatus('DISCONNECTED', 'Thiết bị đã rời phòng');
    }

    _stopTimers() {
        this._stopHostHeartbeat();
        if (this.hostWatchdog) {
            clearInterval(this.hostWatchdog);
            this.hostWatchdog = null;
        }
    }

    _stopHostHeartbeat() {
        if (this.heartbeatTimer) {
            clearInterval(this.heartbeatTimer);
            this.heartbeatTimer = null;
        }
    }

    _stopMediaCalls() {
        if (this.incomingCall) {
            try { this.incomingCall.close(); } catch (_) {}
            this.incomingCall = null;
        }
        if (this.outgoingCall) {
            try { this.outgoingCall.close(); } catch (_) {}
            this.outgoingCall = null;
        }
    }

    _destroyPeerOnly() {
        this._stopMediaCalls();
        if (this.hubConnection) {
            try { this.hubConnection.close(); } catch (_) {}
            this.hubConnection = null;
        }
        if (this.peer) {
            try { this.peer.destroy(); } catch (_) {}
            this.peer = null;
        }
        this.remotePeerId = '';
    }

    _notifySignalingReady() {
        if (this._signalingReady) return;
        this._signalingReady = true;
        if (this.onSignalingReady) this.onSignalingReady();
    }

    _updateStatus(code, label) {
        if (this.onStatusChange) this.onStatusChange(code, label);
    }

    _startStatsMonitoring() {
        if (this.statsInterval) return;
        this.statsInterval = setInterval(async () => {
            try {
                const calls = [this.incomingCall, this.outgoingCall].filter(Boolean);
                const pc = calls.map(c => c && c.peerConnection).find(Boolean);
                if (!pc) return;
                const stats = await pc.getStats();
                let fps = 0, rtt = 0, jitter = 0, decodeMs = 0, localType = '', remoteType = '';
                stats.forEach(report => {
                    if (report.type === 'inbound-rtp' && (report.kind === 'video' || report.mediaType === 'video')) {
                        if (Number.isFinite(report.framesPerSecond)) fps = report.framesPerSecond;
                        if (Number.isFinite(report.jitter)) jitter = report.jitter * 1000;
                        if (Number.isFinite(report.totalDecodeTime) && report.framesDecoded > 0) decodeMs = (report.totalDecodeTime / report.framesDecoded) * 1000;
                    }
                    if (report.type === 'candidate-pair' && report.state === 'succeeded') {
                        if (Number.isFinite(report.currentRoundTripTime)) rtt = report.currentRoundTripTime * 1000;
                        const local = report.localCandidateId ? stats.get(report.localCandidateId) : null;
                        const remote = report.remoteCandidateId ? stats.get(report.remoteCandidateId) : null;
                        localType = local?.candidateType || localType;
                        remoteType = remote?.candidateType || remoteType;
                    }
                });
                if (this.onMetrics) this.onMetrics({
                    fps: Math.round(fps),
                    ping: Math.round(rtt),
                    pipelineMs: Math.round(Math.max(0, rtt + jitter + decodeMs)),
                    localCandidateType: localType,
                    remoteCandidateType: remoteType,
                    lan: localType === 'host' && remoteType === 'host'
                });
            } catch (_) {}
        }, 500);
    }

    _stopStatsMonitoring() {
        if (this.statsInterval) {
            clearInterval(this.statsInterval);
            this.statsInterval = null;
        }
    }

    close() {
        if (this._closed) return;
        this._closed = true;
        this._stopTimers();
        this._stopStatsMonitoring();
        if (this.hubConnection && !this.isHost) {
            try { this.hubConnection.send({ type: 'client-goodbye' }); } catch (_) {}
        }
        if (this.localStream) {
            this.localStream.getTracks().forEach(track => { try { track.stop(); } catch (_) {} });
            this.localStream = null;
        }
        this._destroyPeerOnly();
        this.peerId = '';
        this.remoteStream = null;
    }
}

window.WebRTCManager = WebRTCManager;
