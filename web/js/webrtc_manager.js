/**
 * Bidirectional WebRTC manager for Cast Screen Web.
 *
 * Two machines can open the same room and both can send/receive screen streams.
 * A deterministic room hub peer is used only for discovery; media stays P2P.
 * No WebSocket /signal backend is required for the web-to-web path.
 */
class WebRTCManager {
    constructor(options = {}) {
        this.role = options.role || 'peer';
        this.roomId = String(options.roomId || 'default').replace(/[^a-zA-Z0-9_-]/g, '').slice(0, 40) || 'default';
        this.onStream = options.onStream || null;
        this.onStatusChange = options.onStatusChange || null;
        this.onMetrics = options.onMetrics || null;
        this.onSignalingReady = options.onSignalingReady || null;

        this.peer = null;
        this.peerId = '';
        this.isHub = false;
        this.remotePeerId = '';
        this.hubConnection = null;
        this.currentCall = null;
        this.localStream = null;
        this.remoteStream = null;
        this.statsInterval = null;
        this.retryTimer = null;
        this._closed = false;
        this._signalingReady = false;
        this._lastFramesDecoded = 0;
        this._lastStatsTimestamp = 0;

        this.rtcConfig = {
            iceServers: [
                { urls: 'stun:stun.l.google.com:19302' },
                { urls: 'stun:stun1.l.google.com:19302' },
                { urls: 'stun:stun2.l.google.com:19302' },
                { urls: 'stun:global.stun.twilio.com:3478' }
            ],
            sdpSemantics: 'unified-plan'
        };
    }

    get hubId() {
        return `castscreen-room-${this.roomId}-hub`;
    }

    connectSignaling() {
        this._closed = false;
        this._updateStatus('CONNECTING_SIGNALING', 'Đang tham gia phòng...');
        this._createHubOrNode();
    }

    _createHubOrNode() {
        if (this._closed) return;
        this._destroyPeerOnly();
        const peer = new Peer(this.hubId, { config: this.rtcConfig, debug: 0 });
        this.peer = peer;

        peer.on('open', (id) => {
            this.peerId = id;
            this.isHub = true;
            console.log('[PeerJS] Room hub active:', id);
            this._bindHubHandlers();
            this._updateStatus('SIGNALING_READY', 'Đang chờ máy thứ hai...');
            this._notifySignalingReady();
        });

        peer.on('error', (err) => {
            console.warn('[PeerJS] Hub error:', err?.type || err);
            if (err && (err.type === 'unavailable-id' || err.type === 'id-taken')) {
                this._becomeNode();
            } else if (!this._closed) {
                this._scheduleReconnect();
            }
        });

        peer.on('disconnected', () => {
            if (!this._closed) this._scheduleReconnect();
        });

        peer.on('close', () => {
            if (!this._closed) this._scheduleReconnect();
        });
    }

    _becomeNode() {
        if (this._closed) return;
        this._destroyPeerOnly();

        const nodeId = `castscreen-room-${this.roomId}-node-${Math.random().toString(36).slice(2, 10)}`;
        const peer = new Peer(nodeId, { config: this.rtcConfig, debug: 0 });
        this.peer = peer;
        this.isHub = false;

        peer.on('open', (id) => {
            this.peerId = id;
            console.log('[PeerJS] Node active:', id);
            this._connectToHub();
        });

        peer.on('call', (call) => this._handleIncomingCall(call));
        peer.on('error', (err) => {
            console.warn('[PeerJS] Node error:', err?.type || err);
            if (!this._closed) this._scheduleReconnect();
        });
        peer.on('disconnected', () => {
            if (!this._closed) this._scheduleReconnect();
        });
        peer.on('close', () => {
            if (!this._closed) this._scheduleReconnect();
        });
    }

    _bindHubHandlers() {
        this.peer.on('connection', (conn) => {
            console.log('[PeerJS] Node joined:', conn.peer);
            this._acceptHubConnection(conn);
        });
        this.peer.on('call', (call) => this._handleIncomingCall(call));
    }

