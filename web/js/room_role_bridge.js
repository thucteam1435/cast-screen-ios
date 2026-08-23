(function(){
'use strict';
const isIOS=()=>/iPad|iPhone|iPod/.test(navigator.userAgent)||(/Macintosh/.test(navigator.userAgent)&&navigator.maxTouchPoints>1);
const qs=new URLSearchParams(location.search);
const isHost=qs.has('host')||qs.has('create');
const room=String(qs.get('host')||qs.get('room')||'').replace(/[^0-9A-Za-z_-]/g,'');
const bases=['http://127.0.0.1:8765','http://localhost:8765'];
async function agent(path,opts={}){for(const b of bases){try{const r=await fetch(b+path,{...opts,cache:'no-store'});if(r.ok)return await r.json()}catch(_){}}throw new Error('agent-offline')}
function enforceRole(){
 const share=document.getElementById('share'),stage=document.getElementById('stage'),video=document.getElementById('video'),empty=document.getElementById('empty'),unmute=document.getElementById('unmute'),fs=document.getElementById('fs'),exitfs=document.getElementById('exitfs'),hud=document.querySelector('.hud'),info=document.getElementById('infoBox'),host=document.getElementById('hostBox'),client=document.getElementById('clientBox'),agentPanel=document.getElementById('agentPanel');
 if(isHost){
  if(share){share.hidden=true;share.style.display='none';}
  if(stage)stage.style.display=''; if(video)video.style.display=''; if(empty)empty.style.display='grid';
  if(host)host.style.display=''; if(client)client.style.display='none'; if(agentPanel)agentPanel.style.display='';
  if(unmute)unmute.style.display=''; if(fs)fs.style.display=''; if(exitfs)exitfs.style.display=''; if(hud)hud.style.display=''; if(info)info.style.display='grid';
 }else{
  if(share){share.hidden=false;share.style.display='block';share.textContent='📺 Chia sẻ màn hình';}
  if(stage)stage.style.display='none'; if(video)video.style.display='none'; if(empty)empty.style.display='none';
  if(host)host.style.display='none'; if(client)client.style.display=''; if(agentPanel)agentPanel.style.display='none';
  if(unmute)unmute.style.display='none'; if(fs)fs.style.display='none'; if(exitfs)exitfs.style.display='none'; if(hud)hud.style.display='none'; if(info)info.style.display='none';
 }
}
function patchManager(){
 const M=window.WebRTCManager;if(!M||M.__roleBridgePatched)return false;M.__roleBridgePatched=true;const p=M.prototype;
 const origConnect=p._connectToHost;
 p._connectToHost=function(){const r=origConnect.apply(this,arguments);const send=()=>{try{if(this.control?.open)this.control.send({type:'client-platform',platform:isIOS()?'ios':'other',roomId:this.roomId})}catch(_){}};setTimeout(send,50);setTimeout(send,300);setTimeout(send,1000);return r};
 const origAccept=p._acceptClient;
 p._acceptClient=function(conn){const r=origAccept.apply(this,arguments);try{conn.on('data',data=>{if(data?.type==='client-platform'){window.dispatchEvent(new CustomEvent('castscreen-client-platform',{detail:{platform:data.platform==='ios'?'ios':'other',peer:conn.peer}}))}});conn.on('close',()=>window.dispatchEvent(new CustomEvent('castscreen-client-platform',{detail:{platform:'none',peer:conn.peer}})))}catch(_){}return r};
 return true;
}
async function hostAirplayLifecycle(){
 if(!isHost)return;
 let token='';let iosPresent=false;let serial=0;
 async function stop(){try{await agent('/airplay/stop',{method:'POST',headers:token?{'X-CastScreen-Agent-Token':token}:{}})}catch(_){} }
 async function start(){try{const s=await agent('/airplay/status');token=s.token||token;if(!iosPresent){await stop();return}await agent('/airplay/start',{method:'POST',headers:{'Content-Type':'application/json','X-CastScreen-Agent-Token':token},body:JSON.stringify({roomId:room,resolution:'1920x1080',fps:60,sharpen:0})});await agent('/airplay/lease',{method:'POST',headers:{'Content-Type':'application/json','X-CastScreen-Agent-Token':token},body:JSON.stringify({roomId:room})})}catch(_){} }
 // Neutralize any stale receiver from a previous room as soon as the local Agent is reachable.
 const neutralize=async()=>{try{const s=await agent('/airplay/status');token=s.token||token;await stop()}catch(_){} };
 neutralize();
 window.addEventListener('castscreen-client-platform',ev=>{iosPresent=ev.detail?.platform==='ios';if(iosPresent){serial++;start();}else{serial++;stop();}});
 // Keep lease only while the iOS client is actually present.
 setInterval(()=>{if(iosPresent)start();},2000);
}
function boot(){
 enforceRole();patchManager();setTimeout(()=>{enforceRole();patchManager();},0);setTimeout(()=>{enforceRole();patchManager();},250);setTimeout(()=>{enforceRole();patchManager();},1000);
 if(isHost)hostAirplayLifecycle();
 const observer=new MutationObserver(()=>enforceRole());observer.observe(document.body,{subtree:true,childList:true,attributes:true,attributeFilter:['style','hidden']});
 setTimeout(()=>observer.disconnect(),15000);
}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot,{once:true});else boot();
})();
