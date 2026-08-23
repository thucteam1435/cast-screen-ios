/**
 * Cast Screen WebRTC manager.
 * PeerJS is rendezvous/control only; media uses direct LAN host candidates.
 */
class WebRTCManager {
    constructor(options = {}) {
        this.role = options.role === 'host' ? 'host' : 'client';
        this.isHost = this.role === 'host';
        this.roomId = String(options.roomId || '').replace(/[^a-zA-Z0-9_-]/g, '').slice(0, 40);
        if (!this.roomId) throw new Error('roomId is required');
        this.onStream = options.onStream || null;
        this.onStreamEnded = options.onStreamEnded || null;
        this.onStatusChange = options.onStatusChange || null;
        this.onMetrics = options.onMetrics || null;
        this.onPeerCountChange = options.onPeerCountChange || null;
        this.peer = null; this.peerId = ''; this.control = null; this.remotePeerId = '';
        this.outgoingCall = null; this.incomingCalls = new Set(); this.localStream = null; this.remoteStreams = new Map();
        this.statsTimer = null; this.heartbeatTimer = null; this.clientWatchdog = null; this.agentLeaseTimer = null;
        this.lastHeartbeat = 0; this.closed = false; this.clientConnected = false; this.roomReady = false;
        this.statsPrev = new Map(); this.agentToken = '';
        this.rtcConfig = { iceServers: [], iceCandidatePoolSize: 0, sdpSemantics: 'unified-plan' };
        this._installRoomEnhancements();
    }
    get hostPeerId() { return `castscreen-room-${this.roomId}-host`; }
    get hasPeer() { return !!(this.control?.open && this.remotePeerId); }
    connectSignaling() { return this.connect(); }
    connect() {
        if (this.closed) return;
        if (typeof window.Peer !== 'function') { this._setStatus('FAILED','Không tải được PeerJS — hãy tải lại trang'); return; }
        this._setStatus('CONNECTING', this.isHost ? 'Đang tạo phòng…' : 'Đang kiểm tra phòng…');
        if (this.isHost) this._startAgentLease();
        this.isHost ? this._createHostPeer() : this._createClientPeer();
    }
    async _startAgentLease() {
        if (!this.isHost || this.agentLeaseTimer) return;
        const bases=['http://127.0.0.1:8765','http://localhost:8765'];
        const call=async(path,opts={})=>{for(const b of bases){try{const r=await fetch(b+path,{...opts,cache:'no-store'});if(r.ok)return await r.json();}catch(_){}}return null;};
        const status=await call('/airplay/status'); if(!status)return;
        this.agentToken=status.token||'';
        const lease=async()=>{if(this.closed){this._stopAgentLease();return;}const r=await call('/airplay/lease',{method:'POST',headers:{'X-CastScreen-Agent-Token':this.agentToken}});if(!r)this._stopAgentLease();};
        lease(); this.agentLeaseTimer=setInterval(lease,2000);
    }
    _stopAgentLease(){
        if(this.agentLeaseTimer){clearInterval(this.agentLeaseTimer);this.agentLeaseTimer=null;}
        if(!this.isHost)return;
        const token=this.agentToken; const bases=['http://127.0.0.1:8765','http://localhost:8765'];
        for(const b of bases){try{fetch(b+'/airplay/stop',{method:'POST',headers:{'X-CastScreen-Agent-Token':token},keepalive:true}).catch(()=>{});}catch(_){}}
    }
    _createHostPeer(){
        this._destroyPeerOnly(); const peer=new Peer(this.hostPeerId,{config:this.rtcConfig,debug:0}); this.peer=peer; this.peerId=this.hostPeerId;
        peer.on('open',id=>{if(this.closed)return;this.peerId=id||this.hostPeerId;this.roomReady=true;this._setStatus('WAITING','Phòng đã sẵn sàng — đang chờ thiết bị thứ hai');});
        peer.on('connection',c=>this._acceptClient(c)); peer.on('call',c=>this._handleIncomingCall(c));
        peer.on('error',e=>{if(this.closed)return;console.warn('[CastScreen][Host]',e?.type||e);this._setStatus('FAILED',e?.type==='unavailable-id'?'Mã phòng đang được sử dụng':'Không thể tạo phòng');});
        peer.on('disconnected',()=>{if(!this.closed)this._setStatus('FAILED','Mất kết nối dịch vụ điều phối');});
    }
    _createClientPeer(){
        this._destroyPeerOnly(); const id=`castscreen-client-${Math.random().toString(36).slice(2,11)}`; const peer=new Peer(id,{config:this.rtcConfig,debug:0}); this.peer=peer; this.peerId=id;
        peer.on('open',()=>this._connectToHost()); peer.on('call',c=>this._handleIncomingCall(c));
        peer.on('error',e=>{if(this.closed)return;console.warn('[CastScreen][Client]',e?.type||e);this._setStatus(e?.type==='peer-unavailable'||e?.type==='unavailable-id'?'ROOM_NOT_FOUND':'FAILED',e?.type==='peer-unavailable'||e?.type==='unavailable-id'?'Phòng không tồn tại hoặc đã đóng':'Không thể tham gia phòng');});
        peer.on('disconnected',()=>{if(!this.closed)this._setStatus('HOST_GONE','Mất kết nối với chủ phòng');});
    }
    _acceptClient(conn){
        if(this.control?.open||this.clientConnected){try{conn.send({type:'room-full'});}catch(_){}try{conn.close();}catch(_){}return;}
        this.control=conn;this.remotePeerId=conn.peer;
        conn.on('open',()=>{if(this.closed)return;this.clientConnected=true;this.roomReady=true;try{conn.send({type:'host-ready',roomId:this.roomId,hostPeerId:this.peerId});}catch(_){}this._startHeartbeat();this._notifyPeerCount(2);this._setStatus('CONNECTED','Đã kết nối thiết bị thứ hai');this._maybeSendLocalStream();});
        conn.on('data',d=>{if(d?.type==='client-hello')this._setStatus('CONNECTED','Đã kết nối thiết bị thứ hai');});
        conn.on('close',()=>this._handleClientGone());conn.on('error',()=>this._handleClientGone());
    }
    _connectToHost(){
        if(this.closed||!this.peer||this.peer.destroyed)return; const conn=this.peer.connect(this.hostPeerId,{reliable:true,serialization:'json'});this.control=conn;let opened=false;
        conn.on('open',()=>{if(this.closed)return;opened=true;this.remotePeerId=this.hostPeerId;this.clientConnected=true;this.roomReady=true;this.lastHeartbeat=performance.now();try{conn.send({type:'client-hello',roomId:this.roomId,peerId:this.peerId});}catch(_){}this._startClientWatchdog();this._notifyPeerCount(2);this._setStatus('CONNECTED','Đã vào phòng');this._maybeSendLocalStream();});
        conn.on('data',d=>{if(d?.type==='host-ready')this.remotePeerId=d.hostPeerId||this.hostPeerId;else if(d?.type==='room-full'){this._setStatus('ROOM_FULL','Phòng đã đủ 2 thiết bị');try{conn.close();}catch(_){}}else if(d?.type==='host-heartbeat'){this.lastHeartbeat=performance.now();try{conn.send({type:'heartbeat-ack',t:d.t});}catch(_){}}});
        conn.on('close',()=>this._handleHostGone());conn.on('error',()=>this._handleHostGone());
        setTimeout(()=>{if(!opened&&!this.closed&&!this.roomReady)this._setStatus('ROOM_NOT_FOUND','Phòng không tồn tại hoặc đã đóng');},5500);
    }
    _handleIncomingCall(call){if(this.closed){try{call.close();}catch(_){}return;}this.remotePeerId=call.peer;this.incomingCalls.add(call);try{call.answer(this.localStream||undefined);}catch(_){try{call.answer();}catch(__){}}call.on('stream',s=>{this.remoteStreams.set(call,s);if(this.onStream)this.onStream(s,s.getVideoTracks()[0]||null);this._startStats();});const cleanup=()=>{this.incomingCalls.delete(call);this.remoteStreams.delete(call);if(this.onStreamEnded)this.onStreamEnded();};call.on('close',cleanup);call.on('error',cleanup);}
    async startScreenCapture(stream){if(!stream)throw new Error('Không có luồng màn hình');this.stopScreenCapture(false);this.localStream=stream;for(const t of stream.getTracks()){if(t.kind==='video')t.contentHint='motion';t.addEventListener('ended',()=>{if(this.localStream===stream)this.stopScreenCapture(true);},{once:true});}if(!this.hasPeer){this._setStatus('WAITING','Đang chờ thiết bị thứ hai…');return;}this._makeOutgoingCall();}
    stopScreenCapture(updateStatus=true){if(this.localStream){for(const t of this.localStream.getTracks()){try{t.stop();}catch(_){} }this.localStream=null;}if(this.outgoingCall){try{this.outgoingCall.close();}catch(_){}this.outgoingCall=null;}if(updateStatus&&this.hasPeer)this._setStatus('CONNECTED','Đã kết nối thiết bị thứ hai');}
    _maybeSendLocalStream(){if(this.localStream&&this.hasPeer)this._makeOutgoingCall();}
    _makeOutgoingCall(){if(!this.localStream||!this.remotePeerId||!this.peer||this.peer.destroyed||this.closed)return;if(this.outgoingCall){try{this.outgoingCall.close();}catch(_){}this.outgoingCall=null;}try{const call=this.peer.call(this.remotePeerId,this.localStream,{metadata:{roomId:this.roomId,lanOnly:true}});this.outgoingCall=call;call.on('stream',s=>{this.remoteStreams.set(call,s);if(this.onStream)this.onStream(s,s.getVideoTracks()[0]||null);this._startStats();});const cleanup=()=>{if(this.outgoingCall===call)this.outgoingCall=null;};call.on('close',cleanup);call.on('error',cleanup);}catch(e){console.warn('[CastScreen] outgoing call failed',e);}}
    _startHeartbeat(){clearInterval(this.heartbeatTimer);this.heartbeatTimer=setInterval(()=>{if(!this.isHost||!this.control?.open||this.closed)return;try{this.control.send({type:'host-heartbeat',t:Date.now()});}catch(_){}},2000);}
    _startClientWatchdog(){clearInterval(this.clientWatchdog);this.clientWatchdog=setInterval(()=>{if(this.isHost||this.closed||!this.roomReady)return;if(performance.now()-this.lastHeartbeat>6500)this._handleHostGone();},1000);}
    _handleClientGone(){if(this.closed)return;this.clientConnected=false;this.remotePeerId='';clearInterval(this.heartbeatTimer);this._closeMediaCalls();this._notifyPeerCount(1);this._setStatus('WAITING','Thiết bị thứ hai đã rời phòng');}
    _handleHostGone(){if(this.isHost||this.closed)return;this.closed=true;clearInterval(this.clientWatchdog);this.remotePeerId='';this._closeMediaCalls();this._notifyPeerCount(0);this._setStatus('HOST_GONE','Chủ phòng đã thoát — phòng đã đóng');this._destroyPeerOnly();}
    _closeMediaCalls(){if(this.outgoingCall){try{this.outgoingCall.close();}catch(_){}this.outgoingCall=null;}for(const c of this.incomingCalls){try{c.close();}catch(_){} }this.incomingCalls.clear();this.remoteStreams.clear();if(this.onStreamEnded)this.onStreamEnded();}
    _notifyPeerCount(n){if(this.onPeerCountChange)this.onPeerCountChange(n);}
    _startStats(){
        if(this.statsTimer)return; this.statsTimer=setInterval(async()=>{try{const calls=[this.outgoingCall,...this.incomingCalls].filter(Boolean);if(!calls.length)return;let fps=0,rtt=0,jitter=0,decode=0,localType='',remoteType='',bitrateBps=0,packetsLost=0,packetsReceived=0;
            for(const call of calls){if(!call.peerConnection)continue;const stats=await call.peerConnection.getStats();stats.forEach(r=>{
                if(r.type==='inbound-rtp'&&(r.kind==='video'||r.mediaType==='video')){if(Number.isFinite(r.framesPerSecond))fps=Math.max(fps,r.framesPerSecond);if(Number.isFinite(r.jitter))jitter=Math.max(jitter,r.jitter*1000);if(Number.isFinite(r.totalDecodeTime)&&r.framesDecoded>0)decode=Math.max(decode,r.totalDecodeTime/r.framesDecoded*1000);const now=performance.now();const bytes=Number(r.bytesReceived)||0;const prev=this.statsPrev.get(r.ssrc);if(prev){const dt=(now-prev.t)/1000;if(dt>0&&bytes>=prev.bytes)bitrateBps=Math.max(bitrateBps,(bytes-prev.bytes)*8/dt);}this.statsPrev.set(r.ssrc,{bytes,t:now});packetsLost+=Number(r.packetsLost)||0;packetsReceived+=Number(r.packetsReceived)||0;}
                if(r.type==='candidate-pair'&&r.state==='succeeded'){if(Number.isFinite(r.currentRoundTripTime))rtt=Math.max(rtt,r.currentRoundTripTime*1000);if(r.localCandidateId){const c=stats.get(r.localCandidateId);if(c?.candidateType)localType=c.candidateType;}if(r.remoteCandidateId){const c=stats.get(r.remoteCandidateId);if(c?.candidateType)remoteType=c.candidateType;}}
            });}
            const metrics={fps:Math.round(fps||0),rtt:Math.round(rtt||0),ping:Math.round(rtt||0),bandwidthBps:Math.round(bitrateBps||0),bandwidthMbps:Number((bitrateBps/1e6).toFixed(2)),packetLoss:packetsReceived+packetsLost>0?Number((packetsLost/(packetsReceived+packetsLost)*100).toFixed(2)):0,pipelineMs:Math.round(Math.max(0,rtt+jitter+decode)),localCandidateType:localType,remoteCandidateType:remoteType,lan:localType==='host'&&remoteType==='host'};
            if(this.onMetrics)this.onMetrics(metrics);this._renderTelemetry(metrics);
        }catch(_){}},500);
    }
    _renderTelemetry(m){if(!document||!document.body)return;let hud=document.getElementById('castTelemetry');if(!hud){hud=document.createElement('div');hud.id='castTelemetry';hud.innerHTML='<span>FPS <b id="csFps">—</b></span><span>Ping <b id="csPing">—</b></span><span>Rx <b id="csBw">—</b></span><span>Loss <b id="csLoss">—</b></span><span id="csPath">LAN</span>';Object.assign(hud.style,{position:'fixed',left:'14px',top:'84px',zIndex:9997,display:'flex',gap:'8px',padding:'8px 10px',borderRadius:'10px',background:'rgba(3,8,18,.78)',backdropFilter:'blur(8px)',border:'1px solid rgba(255,255,255,.12)',color:'#cbd5e1',font:'700 11px/1.2 system-ui',pointerEvents:'none'});document.body.appendChild(hud);}const set=(id,v)=>{const e=document.getElementById(id);if(e)e.textContent=v;};set('csFps',m.fps?m.fps+' FPS':'—');set('csPing',Number.isFinite(m.rtt)?m.rtt+' ms':'—');set('csBw',m.bandwidthMbps?m.bandwidthMbps.toFixed(2)+' Mbps':'—');set('csLoss',m.packetLoss+'%');set('csPath',m.lan?'LAN':'ICE');}
    _installRoomEnhancements(){
        if(document.readyState==='loading'){document.addEventListener('DOMContentLoaded',()=>this._installRoomEnhancements(),{once:true});return;}
        const isIOS=/iPhone|iPad|iPod/i.test(navigator.userAgent)||(/Macintosh/i.test(navigator.userAgent)&&navigator.maxTouchPoints>1);
        const share=document.getElementById('share'); const video=document.getElementById('remoteVideo'); const controls=document.querySelector('.controls');
        if(isIOS&&share&&!share.dataset.airplayGuideInstalled){share.textContent='📱 Hướng dẫn AirPlay';share.dataset.airplayGuideInstalled='1';share.addEventListener('click',e=>{e.preventDefault();e.stopImmediatePropagation();this._showAirplayGuide();},true);}
        if(controls&&!document.getElementById('fullscreenBtn')){const b=document.createElement('button');b.id='fullscreenBtn';b.className='ghost';b.textContent='⛶ Toàn màn hình';b.type='button';b.onclick=()=>this._toggleFullscreen();controls.insertBefore(b,document.getElementById('leave')||null);}
        if(video&&!video.dataset.fsInstalled){video.dataset.fsInstalled='1';video.addEventListener('dblclick',()=>this._toggleFullscreen());}
    }
    _toggleFullscreen(){const stage=document.querySelector('.stage');const video=document.getElementById('remoteVideo');const target=stage||video;if(document.fullscreenElement){document.exitFullscreen().catch(()=>{});return;}if(target?.requestFullscreen)target.requestFullscreen().catch(()=>video?.requestFullscreen?.().catch(()=>{}));else video?.webkitEnterFullscreen?.();}
    _showAirplayGuide(){let m=document.getElementById('airplayGuideModal');if(!m){m=document.createElement('div');m.id='airplayGuideModal';Object.assign(m.style,{position:'fixed',inset:'0',zIndex:10000,display:'flex',alignItems:'center',justifyContent:'center',padding:'20px',background:'rgba(0,0,0,.78)',backdropFilter:'blur(10px)'});m.innerHTML='<div style="width:min(420px,100%);padding:24px;border-radius:22px;background:#0b1220;border:1px solid rgba(255,255,255,.14);color:#f8fafc;font-family:system-ui"><div style="font-size:28px">📱</div><h2 style="margin:8px 0">Chia sẻ màn hình iPhone</h2><p style="color:#94a3b8;line-height:1.6;font-size:14px">iPhone sẽ gửi màn hình bằng AirPlay vào PC Host.</p><ol style="color:#cbd5e1;line-height:1.7;padding-left:22px"><li>Mở <b>Trung tâm điều khiển</b>.</li><li>Chạm <b>Phản chiếu màn hình / Screen Mirroring</b>.</li><li>Chọn <b>CastScreen-PC</b>.</li><li>Quay lại phòng này; PC Host sẽ hỏi bạn có cho phép nhận AirPlay hay không.</li></ol><button id="closeAirGuide" style="width:100%;margin-top:8px;background:linear-gradient(135deg,#22d3ee,#4f8cff);border:0;border-radius:12px;padding:12px;font-weight:900;cursor:pointer">Đã hiểu</button></div>';document.body.appendChild(m);document.getElementById('closeAirGuide').onclick=()=>m.remove();}else m.style.display='flex';}
    _setStatus(c,l){if(this.onStatusChange)this.onStatusChange(c,l);}
    _destroyPeerOnly(){clearInterval(this.heartbeatTimer);clearInterval(this.clientWatchdog);this.heartbeatTimer=null;this.clientWatchdog=null;if(this.control){try{this.control.close();}catch(_){}this.control=null;}this._closeMediaCalls();if(this.peer){try{this.peer.destroy();}catch(_){}this.peer=null;}this.remotePeerId='';this.statsPrev.clear();}
    close(){if(this.closed)return;this.closed=true;this._destroyPeerOnly();this.stopScreenCapture(false);clearInterval(this.statsTimer);this.statsTimer=null;this.roomReady=false;this.clientConnected=false;this.statsPrev.clear();this._stopAgentLease();}
}
window.WebRTCManager=WebRTCManager;
