# 📱 Cast Screen Pro - Chiếu Màn Hình iOS Lên Laptop Windows Qua Wi-Fi

Phần mềm chuyên nghiệp cho phép chiếu (mirror) trực tiếp màn hình từ iPhone, iPad (iOS) lên Laptop Windows với chất lượng cao (1080p / 60 FPS, 4K), độ trễ cực thấp và **tự động điều chỉnh kích thước màn hình** khi xoay dọc hoặc xoay ngang.

---

## 🌟 Tính Năng Nổi Bật

- **Chiếu qua AirPlay gốc của iOS (Native Screen Mirroring)**: Không cần cài đặt bất kỳ ứng dụng nào trên iPhone/iPad.
- **Tối ưu Siêu Giảm Độ Trễ (Ultra-Low Latency Mode)**:
  - Tắt bộ đệm giữ khung hình (`-vsync no`, `-async no`, `-nohold`) giúp giảm độ trễ xuống mức tối thiểu (30ms - 50ms).
  - Phản hồi tức thì khi vuốt lướt, chơi game, xem camera trực tiếp.
  - Tăng tốc phần cứng GPU Direct3D 11 (D3D11).
  - Tuỳ chọn chế độ **720p 60FPS (Siêu mượt)** hoặc **1080p 60FPS (Sắc nét)**.
- **Tự động điều chỉnh kích thước thông minh (Smart Auto-Fit)**:
  - Tự động nhận diện khi iPhone xoay ngang (Landscape - xem phim, chơi game) hoặc xoay dọc (Portrait - lướt TikTok, Facebook, nhắn tin) để căn chỉnh khung hình chuẩn xác, không bị biến dạng.
  - Phím tắt tiện lợi: **F11 (Toàn màn hình)**, **Ghim cửa sổ nổi lên trên cùng (Always on Top)**.
- **Giao diện điều khiển Dark Glassmorphism hiện đại**:
  - Bật/Tắt máy chủ chỉ với 1 click.
  - Tùy chỉnh tên hiển thị trên iPhone (VD: `Laptop-Cua-Thuc`).
  - Hiển thị địa chỉ IP, trạng thái kết nối và nhật ký hoạt động thời gian thực.
  - Tùy chọn truyền âm thanh từ iPhone sang loa máy tính hoặc tắt tiếng.
- **Khởi chạy 1-Click**: Có sẵn file `run.bat` để mở nhanh mà không cần gõ lệnh.

---

## 🚀 Hướng Dẫn Sử Dụng

### Bước 1: Khởi động phần mềm
- Nhấp đúp vào file `run.bat` (hoặc chạy `python app.py`).
- Giao diện bảng điều khiển sẽ mở ra và tự động kích hoạt máy chủ AirPlay (đèn báo xanh: `🟢 ĐANG PHÁT AIRPLAY`).

### Bước 2: Kết nối từ iPhone / iPad
1. Đảm bảo iPhone/iPad và Laptop đang kết nối **chung một mạng Wi-Fi**.
2. Trên iPhone, vuốt từ góc trên bên phải màn hình xuống (đối với iPhone có tai thỏ / Dynamic Island) hoặc vuốt từ dưới lên để mở **Trung tâm điều khiển (Control Center)**.
3. Nhấn vào biểu tượng **Phản chiếu màn hình** (Hình 2 màn hình chữ nhật xếp chồng).
4. Chọn tên máy chủ hiển thị trên phần mềm (VD: `CastScreen-PC`).

### Bước 3: Thưởng thức màn hình lớn
- Màn hình iPhone sẽ xuất hiện ngay lập tức trên Laptop với độ phân giải cao và độ mượt 60 FPS.
- Cửa sổ sẽ tự động co giãn vừa vặn màn hình Laptop khi bạn xoay ngang hoặc dọc iPhone.

---

## 🛠 Cấu Trúc Dự Án

```
d:/Cast Screen/
├── app.py                     # Entry point khởi chạy ứng dụng
├── run.bat                    # Script khởi động nhanh 1-click
├── config.py                  # Quản lý cấu hình cài đặt
├── settings.json              # Lưu tùy chọn người dùng
├── requirements.txt           # Thư viện Python cần thiết
├── engine/
│   ├── airplay_server.py      # Lõi quản lý tiến trình AirPlay Server
│   └── bin/                   # Bộ thư viện giải mã H.264 & Bonjour
├── display/
│   └── window_manager.py      # Quản lý kích thước, Auto-Fit, Fullscreen
└── gui/
    └── dashboard.py           # Giao diện điều khiển Dark Theme
```