    _acceptHubConnection(conn) {
        if (this.remotePeerId && this.remotePeerId !== conn.peer) {
            try { conn.close(); } catch (_) {}
            return;
        }

        this.hubConnection = conn;
        this.remotePeerId = conn.peer;
        conn.on('open', () => {
            conn.send({ type: 'room-ready', peerId: this.peerId, roomId: this.roomId });
            this._updateStatus('CONNECTED', 'Đã kết nối máy thứ hai');
            this._notifySignalingReady();
            this._callRemoteIfPossible();
        });
        conn.on('data', (data) => {
            if (data?.type === 'hello') {
                this.remotePeerId = data.peerId || conn.peer;
                this._updateStatus('CONNECTED', 'Đã kết nối máy thứ hai');
                this._notifySignalingReady();
                this._callRemoteIfPossible();
            }
        });
        conn.on('close', () => this._handleRemoteGone());
        conn.on('error', () => this._handleRemoteGone());

        // The fixed hub peer is also the media endpoint.
        if (this.localStream) this._callRemoteIfPossible();
    }

    _connectToHub() {
        if (!this.peer || this.peer.destroyed || this._closed) return;
        console.log('[PeerJS] Connecting to room hub:', this.hubId);
        const conn = this.peer.connect(this.hubId, { reliable: true, serialization: 'json' });
        this.hubConnection = conn;

        conn.on('open', () => {
            console.log('[PeerJS] Connected to room hub');
            this.remotePeerId = this.hubId;
            conn.send({ type: 'hello', peerId: this.peerId, roomId: this.roomId });
            this._updateStatus('CONNECTED', 'Đã kết nối máy thứ hai');
            this._notifySignalingReady();
            this._callRemoteIfPossible();
        });
        conn.on('data', (data) => {
            if (data?.type === 'room-ready') {
                this.remotePeerId = data.peerId || this.hubId;
                this._updateStatus('CONNECTED', 'Đã kết nối máy thứ hai');
                this._notifySignalingReady();
                this._callRemoteIfPossible();
            }
        });
        conn.on('close', () => this._handleRemoteGone());
        conn.on('error', () => this._handleRemoteGone());
    }

    _handleIncomingCall(call) {
        console.log('[PeerJS] Incoming media call from:', call.peer);
        this.remotePeerId = call.peer;
        try {
            // Answer with our stream when available. This makes the path genuinely bidirectional.
            call.answer(this.localStream || undefined);
        } catch (e) {
            console.warn('[PeerJS] answer error:', e);
            try { call.answer(); } catch (_) {}
        }

        call.on('stream', (stream) => {
            console.log('[PeerJS] Remote stream received');
            this.remoteStream = stream;
            this._bindRemoteStream(stream);
            this._updateStatus('CONNECTED', 'Đang truyền màn hình');
            this._startStatsMonitoring();
        });
        call.on('close', () => {
            if (this.currentCall === call) this.currentCall = null;
        });
        call.on('error', (err) => console.warn('[PeerJS] Media call error:', err));
        this.currentCall = call;
    }

    _bindRemoteStream(stream) {
        if (this.onStream) {
            this.onStream(stream, stream.getVideoTracks()[0] || null);
        }
    }

