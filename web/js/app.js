/**
 * Cast Screen Web Receiver Application
 * Handles room connection, WebRTC stream playback, GPU WebGL Bicubic Sharpening,
 * Cross-platform Fullscreen (iOS Safari + Android/PC), and Audio Playback.
 */
document.addEventListener('DOMContentLoaded', () => {
    // Generate or read Room PIN from URL
    const urlParams = new URLSearchParams(window.location.search);
    let roomId = urlParams.get('room');
    if (!roomId) {
        roomId = Math.floor(100000 + Math.random() * 900000).toString();
        const newUrl = new URL(window.location.href);
        newUrl.searchParams.set('room', roomId);
        window.history.replaceState({}, '', newUrl.toString());
    }

    // DOM Elements
    const roomPinDisplay = document.getElementById('roomPinDisplay');
    const qrCodeContainer = document.getElementById('qrCodeContainer');
    const remoteVideo = document.getElementById('remoteVideo');
    const glCanvas = document.getElementById('glCanvas');
    const videoStage = document.getElementById('videoStage');
    const waitingOverlay = document.getElementById('waitingOverlay');
    const statusBadge = document.getElementById('statusBadge');
    const statusText = document.getElementById('statusText');
    const streamDeviceName = document.getElementById('streamDeviceName');
    const streamResInfo = document.getElementById('streamResInfo');

    const btnFullscreen = document.getElementById('btnFullscreen');
    const btnFullscreenLabel = document.getElementById('btnFullscreenLabel');
    const iconFullscreenSvg = document.getElementById('iconFullscreenSvg');
    const btnExitFullscreenFloating = document.getElementById('btnExitFullscreenFloating');

    const btnUnmuteAudio = document.getElementById('btnUnmuteAudio');
    const btnAudioToggle = document.getElementById('btnAudioToggle');
    const btnAudioLabel = document.getElementById('btnAudioLabel');
    const iconAudioSvg = document.getElementById('iconAudioSvg');

    const toggleSharpen = document.getElementById('toggleSharpen');
    const sharpenStrength = document.getElementById('sharpenStrength');
    const toggleHud = document.getElementById('toggleHud');

    if (roomPinDisplay) roomPinDisplay.textContent = roomId;

    // Render Dynamic QR Code
    const baseUrl = window.location.origin + window.location.pathname.replace('index.html', '');
    const senderUrl = `${baseUrl.replace(/\/$/, '')}/sender.html?room=${roomId}`;
    console.log('[App] Mobile Sender URL:', senderUrl);
    
    if (qrCodeContainer && window.QRCode) {
        new QRCode(qrCodeContainer, {
            text: senderUrl,
            width: 180,
            height: 180,
            colorDark: "#00E5FF",
            colorLight: "#0B1220"
        });
    }

    // Initialize Video Renderer and HUD
    const renderer = new VideoRenderer(glCanvas, remoteVideo);
    const hud = new HUDOverlay(videoStage, remoteVideo);

    // Audio Control & Web Audio API Bridge
    let audioCtx = null;
    let audioSourceNode = null;

    function routeAudioContext(stream) {
        try {
            if (!stream || stream.getAudioTracks().length === 0) return;
            const AudioContextClass = window.AudioContext || window.webkitAudioContext;
            if (!AudioContextClass) return;
            if (!audioCtx) {
                audioCtx = new AudioContextClass();
            }
            if (audioCtx.state === 'suspended') {
                audioCtx.resume().catch(() => {});
            }
            if (audioSourceNode) {
                try { audioSourceNode.disconnect(); } catch (e) {}
            }
            audioSourceNode = audioCtx.createMediaStreamSource(stream);
            audioSourceNode.connect(audioCtx.destination);
            console.log('[App] Web Audio Bridge active for', stream.getAudioTracks().length, 'audio track(s)');
        } catch (e) {
            console.warn('[App] AudioContext bridge info:', e);
        }
    }

    function unmuteAudio() {
        if (!remoteVideo) return;
        remoteVideo.muted = false;
        remoteVideo.removeAttribute('muted');
        remoteVideo.volume = 1.0;
        const p = remoteVideo.play();
        if (p !== undefined) {
            p.catch(e => console.warn('[App] Unmute play error:', e));
        }
        if (audioCtx && audioCtx.state === 'suspended') {
            audioCtx.resume().catch(() => {});
        }
        if (remoteVideo.srcObject) {
            routeAudioContext(remoteVideo.srcObject);
        }
        if (btnUnmuteAudio) btnUnmuteAudio.style.display = 'none';
        if (btnAudioLabel) btnAudioLabel.textContent = 'Tắt Âm Thanh';
        if (btnAudioToggle) btnAudioToggle.classList.add('active');
        if (iconAudioSvg) {
            iconAudioSvg.innerHTML = `
                <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/>
                <path d="M19.07 4.93a10 10 0 0 1 0 14.14M15.54 8.46a5 5 0 0 1 0 7.07"/>`;
        }
    }

    function muteAudio() {
        if (!remoteVideo) return;
        remoteVideo.muted = true;
        remoteVideo.setAttribute('muted', '');
        if (audioCtx && audioCtx.state === 'running') {
            audioCtx.suspend().catch(() => {});
        }
        if (btnAudioLabel) btnAudioLabel.textContent = 'Bật Âm Thanh';
        if (btnAudioToggle) btnAudioToggle.classList.remove('active');
        if (iconAudioSvg) {
            iconAudioSvg.innerHTML = `
                <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/>
                <line x1="23" y1="9" x2="17" y2="15"/>
                <line x1="17" y1="9" x2="23" y2="15"/>`;
        }
    }

    if (btnUnmuteAudio) {
        btnUnmuteAudio.addEventListener('click', (e) => {
            e.stopPropagation();
            unmuteAudio();
        });
    }

    if (btnAudioToggle) {
        btnAudioToggle.addEventListener('click', () => {
            if (remoteVideo.muted) {
                unmuteAudio();
            } else {
                muteAudio();
            }
        });
    }

    // Initialize WebRTC Manager
    const webrtc = new WebRTCManager({
        role: 'receiver',
        roomId: roomId,
        onStream: (stream, track) => {
            console.log('[App] Stream connected! Audio tracks:', stream.getAudioTracks().length, 'Video tracks:', stream.getVideoTracks().length);
            if (remoteVideo.srcObject !== stream) {
                remoteVideo.srcObject = stream;
            }

            // Try playing unmuted first (desktop), fall back to muted + prompt on mobile
            remoteVideo.muted = false;
            remoteVideo.removeAttribute('muted');
            remoteVideo.volume = 1.0;
            remoteVideo.play().then(() => {
                routeAudioContext(stream);
                if (btnUnmuteAudio) btnUnmuteAudio.style.display = 'none';
                if (btnAudioLabel) btnAudioLabel.textContent = 'Tắt Âm Thanh';
                if (btnAudioToggle) btnAudioToggle.classList.add('active');
            }).catch(() => {
                remoteVideo.muted = true;
                remoteVideo.setAttribute('muted', '');
                remoteVideo.play().catch(e => console.warn('[App] Play error:', e));
                if (btnUnmuteAudio) btnUnmuteAudio.style.display = 'flex';
                if (btnAudioLabel) btnAudioLabel.textContent = 'Bật Âm Thanh';
                if (btnAudioToggle) btnAudioToggle.classList.remove('active');
            });

            waitingOverlay.classList.add('hidden');
            statusBadge.classList.add('connected');
            statusBadge.classList.remove('error');
            statusText.textContent = 'ĐANG CHIẾU MÀN HÌNH';
            streamDeviceName.textContent = 'Thiết bị Kết Nối (WebRTC 60fps)';

            // Activate sharpening on live stream
            const sharpenOn = toggleSharpen ? toggleSharpen.checked : true;
            const strength = sharpenStrength ? parseFloat(sharpenStrength.value) : 0.60;
            renderer.setSharpening(sharpenOn, strength);
            renderer.startLoop();

            remoteVideo.onloadedmetadata = () => {
                const w = remoteVideo.videoWidth;
                const h = remoteVideo.videoHeight;
                if (streamResInfo) streamResInfo.textContent = `${w} x ${h}`;
                hud.setResolution(w, h);
            };
        },
        onStatusChange: (code, label) => {
            if (code === 'DISCONNECTED') {
                remoteVideo.srcObject = null;
                renderer.clear();
                renderer.stopLoop();
                renderer.setSharpening(false);
                waitingOverlay.classList.remove('hidden');
                statusBadge.classList.remove('connected');
                statusBadge.classList.remove('error');
                statusText.textContent = 'SẴN SÀNG KẾT NỐI';
                streamDeviceName.textContent = 'Chưa có kết nối';
                hud.stop();
                hud.start();
                if (btnUnmuteAudio) btnUnmuteAudio.style.display = 'none';
                if (btnAudioLabel) btnAudioLabel.textContent = 'Bật Âm Thanh';
                if (btnAudioToggle) btnAudioToggle.classList.remove('active');
            } else if (code === 'ICE_FAILED' || code === 'FAILED') {
                waitingOverlay.classList.remove('hidden');
                statusBadge.classList.remove('connected');
                statusBadge.classList.add('error');
                statusText.textContent = 'LỖI KẾT NỐI';
                const waitingTitle = waitingOverlay.querySelector('.waiting-title');
                if (waitingTitle) {
                    waitingTitle.textContent = 'Kết nối thất bại';
                    waitingTitle.style.color = '#F43F5E';
                    setTimeout(() => {
                        waitingTitle.textContent = 'Sẵn Sàng Nhận Chiếu Màn Hình';
                        waitingTitle.style.color = '';
                        statusBadge.classList.remove('error');
                        statusText.textContent = 'SẴN SÀNG KẾT NỐI';
                    }, 4000);
                }
            }
        },
        onMetrics: (metrics) => {
            if (metrics.ping !== undefined) {
                hud.setPing(metrics.ping);
            }
            if (metrics.fps !== undefined) {
                hud.setFps(metrics.fps);
            }
        }
    });

    webrtc.connectSignaling();

    // UI Controls for Sharpen & HUD
    if (toggleHud) {
        toggleHud.addEventListener('change', (e) => {
            hud.setEnabled(e.target.checked);
        });
    }

    if (toggleSharpen) {
        toggleSharpen.addEventListener('change', (e) => {
            const strength = parseFloat(sharpenStrength ? sharpenStrength.value : 0.60);
            renderer.setSharpening(e.target.checked, strength);
        });
    }

    if (sharpenStrength) {
        sharpenStrength.addEventListener('change', (e) => {
            if (toggleSharpen && toggleSharpen.checked) {
                renderer.setSharpening(true, parseFloat(e.target.value));
            }
        });
    }

    // Universal Fullscreen Handler (Hybrid CSS Fullscreen + Native Fullscreen API)
    function enterFullscreen() {
        if (!videoStage) return;
        videoStage.classList.add('fullscreen-active');
        if (btnFullscreen) btnFullscreen.classList.add('active');
        if (btnFullscreenLabel) btnFullscreenLabel.textContent = 'Thu Nhỏ';
        if (iconFullscreenSvg) {
            iconFullscreenSvg.innerHTML = `<path d="M8 3v3a2 2 0 0 1-2 2H3m18 0h-3a2 2 0 0 1-2-2V3m0 18v-3a2 2 0 0 1 2-2h3M3 16h3a2 2 0 0 1 2 2v3"/>`;
        }

        // Also attempt native fullscreen if supported
        try {
            if (videoStage.requestFullscreen) {
                videoStage.requestFullscreen().catch(() => {});
            } else if (videoStage.webkitRequestFullscreen) {
                videoStage.webkitRequestFullscreen();
            } else if (remoteVideo && remoteVideo.webkitEnterFullscreen && /iPhone|iPod/.test(navigator.userAgent)) {
                remoteVideo.webkitEnterFullscreen();
            }
        } catch (e) {}
    }

    function exitFullscreen() {
        if (!videoStage) return;
        videoStage.classList.remove('fullscreen-active');
        if (btnFullscreen) btnFullscreen.classList.remove('active');
        if (btnFullscreenLabel) btnFullscreenLabel.textContent = 'Toàn Màn Hình';
        if (iconFullscreenSvg) {
            iconFullscreenSvg.innerHTML = `<path d="M8 3H5a2 2 0 0 0-2 2v3m18 0V5a2 2 0 0 0-2-2h-3m0 18h3a2 2 0 0 0 2-2v-3M3 16v3a2 2 0 0 0 2 2h3"/>`;
        }

        try {
            if (document.exitFullscreen) {
                document.exitFullscreen().catch(() => {});
            } else if (document.webkitExitFullscreen) {
                document.webkitExitFullscreen();
            }
        } catch (e) {}
    }

    function toggleUniversalFullscreen() {
        const isFs = videoStage.classList.contains('fullscreen-active') ||
                     !!(document.fullscreenElement || document.webkitFullscreenElement);
        if (isFs) {
            exitFullscreen();
        } else {
            enterFullscreen();
        }
    }

    if (btnFullscreen) {
        btnFullscreen.addEventListener('click', toggleUniversalFullscreen);
    }

    if (btnExitFullscreenFloating) {
        btnExitFullscreenFloating.addEventListener('click', (e) => {
            e.stopPropagation();
            exitFullscreen();
        });
    }

    // Sync native fullscreen changes
    document.addEventListener('fullscreenchange', () => {
        if (!document.fullscreenElement) {
            videoStage.classList.remove('fullscreen-active');
            if (btnFullscreen) btnFullscreen.classList.remove('active');
            if (btnFullscreenLabel) btnFullscreenLabel.textContent = 'Toàn Màn Hình';
            if (iconFullscreenSvg) {
                iconFullscreenSvg.innerHTML = `<path d="M8 3H5a2 2 0 0 0-2 2v3m18 0V5a2 2 0 0 0-2-2h-3m0 18h3a2 2 0 0 0 2-2v-3M3 16v3a2 2 0 0 0 2 2h3"/>`;
            }
        }
    });

    document.addEventListener('webkitfullscreenchange', () => {
        if (!document.webkitFullscreenElement) {
            videoStage.classList.remove('fullscreen-active');
            if (btnFullscreen) btnFullscreen.classList.remove('active');
            if (btnFullscreenLabel) btnFullscreenLabel.textContent = 'Toàn Màn Hình';
        }
    });

    // Tap/Click on video area to unmute or double tap to fullscreen
    if (videoStage) {
        videoStage.addEventListener('click', (e) => {
            if (e.target === btnExitFullscreenFloating || btnExitFullscreenFloating.contains(e.target)) {
                return;
            }
            if (remoteVideo && remoteVideo.muted && remoteVideo.srcObject) {
                unmuteAudio();
            }
        });
        videoStage.addEventListener('dblclick', toggleUniversalFullscreen);
    }

    // Auto-unmute on first touch interaction anywhere on mobile
    document.addEventListener('touchstart', () => {
        if (remoteVideo && remoteVideo.muted && remoteVideo.srcObject) {
            unmuteAudio();
        }
    }, { once: true });

    // Keyboard Shortcuts (F / F11 Fullscreen, H HUD)
    window.addEventListener('keydown', (e) => {
        if (e.key === 'f' || e.key === 'F' || e.key === 'F11') {
            toggleUniversalFullscreen();
        } else if (e.key === 'h' || e.key === 'H') {
            if (toggleHud) {
                toggleHud.checked = !toggleHud.checked;
                hud.setEnabled(toggleHud.checked);
            }
        } else if (e.key === 'Escape') {
            exitFullscreen();
        }
    });
});

