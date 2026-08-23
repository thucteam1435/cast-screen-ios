(() => {
  // Hard UI contract: HOST receives, JOIN sends. This runs immediately after room HTML
  // so the generic room UI cannot briefly expose the wrong controls.
  const q = new URLSearchParams(location.search);
  const isHost = q.has('host') || q.has('create');
  const $ = id => document.getElementById(id);
  function apply() {
    const share = $('share');
    const stage = $('stage');
    const video = $('video');
    const empty = $('empty');
    const hud = document.querySelector('.hud');
    const unmute = $('unmute');
    const fs = $('fs');
    const exitfs = $('exitfs');
    const info = $('infoBox');
    const hostBox = $('hostBox');
    const clientBox = $('clientBox');
    const agentPanel = $('agentPanel');
    const controls = document.querySelector('.controls');
    const side = document.querySelector('.side');

    if (isHost) {
      if (share) { share.style.display = 'none'; share.hidden = true; }
      if (hostBox) hostBox.style.display = '';
      if (clientBox) clientBox.style.display = 'none';
      if (stage) stage.style.display = '';
      if (video) video.style.display = '';
      if (empty) empty.style.display = 'grid';
      if (hud) hud.style.display = '';
      if (unmute) unmute.style.display = '';
      if (fs) fs.style.display = '';
      if (exitfs) exitfs.style.display = '';
      if (info) info.style.display = '';
      return;
    }

    // JOIN: sender-only. No receiver stage/preview or receiver controls.
    if (stage) stage.style.display = 'none';
    if (hud) hud.style.display = 'none';
    if (unmute) unmute.style.display = 'none';
    if (fs) fs.style.display = 'none';
    if (exitfs) exitfs.style.display = 'none';
    if (info) info.style.display = 'none';
    if (hostBox) hostBox.style.display = 'none';
    if (clientBox) clientBox.style.display = '';
    if (agentPanel) agentPanel.style.display = 'none';

    if (controls) {
      controls.style.display = 'flex';
      if (share) {
        share.hidden = false;
        share.style.display = 'block';
        share.textContent = '📺 Chia sẻ màn hình';
        share.className = 'primary';
        // Remove receiver buttons, leaving only Share + Leave.
        [unmute, fs, exitfs].forEach(b => { if (b) b.style.display = 'none'; });
      }
    }

    let panel = $('joinSharePanel');
    if (!panel && controls?.parentElement) {
      panel = document.createElement('div');
      panel.id = 'joinSharePanel';
      panel.style.cssText = 'min-height:320px;display:grid;place-items:center;text-align:center;padding:32px;border-radius:19px 19px 0 0;background:radial-gradient(520px 260px at 50% 20%,#22d3ee14,transparent 70%),#02050a;color:#f8fafc';
      panel.innerHTML = '<div><div style="font-size:54px;margin-bottom:14px">📺</div><div style="font-size:24px;font-weight:950;margin-bottom:8px">Sẵn sàng chia sẻ</div><div style="font-size:13px;line-height:1.6;color:#94a3b8;margin-bottom:20px">Bấm <b>Chia sẻ màn hình</b> để gửi màn hình thiết bị này tới Host.</div></div>';
      controls.parentElement.insertBefore(panel, controls);
    }
  }

  // Apply immediately and again after DOMContentLoaded because room_v6 also mutates the UI.
  apply();
  document.addEventListener('DOMContentLoaded', apply, { once: false });
  setTimeout(apply, 250);
  setTimeout(apply, 1000);
})();
