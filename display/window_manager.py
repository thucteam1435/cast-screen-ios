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
        uxplay_pids = cls.get_uxplay_pids()
        found = []

        def enum_cb(hwnd, _):
            try:
                if not win32gui.IsWindow(hwnd) or not win32gui.IsWindowVisible(hwnd):
                    return True
                if win32gui.IsIconic(hwnd):
                    return True
                rect = win32gui.GetWindowRect(hwnd)
                w = rect[2] - rect[0]
                h = rect[3] - rect[1]
                if w < 150 or h < 150:
                    return True

                title = (win32gui.GetWindowText(hwnd) or "").lower()
                cls_name = (win32gui.GetClassName(hwnd) or "").lower()

                # Skip known editor and development windows
                if any(k in title for k in ["cast screen pro", "visual studio", "antigravity",
                                             "cursor", "cmd.exe", "powershell", "taskbar", "program manager"]):
                    return True

                _, win_pid = win32process.GetWindowThreadProcessId(hwnd)
                score = 0

                # Match title
                if any(k in title for k in ["airplay", "direct3d", "gstreamer", "stream", "iphone", "ipad", "castscreen", "renderer"]):
                    score += 50

                # Match class
                if any(k in cls_name for k in ["d3d", "gst", "video", "renderer", "direct3d", "qwidget"]):
                    score += 30

                # Match PID
                if uxplay_pids and win_pid in uxplay_pids:
                    score += 40

                # Area bonus
                if w >= 300 and h >= 200:
                    score += min(50, int((w * h) / 40000))

                if score > 0:
                    found.append((hwnd, score, w * h))
            except Exception:
                pass
            return True

        win32gui.EnumWindows(enum_cb, None)
        if found:
            found.sort(key=lambda x: (x[1], x[2]), reverse=True)
            return found[0][0]

        for title in cls.WINDOW_TITLES:
            h = win32gui.FindWindow(None, title)
            if h and win32gui.IsWindow(h) and win32gui.IsWindowVisible(h):
                return h
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

    @classmethod
    def bring_to_front(cls, hwnd: int) -> bool:
        """Forcefully bring window to the absolute foreground, restoring if minimized."""
        if not hwnd or not win32gui.IsWindow(hwnd):
            return False
        try:
            if win32gui.IsIconic(hwnd):
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            else:
                win32gui.ShowWindow(hwnd, win32con.SW_SHOW)

            fore_hwnd = win32gui.GetForegroundWindow()
            cur_thread = win32api.GetCurrentThreadId()
            fore_thread, _ = win32process.GetWindowThreadProcessId(fore_hwnd)

            if fore_thread != cur_thread and fore_thread != 0:
                ctypes.windll.user32.AttachThreadInput(fore_thread, cur_thread, True)

            win32gui.SetWindowPos(
                hwnd, win32con.HWND_TOPMOST, 0, 0, 0, 0,
                win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_SHOWWINDOW
            )
            win32gui.SetForegroundWindow(hwnd)
            win32gui.BringWindowToTop(hwnd)
            win32gui.SetFocus(hwnd)

            win32gui.SetWindowPos(
                hwnd, win32con.HWND_NOTOPMOST, 0, 0, 0, 0,
                win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_SHOWWINDOW
            )

            if fore_thread != cur_thread and fore_thread != 0:
                ctypes.windll.user32.AttachThreadInput(fore_thread, cur_thread, False)

            return True
        except Exception:
            try:
                win32gui.ShowWindow(hwnd, win32con.SW_SHOW)
                win32gui.SetForegroundWindow(hwnd)
                return True
            except Exception:
                return False

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
    # Auto-fit & Aspect Ratio (windowed mode)
    # -------------------------------------------------------------------------

    @classmethod
    def get_content_aspect_ratio(cls, hwnd: int) -> float:
        """Dynamically detect content aspect ratio (19.5:9 for modern iPhone, 16:9 for older iPhone, 4:3 for iPad)."""
        try:
            rect = win32gui.GetClientRect(hwnd)
            cw = rect[2] - rect[0]
            ch = rect[3] - rect[1]
            if cw > 0 and ch > 0:
                raw = max(cw, ch) / min(cw, ch)
                # Check for standard ratios within tolerance
                if abs(raw - (19.5 / 9.0)) < 0.15:  # ~2.1667 (iPhone 13-16 series)
                    return 19.5 / 9.0
                elif abs(raw - (16.0 / 9.0)) < 0.10:  # ~1.7778 (iPhone SE / 8 / Standard video)
                    return 16.0 / 9.0
                elif abs(raw - (4.0 / 3.0)) < 0.10:   # ~1.3333 (iPad)
                    return 4.0 / 3.0
                elif 1.2 <= raw <= 2.5:
                    return raw
        except Exception:
            pass
        return cls.PHONE_ASPECT

    @classmethod
    def auto_fit_window(cls, hwnd: int, scale_factor: float = 0.95) -> bool:
        """Resize and center the window dynamically matching device aspect ratio on the correct monitor."""
        if not hwnd or not win32gui.IsWindow(hwnd):
            return False

        rect = win32gui.GetWindowRect(hwnd)
        cur_w = rect[2] - rect[0]
        cur_h = rect[3] - rect[1]
        if cur_w <= 0 or cur_h <= 0:
            return False

        aspect = cur_w / cur_h
        target_ratio = cls.get_content_aspect_ratio(hwnd)
        sw, sh, left, top = cls.get_monitor_work_area(hwnd)

        if aspect < 1.1:
            # Portrait
            new_h = int(sh * 0.90)
            new_w = int(new_h / target_ratio)
        else:
            # Landscape — fit target_ratio inside available work area
            new_w = int(sw * scale_factor)
            new_h = int(new_w / target_ratio)
            if new_h > int(sh * scale_factor):
                new_h = int(sh * scale_factor)
                new_w = int(new_h * target_ratio)

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
        """Crop-Fill (F9): resize window to EXACT device aspect ratio using full monitor width.

        Eliminates letterbox/pillarbox bars for 1:1 pixel rendering.
        """
        if not hwnd or not win32gui.IsWindow(hwnd):
            return False
        try:
            if cls.is_fullscreen(hwnd):
                cls.set_fullscreen(hwnd, False)

            sw, sh, left, top = cls.get_monitor_work_area(hwnd)
            target_ratio = cls.get_content_aspect_ratio(hwnd)

            new_w = sw
            new_h = int(sw / target_ratio)

            if new_h > sh:
                new_h = sh
                new_w = int(sh * target_ratio)

            pos_x = left + (sw - new_w) // 2
            pos_y = top  + (sh - new_h) // 2

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
        cropping left & right sides equally."""
        if not hwnd or not win32gui.IsWindow(hwnd):
            return False
        try:
            if cls.is_fullscreen(hwnd):
                cls.set_fullscreen(hwnd, False)

            sw, sh, left, top = cls.get_monitor_work_area(hwnd)
            target_ratio = cls.get_content_aspect_ratio(hwnd)

            new_h  = sh
            new_w  = int(sh * target_ratio)
            crop_x = (new_w - sw) // 2
            pos_x  = left - crop_x
            pos_y  = top

            ctypes.windll.user32.MoveWindow(hwnd, pos_x, pos_y, new_w, new_h, True)

            actual   = win32gui.GetWindowRect(hwnd)
            actual_w = actual[2] - actual[0]
            if actual_w < new_w - 50:
                ctypes.windll.user32.MoveWindow(hwnd, left, top, sw, new_h, True)

            win32gui.SetWindowPos(
                hwnd, win32con.HWND_NOTOPMOST, 0, 0, 0, 0,
                win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_SHOWWINDOW
            )
            return True
        except Exception:
            return False

    @classmethod
    def find_all_mirror_windows(cls) -> list:
        """Find all active mirror window HWNDs."""
        uxplay_pids = cls.get_uxplay_pids()
        found = []

        def enum_cb(hwnd, _):
            try:
                if not win32gui.IsWindow(hwnd) or not win32gui.IsWindowVisible(hwnd) or win32gui.IsIconic(hwnd):
                    return True
                rect = win32gui.GetWindowRect(hwnd)
                w, h = rect[2] - rect[0], rect[3] - rect[1]
                if w < 150 or h < 150:
                    return True
                title = (win32gui.GetWindowText(hwnd) or "").lower()
                cls_name = (win32gui.GetClassName(hwnd) or "").lower()
                if any(k in title for k in ["cast screen pro", "visual studio", "antigravity", "cursor", "cmd.exe", "powershell"]):
                    return True
                _, win_pid = win32process.GetWindowThreadProcessId(hwnd)
                if (uxplay_pids and win_pid in uxplay_pids) or any(k in title for k in ["airplay", "direct3d", "gstreamer", "stream", "iphone", "ipad"]):
                    found.append(hwnd)
            except Exception:
                pass
            return True

        win32gui.EnumWindows(enum_cb, None)
        return found

    @classmethod
    def tile_windows_grid(cls):
        """Automatically arrange all connected device mirror windows side-by-side."""
        hwnds = cls.find_all_mirror_windows()
        if not hwnds:
            return
        n = len(hwnds)
        if n == 1:
            cls.bring_to_front(hwnds[0])
            cls.auto_fit_window(hwnds[0])
            return

        sw, sh, left, top = cls.get_monitor_work_area(hwnds[0])
        if n == 2:
            # Side by side: 2 columns
            half_w = sw // 2
            for idx, h in enumerate(hwnds[:2]):
                pos_x = left + idx * half_w
                ctypes.windll.user32.MoveWindow(h, pos_x, top, half_w, sh, True)
                cls.bring_to_front(h)
        elif n >= 3:
            # 2x2 grid
            half_w = sw // 2
            half_h = sh // 2
            for idx, h in enumerate(hwnds[:4]):
                row = idx // 2
                col = idx % 2
                pos_x = left + col * half_w
                pos_y = top + row * half_h
                ctypes.windll.user32.MoveWindow(h, pos_x, pos_y, half_w, half_h, True)
                cls.bring_to_front(h)
