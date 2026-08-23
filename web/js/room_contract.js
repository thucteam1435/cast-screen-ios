/* Cast Screen room contract: Host=receiver, Join=sender. Agent starts only when an iOS client is present. */
(()=>{
'use strict';
const q=new URLSearchParams(location.search),isHost=q.has('host')||q.has('create');
const room=String(q.get('host')||q.get('room')||'').replace(/[^0-9A-Za-z_-]/g,'');
const $=id=>document.getElementById(id),bases=['http://127.0.0.1:8765','http://localhost:8765'];
let agentToken='',agentOnline=false,iosPresent=false,checkBusy=false;
async function agent(path,opts={}){for(const b of bases){try{const r=await fetch(b+path,{...opts,cache:'no-store'});if(r.ok)return await r.json()}catch(_){}}throw new Error('agent-offline')}
function set(id,text){const e=$(id);if(e)e.textContent=text}
function enforceRole(){
 const stage=$('stage'),video=$('video'),empty=$('empty'),share=$('share'),unmute=$('unmute'),fs=$('fs'),exitfs=$('exitfs'),hud=document.querySelector('.hud'),info=$('infoBox'),host=$('hostBox'),client=$('clientBox'),panel=$('agentPanel'),controls=document.querySelector('.controls');
 if(isHost){
  [stage,video,empty,hud,info,host,panel,unmute,fs,exitfs].forEach(e=>{if(e)e.style.setProperty('display','','important')});
  if(share){share.hidden=true;share.style.setProperty('display','none','important')}
  if(client)client.style.setProperty('display','none','important');
 }else{
  [stage,video,empty,hud,info,panel,unmute,fs,exitfs,host].forEach(e=>{if(e)e.style.setProperty('display','none','important')});
  if(client)client.style.setProperty('display','block','important');
  if(controls)controls.style.setProperty('display','flex','important');
  if(share){share.hidden=false;share.style.setProperty('display','inline-flex','important');share.textContent='📺 Chia sẻ màn hình';share.className='primary'}
  let p=$('joinOnlyPanel');
  if(!p){p=document.createElement('div');p.id='joinOnlyPanel';p.style.cssText='display:grid;place-items:center;min-height:360px;padding:32px;text-align:center;background:#02050a;color:#f8fafc;border-radius:19px 19px 0 0';p.innerHTML='<div><div style="font-size:58px;margin-bottom:14px">📺</div><div style="font-size:25px;font-weight:950">Sẵn sàng chia sẻ</div><div style="margin-top:9px;color:#94a3b8;font-size:13px">Thiết bị này chỉ phát màn hình tới Host.</div><div style="margin-top:6px;color:#64748b;font-size:12px">Bấm nút <b>Chia sẻ màn hình</b> bên dưới để bắt đầu.</div></div>';
   const card=stage?.parentElement;if(card&&stage)card.insertBefore(p,stage);else document.body.prepend(p);
  }
 }
}
function installAgentCheck(){
 if(!isHost)return;const panel=$('agentPanel');if(!panel)return;const install=$('install');let btn=$('checkAgent');
 if(!btn){btn=document.createElement('button');btn.id='checkAgent';btn.type='button';btn.textContent='🔄 Kiểm tra Agent';btn.className='ghost';btn.style.cssText='width:100%;margin-top:9px';panel.appendChild(btn)}
 if(install)install.querySelector('a')?.setAttribute('target','_blank');btn.onclick=()=>checkAgent(true);
}
async function checkAgent(){
 if(!isHost||checkBusy)return;checkBusy=true;const dot=$('agentDot'),install=$('install'),btn=$('checkAgent');if(btn)btn.disabled=true;
 try{const h=await agent('/health');agentOnline=!!h.ok;if(!agentOnline)throw 0;const s=await agent('/airplay/status');agentToken=s.token||'';if(dot)dot.className='dot on';set('agentText',iosPresent?'🟢 Agent đang chạy · iPhone đã vào phòng.':'🟢 Agent đang chạy · Chờ iPhone vào phòng.');if(install)install.hidden=true}
 catch(_){agentOnline=false;if(dot)dot.className='dot';set('agentText','🔴 Agent chưa chạy hoặc chưa được cài trên PC Host.');if(install)install.hidden=false}
 if(btn){btn.disabled=false;btn.textContent=agentOnline?'🔄 Kiểm tra lại Agent':'🔄 Kiểm tra Agent'}checkBusy=false;
}
async function startAirplay(){if(!isHost||!agentOnline||!iosPresent)return;try{if(!agentToken){const s=await agent('/airplay/status');agentToken=s.token||''}await agent('/airplay/start',{method:'POST',headers:{'Content-Type':'application/json','X-CastScreen-Agent-Token':agentToken,'X-CastScreen-iOS-Confirmed':'true'},body:JSON.stringify({roomId:room,resolution:'1920x1080',fps:60,sharpen:0})});set('agentText','🟢 Agent đang chạy · 🟢 iPhone đã vào phòng · AirPlay đang bật')}catch(e){console.warn('[CastScreen] AirPlay start failed',e)}}
async function stopAirplay(){if(!isHost||!agentOnline)return;try{await agent('/airplay/stop',{method:'POST',headers:agentToken?{'X-CastScreen-Agent-Token':agentToken}:{}})}catch(_){} }
async function bind(){
 enforceRole();installAgentCheck();
 if(isHost){await checkAgent();if(!iosPresent)await stopAirplay();window.addEventListener('castscreen-client-platform',e=>{iosPresent=e.detail?.platform==='ios';if(iosPresent)startAirplay();else stopAirplay()});const poll=setInterval(()=>{checkAgent()},5000);window.addEventListener('pagehide',()=>{clearInterval(poll);stopAirplay()},{once:true})}
}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>setTimeout(bind,0),{once:true});else setTimeout(bind,0);
const mo=new MutationObserver(()=>enforceRole());mo.observe(document.documentElement,{subtree:true,childList:true,attributes:true,attributeFilter:['style','hidden']});
})();
