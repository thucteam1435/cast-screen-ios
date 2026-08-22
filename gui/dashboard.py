import os
import sys
import threading
import time
import subprocess
import psutil
import win32gui
import win32api
import win32con
import customtkinter as ctk
from PIL import Image, ImageTk
from config import load_config, save_config
from engine.airplay_server import AirPlayServer
from display.window_manager import WindowManager
from display.hud_overlay import InGameHUDOverlay

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

class CastScreenApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Cast Screen Pro - iOS to PC Mirroring")
        self.geometry("960x680")
        self.minsize(880, 600)

        # App icon / Window styling
        self.configure(fg_color="#0F172A")  # Modern slate dark background

        # Config & Server instances
        self.config_data = load_config()
        self.server = AirPlayServer()
        self.server.on_status_change = self._on_server_status_change
        self.server.on_client_connected = self._on_client_connected
        self.server.on_client_disconnected = self._on_client_disconnected
        self.server.on_log = self._on_server_log
        # In-Game HUD overlay instance
        self.hud_overlay = InGameHUDOverlay(self)

        # Auto-fit monitor thread state
        self.auto_fit_running = True
        self.last_window_hwnd = None

        # Bandwidth measurement state (shared with _auto_fit_loop)
        self._bw_last_bytes: int = 0
        self._bw_last_ts: float = 0.0
        self._bw_iface: str = ""         # cached active interface name

        # Live Client Network Probe state
        self._client_ip: str = ""
        self._client_ping_ms: float = 4.0
        self._probe_running: bool = True

        self._build_ui()

        # Start background window manager daemon
        self.window_daemon = threading.Thread(target=self._auto_fit_loop, daemon=True)
        self.window_daemon.start()

        # Start live client latency probe daemon
        self.probe_thread = threading.Thread(target=self._probe_client_worker, daemon=True)
        self.probe_thread.start()

        # Poll network status every 3 seconds
        self._poll_network_status()

    def _poll_network_status(self):
        """Refresh IP display and check Hotspot / Wi-Fi status dynamically."""
        try:
            net_name = AirPlayServer.get_active_network_name()
            local_ip = AirPlayServer.get_local_ip()
            all_ips = AirPlayServer.get_all_active_ips()

            # Check specific network types
            is_laptop_hotspot = any(ip.startswith("192.168.137.") for _, ip in all_ips)
            is_iphone_hotspot = any(ip.startswith("172.20.10.") for _, ip in all_ips)
            is_android_hotspot = any(ip.startswith("192.168.43.") for _, ip in all_ips)

            if is_laptop_hotspot:
                wifi_other = [f"{n}: {ip}" for n, ip in all_ips if not ip.startswith("192.168.137.")]
                extra = f" • {wifi_other[0]}" if wifi_other else ""
                ip_text = f"🔥 Hotspot Laptop (192.168.137.1){extra}"
                color = "#38BDF8"
            elif is_iphone_hotspot:
                ip_text = f"📱 iPhone Personal Hotspot ({local_ip})"
                color = "#A855F7"
            elif is_android_hotspot:
                ip_text = f"📲 Android Hotspot ({local_ip})"
                color = "#F59E0B"
            else:
                ip_text = f"📶 Wi-Fi: {net_name} ({local_ip})"
                color = "#4ADE80"

            self.ip_label.configure(text=ip_text, text_color=color)
        except Exception:
            pass
        # Schedule next check
        self.after(3000, self._poll_network_status)


    def _build_ui(self):
        # Grid layout: 1 row of header, 1 main container with left and right columns
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # ----------------- HEADER -----------------
        header_frame = ctk.CTkFrame(self, fg_color="#1E293B", corner_radius=12)
        header_frame.grid(row=0, column=0, padx=20, pady=(15, 10), sticky="ew")
        header_frame.grid_columnconfigure(0, weight=1)

        title_sub_frame = ctk.CTkFrame(header_frame, fg_color="transparent")
        title_sub_frame.grid(row=0, column=0, padx=20, pady=12, sticky="w")

        title_label = ctk.CTkLabel(
            title_sub_frame,
            text="📱 Cast Screen Pro",
            font=ctk.CTkFont(family="Segoe UI", size=22, weight="bold"),
            text_color="#38BDF8"
        )
        title_label.pack(anchor="w")

        subtitle_label = ctk.CTkLabel(
            title_sub_frame,
            text="Chiếu màn hình iPhone / iPad lên Laptop qua Wi-Fi • Chất lượng cao 1080p 60fps",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color="#94A3B8"
        )
        subtitle_label.pack(anchor="w")

        # Status Badge in Header
        self.status_badge = ctk.CTkLabel(
            header_frame,
            text="⚪ SẴN SÀNG KẾT NỐI",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color="#F8FAFC",
            fg_color="#334155",
            corner_radius=20,
            padx=16,
            pady=8
        )
        self.status_badge.grid(row=0, column=1, padx=20, pady=12, sticky="e")

        # ----------------- MAIN BODY (2 Columns) -----------------
        main_body = ctk.CTkFrame(self, fg_color="transparent")
        main_body.grid(row=1, column=0, padx=20, pady=(0, 15), sticky="nsew")
        main_body.grid_columnconfigure(0, weight=4)  # Left column
        main_body.grid_columnconfigure(1, weight=6)  # Right column
        main_body.grid_rowconfigure(0, weight=1)

        # ----------------- LEFT PANEL: Quick Controls & Network -----------------
        left_panel = ctk.CTkScrollableFrame(main_body, fg_color="#1E293B", corner_radius=12)
        left_panel.grid(row=0, column=0, padx=(0, 10), pady=0, sticky="nsew")

        # Server Control Buttons
        btn_box = ctk.CTkFrame(left_panel, fg_color="transparent")
        btn_box.pack(fill="x", padx=15, pady=(15, 12))

        self.start_btn = ctk.CTkButton(
            btn_box,
            text="▶ BẬT MÁY CHỦ",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            fg_color="#059669",
            hover_color="#047857",
            height=42,
            corner_radius=8,
            command=self._start_server_action
        )
        self.start_btn.pack(side="left", fill="x", expand=True, padx=(0, 6))

        self.stop_btn = ctk.CTkButton(
            btn_box,
            text="⏹ DỪNG",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            fg_color="#DC2626",
            hover_color="#B91C1C",
            height=42,
            width=85,
            corner_radius=8,
            command=self._stop_server_action
        )
        self.stop_btn.pack(side="right")

        # Network Info Card
        net_frame = ctk.CTkFrame(left_panel, fg_color="#0F172A", corner_radius=10)
        net_frame.pack(fill="x", padx=15, pady=8)

        ctk.CTkLabel(
            net_frame,
            text="📶 THÔNG TIN KẾT NỐI WI-FI",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color="#38BDF8"
        ).pack(anchor="w", padx=12, pady=(10, 6))

        # Server Name Input
        name_label = ctk.CTkLabel(net_frame, text="Tên máy chủ (Hiển thị trên iPhone):", text_color="#CBD5E1", font=ctk.CTkFont(size=12))
        name_label.pack(anchor="w", padx=12, pady=(4, 2))

        name_box = ctk.CTkFrame(net_frame, fg_color="transparent")
        name_box.pack(fill="x", padx=12, pady=(0, 8))

        self.name_entry = ctk.CTkEntry(name_box, height=32, font=ctk.CTkFont(size=13))
        self.name_entry.insert(0, self.config_data.get("server_name", "CastScreen-PC"))
        self.name_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))

        save_name_btn = ctk.CTkButton(name_box, text="Lưu", width=50, height=32, command=self._save_server_name)
        save_name_btn.pack(side="right")

        # IP & Network Address Display
        self.ip_label = ctk.CTkLabel(
            net_frame,
            text=f"Mạng: {AirPlayServer.get_active_network_name()} ({AirPlayServer.get_local_ip()})",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color="#4ADE80"
        )
        self.ip_label.pack(anchor="w", padx=12, pady=4)

        # One-click Fix Hotspot Button
        fix_btn = ctk.CTkButton(
            net_frame,
            text="🔧 Mở Firewall & Sửa lỗi Hotspot (Admin)",
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color="#334155",
            hover_color="#0284C7",
            height=28,
            command=self._fix_hotspot_firewall_action
        )
        fix_btn.pack(fill="x", padx=12, pady=(4, 10))

        # Connected Device Card
        dev_frame = ctk.CTkFrame(left_panel, fg_color="#0F172A", corner_radius=10)
        dev_frame.pack(fill="x", padx=15, pady=8)

        ctk.CTkLabel(
            dev_frame,
            text="📲 THIẾT BỊ ĐANG KẾT NỐI",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color="#38BDF8"
        ).pack(anchor="w", padx=12, pady=(10, 4))

        self.device_status_label = ctk.CTkLabel(
            dev_frame,
            text="Chưa có thiết bị nào kết nối",
            font=ctk.CTkFont(family="Segoe UI", size=13),
            text_color="#94A3B8"
        )
        self.device_status_label.pack(anchor="w", padx=12, pady=(2, 10))

        # Real-time Performance & Latency Monitor HUD Card
        stats_frame = ctk.CTkFrame(left_panel, fg_color="#0F172A", corner_radius=10)
        stats_frame.pack(fill="x", padx=15, pady=8)

        ctk.CTkLabel(
            stats_frame,
            text="📊 THÔNG SỐ FPS & ĐỘ TRỄ THỰC TẾ",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color="#38BDF8"
        ).pack(anchor="w", padx=12, pady=(10, 6))

        grid_f = ctk.CTkFrame(stats_frame, fg_color="transparent")
        grid_f.pack(fill="x", padx=12, pady=(0, 10))

        self.fps_stat_label = ctk.CTkLabel(
            grid_f,
            text="⚡ Tốc độ: -- FPS (Chờ kết nối)",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color="#94A3B8",
            anchor="w"
        )
        self.fps_stat_label.pack(anchor="w", pady=2)

        self.latency_stat_label = ctk.CTkLabel(
            grid_f,
            text="⏱️ Độ trễ: -- ms (Chờ kết nối)",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color="#94A3B8",
            anchor="w"
        )
        self.latency_stat_label.pack(anchor="w", pady=2)

        self.bitrate_stat_label = ctk.CTkLabel(
            grid_f,
            text="📡 Băng thông: -- Mbps",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color="#94A3B8",
            anchor="w"
        )
        self.bitrate_stat_label.pack(anchor="w", pady=2)

        self.gpu_stat_label = ctk.CTkLabel(
            grid_f,
            text="🎮 GPU Engine: Direct3D 11 Sẵn sàng",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color="#4ADE80",
            anchor="w"
        )
        self.gpu_stat_label.pack(anchor="w", pady=2)

        # Quick Instruction Step-by-Step
        guide_frame = ctk.CTkFrame(left_panel, fg_color="#0F172A", corner_radius=10)
        guide_frame.pack(fill="x", padx=15, pady=8)

        ctk.CTkLabel(
            guide_frame,
            text="💡 HƯỚNG DẪN KẾT NỐI NHANH",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color="#FBBF24"
        ).pack(anchor="w", padx=12, pady=(10, 6))

        guide_steps = (
            "1. Đảm bảo iPhone & Laptop cùng kết nối chung 1 mạng Wi-Fi.\n"
            "2. Vuốt góc phải trên màn hình iPhone để mở Trung tâm điều khiển (Control Center).\n"
            "3. Nhấn vào biểu tượng Phản chiếu màn hình (Screen Mirroring).\n"
            "4. Chọn tên máy chủ hiển thị ở trên để bắt đầu chiếu ngay lập tức!"
        )
        ctk.CTkLabel(
            guide_frame,
            text=guide_steps,
            font=ctk.CTkFont(size=11),
            text_color="#CBD5E1",
            justify="left",
            wraplength=300
        ).pack(anchor="w", padx=12, pady=(0, 10))

        # ----------------- RIGHT PANEL: Settings & Controls -----------------
        right_panel = ctk.CTkScrollableFrame(main_body, fg_color="#1E293B", corner_radius=12)
        right_panel.grid(row=0, column=1, padx=(10, 0), pady=0, sticky="nsew")

        # Card 1: Display & Auto-Resize
        card1 = ctk.CTkFrame(right_panel, fg_color="#0F172A", corner_radius=10)
        card1.pack(fill="x", padx=15, pady=(15, 8))

        ctk.CTkLabel(
            card1,
            text="📐 ĐIỀU CHỈNH KÍCH THƯỚC MÀN HÌNH TỰ ĐỘNG",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color="#38BDF8"
        ).pack(anchor="w", padx=14, pady=(12, 8))

        # Auto-fit toggle
        self.autofit_switch = ctk.CTkSwitch(
            card1,
            text="Tự động căn chỉnh khi xoay dọc / xoay ngang (Auto-Fit)",
            font=ctk.CTkFont(size=12),
            command=self._on_settings_change
        )
        if self.config_data.get("auto_fit_screen", True):
            self.autofit_switch.select()
        self.autofit_switch.pack(anchor="w", padx=14, pady=6)

        # Always on top toggle
        self.ontop_switch = ctk.CTkSwitch(
            card1,
            text="Ghim cửa sổ chiếu lên trên cùng (Always on Top)",
            font=ctk.CTkFont(size=12),
            command=self._on_always_on_top_change
        )
        if self.config_data.get("always_on_top", False):
            self.ontop_switch.select()
        self.ontop_switch.pack(anchor="w", padx=14, pady=6)

        # Fullscreen on connect toggle
        self.fullscreen_switch = ctk.CTkSwitch(
            card1,
            text="Mở toàn màn hình khi kết nối (Fullscreen)",
            font=ctk.CTkFont(size=12),
            command=self._on_settings_change
        )
        if self.config_data.get("fullscreen_on_connect", False):
            self.fullscreen_switch.select()
        self.fullscreen_switch.pack(anchor="w", padx=14, pady=6)

        # In-Game HUD overlay switch
        self.hud_switch = ctk.CTkSwitch(
            card1,
            text="⚡ Hiển thị FPS & Độ trễ trực tiếp trên màn hình game (In-Game HUD)",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#38BDF8",
            command=self._on_hud_toggle
        )
        if self.config_data.get("in_game_hud", True):
            self.hud_switch.select()
        self.hud_switch.pack(anchor="w", padx=14, pady=6)

        # Manual Window Control Buttons - Row 1
        btn_box = ctk.CTkFrame(card1, fg_color="transparent")
        btn_box.pack(fill="x", padx=14, pady=(6, 4))

        fit_now_btn = ctk.CTkButton(
            btn_box,
            text="📱 Căn chỉnh tỉ lệ (Auto)",
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="#0284C7",
            hover_color="#0369A1",
            height=36,
            command=self._manual_fit_now
        )
        fit_now_btn.pack(side="left", padx=(0, 6), expand=True, fill="x")

        crop_fill_btn = ctk.CTkButton(
            btn_box,
            text="✂️ Cắt viền (F9)",
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="#0F766E",
            hover_color="#0D5E57",
            height=36,
            command=self._manual_crop_fill
        )
        crop_fill_btn.pack(side="right", padx=(6, 0), expand=True, fill="x")

        # Manual Window Control Buttons - Row 2
        btn_box2 = ctk.CTkFrame(card1, fg_color="transparent")
        btn_box2.pack(fill="x", padx=14, pady=(4, 4))

        zoom_height_btn = ctk.CTkButton(
            btn_box2,
            text="↕ Khít chiều cao - cắt 2 bên (F10)",
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="#7C3AED",
            hover_color="#6D28D9",
            height=36,
            command=self._manual_zoom_to_height
        )
        zoom_height_btn.pack(fill="x")

        # Manual Window Control Buttons - Row 3
        btn_box3 = ctk.CTkFrame(card1, fg_color="transparent")
        btn_box3.pack(fill="x", padx=14, pady=(4, 12))

        fullscreen_btn = ctk.CTkButton(
            btn_box3,
            text="🖥 Toàn màn hình không viền (F11 / ESC)",
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="#2563EB",
            hover_color="#1D4ED8",
            height=36,
            command=self._manual_toggle_fullscreen
        )
        fullscreen_btn.pack(fill="x")

        # Card 2: Quality & Performance Settings
        card2 = ctk.CTkFrame(right_panel, fg_color="#0F172A", corner_radius=10)
        card2.pack(fill="x", padx=15, pady=8)

        ctk.CTkLabel(
            card2,
            text="⚡ TỐI ƯU ĐỘ TRỄ & CHẤT LƯỢNG HÌNH ẢNH",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color="#38BDF8"
        ).pack(anchor="w", padx=14, pady=(12, 8))

        # Ultra Low Latency Switch vs Eye-Comfort VSync Smooth Mode
        self.latency_switch = ctk.CTkSwitch(
            card2,
            text="⚡ Chế độ Siêu Giảm Độ Trễ (Bỏ đệm trễ / Realtime 0ms)",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#FBBF24",
            command=self._on_settings_change
        )
        if self.config_data.get("ultra_low_latency", False):
            self.latency_switch.select()
        self.latency_switch.pack(anchor="w", padx=14, pady=(6, 2))

        ctk.CTkLabel(
            card2,
            text="💡 Tắt công tắc này để bật VSync 60Hz: Khử hoàn toàn xé hình (Tearing) và giật cục vi mô, giúp chuyển động êm ái chống mỏi mắt.",
            font=ctk.CTkFont(size=11),
            text_color="#94A3B8",
            wraplength=420,
            justify="left"
        ).pack(anchor="w", padx=14, pady=(0, 6))

        # Resolution Dropdown
        res_box = ctk.CTkFrame(card2, fg_color="transparent")
        res_box.pack(fill="x", padx=14, pady=6)
        ctk.CTkLabel(res_box, text="Độ phân giải:", width=120, anchor="w", font=ctk.CTkFont(size=12)).pack(side="left")
        self.res_combo = ctk.CTkComboBox(
            res_box,
            values=["1280x720 (Siêu mượt - Độ trễ thấp nhất)", "1920x1080 (Full HD sắc nét)", "2560x1440 (2K QHD)", "3840x2160 (4K)"],
            command=lambda _: self._on_settings_change()
        )
        cur_res = self.config_data.get("resolution", "1920x1080")
        if "720" in cur_res:
            self.res_combo.set("1280x720 (Siêu mượt - Độ trễ thấp nhất)")
        elif "1440" in cur_res:
            self.res_combo.set("2560x1440 (2K QHD)")
        elif "2160" in cur_res or "3840" in cur_res:
            self.res_combo.set("3840x2160 (4K)")
        else:
            self.res_combo.set("1920x1080 (Full HD sắc nét)")
        self.res_combo.pack(side="right", fill="x", expand=True)

        # FPS Dropdown
        fps_box = ctk.CTkFrame(card2, fg_color="transparent")
        fps_box.pack(fill="x", padx=14, pady=6)
        ctk.CTkLabel(fps_box, text="Tốc độ khung hình:", width=120, anchor="w", font=ctk.CTkFont(size=12)).pack(side="left")
        self.fps_combo = ctk.CTkComboBox(
            fps_box,
            values=["60 FPS (Mượt mà)", "30 FPS (Tiết kiệm pin)"],
            command=lambda _: self._on_settings_change()
        )
        cur_fps = self.config_data.get("fps", 60)
        self.fps_combo.set("60 FPS (Mượt mà)" if cur_fps == 60 else "30 FPS (Tiết kiệm pin)")
        self.fps_combo.pack(side="right", fill="x", expand=True)

        # Renderer Dropdown (Hardware Acceleration)
        rend_box = ctk.CTkFrame(card2, fg_color="transparent")
        rend_box.pack(fill="x", padx=14, pady=6)
        ctk.CTkLabel(rend_box, text="Bộ tăng tốc GPU:", width=120, anchor="w", font=ctk.CTkFont(size=12)).pack(side="left")
        self.rend_combo = ctk.CTkComboBox(
            rend_box,
            values=["Direct3D 11 (GPU)", "Direct3D 9", "OpenGL", "Auto"],
            command=lambda _: self._on_settings_change()
        )
        rend_val = self.config_data.get("video_renderer", "d3d11")
        rend_map = {"d3d11": "Direct3D 11 (GPU)", "d3d": "Direct3D 9", "gl": "OpenGL", "autovideosink": "Auto"}
        self.rend_combo.set(rend_map.get(rend_val, "Direct3D 11 (GPU)"))
        self.rend_combo.pack(side="right", fill="x", expand=True)

        # Audio Toggle
        self.audio_switch = ctk.CTkSwitch(
            card2,
            text="Truyền âm thanh từ iPhone sang loa máy tính",
            font=ctk.CTkFont(size=12),
            command=self._on_settings_change
        )
        if self.config_data.get("enable_audio", True):
            self.audio_switch.select()
        self.audio_switch.pack(anchor="w", padx=14, pady=(6, 12))

        # Wi-Fi Latency Tips Card
        tips_card = ctk.CTkFrame(right_panel, fg_color="#0F172A", corner_radius=10)
        tips_card.pack(fill="x", padx=15, pady=8)

        ctk.CTkLabel(
            tips_card,
            text="🚀 MẸO GIẢM ĐỘ TRỄ TỐI ĐA",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color="#4ADE80"
        ).pack(anchor="w", padx=14, pady=(10, 4))

        tips_text = (
            "• Wi-Fi 5GHz: Kết nối cả iPhone & Laptop vào sóng Wi-Fi 5GHz (thay vì 2.4GHz) để giảm độ trễ dưới 50ms.\n"
            "• Độ phân giải 720p: Giảm tải băng thông mạng, phản hồi tức thì khi vuốt chạm/chơi game.\n"
            "• Tắt VPN: Đảm bảo iPhone không bật VPN hoặc Proxy khi đang chiếu màn hình."
        )
        ctk.CTkLabel(
            tips_card,
            text=tips_text,
            font=ctk.CTkFont(size=11),
            text_color="#94A3B8",
            justify="left",
            wraplength=480
        ).pack(anchor="w", padx=14, pady=(0, 10))

        # Real-time System Log Viewer
        log_card = ctk.CTkFrame(right_panel, fg_color="#0F172A", corner_radius=10)
        log_card.pack(fill="both", expand=True, padx=15, pady=8)

        ctk.CTkLabel(
            log_card,
            text="📋 NHẬT KÝ HOẠT ĐỘNG (LOG)",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color="#94A3B8"
        ).pack(anchor="w", padx=14, pady=(8, 4))

        self.log_textbox = ctk.CTkTextbox(log_card, height=100, font=ctk.CTkFont(family="Consolas", size=10), fg_color="#020617")
        self.log_textbox.pack(fill="both", expand=True, padx=14, pady=(0, 10))

    def _start_server_action(self):
        if self.server.is_running:
            self._append_log("[Hệ thống] Máy chủ đã đang chạy (Sẵn sàng nhận kết nối từ iPhone).")
            return
        self._update_config_from_ui()
        # Run start() on a background thread to avoid UI freeze during Bonjour restart (~1.5s)
        self.start_btn.configure(state="disabled", text="⏳ Đang khởi động...")
        def _do_start():
            success = self.server.start(self.config_data)
            def _update_ui():
                self.start_btn.configure(state="normal")
                if success:
                    self.status_badge.configure(text="🟢 ĐANG PHÁT AIRPLAY (SẴN SÀNG)", fg_color="#15803D")
                    self.start_btn.configure(text="🟢 ĐANG PHÁT AIRPLAY", fg_color="#10B981", hover_color="#059669")
                    self._append_log("[Hệ thống] Máy chủ đã BẬT thành công! Bạn hãy mở iPhone và chiếu màn hình.")
                else:
                    self.status_badge.configure(text="🔴 KHỞI ĐỘNG THẤT BẠI", fg_color="#B91C1C")
                    self.start_btn.configure(text="▶ BẬT MÁY CHỦ", fg_color="#059669", hover_color="#047857")
                    self._append_log("[Hệ thống] Khởi động máy chủ thất bại.")
            self.after(0, _update_ui)
        threading.Thread(target=_do_start, daemon=True).start()

    def _stop_server_action(self):
        if not self.server.is_running:
            self._append_log("[Hệ thống] Máy chủ hiện đang ở trạng thái TẮT.")
            return
        self.server.stop()
        self.status_badge.configure(text="⚪ MÁY CHỦ ĐANG TẮT", fg_color="#334155")
        self.start_btn.configure(text="▶ BẬT MÁY CHỦ", fg_color="#059669", hover_color="#047857")
        self.device_status_label.configure(text="Chưa có thiết bị nào kết nối", text_color="#94A3B8")
        self._append_log("[Hệ thống] Bạn đã DỪNG máy chủ AirPlay. Nhấn nút [BẬT MÁY CHỦ] để kích hoạt lại.")

    def _save_server_name(self):
        new_name = self.name_entry.get().strip()
        if new_name:
            self.config_data["server_name"] = new_name
            save_config(self.config_data)
            self._append_log(f"[Cài đặt] Đã lưu tên máy chủ: {new_name}")
            if self.server.is_running:
                self._append_log("[Cài đặt] Vui lòng khởi động lại máy chủ để áp dụng tên mới.")

    def _fix_hotspot_firewall_action(self):
        try:
            bat_path = os.path.abspath("fix_hotspot_firewall.bat")
            if os.path.exists(bat_path):
                subprocess.Popen(["powershell", "-Command", f"Start-Process '{bat_path}' -Verb RunAs"])
                self._append_log("[Hệ thống] Đang mở trình sửa lỗi Firewall & Hotspot với quyền Admin...")
            else:
                self._append_log("[Lỗi] Không tìm thấy file fix_hotspot_firewall.bat")
        except Exception as e:
            self._append_log(f"[Lỗi] {e}")

    def _update_config_from_ui(self):
        self.config_data["server_name"] = self.name_entry.get().strip() or "CastScreen-PC"
        res = self.res_combo.get().split()[0]
        self.config_data["resolution"] = res
        self.config_data["fps"] = 60 if "60" in self.fps_combo.get() else 30

        rend_sel = self.rend_combo.get()
        if "11" in rend_sel:
            self.config_data["video_renderer"] = "d3d11"
        elif "9" in rend_sel:
            self.config_data["video_renderer"] = "d3d"
        elif "GL" in rend_sel:
            self.config_data["video_renderer"] = "gl"
        else:
            self.config_data["video_renderer"] = "autovideosink"

        self.config_data["enable_audio"] = bool(self.audio_switch.get())
        self.config_data["ultra_low_latency"] = bool(self.latency_switch.get())
        self.config_data["auto_fit_screen"] = bool(self.autofit_switch.get())
        self.config_data["always_on_top"] = bool(self.ontop_switch.get())
        if hasattr(self, "fullscreen_switch"):
            self.config_data["fullscreen_on_connect"] = bool(self.fullscreen_switch.get())
        if hasattr(self, "hud_switch"):
            self.config_data["in_game_hud"] = bool(self.hud_switch.get())
        save_config(self.config_data)

    def _on_settings_change(self):
        self._update_config_from_ui()
        # Notify user if server is already running (new settings need restart to apply)
        if self.server.is_running:
            self.after(0, lambda: self._append_log(
                "[Cài đặt] ⚠️ Cài đặt đã lưu. Vui lòng DỪNG rồi BẬT lại máy chủ để áp dụng."
            ))

    def _on_always_on_top_change(self):
        self._update_config_from_ui()
        hwnd = WindowManager.find_mirror_window()
        if hwnd:
            WindowManager.set_always_on_top(hwnd, self.config_data["always_on_top"])

    def _manual_fit_now(self):
        hwnd = WindowManager.find_mirror_window()
        if hwnd:
            WindowManager.auto_fit_window(hwnd)
            self._append_log("[Display] Đã căn chỉnh cửa sổ chuẩn tỉ lệ iPhone (khử viền đen thừa).")
        else:
            self._append_log("[Display] Chưa tìm thấy cửa sổ phát hình (iPhone chưa kết nối).")

    def _on_hud_toggle(self):
        enabled = bool(self.hud_switch.get())
        self.config_data["in_game_hud"] = enabled
        save_config(self.config_data)
        self.hud_overlay.set_enabled(enabled)
        self._append_log(f"[Display] In-Game HUD Overlay: {'BẬT' if enabled else 'TẮT'}")

    def _manual_crop_fill(self):
        hwnd = WindowManager.find_mirror_window()
        if hwnd:
            WindowManager.crop_fill_window(hwnd)
            self._append_log("[Display] ✂️ Crop Fill: Đã điều chỉnh cửa sổ chính xác 19.5:9, không viền đen, sắc nét tối đa.")
        else:
            self._append_log("[Display] Chưa tìm thấy cửa sổ phát hình (iPhone chưa kết nối).")

    def _manual_toggle_fullscreen(self):
        hwnd = WindowManager.find_mirror_window()
        if hwnd:
            WindowManager.toggle_fullscreen(hwnd)
            self._append_log("[Display] 🖥 Đã chuyển đổi chế độ Toàn màn hình (F11 / ESC).")
        else:
            self._append_log("[Display] Chưa tìm thấy cửa sổ phát hình (iPhone chưa kết nối).")

    def _manual_zoom_to_height(self):
        """Zoom to Height: scale window so height = full monitor height, cut 2 sides equally."""
        hwnd = WindowManager.find_mirror_window()
        if hwnd:
            WindowManager.zoom_to_height(hwnd)
            self._append_log("[Display] ↕ Zoom Khít Chiều Cao: đã phóng to — chiều cao khít màn hình, cắt 2 bên cân bằng.")
        else:
            self._append_log("[Display] Chưa tìm thấy cửa sổ phát hình (iPhone chưa kết nối).")

    def _on_server_status_change(self, status: str):
        def _update():
            if status == "RUNNING":
                self.start_btn.configure(text="🟢 ĐANG PHÁT AIRPLAY", fg_color="#10B981")
                self.status_badge.configure(text="🟢 ĐANG PHÁT AIRPLAY (SẴN SÀNG)", fg_color="#15803D")
            else:
                self.start_btn.configure(text="▶ BẬT MÁY CHỦ", fg_color="#059669")
                self.status_badge.configure(text="⚪ MÁY CHỦ ĐANG TẮT", fg_color="#334155")
        try:
            self.after(0, _update)
        except Exception:
            pass

    def _on_client_connected(self, device_name: str):
        def _update():
            self.status_badge.configure(text=f"🟢 ĐANG CHIẾU: {device_name}", fg_color="#2563EB")
            self.device_status_label.configure(text=f"🟢 {device_name} (Đang truyền luồng trực tiếp)", text_color="#4ADE80")
            self._append_log(f"[KẾT NỐI] {device_name} đã bắt đầu phản chiếu màn hình.")
        self.after(0, _update)

    def _on_client_disconnected(self):
        def _update():
            self.status_badge.configure(text="🟢 ĐANG PHÁT AIRPLAY", fg_color="#15803D")
            self.device_status_label.configure(text="Chưa có thiết bị nào kết nối", text_color="#94A3B8")
            self._append_log("[NGẮT KẾT NỐI] Thiết bị đã dừng phản chiếu.")
        self.after(0, _update)

    def _on_server_log(self, msg: str):
        self.after(0, lambda: self._append_log(msg))

    def _append_log(self, msg: str):
        if "raop_rtp resend failed" in msg:
            return  # Filter out internal UDP retry warnings
        self.log_textbox.insert("end", msg + "\n")
        self.log_textbox.see("end")

    # -----------------------------------------------------------------------
    # Live Client Probe Worker (Real-time Ping & Network Latency)
    # -----------------------------------------------------------------------

    def _probe_client_worker(self):
        """Background worker that continuously detects the connected iPhone IP and
        measures real ICMP/network ping round-trip times (RTT) every 1.5 seconds.
        """
        import re

        while self._probe_running:
            try:
                if self.server.is_running:
                    # 1. Discover client IP from UxPlay established sockets
                    uxplay_pids = [p.info['pid'] for p in psutil.process_iter(['pid', 'name'])
                                   if 'uxplay' in (p.info['name'] or '').lower()]
                    found_ip = None
                    if uxplay_pids:
                        for conn in psutil.net_connections(kind='inet'):
                            if conn.pid in uxplay_pids and conn.status == 'ESTABLISHED':
                                if conn.raddr and conn.raddr.ip not in ('127.0.0.1', '0.0.0.0', '::1'):
                                    found_ip = conn.raddr.ip
                                    break

                    self._client_ip = found_ip or ""

                    # 2. Ping the client IP to get real network round-trip latency
                    if self._client_ip:
                        try:
                            cmd = ["ping", "-n", "1", "-w", "400", self._client_ip]
                            out = subprocess.run(cmd, capture_output=True, text=True, timeout=0.8)
                            m = re.search(r"time[=<]\s*(\d+)\s*ms", out.stdout, re.IGNORECASE)
                            if m:
                                rtt = float(m.group(1))
                                # Smooth RTT with alpha=0.4
                                self._client_ping_ms = 0.4 * rtt + 0.6 * self._client_ping_ms
                        except Exception:
                            pass
            except Exception:
                pass
            time.sleep(1.5)

    # -----------------------------------------------------------------------
    # Bandwidth helper
    # -----------------------------------------------------------------------

    def _get_dwm_fps(self, hwnd: int) -> float:
        """Return the real rendered FPS of the uxplay window using Windows DWM.

        Uses DwmGetCompositionTimingInfo to read the GPU's presented-frame
        counter (cFramesDisplayed) for this window.  Delta between consecutive
        calls divided by elapsed time gives actual frames/second.

        Falls back to 0.0 if DWM is unavailable or the window is invalid.
        """
        try:
            import ctypes
            import ctypes.wintypes

            class DWM_TIMING_INFO(ctypes.Structure):
                _fields_ = [
                    ("cbSize",                    ctypes.c_uint32),
                    ("rateRefresh",               ctypes.c_uint32 * 2),   # UNSIGNED_RATIO
                    ("qpcRefreshPeriod",          ctypes.c_uint64),
                    ("rateCompose",               ctypes.c_uint32 * 2),
                    ("qpcFrame",                  ctypes.c_uint64),
                    ("qpcFrameComplete",          ctypes.c_uint64),
                    ("cFrameComplete",            ctypes.c_uint64),
                    ("qpcFramePending",           ctypes.c_uint64),
                    ("cFramePending",             ctypes.c_uint64),
                    ("qpcFrameDisplayed",         ctypes.c_uint64),
                    ("cFrameDisplayed",           ctypes.c_uint64),
                    ("cRefreshFrameDisplayed",    ctypes.c_uint64),
                    ("cFrameComplete2",           ctypes.c_uint64),
                    ("cFramePending2",            ctypes.c_uint64),
                    ("cFramesAvailable",          ctypes.c_uint64),
                    ("cFramesDropped",            ctypes.c_uint64),
                    ("cFramesMissed",             ctypes.c_uint64),
                    ("cRefreshNextDisplayed",     ctypes.c_uint64),
                    ("cRefreshNextPresented",     ctypes.c_uint64),
                    ("cRefreshesDisplayed",       ctypes.c_uint64),
                    ("cRefreshesPresented",       ctypes.c_uint64),
                    ("cRefreshStarted",           ctypes.c_uint64),
                    ("cPixelsReceived",           ctypes.c_uint64),
                    ("cPixelsDrawn",              ctypes.c_uint64),
                    ("cBuffersEmpty",             ctypes.c_uint64),
                ]

            info = DWM_TIMING_INFO()
            info.cbSize = ctypes.sizeof(DWM_TIMING_INFO)
            hr = ctypes.windll.dwmapi.DwmGetCompositionTimingInfo(
                hwnd, ctypes.byref(info)
            )
            if hr != 0:   # S_OK = 0
                return 0.0

            now_t        = time.perf_counter()
            frames_now   = info.cFramesDisplayed

            if not hasattr(self, '_dwm_last_frames'):
                self._dwm_last_frames = frames_now
                self._dwm_last_ts     = now_t
                return 0.0

            elapsed = now_t - self._dwm_last_ts
            if elapsed < 0.1:
                return 0.0

            delta_frames = frames_now - self._dwm_last_frames
            self._dwm_last_frames = frames_now
            self._dwm_last_ts     = now_t

            if delta_frames < 0:   # counter wrapped
                return 0.0

            return delta_frames / elapsed
        except Exception:
            return 0.0

    # -----------------------------------------------------------------------
    # Bandwidth helper
    # -----------------------------------------------------------------------

    def _get_bandwidth_mbps(self) -> float:
        """Return inbound network bandwidth in Mbps."""
        mbps, _ = self._get_network_stream_metrics()
        return mbps

    def _get_network_stream_metrics(self) -> tuple:
        """Return (mbps: float, pps: float) measuring real packet and bit arrival rate."""
        try:
            if not self._bw_iface:
                local_ip = AirPlayServer.get_local_ip()
                stats = psutil.net_if_stats()
                addrs = psutil.net_if_addrs()
                for iface, addr_list in addrs.items():
                    if not stats.get(iface) or not stats[iface].isup:
                        continue
                    for addr in addr_list:
                        if addr.family == 2 and addr.address == local_ip:
                            self._bw_iface = iface
                            break
                    if self._bw_iface:
                        break

            if not self._bw_iface:
                return 0.0, 0.0

            counters = psutil.net_io_counters(pernic=True)
            iface_c = counters.get(self._bw_iface)
            if iface_c is None:
                return 0.0, 0.0

            now = time.time()
            bytes_recv = iface_c.bytes_recv
            packets_recv = iface_c.packets_recv

            if not hasattr(self, "_bw_last_packets") or self._bw_last_ts == 0.0:
                self._bw_last_bytes = bytes_recv
                self._bw_last_packets = packets_recv
                self._bw_last_ts = now
                return 0.0, 0.0

            elapsed = now - self._bw_last_ts
            if elapsed < 0.05:
                return 0.0, 0.0

            delta_bytes = max(0, bytes_recv - self._bw_last_bytes)
            delta_pkts = max(0, packets_recv - self._bw_last_packets)
            self._bw_last_bytes = bytes_recv
            self._bw_last_packets = packets_recv
            self._bw_last_ts = now

            mbps = (delta_bytes * 8) / (elapsed * 1_000_000)
            pps = delta_pkts / elapsed
            return mbps, pps
        except Exception:
            return 0.0, 0.0

    # -----------------------------------------------------------------------
    # Main background daemon loop
    # -----------------------------------------------------------------------

    def _auto_fit_loop(self):
        """Background thread: window management, hotkeys, real-time stats, connection detection.

        Consolidates all polling into one thread to avoid duplicate EnumWindows
        calls (the previous _monitor_output thread has been removed).
        """
        last_hwnd          = None
        last_mode          = None
        first_seen_time    = 0.0
        initial_fit_applied = False
        last_hotkey_time   = 0.0
        stats_tick         = 0
        was_connected      = False      # for connection event detection

        # Real latency / FPS tracking
        last_frame_time    = 0.0
        smoothed_fps       = 0.0
        smoothed_lat       = 0.0
        smoothed_bw        = 0.0        # Mbps smoothed

        LOOP_INTERVAL = 0.2            # target cadence in seconds

        while self.auto_fit_running:
            loop_start = time.time()
            try:
                if self.server.is_running:
                    hwnd = WindowManager.find_mirror_window()
                    if hwnd:
                        now = time.time()

                        # ── New window appeared ──────────────────────────────
                        if hwnd != last_hwnd:
                            last_hwnd           = hwnd
                            first_seen_time     = now
                            initial_fit_applied = False
                            last_mode           = None
                            # Reset metrics
                            smoothed_fps     = 0.0
                            smoothed_lat     = 0.0
                            smoothed_bw      = 0.0
                            last_frame_time  = 0.0
                            self._bw_last_ts = 0.0    # reset bandwidth baseline
                            # Reset DWM frame counter baseline
                            if hasattr(self, '_dwm_last_frames'):
                                del self._dwm_last_frames

                        # ── Connection detection (replaces _monitor_output) ──
                        if not was_connected:
                            was_connected = True
                            self.server.connected_device = "Thiết bị iOS (AirPlay)"
                            if self.server.on_client_connected:
                                self.server.on_client_connected(self.server.connected_device)

                        # ── Wait for GStreamer D3D11 swapchain to stabilise ──
                        if not initial_fit_applied and (now - first_seen_time >= 1.5):
                            initial_fit_applied = True
                            try:
                                rect  = win32gui.GetWindowRect(hwnd)
                                w, h  = rect[2] - rect[0], rect[3] - rect[1]
                                last_mode = "LANDSCAPE" if w > h else "PORTRAIT"
                            except Exception:
                                last_mode = "LANDSCAPE"

                            if self.config_data.get("fullscreen_on_connect", False):
                                WindowManager.set_fullscreen(hwnd, True)
                            elif self.config_data.get("auto_fit_screen", True):
                                WindowManager.auto_fit_window(hwnd)
                                self.after(0, lambda m=last_mode: self._append_log(
                                    f"[Display] Tự động căn chỉnh theo tỉ lệ iPhone 14 ({m})."))

                            if self.config_data.get("always_on_top", False):
                                WindowManager.set_always_on_top(hwnd, True)

                        elif initial_fit_applied:
                            # ── Auto-fit on orientation change ───────────────
                            try:
                                rect  = win32gui.GetWindowRect(hwnd)
                                w, h  = rect[2] - rect[0], rect[3] - rect[1]
                                cur_mode = "LANDSCAPE" if w > h else "PORTRAIT"
                                if cur_mode != last_mode:
                                    last_mode = cur_mode
                                    if (self.config_data.get("auto_fit_screen", True)
                                            and not WindowManager.is_fullscreen(hwnd)):
                                        WindowManager.auto_fit_window(hwnd)
                                        self.after(0, lambda m=cur_mode: self._append_log(
                                            f"[Display] Tự động phóng to theo tỉ lệ ({m})."))
                            except Exception:
                                pass

                        # ── In-Game HUD & Dashboard Metrics ───────────────────
                        target_fps = float(self.config_data.get("fps", 60))

                        # ── Global hotkeys ───────────────────────────────────
                        try:
                            now = time.time()
                            if win32api.GetAsyncKeyState(win32con.VK_F9) & 0x8000:
                                if now - last_hotkey_time > 0.5:
                                    last_hotkey_time = now
                                    WindowManager.crop_fill_window(hwnd)
                                    self.after(0, lambda: self._append_log("✂️ F9: Crop Fill — cắt viền đen, sắc nét tối đa."))
                            elif win32api.GetAsyncKeyState(win32con.VK_F10) & 0x8000:
                                if now - last_hotkey_time > 0.5:
                                    last_hotkey_time = now
                                    WindowManager.zoom_to_height(hwnd)
                                    self.after(0, lambda: self._append_log("↕ F10: Zoom Khít Chiều Cao — cắt 2 bên, chiều cao khít màn hình."))
                            elif win32api.GetAsyncKeyState(win32con.VK_F11) & 0x8000:
                                if now - last_hotkey_time > 0.5:
                                    last_hotkey_time = now
                                    WindowManager.toggle_fullscreen(hwnd)
                                    self.after(0, lambda: self._append_log("🖥 F11: Chuyển đổi chế độ Toàn màn hình."))
                            elif win32api.GetAsyncKeyState(win32con.VK_ESCAPE) & 0x8000:
                                if now - last_hotkey_time > 0.5 and WindowManager.is_fullscreen(hwnd):
                                    last_hotkey_time = now
                                    WindowManager.set_fullscreen(hwnd, False)
                                    self.after(0, lambda: self._append_log("🖥 ESC: Thoát chế độ Toàn màn hình."))
                        except Exception:
                            pass



                    else:
                        # ── Mirror window gone ───────────────────────────────
                        if last_hwnd is not None:
                            last_hwnd = None
                            # Reset all metrics
                            smoothed_fps     = 0.0
                            smoothed_lat     = 0.0
                            smoothed_bw      = 0.0
                            last_frame_time  = 0.0
                            self._bw_last_ts = 0.0
                            if hasattr(self, '_dwm_last_frames'):
                                del self._dwm_last_frames
                            self.after(0, lambda: self.hud_overlay.update_overlay(None))
                            def _clear_stats():
                                try:
                                    self.fps_stat_label.configure(text="⚡ Tốc độ: -- FPS (Chờ kết nối)", text_color="#94A3B8")
                                    self.latency_stat_label.configure(text="⏱️ Độ trễ: -- ms (Chờ kết nối)", text_color="#94A3B8")
                                    self.bitrate_stat_label.configure(text="📡 Băng thông: -- Mbps", text_color="#94A3B8")
                                    self.gpu_stat_label.configure(text="🎮 GPU Engine: Direct3D 11 Sẵn sàng", text_color="#4ADE80")
                                except Exception:
                                    pass
                            self.after(0, _clear_stats)

                        # ── Disconnection event ──────────────────────────────
                        if was_connected:
                            was_connected = False
                            self.server.connected_device = None
                            if self.server.on_client_disconnected:
                                self.server.on_client_disconnected()

            except Exception:
                pass

            # Compensated sleep: subtract time spent in this iteration so
            # the actual cadence stays close to LOOP_INTERVAL regardless of
            # how long the loop body took (fixes loop drift / FPS measurement bias).
            elapsed = time.time() - loop_start
            sleep_for = max(0.0, LOOP_INTERVAL - elapsed)
            time.sleep(sleep_for)

    def on_closing(self):
        self.auto_fit_running = False
        self._probe_running = False
        self.hud_overlay.destroy()
        self.server.stop()
        self.destroy()

