/**
 * WebGL 2.0 Hardware Video Renderer with Real-time GPU Image Sharpening
 * Uses the user's GPU (NVIDIA / AMD / Intel) to enhance resolution and contrast.
 */
class VideoRenderer {
    constructor(canvas, videoElement) {
        this.canvas = canvas;
        this.video = videoElement;
        this.gl = null;
        this.program = null;
        this.texture = null;
        this.isSharpenEnabled = false;
        this.sharpenStrength = 0.5;
        this.animationFrameId = null;
        this.useWebGL = false;

        this._initWebGL();
    }

    _initWebGL() {
        try {
            this.gl = this.canvas.getContext('webgl2', { alpha: false, preserveDrawingBuffer: false }) ||
                      this.canvas.getContext('webgl', { alpha: false });
            if (!this.gl) {
                console.warn('[Renderer] WebGL not supported, falling back to direct video element.');
                return;
            }

            const vsSource = `
                attribute vec2 a_position;
                attribute vec2 a_texCoord;
                varying vec2 v_texCoord;
                void main() {
                    gl_Position = vec4(a_position, 0.0, 1.0);
                    v_texCoord = a_texCoord;
                }
            `;

            // GPU Sharpening Fragment Shader (Adaptive Unsharp Mask)
            const fsSource = `
                precision mediump float;
                uniform sampler2D u_image;
                uniform vec2 u_resolution;
                uniform float u_sharpen;
                varying vec2 v_texCoord;

                void main() {
                    vec2 step = 1.0 / u_resolution;
                    vec4 center = texture2D(u_image, v_texCoord);
                    
                    if (u_sharpen <= 0.01) {
                        gl_FragColor = center;
                        return;
                    }

                    vec4 top    = texture2D(u_image, v_texCoord + vec2(0.0, -step.y));
                    vec4 bottom = texture2D(u_image, v_texCoord + vec2(0.0, step.y));
                    vec4 left   = texture2D(u_image, v_texCoord + vec2(-step.x, 0.0));
                    vec4 right  = texture2D(u_image, v_texCoord + vec2(step.x, 0.0));

                    // Laplacian edge detection kernel
                    vec4 laplacian = (top + bottom + left + right) - 4.0 * center;
                    vec4 sharpened = center - u_sharpen * laplacian;

                    gl_FragColor = clamp(sharpened, 0.0, 1.0);
                }
            `;

            this.program = this._createProgram(vsSource, fsSource);
            // BUG-03 FIX: Abort if shader compilation failed
            if (!this.program) {
                console.warn('[Renderer] Shader compilation failed, falling back to direct video element.');
                this.useWebGL = false;
                return;
            }
            this._setupBuffers();
            this._setupTexture();
            this.useWebGL = true;
        } catch (e) {
            console.warn('[Renderer] WebGL setup failed:', e);
            this.useWebGL = false;
        }
    }

    _createProgram(vsSrc, fsSrc) {
        const gl = this.gl;
        const vs = gl.createShader(gl.VERTEX_SHADER);
        gl.shaderSource(vs, vsSrc);
        gl.compileShader(vs);

        // BUG-03 FIX: Check vertex shader compile error
        if (!gl.getShaderParameter(vs, gl.COMPILE_STATUS)) {
            console.error('[Renderer] Vertex shader compile error:', gl.getShaderInfoLog(vs));
            gl.deleteShader(vs);
            return null;
        }

        const fs = gl.createShader(gl.FRAGMENT_SHADER);
        gl.shaderSource(fs, fsSrc);
        gl.compileShader(fs);

        // BUG-03 FIX: Check fragment shader compile error
        if (!gl.getShaderParameter(fs, gl.COMPILE_STATUS)) {
            console.error('[Renderer] Fragment shader compile error:', gl.getShaderInfoLog(fs));
            gl.deleteShader(fs);
            return null;
        }

        const prog = gl.createProgram();
        gl.attachShader(prog, vs);
        gl.attachShader(prog, fs);
        gl.linkProgram(prog);

        // BUG-03 FIX: Check program link error
        if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) {
            console.error('[Renderer] Shader program link error:', gl.getProgramInfoLog(prog));
            gl.deleteProgram(prog);
            return null;
        }

