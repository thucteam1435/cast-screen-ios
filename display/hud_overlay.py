import tkinter as tk
import win32gui
import win32con
import time
from typing import Optional


class InGameHUDOverlay:
    """A sleek, high-visibility on-screen overlay HUD displaying real-time FPS & Latency directly over the game screen.

    FPS is measured by counting how many times update_overlay() is called per second
    (each call = one display refresh tick from the daemon loop), giving a real cadence
    reading.  Latency is the round-trip wall-clock time between consecutive update calls,
    which reflects both network arrival jitter and render pipeline delay.
    """

    def __init__(self, master=None):
        self.master = master
        self.root: Optional[tk.Toplevel] = None
        self.label: Optional[tk.Label] = None
        self.is_enabled: bool = True
        self.is_visible: bool = False

        # Real-time FPS / latency tracking
        self._frame_times: list = []       # timestamps of the last N update calls
        self._last_call_ts: float = 0.0    # for per-frame latency
        self._smoothed_fps: float = 0.0
        self._smoothed_lat: float = 0.0

    def init_window(self):
        """Create the overlay window properly tied to master."""
        if self.root is not None or self.master is None:
            return

        try:
            self.root = tk.Toplevel(self.master)
            self.root.overrideredirect(True)
            # Do NOT use attributes -topmost here; we'll manage z-order via SetWindowPos
            # with HWND_TOPMOST **only if** the mirror window is also topmost, to avoid
            # stealing focus/activation from other windows.
            self.root.configure(bg="#00E5FF")

            # Border frame with glowing cyan neon border
            frame = tk.Frame(self.root, bg="#00E5FF", padx=2, pady=2)
            frame.pack(fill="both", expand=True)

            inner = tk.Frame(frame, bg="#0B1220", padx=12, pady=5)
            inner.pack(fill="both", expand=True)

            self.label = tk.Label(
                inner,
                text="⚡ -- FPS  •  ⏱ -- ms",
                font=("Consolas", 12, "bold"),
                fg="#00FF66",
                bg="#0B1220"
            )
            self.label.pack()

            self.root.update_idletasks()
            self.root.withdraw()
        except Exception:
            pass

    def _get_top_hwnd(self) -> Optional[int]:
        """Get the true top-level OS HWND for this overlay."""
        if not self.root:
            return None
        try:
            frame = self.root.wm_frame()
            if frame:
                return int(frame, 16)
        except Exception:
            pass
        try:
            p = win32gui.GetParent(self.root.winfo_id())
            if p:
                return p
        except Exception:
            pass
        return self.root.winfo_id()

    def set_enabled(self, enabled: bool):
        self.is_enabled = enabled
        if not enabled and self.root and self.is_visible:
            try:
                self.root.withdraw()
            except Exception:
                pass
            self.is_visible = False

    def _compute_metrics(self) -> tuple:
        """Compute real FPS and latency from call timestamps.

        Returns (fps: float, latency_ms: float).
        """
        now = time.perf_counter()

        # Per-call latency = time since last update_overlay call (ms)
        latency_ms = 0.0
        if self._last_call_ts > 0:
            raw_lat = (now - self._last_call_ts) * 1000.0
            # Exponential smoothing α=0.2 to avoid jitter from single slow frames
            if self._smoothed_lat == 0.0:
                self._smoothed_lat = raw_lat
            else:
                self._smoothed_lat = 0.2 * raw_lat + 0.8 * self._smoothed_lat
            latency_ms = self._smoothed_lat
        self._last_call_ts = now

        # FPS = number of calls in the last 1 second window
        self._frame_times.append(now)
        cutoff = now - 1.0
        self._frame_times = [t for t in self._frame_times if t >= cutoff]
        raw_fps = float(len(self._frame_times))

        # Exponential smoothing α=0.15
        if self._smoothed_fps == 0.0:
            self._smoothed_fps = raw_fps
        else:
            self._smoothed_fps = 0.15 * raw_fps + 0.85 * self._smoothed_fps

        return self._smoothed_fps, latency_ms

    def update_overlay(self, mirror_hwnd: Optional[int], fps_val: float = 0.0, lat_val: float = 0.0, target_fps: float = 60.0):
        """Update position and metrics directly on top of the active mirror window."""
        if not self.is_enabled:
            if self.root and self.is_visible:
                try:
                    self.root.withdraw()
                except Exception:
                    pass
                self.is_visible = False
            return

        if not mirror_hwnd or not win32gui.IsWindow(mirror_hwnd) or not win32gui.IsWindowVisible(mirror_hwnd):
            if self.root and self.is_visible:
                try:
                    self.root.withdraw()
                except Exception:
                    pass
                self.is_visible = False
            return

        if self.root is None:
            self.init_window()

        if self.root is None:
            return

        try:
            rect = win32gui.GetWindowRect(mirror_hwnd)
            win_w = rect[2] - rect[0]
            win_h = rect[3] - rect[1]

            if win_w < 200 or win_h < 200:
                if self.is_visible:
                    self.root.withdraw()
                    self.is_visible = False
                return

            hud_w = 230
            hud_h = 36
            pos_x = rect[2] - hud_w - 14
            pos_y = rect[1] + 14

            # Avoid offscreen
            pos_x = max(rect[0] + 10, pos_x)
            pos_y = max(rect[1] + 10, pos_y)

            # Color by FPS relative to target
            if fps_val >= target_fps * 0.90:
                color = "#00FF66"   # green — smooth
            elif fps_val >= target_fps * 0.5:
                color = "#FFB800"   # amber — degraded
            elif fps_val > 0:
                color = "#FF3366"   # red — poor
            else:
                color = "#94A3B8"   # gray — waiting

            fps_str = f"{fps_val:.1f}" if fps_val > 0 else "--"
            lat_str = f"{lat_val:.0f}" if lat_val > 0 else "--"

            self.label.configure(
                text=f"⚡ {fps_str} FPS  •  ⏱ {lat_str} ms",
                fg=color
            )

            if not self.is_visible:
                self.root.deiconify()
                self.root.lift()
                self.is_visible = True

            # Position via Win32 SetWindowPos.
            # Use HWND_TOPMOST only when mirror window is itself topmost, otherwise HWND_TOP
            # to avoid pushing unrelated windows behind us.
            top_hwnd = self._get_top_hwnd()
            if top_hwnd:
                try:
                    ex_style = win32gui.GetWindowLong(mirror_hwnd, -20)  # GWL_EXSTYLE
                    mirror_is_topmost = bool(ex_style & 0x00000008)      # WS_EX_TOPMOST
                    z_order = win32con.HWND_TOPMOST if mirror_is_topmost else win32con.HWND_TOP
                except Exception:
                    z_order = win32con.HWND_TOP

                win32gui.SetWindowPos(
                    top_hwnd, z_order, pos_x, pos_y, hud_w, hud_h,
                    win32con.SWP_NOACTIVATE | win32con.SWP_SHOWWINDOW
                )
        except Exception:
            pass

    def destroy(self):
        if self.root:
            try:
                self.root.destroy()
            except Exception:
                pass
            self.root = None
