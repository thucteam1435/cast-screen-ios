# Hướng Dẫn Triển Khai Cast Screen Web Lên Cloudflare Pages (Miễn Phí 100%)

Nền tảng **Cast Screen Web** được thiết kế để chạy hoàn toàn trên gói **Cloudflare Free Tier** (Zero-Cost, Băng thông vô hạn, Hỗ trợ HTTPS & Custom Domain miễn phí).

---

## 🚀 Cách 1: Deploy Bằng Giao Diện Web Cloudflare Dashboard (Khuyên Dùng — 2 Phút)

### Bước 1: Đẩy mã nguồn lên GitHub
1. Tạo một repository mới trên [GitHub](https://github.com/new) (ví dụ đặt tên: `cast-screen-web`).
2. Đẩy toàn bộ thư mục `web/` lên repository này:
   ```bash
   cd "d:\Cast Screen\web"
   git init
   git add .
   git commit -m "Initial commit for Cast Screen Web"
   git branch -M main
   git remote add origin https://github.com/<tai-khoan-cua-ban>/cast-screen-web.git
   git push -u origin main
   ```

### Bước 2: Kết nối với Cloudflare Pages
1. Đăng nhập vào [Cloudflare Dashboard](https://dash.cloudflare.com/).
2. Chọn mục **Workers & Pages** -> Bấm **Create application** -> Chọn tab **Pages** -> Bấm **Connect to Git**.
3. Chọn repository `cast-screen-web` bạn vừa tạo.
4. Ở phần **Build settings**:
   * **Framework preset**: `None`
   * **Build command**: *(Để trống)*
   * **Build output directory**: `./`
5. Nhấn **Save and Deploy**.

🎉 **XONG!** Sau 30 giây, Cloudflare sẽ cấp cho bạn một tên miền miễn phí cực đẹp (ví dụ: `https://cast-screen-web.pages.dev`).

---

## ⚡ Cách 2: Deploy Bằng Dòng Lệnh (Cloudflare Wrangler CLI)

Nếu bạn thích dùng dòng lệnh trực tiếp:
1. Mở PowerShell trong thư mục `web/`:
   ```powershell
   cd "d:\Cast Screen\web"
   ```
2. Cài đặt và đăng nhập Cloudflare:
   ```powershell
   npx wrangler login
   ```
3. Chạy lệnh Deploy:
   ```powershell
   npx wrangler pages deploy ./ --project-name=cast-screen-web
   ```

---

## 🧪 Cách Kiểm Thử Cục Bộ Trước Khi Deploy (Localhost & Wi-Fi)

1. Chạy file **`run_web.bat`** (hoặc lệnh `python local_server.py`).
2. Mở trình duyệt trên máy tính vào địa chỉ: **`http://localhost:8080`**.
3. Dùng iPhone / Android trong cùng mạng Wi-Fi quét mã QR trên màn hình.
4. Bấm nút **"Bắt đầu Chiếu"** trên điện thoại để trải nghiệm luồng truyền WebRTC mượt mà 60 FPS!
