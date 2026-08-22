"""
[TERMINAL 2] Cast Screen Pro — Code Server & AirPlay Engine
Run and reload your code freely here while Terminal 1 keeps the Cloudflare link permanent!
"""
import os
import sys
import time
import socket
import threading
from datetime import datetime

# Configure UTF-8 on Windows Console
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

WEB_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(WEB_DIR)

if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from local_server import HTTPServer, ThreadingHTTPServer, CastScreenWebHandler, get_all_ips

try:
    from engine.airplay_server import AirPlayServer
    from display.window_manager import WindowManager
except Exception as e:
    AirPlayServer = None
    WindowManager = None

def main():
    port = 8080
    print("\n" + "=" * 72)
    print("  🚀 [TERMINAL 2] CAST SCREEN PRO — CODE SERVER & AIRPLAY ENGINE")
    print("=" * 72)
    print("  💡 Bạn có thể bật / tắt / sửa code ở Terminal này thoải mái.")
    print("  Đường link Cloudflare ở Terminal 1 vẫn GIỮ NGUYÊN không đổi!")
    print("-" * 72)

    # 1. Start AirPlay Engine (CastScreen-PC)
    airplay = None
    if AirPlayServer:
        server_name = "CastScreen-PC"
        print(f"  🍏 [AirPlay] Đang phát sóng thiết bị AirPlay DUY NHẤT: {server_name} (2.5K 60fps)...")
        airplay = AirPlayServer()
        
        def on_connected(dev_name):
            print(f"\n  🎉 [AirPlay] THIẾT BỊ ĐÃ KẾT NỐI: {dev_name} → Đang hiển thị 2.5K 60FPS!")
            def arrange():
                for _ in range(25):
                    time.sleep(0.2)
                    if WindowManager:
                        hwnds = WindowManager.find_all_mirror_windows()
                        if hwnds:
                            for h in hwnds:
                                WindowManager.bring_to_front(h)
                            WindowManager.tile_windows_grid()
                            break
            threading.Thread(target=arrange, daemon=True).start()

        airplay.on_client_connected = on_connected
        airplay.start({
            "server_name": server_name,
            "fps": 60,
            "resolution": "2560x1440",
            "ultra_low_latency": False,
            "enable_audio": True,
            "video_renderer": "d3d11"
        })

    # 2. Start Web Server
    all_ips = get_all_ips()
    # Use ThreadingHTTPServer so long-poll /signal/poll never blocks the server
    server = ThreadingHTTPServer(("0.0.0.0", port), CastScreenWebHandler)
    
    print(f"  🌐 [Web Server] Đang lắng nghe trên cổng {port}...")
    for name, ip in all_ips:
        print(f"     👉 http://{ip}:{port}")
    print("-" * 72)
    print("  [LOG TRUY CẬP VÀ PHẢN CHIẾU]:\n")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n\nĐang dừng Server...")
    finally:
        if airplay:
            airplay.stop()
        server.server_close()
        print("✅ Đã tắt Server an toàn.\n")

if __name__ == "__main__":
    main()
