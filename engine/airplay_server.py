import os
import sys
import subprocess
import threading
import socket
import re
import time
import psutil
from typing import Callable, Optional

# Set utf-8 stdout if possible on Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

class AirPlayServer:
    def __init__(self, bin_dir: Optional[str] = None):
        if bin_dir is None:
            if getattr(sys, 'frozen', False):
                base = os.path.dirname(sys.executable)
            else:
                base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            self.bin_dir = os.path.join(base, "engine", "bin")
        else:
            self.bin_dir = bin_dir
            
        self.process: Optional[subprocess.Popen] = None
        self._running_flag = False
        self.connected_device = None
        self.monitor_thread: Optional[threading.Thread] = None
        self.stdout_thread: Optional[threading.Thread] = None
        
        # Callbacks
        self.on_status_change: Optional[Callable[[str], None]] = None
        self.on_client_connected: Optional[Callable[[str], None]] = None
        self.on_client_disconnected: Optional[Callable[[], None]] = None
        self.on_log: Optional[Callable[[str], None]] = None

    @property
    def is_running(self) -> bool:
        if self.process is not None:
            return self.process.poll() is None
        return False

    @staticmethod
    def kill_orphan_instances():
        """Kill any dangling uxplay or beacon processes from past runs (Keep Bonjour running!)."""
        target_procs = ["uxplay-windows.exe", "uxplay-bluetooth-beacon.exe", "uxplay.exe"]
        for proc in psutil.process_iter(['pid', 'name']):
            try:
                if proc.info['name'] and proc.info['name'].lower() in target_procs:
                    proc.kill()
            except Exception:
                pass

    @staticmethod
    def restart_bonjour():
        """Restart Apple Bonjour service to flush stale mDNS records and prevent DNSServiceRegister NameConflict.
        Tries direct net stop/start first, then elevates via PowerShell if needed.
        """
        try:
            result = subprocess.run(
                ['net', 'stop', 'Bonjour Service'],
                capture_output=True, timeout=5
            )
            if result.returncode != 0:
                # Not admin — elevate via PowerShell (triggers UAC prompt)
                subprocess.run(
                    ['powershell', '-Command',
                     'Stop-Service -Name "Bonjour Service" -Force; Start-Sleep -Milliseconds 800; Start-Service -Name "Bonjour Service"'],
                    capture_output=True, timeout=8
                )
            else:
                time.sleep(0.8)
                subprocess.run(['net', 'start', 'Bonjour Service'], capture_output=True, timeout=5)
            time.sleep(0.5)
        except Exception:
            pass

    def find_executable(self) -> Optional[str]:
        """Find uxplay-windows.exe or uxplay.exe in bin directory or subdirectories."""
        if not os.path.exists(self.bin_dir):
            return None
        
        target_names = ["uxplay-windows.exe", "uxplay.exe"]
        for target in target_names:
            direct = os.path.join(self.bin_dir, target)
            if os.path.exists(direct):
                return direct

        for root, _, files in os.walk(self.bin_dir):
            for file in files:
                if file.lower() in target_names:
                    return os.path.join(root, file)
        return None

    @staticmethod
    def get_local_ip() -> str:
        """Get active Wi-Fi / Hotspot IP address intelligently."""
        try:
            stats = psutil.net_if_stats()
            addrs = psutil.net_if_addrs()

            # 1. First priority: Windows Mobile Hotspot adapter (192.168.137.x) if UP
            for iface, addr_list in addrs.items():
                if stats.get(iface) and stats[iface].isup:
                    for addr in addr_list:
                        if addr.family == socket.AF_INET and addr.address.startswith("192.168.137."):
                            return addr.address

            # 2. Second priority: iPhone Personal Hotspot (172.20.10.x) or Android Hotspot (192.168.43.x)
            for iface, addr_list in addrs.items():
                if stats.get(iface) and stats[iface].isup:
                    for addr in addr_list:
                        if addr.family == socket.AF_INET:
                            if addr.address.startswith("172.20.10.") or addr.address.startswith("192.168.43."):
                                return addr.address

            # 3. Third priority: General outgoing route IP
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(0.5)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            if not ip.startswith("127.") and not ip.startswith("172.27."):
                return ip
        except Exception:
            pass

        # 4. Fallback to any active non-loopback, non-WSL IPv4
        try:
            stats = psutil.net_if_stats()
            for iface, addr_list in psutil.net_if_addrs().items():
                if stats.get(iface) and stats[iface].isup:
                    for addr in addr_list:
                        if addr.family == socket.AF_INET:
                            ip = addr.address
                            if not ip.startswith("127.") and not ip.startswith("169.254.") and not ip.startswith("172.27."):
                                return ip
        except Exception:
            pass

        return "127.0.0.1"

    @staticmethod
    def get_active_network_name() -> str:
        """Get active network adapter info."""
        try:
            local_ip = AirPlayServer.get_local_ip()
            if local_ip.startswith("192.168.137."):
                return "Laptop Mobile Hotspot (192.168.137.1)"
            if local_ip.startswith("172.20.10."):
                return "iPhone Personal Hotspot"
            if local_ip.startswith("192.168.43."):
                return "Android Hotspot"

            stats = psutil.net_if_stats()
            for iface, addrs in psutil.net_if_addrs().items():
                if stats.get(iface) and stats[iface].isup:
                    for addr in addrs:
                        if addr.address == local_ip:
                            return iface
        except Exception:
            pass
        return "Wi-Fi"

    def sync_appdata_config(self, config: dict):
        """Write arguments.txt for uxplay-windows and force D3D11 via Registry.

        ultra_low_latency=True  → -vsync no -async no  (0-frame buffer, may tear)
        ultra_low_latency=False → -vsync yes            (VSync 60 Hz, zero tearing)
        """
        try:
            appdata = os.environ.get("APPDATA")
            if not appdata:
                return
            config_dir = os.path.join(appdata, "leapbtw", "uxplay-windows")
            os.makedirs(config_dir, exist_ok=True)
            args_file = os.path.join(config_dir, "arguments.txt")

            server_name       = config.get("server_name", "CastScreen-PC").strip('"').strip("'")
            resolution        = config.get("resolution", "1920x1080").strip()
            fps               = config.get("fps", 60)
            ultra_low_latency = config.get("ultra_low_latency", True)

            # -h265 → HEVC hardware encoder (sharp text, lower bitrate)
            # Standard H.264 hardware acceleration provides much smoother frame pacing
            # than HEVC on Windows Direct3D 11 (zero micro-stutter / zero B-frame reordering delay).
            # We omit -vsync no so GStreamer locks frame presentation to the monitor's 16.67ms cadence (smooth 60 FPS).
            args_str = (
                f"-n {server_name} -fps {fps} -nohold -reset 3 -nofreeze "
                f"-s {resolution}@{fps} -al 0".strip()
            )
            with open(args_file, "w", encoding="utf-8") as f:
                f.write(args_str)
            self._log(f"[CONFIG] arguments.txt → {args_str}")

            # Force Direct3D 11 hardware acceleration (prevents D3D12 crash)
            try:
                import winreg
                key_path = r"Software\leapbtw\uxplay-windows"
                key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path)
                # 1 = D3D11 (DirectX 11 hardware accelerated)
                winreg.SetValueEx(key, "renderer_mode", 0, winreg.REG_DWORD, 1)
                winreg.CloseKey(key)
            except Exception:
                pass
        except Exception:
            pass

    @staticmethod
    def get_all_active_ips() -> list:
        """Get all active non-loopback, non-APIPA IPv4 addresses (Wi-Fi + Hotspot etc)."""
        ips = []
        try:
            stats = psutil.net_if_stats()
            for iface, addrs in psutil.net_if_addrs().items():
                if not stats.get(iface, None) or not stats[iface].isup:
                    continue
                for addr in addrs:
                    if addr.family == socket.AF_INET:
                        ip = addr.address
                        # Skip loopback, APIPA (169.254.x.x), and WSL (172.27.x.x) from main display
                        if not ip.startswith("127.") and not ip.startswith("169.254.") and not ip.startswith("172.27."):
                            ips.append((iface, ip))
        except Exception:
            pass
        return ips

    def build_command(self, config: dict) -> list:
        exe_path = self.find_executable()
        if not exe_path:
            raise FileNotFoundError("Không tìm thấy tệp uxplay-windows.exe trong thư mục engine/bin.")

        # Note: uxplay-windows on Windows is a Qt app that reads configuration from arguments.txt
        return [exe_path]

    def start(self, config: dict) -> bool:
        """Start the AirPlay receiver process with Direct3D 11 & zero-latency sync."""
        # 1. Kill any dangling old instances first
        self.kill_orphan_instances()

        # 2. Restart Bonjour to flush stale mDNS/DNS-SD records (prevents kDNSServiceErr_NameConflict)
        self.restart_bonjour()

        # 3. Sync arguments.txt so uxplay-windows uses the exact custom name and latency flags
        self.sync_appdata_config(config)

        exe_path = self.find_executable()
        if not exe_path:
            self._log(f"[ERROR] Không tìm thấy tệp thực thi engine tại {self.bin_dir}")
            return False

        server_name = config.get("server_name", "CastScreen-PC").strip('"').strip("'")

        cmd = self.build_command(config)
        self._log(f"[INFO] Khởi động AirPlay Server: {' '.join(cmd)}")

        try:
            working_dir = os.path.dirname(exe_path)
            env = os.environ.copy()
            env["PATH"] = working_dir + os.pathsep + env.get("PATH", "")
            # Optimize GStreamer latency & frame buffering
            env["GST_DEBUG"] = "0"
            env["G_MESSAGES_DEBUG"] = "none"
            env["GST_D3D11_ENABLE_VSYNC"] = "1"
            env["GST_GL_VSYNC"] = "1"
            env["GST_DX9_VSYNC"] = "1"
            env["GST_PLUGIN_PATH"] = os.path.join(working_dir, "lib", "gstreamer-1.0")
            # Force GStreamer to disable D3D12 and prioritize stable Direct3D 11 hardware sink
            # Prioritize D3D11 H.265/H.264 decoders + Windows Low-Latency WASAPI2 Audio
            env["GST_PLUGIN_FEATURE_RANK"] = (
                "d3d12videosink:NONE,"           # Disable unstable D3D12 sink
                "d3d11videosink:PRIMARY+100,"    # Use D3D11 video sink (GPU compositing)
                "d3d11h265dec:PRIMARY+100,"      # Hardware H.265 (HEVC) decoder (GPU)
                "d3d11h264dec:PRIMARY+100,"      # Hardware H.264 decoder (GPU)
                "d3d11vp8dec:PRIMARY+100,"       # Hardware VP8 decoder
                "d3d11vp9dec:PRIMARY+100,"       # Hardware VP9 decoder
                "wasapi2sink:PRIMARY+100"        # Ultra-low latency Windows WASAPI 2 audio
            )
            # Enable GPU-side hardware decode path
            env["GST_D3D11_PREFER_HARDWARE"] = "1"

            creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0

            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                cwd=working_dir,
                env=env,
                creationflags=creationflags,
                text=True,
                bufsize=1,
                encoding='utf-8',
                errors='replace'
            )

            self._running_flag = True
            if self.on_status_change:
                self.on_status_change("RUNNING")

            def _read_stdout():
                try:
                    if self.process and self.process.stdout:
                        for line in iter(self.process.stdout.readline, ''):
                            if line:
                                self._log(line.strip())
                            if not self._running_flag:
                                break
                except Exception:
                    pass

            self.stdout_thread = threading.Thread(target=_read_stdout, daemon=True)
            self.stdout_thread.start()

            # NOTE: Connection detection (on_client_connected / on_client_disconnected)
            # is handled by the dashboard _auto_fit_loop which already polls
            # WindowManager.find_mirror_window() every 200ms — no separate monitor
            # thread needed here (avoids double EnumWindows + process_iter overhead).
            self.monitor_thread = threading.Thread(target=self._watch_process_exit, daemon=True)
            self.monitor_thread.start()

            return True

        except Exception as e:
            self._log(f"[ERROR] Không thể khởi chạy AirPlay Server: {e}")
            self._running_flag = False
            if self.on_status_change:
                self.on_status_change("STOPPED")
            return False

    def _detect_uxplay_port(self, timeout: int = 10) -> int:
        """Detect the actual TCP port that uxplay-windows.exe is listening on using process PID."""
        deadline = time.time() + timeout
        while time.time() < deadline and self._running_flag:
            try:
                # 1. First check our spawned process directly
                if self.process and self.process.poll() is None:
                    proc = psutil.Process(self.process.pid)
                    for c in proc.net_connections():
                        if c.status == 'LISTEN' and c.laddr.port > 1024:
                            return c.laddr.port
                
                # 2. Fallback: check any running uxplay-windows.exe
                for proc in psutil.process_iter(['pid', 'name']):
                    name = proc.info.get('name', '')
                    if name and 'uxplay' in name.lower():
                        try:
                            for c in proc.net_connections():
                                if c.status == 'LISTEN' and c.laddr.port > 1024:
                                    return c.laddr.port
                        except (psutil.AccessDenied, psutil.NoSuchProcess):
                            pass
            except Exception:
                pass
            time.sleep(0.3)
        return 0

    def stop(self):
        """Stop the AirPlay receiver process cleanly."""
        self._running_flag = False

        if self.process:
            try:
                self._log("[INFO] Đang dừng AirPlay Server...")
                self.process.kill()
                try:
                    self.process.wait(timeout=0.5)
                except subprocess.TimeoutExpired:
                    pass
            except Exception as e:
                self._log(f"[ERROR] Khi dừng tiến trình: {e}")
            finally:
                self.process = None

        # Clean up any remnants
        self.kill_orphan_instances()

        self.connected_device = None
        if self.on_status_change:
            self.on_status_change("STOPPED")
        if self.on_client_disconnected:
            self.on_client_disconnected()

    def _watch_process_exit(self):
        """Lightweight thread: wait for the uxplay process to exit and fire STOPPED callback.

        Connection detection (on_client_connected / on_client_disconnected) is
        handled by the dashboard _auto_fit_loop via WindowManager.find_mirror_window()
        at 200 ms cadence — no need to duplicate EnumWindows polling here.
        """
        if self.process:
            self.process.wait()   # blocks until uxplay exits — zero CPU spin
        if self._running_flag and self.on_status_change:
            self.on_status_change("STOPPED")

    def _log(self, msg: str):
        try:
            log_path = os.path.join(self.bin_dir, "..", "..", "app_debug.log")
            log_path = os.path.normpath(log_path)

            # Rotating log: keep at most 200 lines so the file never grows unbounded.
            # On each write, if file exceeds 200 lines we trim to the last 150.
            try:
                if os.path.exists(log_path):
                    with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                        lines = f.readlines()
                    if len(lines) > 200:
                        lines = lines[-150:]          # keep last 150 entries
                        with open(log_path, "w", encoding="utf-8") as f:
                            f.writelines(lines)
            except Exception:
                pass

            with open(log_path, "a", encoding="utf-8") as f:
                f.write(msg + "\n")
            if self.on_log:
                self.on_log(msg)
            else:
                print(f"[AirPlayServer] {msg}")
        except Exception:
            pass
