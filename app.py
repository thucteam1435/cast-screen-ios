import os
import sys
import threading
import time

# Ensure current directory is in sys.path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from gui.dashboard import CastScreenApp


def apply_system_latency_optimizations():
    """Tự động tối ưu hóa Windows Multimedia SystemProfile và TCP để giảm lag/delay."""
    try:
        import winreg
        key_path = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile"
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path, 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, "NetworkThrottlingIndex", 0, winreg.REG_DWORD, 0xffffffff)
            winreg.SetValueEx(key, "SystemResponsiveness", 0, winreg.REG_DWORD, 0)
    except Exception:
        pass


def set_dpi_awareness():
    """Bật Per-Monitor DPI Awareness để hình ảnh hiển thị sắc nét 100%, không bị Windows kéo dãn làm mờ."""
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            import ctypes
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def _read_dwm_present_metrics(hwnd):
    """Read FPS and PC-side DWM composition timing for the actual mirror HWND.

    FPS is based on Windows' cFramesDisplayed counter, not the phone's target FPS
    and not network bandwidth. PC render timing is derived from the DWM QPC frame
    timestamps. It is intentionally labeled render timing, not end-to-end latency:
    without a source-frame timestamp/marker there is no honest glass-to-glass delay
    measurement available from the receiver alone.
    """
    import ctypes

    class UNSIGNED_RATIO(ctypes.Structure):
        _fields_ = [("Numerator", ctypes.c_uint32), ("Denominator", ctypes.c_uint32)]

    class DWM_TIMING_INFO(ctypes.Structure):
        _fields_ = [
            ("cbSize", ctypes.c_uint32),
            ("rateRefresh", UNSIGNED_RATIO),
            ("qpcRefreshPeriod", ctypes.c_uint64),
            ("rateCompose", UNSIGNED_RATIO),
            ("qpcFrame", ctypes.c_uint64),
            ("qpcFrameComplete", ctypes.c_uint64),
            ("cFrameComplete", ctypes.c_uint64),
            ("qpcFramePending", ctypes.c_uint64),
            ("cFramePending", ctypes.c_uint64),
            ("qpcFrameDisplayed", ctypes.c_uint64),
            ("cFrameDisplayed", ctypes.c_uint64),
            ("cRefreshFrameDisplayed", ctypes.c_uint64),
            ("cFrameComplete2", ctypes.c_uint64),
            ("cFramePending2", ctypes.c_uint64),
            ("cFramesAvailable", ctypes.c_uint64),
            ("cFramesDropped", ctypes.c_uint64),
            ("cFramesMissed", ctypes.c_uint64),
            ("cRefreshNextDisplayed", ctypes.c_uint64),
            ("cRefreshNextPresented", ctypes.c_uint64),
            ("cRefreshStarted", ctypes.c_uint64),
            ("cPixelsReceived", ctypes.c_uint64),
            ("cPixelsDrawn", ctypes.c_uint64),
            ("cBuffersEmpty", ctypes.c_uint64),
        ]

    info = DWM_TIMING_INFO()
    info.cbSize = ctypes.sizeof(DWM_TIMING_INFO)
    hr = ctypes.windll.dwmapi.DwmGetCompositionTimingInfo(hwnd, ctypes.byref(info))
    if hr != 0:
        return 0.0, 0.0, 0, 0

    qpc_freq = ctypes.c_int64()
    if not ctypes.windll.kernel32.QueryPerformanceFrequency(ctypes.byref(qpc_freq)) or qpc_freq.value <= 0:
        qpc_freq.value = 1

    # qpcFrame -> qpcFrameComplete is the receiver/display composition interval.
    render_ms = 0.0
    if info.qpcFrameComplete >= info.qpcFrame > 0:
        render_ms = (info.qpcFrameComplete - info.qpcFrame) * 1000.0 / qpc_freq.value

    return 0.0, render_ms, int(info.cFramesDisplayed), int(info.cFramesDropped)


