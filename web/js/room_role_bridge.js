(function(){
'use strict';
const qs=new URLSearchParams(location.search);
const isHost=qs.has('host')||qs.has('create');
const room=String(qs.get('host')||qs.get('room')||'').replace(/[^0-9A-Za-z_-]/g,'');
const isIOS=()=>/iPad|iPhone|iPod/.test(navigator.userAgent)||(/Macintosh/.test(navigator.userAgent)&&navigator.maxTouchPoints>1);
const bases=['http://127.0.0.1:8765','http://localhost:8765'];
let roleReady=false;
async function agent(path,opts={}){for(const b of bases){try{const r=await fetch(b+path,{...opts,cache:'no-store'});if(r.ok)return await r.json()}catch(_){} }throw new Error('agent-offline')}

function css(){
 if(document.getElementById('cs-role-css'))return;
 const s=document.createElement('style');s.id='cs-role-css';s.textContent=`
 body.cs-join #stage,body.cs-join #unmute,body.cs-join #fs,body.cs-join #exitfs,body.cs-join .hud,body.cs-join #infoBox{display:none!important}
 body.cs-join #share{display:block!important;visibility:visible!important;opacity:1!important;position:relative!important;z-index:20!important}
 body.cs-host #share{display:none!important}
 body.cs-join .controls{display:flex!important;justify-content:center!important}
 body.cs-join #share{flex:1 1 100%!important;min-height:58px!important;font-size:16px!important}
 .cs-join-card{display:none}
 body.cs-join .cs-join-card{display:grid!important;min-height:320px;place-items:center;text-align:center;padding:32px;border-radius:19px 19px 0 0;background:#02050a;color:#f8fafc}
 .cs-agent-actions{display:flex;gap:8px;margin-top:10px;align-items:center;flex-wrap:wrap}
 #csAgentCheck{background:#ffffff08;border:1px solid #ffffff1a;color:#f8fafc}
 #csAgentCheck:disabled{opacity:.65;cursor:wait}
 #csAgentState{font-size:11px;color:#94a3b8;margin-top:7px;line-height:1.45}
 `;document.head.appendChild(s);
}

function enforceRole(){
 document.body.classList.toggle('cs-host',isHost);document.body.classList.toggle('cs-join',!isHost);
 const ids=['stage','unmute','fs','exitfs','infoBox'];
 const share=document.getElementById('share');
 if(isHost){
  ids.forEach(id=>{const e=document.getElementById(id);if(e)e.style.removeProperty('display')});
  if(share){share.hidden=true;share.style.setProperty('display','none','important')}
  const jc=document.getElementById('csJoinCard');if(jc)jc.remove();
 }else{
  ids.forEach(id=>{const e=document.getElementById(id);if(e)e.style.setProperty('display','none','important')});
  if(share){share.hidden=false;share.disabled=false;share.textContent='📺 Chia sẻ màn hình';share.style.setProperty('display','block','important')}
  let jc=document.getElementById('csJoinCard');const section=document.querySelector('section.card');const controls=document.querySelector('.controls');
  if(!jc&&section&&controls){jc=document.createElement('div');jc.id='csJoinCard';jc.className='cs-join-card';jc.innerHTML='<div><div style="font-size:54px">📺</div><div style="font-size:24px;font-weight:950">Sẵn sàng chia sẻ</div><div style="font-size:13px;color:#94a3b8;margin-top:8px">Thiết bị này chỉ phát màn hình tới Host.</div></div>';section.insertBefore(jc,controls)}
 }
}

function agentUI(){
 if(!isHost)return;
 const panel=document.getElementById('agentPanel');if(!panel)return;
 if(document.getElementById('csAgentCheck'))return;
 const actions=document.createElement('div');actions.className='cs-agent-actions';
 const btn=document.createElement('button');btn.id='csAgentCheck';btn.type='button';btn.textContent='🔄 Kiểm tra Agent';
 actions.appendChild(btn);panel.appendChild(actions);
 const state=document.createElement('div');state.id='csAgentState';panel.appendChild(state);
 btn.addEventListener('click',()=>checkAgent(true));
 checkAgent(false);
}
async function checkAgent(manual){
 const btn=document.getElementById('csAgentCheck'),state=document.getElementById('csAgentState'),text=document.getElementById('agentText'),dot=document.getElementById('agentDot'),install=document.getElementById('install');
 if(btn){btn.disabled=true;btn.textContent='⏳ Kiểm tra…'}
 if(state)state.textContent='Đang kiểm tra localhost:8765…';
 try{
  const h=await agent('/health');
  if(!h?.ok)throw new Error('not-ready');
  if(dot)dot.classList.add('on');
  if(text)text.textContent='🟢 Agent đang chạy — sẵn sàng.';
  if(state)state.textContent='Kết nối localhost:8765 thành công.';
  if(install)install.hidden=true;
 }catch(_){
  if(dot)dot.classList.remove('on');
  if(text)text.textContent='🔴 Chưa kết nối được Agent.';
  if(state)state.textContent='Agent chưa chạy hoặc chưa được cài trên PC Host.';
  if(install)install.hidden=false;
  if(manual)alert('Không kết nối được Cast Screen Agent tại localhost:8765. Hãy mở Agent rồi bấm Kiểm tra Agent lại.');
 }finally{if(btn){btn.disabled=false;btn.textContent='🔄 Kiểm tra Agent'}}
}

function patchManager(){
 const M=window.WebRTCManager;if(!M||M.__csRoleBridge)return;
 M.__csRoleBridge=true;const p=M.prototype;
 const oldConnect=p.connect;p.connect=function(){window.__castScreenManager=this;return oldConnect.apply(this,arguments)};
 const oldHost=p._acceptClient;p._acceptClient=function(conn){const r=oldHost.apply(this,arguments);try{conn.on('data',data=>{if(data?.type==='client-platform')window.dispatchEvent(new CustomEvent('castscreen-client-platform',{detail:{platform:data.platform==='ios'?'ios':'other'}}))});conn.on('close',()=>window.dispatchEvent(new CustomEvent('castscreen-client-platform',{detail:{platform:'none'}})))}catch(_){}return r};
 const oldClient=p._connectToHost;p._connectToHost=function(){const r=oldClient.apply(this,arguments);window.__castScreenManager=this;const send=()=>{try{if(this.control?.open){this.control.send({type:'client-platform',platform:isIOS()?'ios':'other',roomId:this.roomId,t:Date.now()});return true}}catch(_){}return false};let n=0;const timer=setInterval(()=>{if(send()||++n>24)clearInterval(timer)},250);return r};
}

async function airplayLifecycle(){
 if(!isHost)return;let token='',ios=false;
 const stop=async()=>{try{await agent('/airplay/stop',{method:'POST',headers:token?{'X-CastScreen-Agent-Token':token}:{}})}catch(_) {}};
 const start=async()=>{if(!ios)return;try{const st=await agent('/airplay/status');token=st.token||token;await agent('/airplay/start',{method:'POST',headers:{'Content-Type':'application/json','X-CastScreen-Agent-Token':token,'X-CastScreen-iOS-Confirmed':'true'},body:JSON.stringify({roomId:room,resolution:'1920x1080',fps:60,sharpen:0})});const t=document.getElementById('agentText');if(t)t.textContent='🟢 iPhone đã vào phòng — AirPlay đang bật.'}catch(_){const t=document.getElementById('agentText');if(t)t.textContent='🔴 iPhone đã vào phòng nhưng Agent chưa kết nối.'}};
 try{const st=await agent('/airplay/status');token=st.token||'';await stop()}catch(_){}
 window.addEventListener('castscreen-client-platform',e=>{ios=e.detail?.platform==='ios';if(ios)start();else stop()});
 window.addEventListener('pagehide',stop);window.addEventListener('beforeunload',stop);
}

function wireJoinShare(){
 if(isHost)return;const b=document.getElementById('share');if(!b||b.dataset.csShare)return;b.dataset.csShare='1';
 b.onclick=async()=>{
  if(isIOS()){const m=document.getElementById('modal');if(m)m.classList.add('show');return}
  const m=window.__castScreenManager;if(!m){alert('Đang kết nối phòng, vui lòng thử lại sau vài giây.');return}
  try{const stream=await navigator.mediaDevices.getDisplayMedia({video:{frameRate:{ideal:60,max:60}},audio:true});await m.startScreenCapture(stream);b.textContent='🟢 Đang chia sẻ';stream.getVideoTracks()[0]?.addEventListener('ended',()=>b.textContent='📺 Chia sẻ màn hình')}catch(e){if(e?.name!=='NotAllowedError')alert('Không thể bắt đầu chia sẻ màn hình.')}};
}

function boot(){
 css();enforceRole();agentUI();patchManager();wireJoinShare();
 const observer=new MutationObserver(()=>{enforceRole();agentUI();patchManager();wireJoinShare()});observer.observe(document.documentElement,{subtree:true,childList:true,attributes:true,attributeFilter:['style','hidden','class']});
 if(isHost)airplayLifecycle();
}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot,{once:true});else boot();
})();