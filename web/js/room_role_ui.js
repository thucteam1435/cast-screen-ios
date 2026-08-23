(() => {
  'use strict';
  const ready = (fn) => {
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', fn, { once: true });
    else fn();
  };

  ready(() => {
    const qs = new URLSearchParams(location.search);
    const isHost = qs.has('host') || qs.has('create');
    const stage = document.getElementById('stage');
    const share = document.getElementById('share');
    const fullscreen = document.getElementById('fullscreen') || document.getElementById('fs');
    const exitFullscreen = document.getElementById('exitFullscreen') || document.getElementById('exitfs');
    const unmute = document.getElementById('unmute');
    const hostPanel = document.getElementById('hostPanel') || document.getElementById('hostBox');
    const clientPanel = document.getElementById('clientPanel') || document.getElementById('clientBox');
    const agentPanel = document.getElementById('agentPanel');
    const quality = document.getElementById('quality');
    const info = document.getElementById('infoBox');
    const remoteVideo = document.getElementById('remoteVideo') || document.getElementById('video');
    const empty = document.getElementById('empty');
    if (!stage || !share) return;

    // The room contract is strict:
    // HOST = receiver/viewer only.
    // CLIENT = sender only, no remote-view area.
    if (isHost) {
      share.hidden = true;
      share.style.display = 'none';
      if (hostPanel) hostPanel.style.display = '';
      if (clientPanel) clientPanel.style.display = 'none';
      if (agentPanel) agentPanel.style.display = '';
      if (quality) quality.style.display = '';
      if (stage) stage.style.display = '';
      if (fullscreen) fullscreen.style.display = '';
      if (exitFullscreen) exitFullscreen.style.display = '';
      if (unmute) unmute.style.display = '';
      if (info) info.style.display = '';
      return;
    }

    // CLIENT / JOIN: sender-only UI.
    if (hostPanel) hostPanel.style.display = 'none';
    if (clientPanel) clientPanel.style.display = '';
    if (agentPanel) agentPanel.style.display = 'none';
    if (quality) quality.style.display = 'none';
    if (fullscreen) fullscreen.style.display = 'none';
    if (exitFullscreen) exitFullscreen.style.display = 'none';
    if (unmute) unmute.style.display = 'none';
    if (info) info.style.display = 'none';

    stage.style.display = 'none';
    share.hidden = false;
    share.style.display = 'block';
    share.textContent = '📺 Chia sẻ màn hình';
    share.title = 'Gửi màn hình của thiết bị này tới Host';

    const card = stage.parentElement;
    if (card && !document.getElementById('senderOnlyPanel')) {
      const panel = document.createElement('div');
      panel.id = 'senderOnlyPanel';
      panel.style.cssText = [
        'min-height:340px','display:grid','place-items:center','padding:32px',
        'text-align:center','border-radius:19px 19px 0 0',
        'background:radial-gradient(520px 260px at 50% 20%,#22d3ee14,transparent 70%),#02050a'
      ].join(';');
      panel.innerHTML = `
        <div style="max-width:460px">
          <div style="font-size:48px;margin-bottom:16px">📺</div>
          <div style="font-size:22px;font-weight:950;margin-bottom:8px">Thiết bị chia sẻ màn hình</div>
          <div style="font-size:13px;line-height:1.6;color:#94a3b8;margin-bottom:22px">
            Bạn đang là thiết bị phát. Màn hình của bạn sẽ được gửi trực tiếp tới máy Host.
          </div>
          <div style="font-size:11px;color:#64748b">Không hiển thị preview trên thiết bị Join để giảm tải và độ trễ.</div>
        </div>`;
      card.insertBefore(panel, card.querySelector('.controls'));
    }

    // Prevent the old room callback from ever showing a remote stream on Join.
    const observer = new MutationObserver(() => {
      if (remoteVideo) {
        remoteVideo.pause?.();
        remoteVideo.srcObject = null;
        remoteVideo.style.display = 'none';
      }
      if (empty) empty.style.display = 'none';
    });
    observer.observe(document.body, { subtree: true, attributes: true, attributeFilter: ['style', 'hidden'] });
  });
})();
