(() => {
 const q = new URLSearchParams(location.search);
 const isHost = q.has('host') || q.has('create');
 const roomId = (q.get('host') || q.get('room') || '').replace(/\D/g,'').slice(0,6);
 const isIOS = /iPad|iPhone|iPod/.test(navigator.userAgent) || (/Macintosh/.test(navigator.userAgent) && navigator.maxTouchPoints > 1);
 const $ = id => document.getElementById(id);
 let platformSocket = null;
 let platformTimer = null;
 let lastIOSHeartbeat = 0;
 let iosClientActive = false;
 let agentToken = '';
 let agentGateInstalled = false;

 const agentBases = ['http://127.0.0.1:8765','http://localhost:8765'];
 async function api(path, opts={}) {
   for (const base of agentBases) {
     try {
       const r = await fetch(base + path, {...opts, cache:'no-store'});
       if (r.ok) return await r.json();
     } catch (_) {}
   }
   throw new Error('agent-offline');
 }

 function localAgentUrl(input) {
   try { return new URL(input, location.href); } catch (_) { return null; }
 }

 /*
  * The room page currently contains the generic Host Agent bootstrap.
  * We gate ONLY /airplay/start so the Host may remain connected to the
  * localhost Agent without actually starting UxPlay/mDNS until an iPhone
  * has joined this room.
  */
 function installAgentGate() {
   if (agentGateInstalled || !isHost) return;
   agentGateInstalled = true;
   const nativeFetch = window.fetch.bind(window);
   window.fetch = async (input, init) => {
     const u = localAgentUrl(typeof input === 'string' ? input : input?.url || '');
     if (u && /(?:127\.0\.0\.1|localhost):8765$/.test(u.host) && u.pathname === '/airplay/start' && !iosClientActive) {
       return new Response(JSON.stringify({ok:false, blockedUntilIOS:true}), {
         status: 409,
         headers: {'Content-Type':'application/json','Cache-Control':'no-store'}
       });
     }
     return nativeFetch(input, init);
   };
 }

 function setAgentStatus(on, text) {
   const dot = $('agentDot');
   const label = $('agentText');
   const install = $('install');
   if (dot) dot.className = on ? 'dot on' : 'dot';
   if (label && text) label.textContent = text;
   if (install) install.hidden = !!on;
 }

 async function startAgentBecauseIOS() {
   if (!isHost || !iosClientActive) return;
   try {
     const st = await api('/airplay/status');
     agentToken = st.token || agentToken;
     if (!agentToken) throw new Error('missing-agent-token');
     const cfg = {
       resolution: $('resolution')?.value || '1920x1080',
       fps: Number($('fpsSelect')?.value || 60),
       sharpen: Number($('sharpen')?.value || 0),
       roomId
     };
     const res = await api('/airplay/start', {
       method:'POST',
       headers:{'Content-Type':'application/json','X-CastScreen-Agent-Token':agentToken},
       body:JSON.stringify(cfg)
     });
     if (res?.ok) setAgentStatus(true, 'iPhone đã vào phòng — AirPlay đang bật trên PC Host.');
   } catch (_) {
     setAgentStatus(false, 'iPhone đã vào phòng nhưng Cast Screen AirPlay Agent chưa sẵn sàng.');
   }
 }

 async function stopAgentBecauseNoIOS() {
   if (!isHost || iosClientActive) return;
   try {
     if (!agentToken) {
       const st = await api('/airplay/status');
       agentToken = st.token || '';
     }
     if (agentToken) await api('/airplay/stop', {method:'POST', headers:{'X-CastScreen-Agent-Token':agentToken}});
   } catch (_) {}
   setAgentStatus(false, 'Không có iPhone trong phòng — AirPlay đang tắt.');
 }

 function connectPlatformSignaling() {
   if (!roomId) return;
   const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
   const role = isHost ? 'host' : 'client';
   const ws = new WebSocket(`${proto}//${location.host}/ws?room=${encodeURIComponent(roomId)}&role=${role}`);
   platformSocket = ws;
   ws.addEventListener('open', () => {
     if (!isHost) sendPlatformHeartbeat();
   });
   ws.addEventListener('message', e => {
     if (!isHost) return;
     let d;
     try { d = JSON.parse(e.data); } catch (_) { return; }
     if (d?.type !== 'client-platform') return;
     const platform = String(d.platform || '').toLowerCase();
     lastIOSHeartbeat = Date.now();
     const next = platform === 'ios';
     if (next !== iosClientActive) {
       iosClientActive = next;
       if (iosClientActive) startAgentBecauseIOS();
       else stopAgentBecauseNoIOS();
     }
   });
   ws.addEventListener('close', () => {
     platformSocket = null;
     if (platformTimer) { clearInterval(platformTimer); platformTimer = null; }
     if (isHost) {
       iosClientActive = false;
       stopAgentBecauseNoIOS();
     }
   });
 }

 function sendPlatformHeartbeat() {
   if (isHost || !platformSocket || platformSocket.readyState !== WebSocket.OPEN) return;
   const platform = isIOS ? 'ios' : 'other';
   platformSocket.send(JSON.stringify({type:'client-platform', platform, roomId, t:Date.now()}));
 }

 function installHostIOSWatchdog() {
   if (!isHost) return;
   setInterval(() => {
     if (iosClientActive && lastIOSHeartbeat && Date.now() - lastIOSHeartbeat > 6500) {
       iosClientActive = false;
       stopAgentBecauseNoIOS();
     }
   }, 1500);
 }

 installAgentGate();
 connectPlatformSignaling();
 if (!isHost) {
   clearInterval(platformTimer);
   platformTimer = setInterval(sendPlatformHeartbeat, 2000);
 }
 installHostIOSWatchdog();

 document.addEventListener('DOMContentLoaded', () => {
   const share=$('share'),stage=$('stage'),video=$('video')||$('remoteVideo'),empty=$('empty'),unmute=$('unmute'),fullscreen=$('fullscreen')||$('fs'),exitFullscreen=$('exitFullscreen')||$('exitfs'),info=$('infoBox'),quality=$('quality'),hostPanel=$('hostPanel')||$('hostBox'),clientPanel=$('clientPanel')||$('clientBox'),agentPanel=$('agentPanel');

   // HOST = receiver/viewer only. CLIENT/JOIN = sender only.
   if(isHost){
     if(share){share.hidden=true;share.style.display='none';}
     if(hostPanel)hostPanel.style.display='';
     if(clientPanel)clientPanel.style.display='none';
     setAgentStatus(false,'Đang chờ iPhone vào phòng — AirPlay chưa bật.');
   }else{
     if(hostPanel)hostPanel.style.display='none';
     if(clientPanel)clientPanel.style.display='';
     if(agentPanel)agentPanel.style.display='none';
     if(quality)quality.style.display='none';
     if(stage){
       stage.style.display='none';
       const section=stage.parentElement;
       if(section&&!$('senderOnlyPanel')){
         const panel=document.createElement('div');
         panel.id='senderOnlyPanel';
         panel.style.cssText='min-height:340px;display:grid;place-items:center;padding:32px;text-align:center;border-radius:19px 19px 0 0;background:radial-gradient(520px 260px at 50% 20%,#22d3ee14,transparent 70%),#02050a';
         panel.innerHTML='<div style="max-width:460px"><div style="font-size:52px;margin-bottom:16px">📺</div><div style="font-size:23px;font-weight:950;margin-bottom:9px">Sẵn sàng chia sẻ</div><div style="font-size:13px;line-height:1.6;color:#94a3b8;margin-bottom:20px">Thiết bị này là nguồn phát. Bấm <b>Chia sẻ màn hình</b> để gửi màn hình tới máy Host.</div><div style="font-size:11px;color:#64748b">Không hiển thị preview trên máy Join để giảm tải và độ trễ.</div></div>';
         section.insertBefore(panel,section.querySelector('.controls'));
       }
     }
     if(unmute)unmute.style.display='none';
     if(fullscreen)fullscreen.style.display='none';
     if(exitFullscreen)exitFullscreen.style.display='none';
     if(info)info.style.display='none';
     if(share){share.hidden=false;share.style.display='block';share.textContent='📺 Chia sẻ màn hình';}
   }

   if(!isHost)return;
   const hostVideo=video,hostEmpty=empty;
   let token='',reader=null,started=false,poll=0,lastEvent=0,canvas=null,ctx=null,decoder=null;
   function ensureCanvas(){if(canvas)return;canvas=document.createElement('canvas');canvas.id='airplayWebCanvas';canvas.style.cssText='position:absolute;inset:0;width:100%;height:100%;object-fit:contain;background:#02050a;z-index:2';canvas.hidden=true;if(hostVideo?.parentElement)hostVideo.parentElement.appendChild(canvas);ctx=canvas.getContext('2d',{alpha:false,desynchronized:true});}
   async function startVideo(){if(started||!iosClientActive)return;started=true;ensureCanvas();try{if(typeof VideoDecoder==='undefined')throw new Error('WebCodecs unavailable');const response=await fetch('http://127.0.0.1:8765/airplay/video',{cache:'no-store',headers:{'X-CastScreen-Agent-Token':token}});if(!response.ok||!response.body)throw new Error('airplay-video-unavailable');reader=response.body.getReader();decoder=new VideoDecoder({output:frame=>{canvas.width=frame.displayWidth;canvas.height=frame.displayHeight;const sharp=Math.min(1,Number(localStorage.getItem('castscreen_sharpen')||0)/100);ctx.filter=sharp?'contrast('+Math.min(1.18,1+sharp*.12)+') saturate('+Math.min(1.12,1+sharp*.08)+')':'none';ctx.drawImage(frame,0,0,canvas.width,canvas.height);frame.close();canvas.hidden=false;if(hostVideo)hostVideo.hidden=true;if(hostEmpty)hostEmpty.style.display='none'},error:e=>console.warn('[CastScreen] AirPlay decode',e)});decoder.configure({codec:'avc1.640028',optimizeForLatency:true});let buf=new Uint8Array(0);while(reader){const {value,done}=await reader.read();if(done)break;if(!value)continue;const next=new Uint8Array(buf.length+value.length);next.set(buf);next.set(value,buf.length);buf=next;while(buf.length>=13){const dv=new DataView(buf.buffer,buf.byteOffset,buf.byteLength);const len=dv.getUint32(0);if(len<9||buf.length<4+len)break;const pts=Number(dv.getBigUint64(4)),key=!!buf[12],payload=buf.slice(13,4+len);try{decoder.decode(new EncodedVideoChunk({type:key?'key':'delta',timestamp:pts,data:payload}));}catch(e){console.warn('[CastScreen] decode chunk',e)}buf=buf.slice(4+len)}}}catch(e){console.warn('[CastScreen] Host AirPlay web video unavailable',e)}finally{started=false;reader=null;try{decoder&&decoder.close()}catch(_){}decoder=null}}
   async function pollAgent(){try{const s=await api('/airplay/status');token=s.token||token;if(s.airplay_connected&&s.approved&&iosClientActive&&!started)startVideo();if(!s.airplay_connected&&canvas){canvas.hidden=true;if(hostVideo)hostVideo.hidden=false;}}catch(_){}poll=setTimeout(pollAgent,900)}
   pollAgent();
 });

 window.addEventListener('pagehide',()=>{if(platformSocket){try{platformSocket.close();}catch(_){} } if(platformTimer)clearInterval(platformTimer);});
})();
