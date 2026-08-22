import os
import sys
import json
import socket

if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

CONFIG_FILE = os.path.join(BASE_DIR, "settings.json")

DEFAULT_CONFIG = {
    "server_name": f"CastScreen-{socket.gethostname()[:8]}",
    "resolution": "1920x1080",
    "fps": 60,
    "video_renderer": "d3d11",  # d3d11, d3d, gl, autovideosink
    "enable_audio": True,
    "ultra_low_latency": True,
    "disable_vsync": True,
    "disable_async_audio": True,
    "always_on_top": False,
    "auto_fit_screen": True,
    "fullscreen_on_connect": False,
    "pin_protection": False,
    "pin_code": "1234",
    "window_scale": 100,
}

def load_config() -> dict:
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                config = DEFAULT_CONFIG.copy()
                config.update(data)
                return config
        except Exception:
            return DEFAULT_CONFIG.copy()
    return DEFAULT_CONFIG.copy()

def save_config(config: dict):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4, ensure_ascii=False)
    except Exception as e:
        print(f"Error saving config: {e}")
