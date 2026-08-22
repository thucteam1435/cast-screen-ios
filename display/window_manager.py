import ctypes
import win32gui
import win32con
import win32api
import win32process
import psutil

# Enable Per-Monitor DPI awareness so all HWND rect calculations are in physical pixels
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    pass


class WindowManager:
    """Manages the AirPlay video mirroring window: auto-resize, aspect-ratio correction,
    crop/fill mode, always-on-top, and true borderless fullscreen."""

    WINDOW_TITLES = [
        "direct3d11", "gstreamer", "opengl", "d3dvideosink", "autovideosink",
        "iphone", "ipad", "airplay", "castscreen", "renderer"
    ]

    # Win32 Window Style constants
    GWL_STYLE      = -16
    WS_CAPTION     = 0x00C00000
    WS_THICKFRAME  = 0x00040000
    WS_SYSMENU     = 0x00080000
    WS_MINIMIZEBOX = 0x00020000
    WS_MAXIMIZEBOX = 0x00010000
    # Only strip caption & thick-frame; keep system menu, min/max so restore works cleanly
    DECORATION_MASK = 0x00C00000 | 0x00040000  # WS_CAPTION | WS_THICKFRAME

    # iPhone 14 landscape native aspect ratio
    PHONE_ASPECT = 19.5 / 9.0   # ≈ 2.1667

    # Per-window state tracking
    _saved_window_states = {}       # hwnd -> (orig_style, orig_rect, orig_ex_style)
    _fullscreen_hwnds: set = set()

    # -------------------------------------------------------------------------
    # Window discovery
    # -------------------------------------------------------------------------

    @classmethod
    def get_uxplay_pids(cls) -> set:
        pids = set()
        for p in psutil.process_iter(['pid', 'name']):
            try:
                name = p.info.get('name', '')
                if name and 'uxplay' in name.lower():
                    pids.add(p.info['pid'])
            except Exception:
                pass
        return pids

    @classmethod
    def find_mirror_window(cls):
        """Find the HWND of the AirPlay video rendering window."""
        for title in cls.WINDOW_TITLES:
            h = win32gui.FindWindow(None, title)
            if h and win32gui.IsWindow(h) and win32gui.IsWindowVisible(h):
                return h

        uxplay_pids = cls.get_uxplay_pids()
        found = []

        def enum_cb(hwnd, _):
            try:
                if not win32gui.IsWindow(hwnd) or not win32gui.IsWindowVisible(hwnd):
                    return True
                rect = win32gui.GetWindowRect(hwnd)
                if (rect[2] - rect[0]) < 100 or (rect[3] - rect[1]) < 100:
                    return True
                title = win32gui.GetWindowText(hwnd).lower()
                cls_name = win32gui.GetClassName(hwnd).lower()
                if any(k in title for k in ["cast screen pro", "visual studio", "antigravity",
                                             "cursor", "cmd.exe", "powershell", "taskbar"]):
                    return True
                _, win_pid = win32process.GetWindowThreadProcessId(hwnd)
                if win_pid in uxplay_pids:
                    found.append((hwnd, 10))
                    return True
                for t in cls.WINDOW_TITLES:
                    if t in title:
                        found.append((hwnd, 5))
                        return True
                if "gst" in cls_name or "d3d" in cls_name:
                    found.append((hwnd, 4))
            except Exception:
                pass
            return True

        win32gui.EnumWindows(enum_cb, None)
        if found:
            found.sort(key=lambda x: x[1], reverse=True)
            return found[0][0]
        return None

    # -------------------------------------------------------------------------
    # Monitor helpers
    # -------------------------------------------------------------------------

    @classmethod
    def _get_monitor_full_rect(cls, hwnd) -> tuple:
        """Return (x, y, w, h) of the full physical monitor that this window is on."""
        try:
            monitor = win32api.MonitorFromWindow(hwnd, win32con.MONITOR_DEFAULTTONEAREST)
            rc = win32api.GetMonitorInfo(monitor)["Monitor"]
            return rc[0], rc[1], rc[2] - rc[0], rc[3] - rc[1]
        except Exception:
            return 0, 0, 1920, 1080

    @classmethod
    def get_monitor_work_area(cls, hwnd=None):
        """Return (sw, sh, left, top) of work area (excluding taskbar) for the window's monitor."""
        try:
            if hwnd:
                monitor = win32api.MonitorFromWindow(hwnd, win32con.MONITOR_DEFAULTTONEAREST)
            else:
                monitor = win32api.MonitorFromPoint((0, 0), win32con.MONITOR_DEFAULTTOPRIMARY)
            wa = win32api.GetMonitorInfo(monitor)["Work"]
            return wa[2] - wa[0], wa[3] - wa[1], wa[0], wa[1]
        except Exception:
            return 1920, 1040, 0, 0

    @classmethod
    def get_dpi_scale(cls, hwnd) -> float:
        """Return the DPI scale factor for the monitor containing this window (1.0 = 96 DPI = 100%)."""
        try:
            monitor = win32api.MonitorFromWindow(hwnd, win32con.MONITOR_DEFAULTTONEAREST)
            dpi = ctypes.windll.shcore.GetScaleFactorForMonitor(monitor)
            return dpi / 100.0
        except Exception:
            try:
                dc = ctypes.windll.user32.GetDC(hwnd)
                dpi_x = ctypes.windll.gdi32.GetDeviceCaps(dc, 88)  # LOGPIXELSX
                ctypes.windll.user32.ReleaseDC(hwnd, dc)
                return dpi_x / 96.0
            except Exception:
                return 1.0

    # -------------------------------------------------------------------------
    # Always-on-top
    # -------------------------------------------------------------------------

    @classmethod
    def set_always_on_top(cls, hwnd: int, enable: bool):
        if not hwnd or not win32gui.IsWindow(hwnd):
            return False
        flag = win32con.HWND_TOPMOST if enable else win32con.HWND_NOTOPMOST
        win32gui.SetWindowPos(
            hwnd, flag, 0, 0, 0, 0,
            win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_SHOWWINDOW
        )
        return True

    # -------------------------------------------------------------------------
    # Fullscreen
    # -------------------------------------------------------------------------

    @classmethod
    def is_fullscreen(cls, hwnd: int) -> bool:
        if not hwnd or not win32gui.IsWindow(hwnd):
            return False
        return hwnd in cls._fullscreen_hwnds

    @classmethod
    def toggle_fullscreen(cls, hwnd: int):
        if not hwnd or not win32gui.IsWindow(hwnd):
            return False
        return cls.set_fullscreen(hwnd, not cls.is_fullscreen(hwnd))

    @classmethod
    def set_fullscreen(cls, hwnd: int, enable: bool) -> bool:
        """True Borderless Fullscreen.

        ON:
          1. Save original Win32 style + rect + ex_style.
          2. Strip WS_CAPTION / WS_THICKFRAME only.
          3. Cover the FULL monitor rectangle.
          4. Apply via SetWindowPos with SWP_FRAMECHANGED.
          5. Set HWND_TOPMOST Z-order without stealing foreground.

        OFF:
          Restore original style + original rect, then HWND_NOTOPMOST.
        """
        if not hwnd or not win32gui.IsWindow(hwnd):
            return False
        try:
            if enable:
                if hwnd in cls._fullscreen_hwnds:
                    return True

                # 1 — Save original state (style + rect + ex_style)
                orig_style    = win32gui.GetWindowLong(hwnd, cls.GWL_STYLE)
                orig_ex_style = win32gui.GetWindowLong(hwnd, -20)  # GWL_EXSTYLE
                orig_rect     = win32gui.GetWindowRect(hwnd)
                cls._saved_window_states[hwnd] = (orig_style, orig_rect, orig_ex_style)

                # 2 — Strip only titlebar & resize border
                borderless = orig_style & ~cls.DECORATION_MASK
                win32gui.SetWindowLong(hwnd, cls.GWL_STYLE, borderless)

                # 3 — Get FULL monitor bounds
                mon_x, mon_y, mon_w, mon_h = cls._get_monitor_full_rect(hwnd)

                # 4 — Apply via SetWindowPos
                win32gui.SetWindowPos(
                    hwnd, win32con.HWND_TOPMOST,
                    mon_x, mon_y, mon_w, mon_h,
                    win32con.SWP_FRAMECHANGED | win32con.SWP_SHOWWINDOW
                )
                cls._fullscreen_hwnds.add(hwnd)

            else:
                # Restore
                cls._fullscreen_hwnds.discard(hwnd)
                if hwnd in cls._saved_window_states:
                    state = cls._saved_window_states.pop(hwnd)
                    orig_style = state[0]
                    orig_rect  = state[1]
                    orig_ex_style = state[2] if len(state) > 2 else 0

                    # Restore style
                    win32gui.SetWindowLong(hwnd, cls.GWL_STYLE, orig_style)
                    if orig_ex_style:
                        win32gui.SetWindowLong(hwnd, -20, orig_ex_style)

                    # Restore original rect
                    rw = orig_rect[2] - orig_rect[0]
                    rh = orig_rect[3] - orig_rect[1]
                    win32gui.SetWindowPos(
                        hwnd, win32con.HWND_NOTOPMOST,
                        orig_rect[0], orig_rect[1], rw, rh,
                        win32con.SWP_FRAMECHANGED | win32con.SWP_SHOWWINDOW
                    )
                else:
                    cls.auto_fit_window(hwnd, scale_factor=0.90)

            return True
        except Exception:
            return False

    @classmethod
    def restore_window(cls, hwnd: int) -> bool:
        if not hwnd or not win32gui.IsWindow(hwnd):
            return False
        try:
            cls._fullscreen_hwnds.discard(hwnd)
            if hwnd in cls._saved_window_states:
                orig_style, orig_rect, orig_ex_style = cls._saved_window_states.pop(hwnd)
                win32gui.SetWindowLong(hwnd, cls.GWL_STYLE, orig_style)
                win32gui.SetWindowLong(hwnd, -20, orig_ex_style)
                rw = orig_rect[2] - orig_rect[0]
                rh = orig_rect[3] - orig_rect[1]
                win32gui.SetWindowPos(
                    hwnd, win32con.HWND_NOTOPMOST,
                    orig_rect[0], orig_rect[1], rw, rh,
                    win32con.SWP_NOACTIVATE | win32con.SWP_FRAMECHANGED | win32con.SWP_SHOWWINDOW
                )
            else:
                cls.auto_fit_window(hwnd, scale_factor=0.90)
            return True
        except Exception:
            return False

    # -------------------------------------------------------------------------
    # Auto-fit (windowed mode)
    # -------------------------------------------------------------------------

    @classmethod
    def auto_fit_window(cls, hwnd: int, scale_factor: float = 0.95) -> bool:
        """Resize and center the window to 19.5:9 on the correct monitor."""
        if not hwnd or not win32gui.IsWindow(hwnd):
            return False

        rect = win32gui.GetWindowRect(hwnd)
        cur_w = rect[2] - rect[0]
        cur_h = rect[3] - rect[1]
        if cur_w <= 0 or cur_h <= 0:
            return False

        aspect = cur_w / cur_h
        sw, sh, left, top = cls.get_monitor_work_area(hwnd)

        if aspect < 1.1:
            # Portrait
            new_h = int(sh * 0.90)
            new_w = int(new_h / cls.PHONE_ASPECT)
        else:
            # Landscape — fit 19.5:9 inside available work area
            new_w = int(sw * scale_factor)
            new_h = int(new_w / cls.PHONE_ASPECT)
            if new_h > int(sh * scale_factor):
                new_h = int(sh * scale_factor)
                new_w = int(new_h * cls.PHONE_ASPECT)

        pos_x = left + (sw - new_w) // 2
        pos_y = top  + (sh - new_h) // 2

        try:
            win32gui.SetWindowPos(
                hwnd, win32con.HWND_NOTOPMOST,
                pos_x, pos_y, new_w, new_h,
                win32con.SWP_NOACTIVATE | win32con.SWP_SHOWWINDOW
            )
            return True
        except Exception:
            return False

    @classmethod
    def crop_fill_window(cls, hwnd: int) -> bool:
        """Crop-Fill (F9): resize window to EXACT 19.5:9 ratio using full monitor width.

        This eliminates all letterbox/pillarbox bars because the window ratio
        exactly matches the iPhone 14 video stream ratio (19.5:9). GStreamer
        then renders the video at 1:1 scale — sharpest possible quality.

        Result: window is full-width (e.g. 1920px wide, 886px tall) centered on screen.
        Black bars from the monitor background appear above/below, but the game
        content itself has ZERO bars and maximum clarity.

        Press F11 for crop-fill + fullscreen coverage (crops sides instead).
        """
        if not hwnd or not win32gui.IsWindow(hwnd):
            return False
        try:
            # Exit fullscreen state if active
            if cls.is_fullscreen(hwnd):
                cls.set_fullscreen(hwnd, False)

            sw, sh, left, top = cls.get_monitor_work_area(hwnd)

            # Use full monitor WIDTH → compute exact 19.5:9 height
            # e.g. on a 1920×1080 monitor: new_w=1920, new_h=886
            new_w = sw
            new_h = int(sw / cls.PHONE_ASPECT)   # sw × 9/19.5

            # If height still doesn't fit, constrain to height instead
            if new_h > sh:
                new_h = sh
                new_w = int(sh * cls.PHONE_ASPECT)

            # Center on screen
            pos_x = left + (sw - new_w) // 2
            pos_y = top  + (sh - new_h) // 2

            # Apply with ctypes MoveWindow (bypasses any Qt size constraints)
            ctypes.windll.user32.MoveWindow(hwnd, pos_x, pos_y, new_w, new_h, True)
            win32gui.SetWindowPos(
                hwnd, win32con.HWND_NOTOPMOST, 0, 0, 0, 0,
                win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_SHOWWINDOW
            )
            return True
        except Exception:
            return False

    @classmethod
    def zoom_to_height(cls, hwnd: int) -> bool:
        """Zoom to Height (F10): scale window so height fills the full monitor work area,
        cropping left & right sides equally.

        This is the 'Khít chiều cao' mode:
          - new_h = full work-area height (e.g. 1040px on a 1080p monitor with taskbar)
          - new_w = new_h × 19.5/9 (wider than monitor, symmetric crop on both sides)
          - Centered horizontally → equal crop on left & right

        Unlike F11 (fullscreen), this mode:
          - Keeps the window titlebar / decorations (windowed, not borderless)
          - Does NOT set HWND_TOPMOST
          - Uses ctypes MoveWindow to bypass Qt's internal size constraints
        """
        if not hwnd or not win32gui.IsWindow(hwnd):
            return False
        try:
            # Exit fullscreen state if active
            if cls.is_fullscreen(hwnd):
                cls.set_fullscreen(hwnd, False)

            sw, sh, left, top = cls.get_monitor_work_area(hwnd)

            # Height = full work-area height, width = 19.5:9 (wider than monitor)
            new_h  = sh                              # e.g. 1040px (1080 - taskbar)
            new_w  = int(sh * cls.PHONE_ASPECT)      # e.g. 1040 × 2.1667 ≈ 2253px
            crop_x = (new_w - sw) // 2              # e.g. (2253-1920)//2 = 166px each side
            pos_x  = left - crop_x                  # negative x → off-screen left
            pos_y  = top                             # flush to top of work area

            # Force resize with MoveWindow (bypasses Qt size constraints)
            ctypes.windll.user32.MoveWindow(hwnd, pos_x, pos_y, new_w, new_h, True)

            # Verify: if Qt capped the width, at minimum set height and center
            actual   = win32gui.GetWindowRect(hwnd)
            actual_w = actual[2] - actual[0]
            if actual_w < new_w - 50:
                # Width was capped → fallback: full-width, full-height (no side crop)
                ctypes.windll.user32.MoveWindow(hwnd, left, top, sw, new_h, True)

            win32gui.SetWindowPos(
                hwnd, win32con.HWND_NOTOPMOST, 0, 0, 0, 0,
                win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_SHOWWINDOW
            )
            return True
        except Exception:
            return False
