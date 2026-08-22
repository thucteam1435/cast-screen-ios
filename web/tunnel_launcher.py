"""
One-Click Temporary Cloudflare HTTPS Tunnel Launcher
Keeps everything running 100% on your local PC, while Cloudflare provides a temporary secure HTTPS link.
"""
import os
import sys
import time
import subprocess
import threading
import re

# Force UTF-8 on Windows Console
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

WEB_DIR = os.path.dirname(os.path.abspath(__file__))

def main():
    print("=" * 68)
    print("🚀 KHỞI ĐỘNG LINK TẠM CLOUDFLARE HTTPS (CHẠY 100% TRÊN MÁY BẠN)")
    print("=" * 68)
    
    # 1. Kill any existing cloudflared
    try:
        subprocess.run(["taskkill", "/f", "/im", "cloudflared.exe"], capture_output=True)
    except Exception:
        pass

    # 2. Start local server
    print("[1/2] Đang khởi động Web Server trên máy tính của bạn (Port 8080)...")
    server_path = os.path.join(WEB_DIR, "local_server.py")
    srv_proc = subprocess.Popen([sys.executable, server_path, "8080"], cwd=WEB_DIR)
    time.sleep(1.5)

    # 3. Start cloudflared
    cloudflared_bin = os.path.join(WEB_DIR, "cloudflared.exe")
    print("[2/2] Đang kết nối tạo link HTTPS bảo mật từ Cloudflare...")

    cmd = [cloudflared_bin, "tunnel", "--url", "http://localhost:8080"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1, encoding="utf-8", errors="replace")

    url_found = False
    try:
        for line in iter(proc.stdout.readline, ""):
            match = re.search(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com", line)
            if match and not url_found:
                url_found = True
                live_url = match.group(0)
                print("\n" + "=" * 68)
                print("  🎉 ĐÃ TẠO THÀNH CÔNG LINK CLOUDFLARE HTTPS:")
                print(f"  👉 COPY LINK NÀY:  {live_url}")
                print("=" * 68 + "\n")
                print("💡 Máy tính và Điện thoại hãy cùng mở đường link trên.")
                print("⚡ Dữ liệu và video vẫn chạy 100% TRỰC TIẾP trên máy tính của bạn.")
                print("Nhấn Ctrl + C để dừng bất kỳ lúc nào.\n")
    except KeyboardInterrupt:
        print("\nĐang tắt Server...")
    finally:
        try:
            proc.terminate()
            srv_proc.terminate()
        except Exception:
            pass
        print("Đã dừng Cloudflare Tunnel.")

if __name__ == "__main__":
    main()
