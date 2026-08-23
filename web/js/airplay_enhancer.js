(() => {
  'use strict';

  const $ = (id) => document.getElementById(id);
  const room = new URLSearchParams(location.search).get('room') || new URLSearchParams(location.search).get('host');
  const isHost = !!new URLSearchParams(location.search).get('host') || new URLSearchParams(location.search).has('create');
  if (!isHost || !room) return;

  const baseCandidates = ['http://127.0.0.1:8765', 'http://localhost:8765'];
  let token = '';
  let audioCtx = null;
  let audioStarted = false;
  let audioReader = null;
  let nextAudioTime = 0;
  let glCanvas = null;
  let gl = null;
  let glProgram = null;
  let texture = null;
  let uTex = null;
  let uSize = null;
  let uAmount = null;
  let framePump = 0;
  let lastSourceSize = '';

  async function agent(path, options = {}) {
    for (const base of baseCandidates) {
      try {
        const r = await fetch(base + path, { ...options, cache: 'no-store' });
        if (r.ok) return r.json();
      } catch (_) {}
    }
    throw new Error('agent-offline');
  }

  function ensureGl() {
    const src = $('airplayCanvas');
    const stage = $('stage');
    if (!src || !stage) return false;
    if (gl && glCanvas) return true;
    glCanvas = document.createElement('canvas');
    glCanvas.id = 'airplayEnhancedCanvas';
    glCanvas.style.position = 'absolute';
    glCanvas.style.inset = '0';
    glCanvas.style.width = '100%';
    glCanvas.style.height = '100%';
    glCanvas.style.objectFit = 'contain';
    glCanvas.style.display = 'none';
    glCanvas.style.pointerEvents = 'none';
    stage.appendChild(glCanvas);
    gl = glCanvas.getContext('webgl2', { alpha: false, antialias: false, desynchronized: true }) ||
         glCanvas.getContext('webgl', { alpha: false, antialias: false, desynchronized: true });
    if (!gl) return false;

    const vs = gl.createShader(gl.VERTEX_SHADER);
    gl.shaderSource(vs, `attribute vec2 aPos; attribute vec2 aUv; varying vec2 vUv; void main(){gl_Position=vec4(aPos,0.0,1.0);vUv=aUv;}`);
    gl.compileShader(vs);
    const fs = gl.createShader(gl.FRAGMENT_SHADER);
    gl.shaderSource(fs, `precision mediump float; uniform sampler2D uTex; uniform vec2 uSize; uniform float uAmount; varying vec2 vUv; void main(){vec2 p=1.0/uSize;vec3 c=texture2D(uTex,vUv).rgb;vec3 n=texture2D(uTex,vUv+vec2(0.0,-p.y)).rgb;vec3 s=texture2D(uTex,vUv+vec2(0.0,p.y)).rgb;vec3 e=texture2D(uTex,vUv+vec2(p.x,0.0)).rgb;vec3 w=texture2D(uTex,vUv+vec2(-p.x,0.0)).rgb;vec3 blur=(n+s+e+w)*0.25;vec3 sharp=c+(c-blur)*uAmount;gl_FragColor=vec4(clamp(sharp,0.0,1.0),1.0);}`);
    gl.compileShader(fs);
    glProgram = gl.createProgram();
    gl.attachShader(glProgram, vs); gl.attachShader(glProgram, fs); gl.linkProgram(glProgram);
    if (!gl.getProgramParameter(glProgram, gl.LINK_STATUS)) return false;
    gl.useProgram(glProgram);

    const buf = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buf);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([
      -1,-1, 0,1,
       1,-1, 1,1,
      -1, 1, 0,0,
       1, 1, 1,0
    ]), gl.STATIC_DRAW);
    const pos = gl.getAttribLocation(glProgram, 'aPos');
    const uv = gl.getAttribLocation(glProgram, 'aUv');
    gl.enableVertexAttribArray(pos); gl.vertexAttribPointer(pos,2,gl.FLOAT,false,16,0);
    gl.enableVertexAttribArray(uv); gl.vertexAttribPointer(uv,2,gl.FLOAT,false,16,8);
    texture = gl.createTexture();
    gl.bindTexture(gl.TEXTURE_2D, texture);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
    uTex = gl.getUniformLocation(glProgram, 'uTex');
    uSize = gl.getUniformLocation(glProgram, 'uSize');
    uAmount = gl.getUniformLocation(glProgram, 'uAmount');
    gl.uniform1i(uTex, 0);
    return true;
  }

  function pumpShader() {
    const src = $('airplayCanvas');
    const slider = $('sharpen');
    if (!src || !gl || !glCanvas || !slider) return;
    const amount = Math.max(0, Math.min(1, Number(slider.value || 0) / 100));
    if (!src.width || !src.height) return;
    if (lastSourceSize !== `${src.width}x${src.height}`) {
      lastSourceSize = `${src.width}x${src.height}`;
      glCanvas.width = src.width;
      glCanvas.height = src.height;
    }
    if (amount <= 0) {
      glCanvas.style.display = 'none';
      src.style.display = 'block';
    } else {
      glCanvas.style.display = 'block';
      src.style.display = 'none';
      gl.viewport(0, 0, glCanvas.width, glCanvas.height);
      gl.activeTexture(gl.TEXTURE0);
      gl.bindTexture(gl.TEXTURE_2D, texture);
      gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, true);
      gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, src);
      gl.uniform2f(uSize, src.width, src.height);
      gl.uniform1f(uAmount, amount * 1.4);
      gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
    }
  }

  function animate() {
    pumpShader();
    framePump = requestAnimationFrame(animate);
  }

  async function startAudio() {
    if (audioStarted) {
      if (audioCtx && audioCtx.state === 'suspended') await audioCtx.resume();
      return;
    }
    try {
      const s = await agent('/airplay/status');
      token = s.token || token;
      const response = await Promise.race(baseCandidates.map(async base => {
        const r = await fetch(base + '/airplay/audio', {
          cache: 'no-store',
          headers: { 'X-CastScreen-Agent-Token': token }
        });
        if (!r.ok || !r.body) throw new Error('audio-http');
        return r;
      }));
      audioCtx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 44100 });
      await audioCtx.resume();
      audioStarted = true;
      $('unmute').textContent = '🔊 Đang phát âm thanh';
      audioReader = response.body.getReader();
      nextAudioTime = audioCtx.currentTime + 0.05;
      readAudio();
    } catch (e) {
      console.warn('[CastScreen] AirPlay audio unavailable', e);
      if ($('unmute')) $('unmute').textContent = '🔊 Chưa có âm thanh';
    }
  }

  async function readAudio() {
    if (!audioReader || !audioCtx) return;
    let buf = new Uint8Array(0);
    try {
      while (audioReader) {
        const { value, done } = await audioReader.read();
        if (done) break;
        const joined = new Uint8Array(buf.length + value.length);
        joined.set(buf); joined.set(value, buf.length); buf = joined;
        while (buf.length >= 12) {
          const len = new DataView(buf.buffer, buf.byteOffset, buf.byteLength).getUint32(0);
          if (len < 8 || buf.length < 4 + len) break;
          const payload = buf.slice(12, 4 + len);
          const frames = Math.floor(payload.length / 4);
          if (frames > 0) {
            const ab = audioCtx.createBuffer(2, frames, 44100);
            const l = ab.getChannelData(0), r = ab.getChannelData(1);
            for (let i = 0; i < frames; i++) {
              const j = i * 4;
              const lv = (payload[j] << 8) | payload[j + 1];
              const rv = (payload[j + 2] << 8) | payload[j + 3];
              const ls = lv & 0x8000 ? lv - 0x10000 : lv;
              const rs = rv & 0x8000 ? rv - 0x10000 : rv;
              l[i] = ls / 32768; r[i] = rs / 32768;
            }
            const src = audioCtx.createBufferSource();
            src.buffer = ab; src.connect(audioCtx.destination);
            const t = Math.max(audioCtx.currentTime + 0.01, nextAudioTime);
            src.start(t); nextAudioTime = t + ab.duration;
          }
          buf = buf.slice(4 + len);
        }
      }
    } catch (e) {
      console.warn('[CastScreen] audio stream ended', e);
    } finally {
      audioReader = null;
    }
  }

  async function pollAgent() {
    try {
      const s = await agent('/airplay/status');
      token = s.token || token;
      const connected = !!s.airplay_connected && !!s.approved;
      if (connected && $('unmute')) $('unmute').disabled = false;
      if (!connected && audioStarted) {
        try { if (audioCtx) await audioCtx.close(); } catch (_) {}
        audioCtx = null; audioStarted = false; audioReader = null;
        if ($('unmute')) { $('unmute').disabled = true; $('unmute').textContent = '🔊 Bật âm thanh'; }
      }
    } catch (_) {}
    setTimeout(pollAgent, 1500);
  }

  document.addEventListener('DOMContentLoaded', () => {
    ensureGl();
    animate();
    const sharp = $('sharpen');
    if (sharp) sharp.addEventListener('input', pumpShader);
    const unmute = $('unmute');
    if (unmute) unmute.addEventListener('click', () => { startAudio(); });
    pollAgent();
  });
})();
