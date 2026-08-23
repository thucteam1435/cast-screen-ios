/**
 * LAN-first WebRTC manager for Cast Screen Web.
 *
 * Room owner = authoritative host. The host owns the room lifetime.
 * Joining clients never promote themselves to host.
 * PeerJS is used only for the initial signaling/discovery handshake.
 * Media is LAN-only: no STUN/TURN/relay candidates are configured.
 * Therefore the actual audio/video path must use direct host candidates.
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

        // IMPORTANT: LAN mode. No STUN/TURN means no cloud relay path.
        // PeerJS remains only the signaling/discovery layer.
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
            this._updateStatus('CONNECTING_SIGNALING', 'Đang tạo phòng LAN...');
            this._createHost();
        } else {
            this._updateStatus('CONNECTING_SIGNALING', 'Đang tìm máy chủ LAN...');
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
            this.isHub = true;
            console.log('[LAN] Host room active:', id);
            this._bindHostHandlers();
            this._updateStatus('SIGNALING_READY', 'Máy chủ LAN đang chờ thiết bị...');
            this._notifySignalingReady();
        });

        peer.on('connection', (conn) => this._acceptHostConnection(conn));
        peer.on('call', (call) => this._handleIncomingCall(call));

        peer.on('error', (err) => {
            console.warn('[LAN] Host error:', err?.type || err);
            if (!this._closed) {
                this._updateStatus('FAILED', err?.type === 'unavailable-id' ? 'Mã phòng đã được sử dụng' : 'Lỗi máy chủ LAN');
            }
        });

        peer.on('disconnected', () => {
            if (!this._closed) this._updateStatus('FAILED', 'Máy chủ LAN mất signaling');
        });

        peer.on('close', () => {
            if (!this._closed) this._updateStatus('FAILED', 'Máy chủ LAN đã đóng');
        });
    }

    _createClient() {
        if (this._closed) return;
        this._destroyPeerOnly();
        const nodeId = `castscreen-room-${this.roomId}-client-${Math.random().toString(36).slice(2, 10)}`;
        const peer = new Peer(nodeId, { config: this.rtcConfig, debug: 0 });
        this.peer = peer;
        this.isHub = false;

        peer.on('open', (id) => {
            this.peerId = id;
            console.log('[LAN] Client active:', id);
            this._connectToHost();
        });

        peer.on('call', (call) => this._handleIncomingCall(call));
        peer.on('error', (err) => {
            console.warn('[LAN] Client error:', err?.type || err);
            if (!this._closed) {
                this._updateStatus('DISCONNECTED', 'Không tìm thấy máy chủ LAN');
            }
        });
        peer.on('disconnected', () => {
            if (!this._closed) this._updateStatus('DISCONNECTED', 'Mất kết nối máy chủ LAN');
        });
        peer.on('close', () => {
            if (!this._closed) this._updateStatus('DISCONNECTED', 'Máy chủ LAN đã tắt');
        });
    }

    _bindHostHandlers() {
        // Host accepts exactly one client for the current room.
        // This matches the requested single host -> single peer projection model.
    }

    _acceptHostConnection(conn) {
        if (this.remotePeerId && this.remotePeerId !== conn.peer) {
            try { conn.close(); } catch (_) {}
            return;
        }
        this.hubConnection = conn;
        this.remotePeerId = conn.peer;

        conn.on('open', () => {
            conn.send({ type: 'host-ready', peerId: this.peerId, roomId: this.roomId });
            this._updateStatus('CONNECTED', 'Thiết bị đã tham gia LAN');
            this._notifySignalingReady();
            this._callRemoteIfPossible();
        });
        conn.on('close', () => this._handleClientGone());
        conn.on('error', () => this._handleClientGone());
    }

    _connectToHost() {
        if (!this.peer || this.peer.destroyed || this._closed) return;
        console.log('[LAN] Connecting client to host:', this.hubId);
        const conn = this.peer.connect(this.hubId, { reliable: true, serialization: 'json' });
        this.hubConnection = conn;

        conn.on('open', () => {
            this.remotePeerId = this.hubId;
            conn.send({ type: 'client-hello', peerId: this.peerId, roomId: this.roomId });
            this._updateStatus('CONNECTED', 'Đã kết nối máy chủ LAN');
            this._notifySignalingReady();
            this._callRemoteIfPossible();
        });
        conn.on('data', (data) => {
            if (data?.type === 'host-ready') {
                this.remotePeerId = data.peerId || this.hubId;
                this._updateStatus('CONNECTED', 'Đã kết nối máy chủ LAN');
                this._notifySignalingReady();
                this._callRemoteIfPossible();
            }
        });
        conn.on('close', () => this._handleHostGone());
        conn.on('error', () => this._handleHostGone());
    }

    _handleIncomingCall(call) {
        console.log('[LAN] Incoming media call from:', call.peer);
        this.remotePeerId = call.peer;
        try {
            call.answer(this.localStream || undefined);
        } catch (e) {
            console.warn('[LAN] answer error:', e);
            try { call.answer(); } catch (_) {}
        }

        call.on('stream', (stream) => {
            this.remoteStream = stream;
            this._bindRemoteStream(stream);
            this._updateStatus('CONNECTED', this.isHost ? 'Đang nhận màn hình qua LAN' : 'Đang nhận màn hình qua LAN');
            this._startStatsMonitoring();
        });
        call.on('close', () => {
            if (this.currentCall === call) this.currentCall = null;
        });
        call.on('error', (err) => console.warn('[LAN] Media call error:', err));
        this.currentCall = call;
    }

    _bindRemoteStream(stream) {
        if (this.onStream) this.onStream(stream, stream.getVideoTracks()[0] || null);
    }

    _callRemoteIfPossible() {
        if (this._closed || !this.localStream || !this.remotePeerId || !this.peer || this.peer.destroyed) return;
        if (this.currentCall && !this.currentCall.open) {
            try { this.currentCall.close(); } catch (_) {}
            this.currentCall = null;
        }
        if (this.currentCall) return;

        try {
            const call = this.peer.call(this.remotePeerId, this.localStream, { metadata: { roomId: this.roomId, lanOnly: true } });
            this.currentCall = call;
            call.on('stream', (stream) => {
                this.remoteStream = stream;
                this._bindRemoteStream(stream);
                this._updateStatus('CONNECTED', 'Đang truyền màn hình qua LAN');
                this._startStatsMonitoring();
            });
            call.on('close', () => {
                if (this.currentCall === call) this.currentCall = null;
            });
            call.on('error', (err) => {
                console.warn('[LAN] Outgoing media call error:', err);
                if (!this._closed) {
                    this.currentCall = null;
                    this._updateStatus('FAILED', 'Không tạo được đường truyền LAN');
                }
            });
        } catch (e) {
            console.warn('[LAN] call() failed:', e);
            this._updateStatus('FAILED', 'Không tạo được đường truyền LAN');
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
        this.localStream.getTracks().forEach(track => {
            try { track.stop(); } catch (_) {}
        });
        this.localStream = null;
        if (this.currentCall) {
            try { this.currentCall.close(); } catch (_) {}
            this.currentCall = null;
        }
        if (this.remotePeerId) this._updateStatus('CONNECTED', this.isHost ? 'Máy chủ LAN đang chờ...' : 'Đã kết nối máy chủ LAN');
    }

    // Client MUST be kicked when host disappears.
    _handleHostGone() {
        if (this.isHost || this._closed) return;
        this._closed = true;
        this.remotePeerId = '';
        this._stopStatsMonitoring();
        if (this.currentCall) {
            try { this.currentCall.close(); } catch (_) {}
            this.currentCall = null;
        }
        if (this.onStatusChange) this.onStatusChange('DISCONNECTED', 'Máy chủ LAN đã tắt — phòng đã đóng');
        this._destroyPeerOnly();
    }

    _handleClientGone() {
        if (!this.isHost || this._closed) return;
        this.remotePeerId = '';
        this._stopStatsMonitoring();
        if (this.currentCall) {
            try { this.currentCall.close(); } catch (_) {}
            this.currentCall = null;
        }
        if (this.onStatusChange) this.onStatusChange('DISCONNECTED', 'Thiết bị đã rời phòng LAN');
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
                let localType = '';
                let remoteType = '';

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
                    if (report.type === 'candidate-pair' && (report.state === 'succeeded' || report.state === 'in-progress')) {
                        if (Number.isFinite(report.currentRoundTripTime)) rtt = report.currentRoundTripTime * 1000;
                        if (report.localCandidateId) {
                            const local = stats.get(report.localCandidateId);
                            if (local) localType = local.candidateType || '';
                        }
                        if (report.remoteCandidateId) {
                            const remote = stats.get(report.remoteCandidateId);
                            if (remote) remoteType = remote.candidateType || '';
                        }
                    }
                });

                const pipelineMs = Math.max(0, rtt + jitter + decodeMs);
                if (this.onMetrics) {
                    this.onMetrics({
                        fps: Math.round(fps || 0),
                        ping: Math.round(rtt || 0),
                        pipelineMs: Math.round(pipelineMs),
                        localCandidateType: localType,
                        remoteCandidateType: remoteType,
                        lan: localType === 'host' && remoteType === 'host'
                    });
                }
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
