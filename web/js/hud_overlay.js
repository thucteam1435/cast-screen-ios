/**
 * In-Browser Esports In-Game OSD HUD Overlay
 * Measures physical video frame delivery, display FPS, and network ping RTT.
 *
 * FIX BUG-06: Added _isRunning flag and stop() method to prevent memory leak.
 * FIX ISSUE-02: Replaced hard-coded DOM IDs with unique IDs per instance.
 */
class HUDOverlay {
    constructor(containerElement, videoElement) {
        this.container = containerElement;
        this.video = videoElement;
        this.isEnabled = true;
        this.fps = 0;
        this.ping = 0;
        this.frameCount = 0;
        this.lastFpsTs = performance.now();
        this.rvfcSupported = 'requestVideoFrameCallback' in HTMLVideoElement.prototype;

        // BUG-06 FIX: Track running state to allow clean stop
        this._isRunning = false;
        this._rafId = null;

        // ISSUE-02 FIX: Unique instance ID to avoid duplicate DOM IDs
        this._uid = `hud_${Date.now()}_${Math.floor(Math.random() * 9999)}`;

        this._createDOM();
        this.start();
    }

    _createDOM() {
        this.hudEl = document.createElement('div');
        this.hudEl.className = 'in-game-hud';
        // ISSUE-02 FIX: use per-instance unique IDs
        this.hudEl.innerHTML = `
            <div class="hud-item hud-fps">⚡ <span id="${this._uid}_fps">--</span> FPS</div>
            <div class="hud-divider">•</div>
            <div class="hud-item hud-ping">⏱ <span id="${this._uid}_ping">--</span> ms</div>
            <div class="hud-divider">•</div>
            <div class="hud-item hud-res"><span id="${this._uid}_res">1080p</span></div>
        `;
        this.container.appendChild(this.hudEl);

        this.fpsValEl  = this.hudEl.querySelector(`#${this._uid}_fps`);
        this.pingValEl = this.hudEl.querySelector(`#${this._uid}_ping`);
        this.resValEl  = this.hudEl.querySelector(`#${this._uid}_res`);
    }

    /** BUG-06 FIX: Start the FPS monitoring loop */
    start() {
        if (this._isRunning) return;
        this._isRunning = true;

        const updateFrame = () => {
            // BUG-06 FIX: Exit loop immediately when stopped
            if (!this._isRunning) return;

            this.frameCount++;
            const now = performance.now();
            const elapsed = now - this.lastFpsTs;

            if (elapsed >= 1000) {
                this.fps = Math.round((this.frameCount * 1000) / elapsed);
                this.frameCount = 0;
                this.lastFpsTs = now;
                this._render();
            }

            if (this.rvfcSupported && this.video && this.video.readyState >= 2) {
                this.video.requestVideoFrameCallback(updateFrame);
            } else {
                this._rafId = requestAnimationFrame(updateFrame);
            }
        };

        if (this.rvfcSupported && this.video) {
            this.video.requestVideoFrameCallback(updateFrame);
        } else {
            this._rafId = requestAnimationFrame(updateFrame);
        }
    }

    /** BUG-06 FIX: Stop the monitoring loop and reset counters */
    stop() {
        this._isRunning = false;
        if (this._rafId) {
            cancelAnimationFrame(this._rafId);
            this._rafId = null;
        }
        this.fps = 0;
        this.ping = 0;
        this.frameCount = 0;
        this._render();
    }

    setFps(fps) {
        if (fps && fps > 0) {
            this.fps = fps;
            this._render();
        }
    }

    setPing(pingMs) {
        this.ping = Math.round(pingMs);
        this._render();
    }

    setResolution(w, h) {
        if (w && h) {
            this.resValEl.textContent = `${w}x${h}`;
        }
    }

    setEnabled(enabled) {
        this.isEnabled = enabled;
        this.hudEl.style.display = enabled ? 'flex' : 'none';
    }

    _render() {
        if (!this.isEnabled) return;
        
        this.fpsValEl.textContent  = this.fps  > 0 ? this.fps  : '--';
        this.pingValEl.textContent = this.ping > 0 ? this.ping : '--';

        // Color coding relative to target 60fps
        if (this.fps >= 55) {
            this.fpsValEl.style.color = '#10B981'; // green
        } else if (this.fps >= 30) {
            this.fpsValEl.style.color = '#F59E0B'; // amber
        } else {
            this.fpsValEl.style.color = '#F43F5E'; // red
        }
    }
}

window.HUDOverlay = HUDOverlay;
