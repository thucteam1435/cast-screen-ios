# Cast Screen AirPlay Agent — Hướng dẫn cho người dùng

## Đây là gì?

**Cast Screen AirPlay Agent** là một thành phần phụ trợ nhỏ chạy trên **PC Host** để cho phép iPhone sử dụng **AirPlay / Screen Mirroring** với Cast Screen.

Website Cast Screen không thể tự biến trình duyệt Windows thành AirPlay Receiver. Vì vậy Agent đảm nhiệm phần native mà trình duyệt không có API để làm: quảng bá thiết bị AirPlay trên mạng LAN, nhận phiên AirPlay bằng UxPlay và báo trạng thái cho trang web.

## Người dùng có cần Python không?

**Không.** Bản phát hành chính thức là `CastScreenAirPlayAgentSetup.exe`. Sau khi cài xong, Agent chạy nền cùng Windows. Người dùng không cần mở PowerShell, không cần cài Python và không cần chạy file `.py`.

## Agent làm gì?

Khi PC không có phòng Cast Screen đang hoạt động:

- Agent chỉ chạy một dịch vụ điều khiển cục bộ trên `127.0.0.1:8765`.
- AirPlay Receiver/UxPlay **không được bật**.
- PC không quảng bá `CastScreen-PC` trên AirPlay.

Khi người dùng bấm **Tạo phòng** trên website:

1. Website gọi Local Agent.
2. Agent khởi động UxPlay.
3. Agent quảng bá `CastScreen-PC` qua mDNS trên các mạng đang hoạt động.
4. iPhone mở Control Center → Screen Mirroring → chọn `CastScreen-PC`.
5. Agent phát hiện iPhone và website hiển thị hộp thoại xin phép.
6. Chọn **Cho phép** để tiếp tục phiên AirPlay.
7. Thoát phòng sẽ yêu cầu Agent tắt UxPlay và ngừng quảng bá AirPlay.

## Dữ liệu có đi qua Internet không?

**Luồng hình ảnh và âm thanh AirPlay đi trực tiếp trong mạng LAN giữa iPhone và PC.** Website Cloudflare chỉ cung cấp giao diện và signaling WebRTC của Cast Screen.

Agent không tải màn hình của bạn lên một máy chủ trung gian.

## Vì sao Windows có thể cảnh báo file `.exe`?

Agent có các thành phần nhận AirPlay, mDNS và xử lý multimedia nên một số phần mềm bảo mật có thể xem đây là ứng dụng mạng cần cấp quyền. Điều này **không đồng nghĩa file là virus**.

Khi cài, hãy kiểm tra nguồn tải là trang phát hành chính thức của Cast Screen và xem hướng dẫn này đi kèm bộ cài.

## Quyền cần thiết

Agent cần:

- Cho phép giao tiếp mạng cục bộ để iPhone có thể tìm thấy PC bằng AirPlay.
- Cho phép `CastScreenAirPlayAgent.exe` và UxPlay giao tiếp qua mạng LAN trong Windows Firewall khi Windows hỏi.
- Chạy nền để website có thể bật/tắt AirPlay Receiver theo vòng đời phòng.

Agent **không cần** quyền quản trị hệ thống để theo dõi bàn phím, đọc file cá nhân hoặc truy cập tài khoản online.

## Gỡ cài đặt

Vào **Settings → Apps → Installed apps → Cast Screen AirPlay Agent → Uninstall**.

Sau khi gỡ cài đặt, Agent, UxPlay và mục khởi động cùng Windows sẽ được xóa.