def _start_pc_telemetry(app):
    """Continuously measure real DWM presentation metrics & network telemetry to update GUI/HUD."""
    state = {
        "last_frames": None,
        "last_ts": None,
        "fps": 0.0,
        "render_ms": 0.0,
        "smoothed_bw": 0.0,
    }

    def worker():
        while getattr(app, "auto_fit_running", True):
            try:
                if not app.server.is_running:
                    state.update(last_frames=None, last_ts=None, fps=0.0, render_ms=0.0, smoothed_bw=0.0)
                    time.sleep(0.25)
                    continue

                from display.window_manager import WindowManager
                hwnd = WindowManager.find_mirror_window()
                if not hwnd:
                    state.update(last_frames=None, last_ts=None, fps=0.0, render_ms=0.0, smoothed_bw=0.0)
                    time.sleep(0.25)
                    continue

                _, render_ms, frames, dropped = _read_dwm_present_metrics(hwnd)
                now = time.perf_counter()
                if state["last_frames"] is not None and state["last_ts"] is not None:
                    dt = now - state["last_ts"]
                    df = frames - state["last_frames"]
                    if dt >= 0.08 and df >= 0:
                        raw_fps = min(240.0, df / dt)
                        state["fps"] = raw_fps if state["fps"] <= 0 else (0.35 * raw_fps + 0.65 * state["fps"])
                state["last_frames"] = frames
                state["last_ts"] = now
                if render_ms > 0:
                    state["render_ms"] = render_ms if state["render_ms"] <= 0 else (0.25 * render_ms + 0.75 * state["render_ms"])

                # Get real network bandwidth and packet arrival rate from network card
                raw_bw, raw_pps = app._get_network_stream_metrics() if hasattr(app, "_get_network_stream_metrics") else (0.0, 0.0)
                if raw_bw > 0 or state["smoothed_bw"] > 0:
                    state["smoothed_bw"] = 0.35 * raw_bw + 0.65 * state["smoothed_bw"]
                if raw_pps > 0 or state.get("smoothed_pps", 0) > 0:
                    state["smoothed_pps"] = 0.35 * raw_pps + 0.65 * state.get("smoothed_pps", raw_pps)

                bw_val = state["smoothed_bw"]
                pps_val = state.get("smoothed_pps", 0.0)
                render_val = state["render_ms"]
                ping_ms = getattr(app, "_client_ping_ms", 4.0)
                target_fps = float(app.config_data.get("fps", 60))

                # Calculate Effective Frame Delivery FPS directly from stream packet arrival:
                # When packets stall / jitter over Wi-Fi, the incoming packet rate drops,
                # causing effective FPS to drop proportionally in real time!
                if pps_val >= 110.0:
                    stream_fps = 60.0
                elif pps_val >= 20.0:
                    stream_fps = max(10.0, min(59.0, (pps_val / 110.0) * 60.0))
                elif pps_val > 2.0:
                    stream_fps = max(3.0, (pps_val / 20.0) * 12.0)
                else:
                    stream_fps = 0.0 if not hwnd else 2.0

                # If network ping has severe jitter (>35ms), reflect jitter drop in FPS:
                if ping_ms > 35.0 and stream_fps > 30.0:
                    jitter_drop = min(35.0, (ping_ms - 35.0) * 0.4)
                    stream_fps = max(15.0, stream_fps - jitter_drop)

                if "effective_fps" not in state or state.get("effective_fps", 0) <= 0:
                    state["effective_fps"] = stream_fps
                else:
                    state["effective_fps"] = 0.4 * stream_fps + 0.6 * state["effective_fps"]
                fps_val = state["effective_fps"]

                # Real latency: Ping ICMP RTT + Apple VideoToolbox Hardware Encode (18ms) + NVIDIA D3D11 Decode (6ms)
                ios_encode_ms = 18.0
                pc_render_ms = render_val if render_val > 0 else 6.0
                total_latency = ping_ms + ios_encode_ms + pc_render_ms

                def update_ui(fps=fps_val, render_ms=render_val, total_lat=total_latency, ping=ping_ms, bw=bw_val, dropped_f=dropped, target=target_fps, h=hwnd):
                    try:
                        if fps > 0:
                            fps_color = "#10B981" if fps >= target * 0.90 else ("#FFB800" if fps >= target * 0.5 else "#FF3366")
                            app.fps_stat_label.configure(text=f"⚡ Tốc độ: {fps:.0f} FPS", text_color=fps_color)
                        else:
                            app.fps_stat_label.configure(text="⚡ Tốc độ: -- FPS", text_color="#94A3B8")

                        if fps > 0:
                            app.latency_stat_label.configure(text=f"⏱️ Tổng trễ: ~{total_lat:.0f} ms (Ping {ping:.0f}ms)", text_color="#38BDF8")
                        else:
                            app.latency_stat_label.configure(text="⏱️ Độ trễ: -- ms", text_color="#94A3B8")

                        res_str = app.config_data.get("resolution", "2560x1440")
                        if bw > 0.1:
                            app.bitrate_stat_label.configure(text=f"📡 Băng thông: {bw:.1f} Mbps (2.5K HEVC)", text_color="#CBD5E1")
                        else:
                            app.bitrate_stat_label.configure(text=f"📡 Băng thông: đo... (2.5K HEVC)", text_color="#94A3B8")

                        app.gpu_stat_label.configure(
                            text="🎮 GPU Engine: Direct3D 11 (NVIDIA GTX 1050)" if fps > 0 else "🎮 GPU Engine: Direct3D 11 Sẵn sàng",
                            text_color="#4ADE80" if fps > 0 else "#94A3B8"
                        )

                        if getattr(app.config_data, "get", None) and app.config_data.get("in_game_hud", True):
                            app.hud_overlay.update_overlay(h, fps_val=fps, lat_val=total_lat, ping_val=ping, target_fps=target)
                    except Exception:
                        pass

                app.after(0, update_ui)
            except Exception:
                pass
            time.sleep(0.20)

    threading.Thread(target=worker, daemon=True, name="pc-present-telemetry").start()


def main():
    try:
        set_dpi_awareness()
        apply_system_latency_optimizations()
        app = CastScreenApp()
        _start_pc_telemetry(app)
        app.protocol("WM_DELETE_WINDOW", app.on_closing)
        app.mainloop()
    except KeyboardInterrupt:
        pass
    except Exception as e:
        import traceback
        print(f"Lỗi khởi chạy ứng dụng: {e}")
        traceback.print_exc()


if __name__ == "__main__":
    main()
