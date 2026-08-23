/**
 * Cloudflare Pages Functions / Cloudflare Workers WebSocket & HTTP Signaling Server
 * Signaling endpoints remain available for legacy clients; the current web UI is split into home/join/room pages.
 */

const wsRooms = new Map();
const httpRooms = new Map();

export default {
    async fetch(request, env) {
        const url = new URL(request.url);
        const corsHeaders = {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Content-Type, Authorization, X-Requested-With',
            'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
            'Cache-Control': 'no-cache, no-store, must-revalidate',
        };

        if (request.method === 'OPTIONS') return new Response(null, { status: 200, headers: corsHeaders });

        const isWsUpgrade = (request.headers.get('Upgrade') || '').toLowerCase() === 'websocket';
        if (url.pathname === '/ws' && isWsUpgrade) {
            const roomId = url.searchParams.get('room') || 'default';
            const role = url.searchParams.get('role') || 'client';
            const pair = new WebSocketPair();
            const [client, server] = Object.values(pair);
            server.accept();
            if (!wsRooms.has(roomId)) wsRooms.set(roomId, new Set());
            const roomPeers = wsRooms.get(roomId);
            roomPeers.add(server);
            try { server.send(JSON.stringify({ type: 'connected', roomId, role })); } catch (_) {}
            server.addEventListener('message', event => {
                let data = null;
                try { data = JSON.parse(event.data); } catch (_) {}
                if (data?.type === 'ping') {
                    try { server.send(JSON.stringify({ type: 'pong', ts: Date.now() })); } catch (_) {}
                    return;
                }
                for (const peer of roomPeers) {
                    if (peer !== server && peer.readyState === 1) {
                        try { peer.send(event.data); } catch (_) {}
                    }
                }
            });
            const cleanup = () => {
                roomPeers.delete(server);
                if (!roomPeers.size) wsRooms.delete(roomId);
            };
            server.addEventListener('close', cleanup);
            server.addEventListener('error', cleanup);
            return new Response(null, { status: 101, webSocket: client, headers: corsHeaders });
        }

        if (url.pathname === '/signal/poll') {
            const roomId = url.searchParams.get('room') || 'default';
            const role = url.searchParams.get('role') || 'client';
            const since = parseFloat(url.searchParams.get('since') || '0');
            const roomList = httpRooms.get(roomId) || [];
            const newMsgs = roomList.filter(m => m.ts > since && m.from !== role);
            return new Response(JSON.stringify(newMsgs), { status: 200, headers: { ...corsHeaders, 'Content-Type': 'application/json; charset=utf-8' } });
        }

        if (url.pathname === '/signal/send' && request.method === 'POST') {
            try {
                const data = await request.json();
                const roomId = data.roomId || 'default';
                const role = data.from || 'client';
                if (!httpRooms.has(roomId)) httpRooms.set(roomId, []);
                const roomList = httpRooms.get(roomId);
                roomList.push({ data, from: role, ts: Date.now() / 1000 });
                if (roomList.length > 50) httpRooms.set(roomId, roomList.slice(-50));
                return new Response(JSON.stringify({ status: 'ok' }), { status: 200, headers: { ...corsHeaders, 'Content-Type': 'application/json' } });
            } catch (e) {
                return new Response(e.message, { status: 400, headers: corsHeaders });
            }
        }

        if (url.pathname === '/favicon.ico') return new Response(null, { status: 204, headers: corsHeaders });

        let targetPath = url.pathname;
        if (targetPath === '/' || targetPath === '') targetPath = '/home.html';
        else if (targetPath === '/sender') targetPath = '/sender.html';
        else if (targetPath === '/join') targetPath = '/join.html';
        else if (targetPath === '/room') targetPath = '/room.html';

        if (env && env.ASSETS && typeof env.ASSETS.fetch === 'function') {
            try {
                const assetUrl = new URL(request.url);
                assetUrl.pathname = targetPath;
                const assetReq = new Request(assetUrl.toString(), request);
                const assetRes = await env.ASSETS.fetch(assetReq);
                if (assetRes && assetRes.status !== 404) return assetRes;
                if (targetPath !== url.pathname) return await env.ASSETS.fetch(request);
                return assetRes;
            } catch (err) {
                console.error('[Worker] Asset fetch error:', err);
            }
        }

        return new Response('Cast Screen WebRTC Server is active.', { status: 200, headers: { ...corsHeaders, 'Content-Type': 'text/plain; charset=utf-8' } });
    }
};