        // Cleanup shaders after linking — they're no longer needed
        gl.deleteShader(vs);
        gl.deleteShader(fs);

        return prog;
    }

    _setupBuffers() {
        const gl = this.gl;
        const posBuffer = gl.createBuffer();
        gl.bindBuffer(gl.ARRAY_BUFFER, posBuffer);
        gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([
            -1.0, -1.0,
             1.0, -1.0,
            -1.0,  1.0,
            -1.0,  1.0,
             1.0, -1.0,
             1.0,  1.0
        ]), gl.STATIC_DRAW);

        const aPos = gl.getAttribLocation(this.program, "a_position");
        gl.enableVertexAttribArray(aPos);
        gl.vertexAttribPointer(aPos, 2, gl.FLOAT, false, 0, 0);

        const texBuffer = gl.createBuffer();
        gl.bindBuffer(gl.ARRAY_BUFFER, texBuffer);
        gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([
            0.0, 1.0,
            1.0, 1.0,
            0.0, 0.0,
            0.0, 0.0,
            1.0, 1.0,
            1.0, 0.0
        ]), gl.STATIC_DRAW);

        const aTex = gl.getAttribLocation(this.program, "a_texCoord");
        gl.enableVertexAttribArray(aTex);
        gl.vertexAttribPointer(aTex, 2, gl.FLOAT, false, 0, 0);
    }

    _setupTexture() {
        const gl = this.gl;
        this.texture = gl.createTexture();
        gl.bindTexture(gl.TEXTURE_2D, this.texture);
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
    }

    setSharpening(enabled, strength = 0.5) {
        this.isSharpenEnabled = enabled;
        this.sharpenStrength = strength;
        
        if (enabled && this.useWebGL) {
            this.canvas.style.display = 'block';
            // CRITICAL FIX: Do NOT set video.style.display = 'none'.
            // On mobile browsers, display: none causes the browser to suspend/mute audio decoding.
            // Instead, keep video rendered with near-zero opacity behind the canvas.
            this.video.style.position = 'absolute';
            this.video.style.opacity = '0.001';
            this.video.style.pointerEvents = 'none';
            this.video.style.display = 'block';
            this.startLoop();
        } else {
            this.canvas.style.display = 'none';
            this.video.style.position = '';
            this.video.style.opacity = '1';
            this.video.style.pointerEvents = '';
            this.video.style.display = 'block';
            this.stopLoop();
        }
    }

    startLoop() {
        if (this.animationFrameId) return;
        const render = () => {
            if (this.isSharpenEnabled && this.useWebGL && this.video.readyState >= 2) {
                const gl = this.gl;
                if (this.canvas.width !== this.video.videoWidth || this.canvas.height !== this.video.videoHeight) {
                    this.canvas.width = this.video.videoWidth || 1920;
                    this.canvas.height = this.video.videoHeight || 1080;
                    gl.viewport(0, 0, this.canvas.width, this.canvas.height);
                }

                gl.useProgram(this.program);
                gl.bindTexture(gl.TEXTURE_2D, this.texture);
                gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, this.video);

                const uRes = gl.getUniformLocation(this.program, "u_resolution");
                gl.uniform2f(uRes, this.canvas.width, this.canvas.height);

                const uSharpen = gl.getUniformLocation(this.program, "u_sharpen");
                gl.uniform1f(uSharpen, this.sharpenStrength);

                gl.drawArrays(gl.TRIANGLES, 0, 6);
            }
            this.animationFrameId = requestAnimationFrame(render);
        };
        this.animationFrameId = requestAnimationFrame(render);
    }

    clear() {
        if (this.gl && this.useWebGL) {
            this.gl.clearColor(0.0, 0.0, 0.0, 0.0);
            this.gl.clear(this.gl.COLOR_BUFFER_BIT);
        }
    }

    stopLoop() {
        if (this.animationFrameId) {
            cancelAnimationFrame(this.animationFrameId);
            this.animationFrameId = null;
        }
        if (this.canvas) {
            this.canvas.style.display = 'none';
        }
        if (this.video) {
            this.video.style.position = '';
            this.video.style.opacity = '1';
            this.video.style.pointerEvents = '';
            this.video.style.display = 'block';
        }
        this.clear();
    }
}

window.VideoRenderer = VideoRenderer;
