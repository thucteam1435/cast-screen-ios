/**
 * Cloudflare Pages Functions / Cloudflare Workers WebSocket & HTTP Signaling Server
 * 100% Free Tier Compatible (handles WebRTC SDP & ICE exchange)
 */

// In-memory room store for active WebSocket connections & HTTP signaling
const wsRooms = new Map();
const httpRooms = new Map();

export default {
    async fetch(request, env) {
        const url = new URL(request.url);

        // CORS Headers
        const corsHeaders = {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Content-Type, Authorization, X-Requested-With',
            'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
            'Cache-Control': 'no-cache, no-store, must-revalidate',
        };

        if (request.method === 'OPTIONS') {
            return new Response(null, { status: 200, headers: corsHeaders });
        }

        // 1. WebSocket Signaling Endpoint (/ws)
        if (url.pathname === '/ws' && request.headers.get('Upgrade') === 'websocket') {
            const roomId = url.searchParams.get('room') || 'default';
            const role = url.searchParams.get('role') || 'receiver';

            const pair = new WebSocketPair();
            const [client, server] = Object.values(pair);

            server.accept();

            if (!wsRooms.has(roomId)) {
                wsRooms.set(roomId, new Set());
            }
            const roomPeers = wsRooms.get(roomId);
            roomPeers.add(server);

            server.addEventListener('message', (event) => {
                for (const peer of roomPeers) {
                    if (peer !== server && peer.readyState === 1) { // 1 = WebSocket.OPEN
                        try {
                            peer.send(event.data);
                        } catch (e) {}
                    }
                }
            });

            server.addEventListener('close', () => {
                roomPeers.delete(server);
                if (roomPeers.size === 0) {
                    wsRooms.delete(roomId);
                }
            });

            return new Response(null, {
                status: 101,
                webSocket: client,
                headers: corsHeaders
            });
        }

        // 2. HTTP Polling Signaling (/signal/poll)
        if (url.pathname === '/signal/poll') {
            const roomId = url.searchParams.get('room') || 'default';
            const role = url.searchParams.get('role') || 'receiver';
            const since = parseFloat(url.searchParams.get('since') || '0');

            const roomList = httpRooms.get(roomId) || [];
            const newMsgs = roomList.filter(m => m.ts > since && m.from !== role);

            return new Response(JSON.stringify(newMsgs), {
                status: 200,
                headers: {
                    ...corsHeaders,
                    'Content-Type': 'application/json; charset=utf-8'
                }
            });
        }

        // 3. HTTP Post Signaling (/signal/send)
        if (url.pathname === '/signal/send' && request.method === 'POST') {
            try {
                const data = await request.json();
                const roomId = data.roomId || 'default';
                const role = data.from || 'receiver';

                if (!httpRooms.has(roomId)) {
                    httpRooms.set(roomId, []);
                }
                const roomList = httpRooms.get(roomId);
                roomList.push({
                    data: data,
                    from: role,
                    ts: Date.now() / 1000
                });
                if (roomList.length > 50) {
                    httpRooms.set(roomId, roomList.slice(-50));
                }

                return new Response(JSON.stringify({ status: 'ok' }), {
                    status: 200,
                    headers: {
                        ...corsHeaders,
                        'Content-Type': 'application/json; charset=utf-8'
                    }
                });
            } catch (e) {
                return new Response(e.message, { status: 400, headers: corsHeaders });
            }
        }

        // 4. Fallback to static asset serving on Cloudflare Pages
        return env.ASSETS.fetch(request);
    }
};
