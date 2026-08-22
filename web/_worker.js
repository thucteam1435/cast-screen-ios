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

        // 4. Handle favicon directly to prevent unnecessary asset lookup errors
        if (url.pathname === '/favicon.ico') {
            return new Response(null, { status: 204, headers: corsHeaders });
        }

        // 5. URL Rewriting for clean routes (/ -> /index.html, /sender -> /sender.html)
        let targetPath = url.pathname;
        if (targetPath === '/' || targetPath === '') {
            targetPath = '/index.html';
        } else if (targetPath === '/sender') {
            targetPath = '/sender.html';
        }

        // 6. Safe Static Asset Serving (Cloudflare Pages / Workers with Assets)
        if (env && env.ASSETS && typeof env.ASSETS.fetch === 'function') {
            try {
                const assetUrl = new URL(request.url);
                assetUrl.pathname = targetPath;
                const assetReq = new Request(assetUrl.toString(), request);
                const assetRes = await env.ASSETS.fetch(assetReq);
                if (assetRes && assetRes.status !== 404) {
                    return assetRes;
                }
                // Try original request if rewritten returned 404
                if (targetPath !== url.pathname) {
                    return await env.ASSETS.fetch(request);
                }
                return assetRes;
            } catch (err) {
                console.error('[Worker] Asset fetch error:', err);
            }
        }

        // 7. Fallback when deployed as a standalone Worker without static asset binding
        return new Response(
            `🚀 Cast Screen WebRTC Signaling Server is Active!\n\n` +
            `• WebSocket Endpoint: wss://${url.host}/ws\n` +
            `• HTTP Signaling: https://${url.host}/signal/poll\n` +
            `• Room: ${url.searchParams.get('room') || 'default'}\n\n` +
            `Ghi chú: Để hiển thị đầy đủ giao diện Web, hãy deploy qua Cloudflare Pages theo hướng dẫn (CLOUDFLARE_DEPLOY_GUIDE.md).`,
            {
                status: 200,
                headers: {
                    ...corsHeaders,
                    'Content-Type': 'text/plain; charset=utf-8'
                }
            }
        );
    }
};

