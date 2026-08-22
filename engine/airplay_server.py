import os
import sys
import subprocess
import threading
import socket
import time
import psutil
from typing import Callable, Optional

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


class AirPlayServer:
    def __init__(self, bin_dir: Optional[str] = None):
        if bin_dir is None:
            if getattr(sys, "frozen", False):
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

        self.on_status_change: Optional[Callable[[str], None]] = None
        self.on_client_connected: Optional[Callable[[str], None]] = None
        self.on_client_disconnected: Optional[Callable[[], None]] = None
        self.on_log: Optional[Callable[[str], None]] = None

    @property
    def is_running(self) -> bool:
        return self.process is not None and self.process.poll() is None

    @staticmethod
    def kill_orphan_instances():
        targets = {"uxplay-windows.exe", "uxplay.exe", "uxplay-bluetooth-beacon.exe"}
        for proc in psutil.process_iter(["pid", "name"]):
            try:
                name = (proc.info.get("name") or "").lower()
                if name in targets:
                    proc.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
            except Exception:
                pass

    @staticmethod
    def restart_bonjour():
        try:
            result = subprocess.run(
                ["net", "stop", "Bonjour Service"],
                capture_output=True,
                timeout=5,
            )
            if result.returncode == 0:
                time.sleep(0.8)
                subprocess.run(
                    ["net", "start", "Bonjour Service"],
                    capture_output=True,
                    timeout=5,
                )
            else:
                subprocess.run(
                    [
                        "powershell",
                        "-Command",
                        'Stop-Service -Name "Bonjour Service" -Force; '
                        'Start-Sleep -Milliseconds 800; '
                        'Start-Service -Name "Bonjour Service"',
                    ],
                    capture_output=True,
                    timeout=8,
                )
            time.sleep(0.5)
        except Exception:
            pass

    def find_executable(self) -> Optional[str]:
        if not os.path.exists(self.bin_dir):
            return None
        targets = ("uxplay-windows.exe", "uxplay.exe")
        for target in targets:
            direct = os.path.join(self.bin_dir, target)
            if os.path.exists(direct):
                return direct
        for root, _, files in os.walk(self.bin_dir):
            for filename in files:
                if filename.lower() in targets:
                    return os.path.join(root, filename)
        return None

    @staticmethod
    def get_local_ip() -> str:
        try:
            stats = psutil.net_if_stats()
            addrs = psutil.net_if_addrs()
            for _, addr_list in addrs.items():
                for addr in addr_list:
                    if addr.family == socket.AF_INET and addr.address.startswith("192.168.137."):
                        return addr.address
            for _, addr_list in addrs.items():
                for addr in addr_list:
                    if addr.family == socket.AF_INET and (
                        addr.address.startswith("172.20.10.") or addr.address.startswith("192.168.43.")
                    ):
                        return addr.address
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(0.5)
            try:
                s.connect(("8.8.8.8", 80))
                ip = s.getsockname()[0]
            finally:
                s.close()
            if not ip.startswith(("127.", "172.27.")):
                return ip
        except Exception:
            pass
        try:
            stats = psutil.net_if_stats()
            for iface, addr_list in psutil.net_if_addrs().items():
                if not stats.get(iface) or not stats[iface].isup:
                    continue
                for addr in addr_list:
                    if addr.family == socket.AF_INET:
                        ip = addr.address
                        if not ip.startswith(("127.", "169.254.", "172.27.")):
                            return ip
        except Exception:
            pass
        return "127.0.0.1"

    @staticmethod
    def get_active_network_name() -> str:
        try:
            ip = AirPlayServer.get_local_ip()
            if ip.startswith("192.168.137."):
                return "Laptop Mobile Hotspot (192.168.137.1)"
            if ip.startswith("172.20.10."):
                return "iPhone Personal Hotspot"
            if ip.startswith("192.168.43."):
                return "Android Hotspot"
            for iface, addrs in psutil.net_if_addrs().items():
                if psutil.net_if_stats().get(iface) and psutil.net_if_stats()[iface].isup:
                    for addr in addrs:
                        if addr.address == ip:
                            return iface
        except Exception:
            pass
        return "Wi-Fi"

    def sync_appdata_config(self, config: dict):
        """Write only valid UxPlay CLI options.

        GStreamer properties such as sync=false must not be placed into
        arguments.txt as free-standing tokens: UxPlay parses them as its own
        command-line options and exits with 'unknown option sync=false'.
        """
        appdata = os.environ.get("APPDATA")
        if not appdata:
            return
        try:
            config_dir = os.path.join(appdata, "leapbtw", "uxplay-windows")
            os.makedirs(config_dir, exist_ok=True)
            args_file = os.path.join(config_dir, "arguments.txt")

            server_name = str(config.get("server_name", "CastScreen-PC")).strip('"').strip("'")
            resolution = str(config.get("resolution", "1920x1080")).strip()
            fps = int(config.get("fps", 60))
            ultra = bool(config.get("ultra_low_latency", True))
            enable_audio = bool(config.get("enable_audio", True))

            args = [
                "-n", server_name,
                "-fps", str(fps),
                "-nohold",
                "-reset", "3",
                "-nofreeze",
                "-s", f"{resolution}@{fps}",
                "-vd", "d3d11h264dec",
                "-vc", "d3d11convert",
                "-vs", "d3d11videosink",
            ]
            if ultra:
                args.extend(["-vsync", "no"])
            if not enable_audio:
                args.extend(["-as", "0"])

            encoded = []
            for arg in args:
                if any(ch.isspace() for ch in arg):
                    encoded.append('"' + arg.replace('"', '\\"') + '"')
                else:
                    encoded.append(arg)
            args_str = " ".join(encoded)

            with open(args_file, "w", encoding="utf-8") as f:
                f.write(args_str)
            self._log(f"[CONFIG] UxPlay arguments → {args_str}")

            try:
                import winreg
                with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\leapbtw\uxplay-windows") as key:
                    winreg.SetValueEx(key, "renderer_mode", 0, winreg.REG_DWORD, 1)
            except Exception:
                pass
        except Exception as exc:
            self._log(f"[CONFIG] Không thể ghi arguments.txt: {exc}")

    @staticmethod
    def get_all_active_ips() -> list:
        ips = []
        try:
            stats = psutil.net_if_stats()
            for iface, addrs in psutil.net_if_addrs().items():
                if not stats.get(iface) or not stats[iface].isup:
                    continue
                for addr in addrs:
                    if addr.family == socket.AF_INET:
                        ip = addr.address
                        if not ip.startswith(("127.", "169.254.", "172.27.")):
                            ips.append((iface, ip))
        except Exception:
            pass
        return ips

    def build_command(self, config: dict) -> list:
        exe_path = self.find_executable()
        if not exe_path:
            raise FileNotFoundError("Không tìm thấy tệp uxplay-windows.exe trong thư mục engine/bin.")
        return [exe_path]

    def start(self, config: dict) -> bool:
        self.kill_orphan_instances()
        self.restart_bonjour()
        self.sync_appdata_config(config)

        exe_path = self.find_executable()
        if not exe_path:
            self._log(f"[ERROR] Không tìm thấy engine tại {self.bin_dir}")
            return False
        try:
            working_dir = os.path.dirname(exe_path)
            env = os.environ.copy()
            env["PATH"] = working_dir + os.pathsep + env.get("PATH", "")
            env["GST_DEBUG"] = "0"
            env["G_MESSAGES_DEBUG"] = "none"
            env["GST_PLUGIN_PATH"] = os.path.join(working_dir, "lib", "gstreamer-1.0")

            ultra = bool(config.get("ultra_low_latency", True))
            env["GST_D3D11_ENABLE_VSYNC"] = "0" if ultra else "1"
            env["GST_GL_VSYNC"] = "0" if ultra else "1"
            env["GST_DX9_VSYNC"] = "0" if ultra else "1"
            env["GST_PLUGIN_FEATURE_RANK"] = (
                "d3d12videosink:NONE,"
                "d3d11videosink:PRIMARY+100,"
                "d3d11h264dec:PRIMARY+100,"
                "d3d11h265dec:PRIMARY+100,"
                "d3d11vp8dec:PRIMARY+100,"
                "d3d11vp9dec:PRIMARY+100,"
                "wasapi2sink:PRIMARY+100"
            )
            env["GST_D3D11_PREFER_HARDWARE"] = "1"

            creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            self.process = subprocess.Popen(
                self.build_command(config),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                cwd=working_dir,
                env=env,
                creationflags=creationflags,
                text=True,
                bufsize=1,
                encoding="utf-8",
                errors="replace",
            )
            self._running_flag = True
            if self.on_status_change:
                self.on_status_change("RUNNING")

            def _read_stdout():
                try:
                    if self.process and self.process.stdout:
                        for line in iter(self.process.stdout.readline, ""):
                            if line:
                                self._log(line.rstrip())
                            if not self._running_flag:
                                break
                except Exception:
                    pass

            self.stdout_thread = threading.Thread(target=_read_stdout, daemon=True)
            self.stdout_thread.start()
            self.monitor_thread = threading.Thread(target=self._watch_process_exit, daemon=True)
            self.monitor_thread.start()
            return True
        except Exception as exc:
            self._log(f"[ERROR] Không thể khởi chạy AirPlay Server: {exc}")
            self._running_flag = False
            if self.on_status_change:
                self.on_status_change("STOPPED")
            return False

    def _detect_uxplay_port(self, timeout: int = 10) -> int:
        deadline = time.time() + timeout
        while time.time() < deadline and self._running_flag:
            try:
                if self.process and self.process.poll() is None:
                    proc = psutil.Process(self.process.pid)
                    for conn in proc.net_connections():
                        if conn.status == "LISTEN" and conn.laddr.port > 1024:
                            return conn.laddr.port
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
            except Exception:
                pass
            time.sleep(0.3)
        return 0

    def stop(self):
        self._running_flag = False
        if self.process:
            try:
                self._log("[INFO] Đang dừng AirPlay Server...")
                self.process.kill()
                try:
                    self.process.wait(timeout=0.5)
                except subprocess.TimeoutExpired:
                    pass
            except Exception as exc:
                self._log(f"[ERROR] Khi dừng tiến trình: {exc}")
            finally:
                self.process = None
        self.kill_orphan_instances()
        self.connected_device = None
        if self.on_status_change:
            self.on_status_change("STOPPED")
        if self.on_client_disconnected:
            self.on_client_disconnected()

    def _watch_process_exit(self):
        process = self.process
        if process:
            try:
                process.wait()
            except Exception:
                pass
        if self._running_flag and self.on_status_change:
            self.on_status_change("STOPPED")

    def _log(self, msg: str):
        try:
            log_path = os.path.normpath(os.path.join(self.bin_dir, "..", "..", "app_debug.log"))
            try:
                if os.path.exists(log_path):
                    with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                        lines = f.readlines()
                    if len(lines) > 200:
                        with open(log_path, "w", encoding="utf-8") as f:
                            f.writelines(lines[-150:])
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
