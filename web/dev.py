"""
Cast Screen Pro — Universal Hybrid Live Development & Terminal Monitor
Runs simultaneously:
1. Local Web Server (Port 8080)
2. Cloudflare Live HTTPS Tunnel (WebRTC P2P for Android / PC)
3. Apple AirPlay Engine & mDNS Advertiser (CastScreen-PC 2.5K 60fps HEVC for iPhone / iPad)
"""
import os
import sys
import time
import subprocess
import threading
import re
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

try:
    from engine.airplay_server import AirPlayServer
except Exception as e:
    AirPlayServer = None

def kill_stale_processes():
    try:
        subprocess.run(["taskkill", "/f", "/im", "cloudflared.exe"], capture_output=True)
    except Exception:
        pass

def main():
    print("\n" + "=" * 72)
    print("  🚀 CAST SCREEN PRO — UNIVERSAL HYBRID DEV MONITOR")
    print("=" * 72)
    
    kill_stale_processes()

    # 1. Start Local Server as subprocess with stdout piping
    print("  [1/3] Đang khởi động Web Server cục bộ (Port 8080)...")
    srv_cmd = [sys.executable, "-u", os.path.join(WEB_DIR, "local_server.py"), "8080"]
    srv_proc = subprocess.Popen(
        srv_cmd,
        cwd=WEB_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        encoding="utf-8",
        errors="replace"
    )

    # 2. Start Cloudflare Tunnel
    print("  [2/3] Đang kết nối Cloudflare Live HTTPS Tunnel...")
    cloudflared_bin = os.path.join(WEB_DIR, "cloudflared.exe")
    cf_cmd = [cloudflared_bin, "tunnel", "--url", "http://localhost:8080"]
    cf_proc = subprocess.Popen(
        cf_cmd,
        cwd=WEB_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        encoding="utf-8",
        errors="replace"
    )

    # 3. Start Native AirPlay Engine & mDNS (CastScreen-PC)
    airplay = None
    if AirPlayServer:
        print("  [3/3] Đang kích hoạt máy chủ Apple AirPlay 2.5K HEVC (CastScreen-PC)...")
        airplay = AirPlayServer()
        airplay.start({
            "server_name": "CastScreen-PC",
            "fps": 60,
            "resolution": "2560x1440",
            "ultra_low_latency": False,
            "enable_audio": True,
            "video_renderer": "d3d11"
        })

    # Function to monitor Cloudflare URL
    def monitor_cloudflare():
        url_printed = False
        for line in iter(cf_proc.stdout.readline, ""):
            match = re.search(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com", line)
            if match and not url_printed:
                url_printed = True
                url = match.group(0)
                print("\n" + "🌟" * 36)
                print("  🎉 HỆ THỐNG ĐÃ SẴN SÀNG TOÀN DIỆN CHO MỌI THIẾT BỊ:")
                print(f"  👉 📱 Link Web (Android / PC):     {url}")
                print(f"  👉 🍏 Tên AirPlay (iPhone / iPad):  CastScreen-PC (2.5K 60fps)")
                print("🌟" * 36)
                print("  💡 Mẹo: Khi sửa HTML/CSS/JS, chỉ cần nhấn F5 trên trình duyệt.")
                print("-" * 72)
                print("  [LOG TRUY CẬP VÀ PHẢN CHIẾU THỜI GIAN THỰC]:\n")

    cf_thread = threading.Thread(target=monitor_cloudflare, daemon=True)
    cf_thread.start()

    # Print Web Server logs in real-time
    try:
        for line in iter(srv_proc.stdout.readline, ""):
            line_str = line.strip()
            if line_str:
                now = datetime.now().strftime("%H:%M:%S")
                if "GET" in line_str or "POST" in line_str:
                    print(f"  [{now}] 🌐 {line_str}")
                elif "joined room" in line_str or "left room" in line_str:
                    print(f"  [{now}] ⚡ {line_str}")
                elif "CAST SCREEN PRO" not in line_str and "=====" not in line_str:
                    print(f"  [{now}] ℹ️  {line_str}")
    except KeyboardInterrupt:
        print("\n\nĐang tắt toàn bộ hệ thống...")
    finally:
        if airplay:
            airplay.stop()
        try:
            srv_proc.terminate()
            cf_proc.terminate()
            kill_stale_processes()
        except Exception:
            pass
        print("✅ Đã tắt Server an toàn.\n")

if __name__ == "__main__":
    main()