    _callRemoteIfPossible() {
        if (this._closed || !this.localStream || !this.remotePeerId || !this.peer || this.peer.destroyed) return;
        if (this.currentCall && !this.currentCall.open) {
            try { this.currentCall.close(); } catch (_) {}
            this.currentCall = null;
        }

        // If an existing call is alive, it already carries the current stream.
        if (this.currentCall) return;

        try {
            console.log('[PeerJS] Calling remote peer:', this.remotePeerId);
            const call = this.peer.call(this.remotePeerId, this.localStream, { metadata: { roomId: this.roomId } });
            this.currentCall = call;
            call.on('stream', (stream) => {
                this.remoteStream = stream;
                this._bindRemoteStream(stream);
                this._updateStatus('CONNECTED', 'Đang truyền màn hình');
                this._startStatsMonitoring();
            });
            call.on('close', () => {
                if (this.currentCall === call) this.currentCall = null;
                if (!this._closed && this.remotePeerId && this.localStream) {
                    setTimeout(() => this._callRemoteIfPossible(), 300);
                }
            });
            call.on('error', (err) => {
                console.warn('[PeerJS] Outgoing media call error:', err);
                if (!this._closed) {
                    this.currentCall = null;
                    setTimeout(() => this._callRemoteIfPossible(), 800);
                }
            });
        } catch (e) {
            console.warn('[PeerJS] call() failed:', e);
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
        this._updateStatus(this.remotePeerId ? 'CONNECTED' : 'SIGNALING_READY', this.remotePeerId ? 'Đang phát màn hình' : 'Đang chờ máy thứ hai...');
        this._callRemoteIfPossible();
    }

    stopScreenCapture() {
        if (!this.localStream) return;
        this.localStream.getTracks().forEach(track => {
            try { track.stop(); } catch (_) {}
        });
        this.localStream = null;
        if (this.currentCall) {
            try { this.currentCall.close(); } catch (_) {}
            this.currentCall = null;
        }
        if (this.remotePeerId) this._updateStatus('CONNECTED', 'Đã kết nối, chưa phát màn hình');
    }

    _handleRemoteGone() {
        this.remotePeerId = '';
        this._signalingReady = false;
        this._stopStatsMonitoring();
        if (this.currentCall) {
            try { this.currentCall.close(); } catch (_) {}
            this.currentCall = null;
        }
        if (this.onStatusChange) {
            this.onStatusChange('DISCONNECTED', 'Máy thứ hai đã ngắt kết nối');
        }
        if (!this._closed) {
            setTimeout(() => this._createHubOrNode(), 500);
        }
    }

    _scheduleReconnect() {
        if (this._closed || this.retryTimer) return;
        this.retryTimer = setTimeout(() => {
            this.retryTimer = null;
            this._createHubOrNode();
        }, 1200);
    }

    _destroyPeerOnly() {
        if (this.hubConnection) {
            try { this.hubConnection.close(); } catch (_) {}
            this.hubConnection = null;
        }
        if (this.currentCall) {
            try { this.currentCall.close(); } catch (_) {}
            this.currentCall = null;
        }
        if (this.peer) {
            try { this.peer.destroy(); } catch (_) {}
            this.peer = null;
        }
        this.remotePeerId = '';
        this.isHub = false;
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
        if (this.statsInterval || !this.peer) return;
        let previousDecoded = 0;
        let previousTime = performance.now();

        this.statsInterval = setInterval(async () => {
            try {
                if (!this.currentCall || !this.currentCall.peerConnection) return;
                const pc = this.currentCall.peerConnection;
                const stats = await pc.getStats();
                let fps = 0;
                let rtt = 0;
                let jitter = 0;
                let decodeMs = 0;

                stats.forEach(report => {
                    if (report.type === 'inbound-rtp' && (report.kind === 'video' || report.mediaType === 'video')) {
                        if (Number.isFinite(report.framesPerSecond)) fps = report.framesPerSecond;
                        if (!fps && Number.isFinite(report.framesDecoded)) {
                            const now = performance.now();
                            const dt = (now - previousTime) / 1000;
                            if (dt > 0.2) {
                                fps = Math.max(0, (report.framesDecoded - previousDecoded) / dt);
                                previousDecoded = report.framesDecoded;
                                previousTime = now;
                            }
                        }
                        if (Number.isFinite(report.jitter)) jitter = report.jitter * 1000;
                        if (Number.isFinite(report.totalDecodeTime) && report.framesDecoded > 0) {
                            decodeMs = (report.totalDecodeTime / report.framesDecoded) * 1000;
                        }
                    }
                    if (report.type === 'candidate-pair' && report.state === 'succeeded' && Number.isFinite(report.currentRoundTripTime)) {
                        rtt = report.currentRoundTripTime * 1000;
                    }
                });

                // This is receiver-side pipeline latency only, not a fake glass-to-glass value.
                const pipelineMs = Math.max(0, rtt + jitter + decodeMs);
                if (this.onMetrics) this.onMetrics({ fps: Math.round(fps || 0), ping: Math.round(rtt || 0), pipelineMs: Math.round(pipelineMs) });
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
        this._closed = true;
        this._stopStatsMonitoring();
        if (this.retryTimer) {
            clearTimeout(this.retryTimer);
            this.retryTimer = null;
        }
        this.stopScreenCapture();
        this._destroyPeerOnly();
        this.peerId = '';
        this.remoteStream = null;
    }
}

window.WebRTCManager = WebRTCManager;
