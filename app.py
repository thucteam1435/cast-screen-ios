import os
import sys

# Ensure current directory is in sys.path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from gui.dashboard import CastScreenApp

def apply_system_latency_optimizations():
    """Tự động tối ưu hóa Windows Multimedia SystemProfile và TCP để giảm lag/delay."""
    try:
        import winreg
        # Disable multimedia network throttling (allows full speed streaming packets)
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

def main():
    try:
        set_dpi_awareness()
        apply_system_latency_optimizations()
        app = CastScreenApp()
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
