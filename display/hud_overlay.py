import tkinter as tk
import win32gui
import win32con
import time
from typing import Optional


class InGameHUDOverlay:
    """A sleek, high-visibility on-screen overlay HUD displaying real-time FPS & Latency directly over the game screen,
    styled exactly like League of Legends (Liên Minh Huyền Thoại) in-game OSD.
    """

    def __init__(self, master=None):
        self.master = master
        self.root: Optional[tk.Toplevel] = None
        self.label: Optional[tk.Label] = None
        self.is_enabled: bool = True
        self.is_visible: bool = False
        self._transparent_set: bool = False

    def init_window(self):
        """Create the overlay window properly tied to master."""
        if self.root is not None or self.master is None:
            return

        try:
            self.root = tk.Toplevel(self.master)
            self.root.overrideredirect(True)
            self.root.wm_attributes("-topmost", True)
            try:
                self.root.wm_attributes("-alpha", 0.90)
            except Exception:
                pass
            self.root.configure(bg="#00E5FF")

            # Border frame with glowing cyan neon border
            frame = tk.Frame(self.root, bg="#00E5FF", padx=1, pady=1)
            frame.pack(fill="both", expand=True)

            inner = tk.Frame(frame, bg="#0B1220", padx=8, pady=3)
            inner.pack(fill="both", expand=True)

            self.label = tk.Label(
                inner,
                text="⚡ 60 FPS  •  24 ms",
                font=("Segoe UI", 10, "bold"),
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

    def update_overlay(self, mirror_hwnd: Optional[int], fps_val: float = 0.0, lat_val: float = 0.0, ping_val: float = 0.0, target_fps: float = 60.0):
        """Update position and metrics directly inside the top-right corner of the mirror window."""
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

            hud_w = 175
            hud_h = 28
            # Anchor inside top-right corner of the video window (like League of Legends)
            pos_x = rect[2] - hud_w - 16
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

            fps_str = f"{fps_val:.0f}" if fps_val > 0 else "--"
            lat_str = f"{lat_val:.0f}" if lat_val > 0 else "--"

            self.label.configure(
                text=f"⚡ {fps_str} FPS  •  {lat_str} ms",
                fg=color
            )

            if not self.is_visible:
                self.root.deiconify()
                self.is_visible = True

            self.root.geometry(f"{hud_w}x{hud_h}+{pos_x}+{pos_y}")
            self.root.lift()
            self.root.wm_attributes("-topmost", True)

            top_hwnd = self._get_top_hwnd()
            if top_hwnd:
                if not self._transparent_set:
                    try:
                        ex_style = win32gui.GetWindowLong(top_hwnd, win32con.GWL_EXSTYLE)
                        win32gui.SetWindowLong(top_hwnd, win32con.GWL_EXSTYLE, ex_style | win32con.WS_EX_TRANSPARENT | win32con.WS_EX_NOACTIVATE)
                        self._transparent_set = True
                    except Exception:
                        pass

                win32gui.SetWindowPos(
                    top_hwnd, win32con.HWND_TOPMOST, pos_x, pos_y, hud_w, hud_h,
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
