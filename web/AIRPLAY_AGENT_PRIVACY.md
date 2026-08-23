# Cast Screen AirPlay Agent — Quyền riêng tư & bảo mật

## Mục đích

Agent chỉ phục vụ tính năng:

- AirPlay Receiver cho PC Host.
- Phát hiện iPhone/iPad kết nối AirPlay.
- Giao tiếp điều khiển cục bộ với website Cast Screen.

## Giao tiếp cục bộ

Agent lắng nghe trên `127.0.0.1:8765`, tức chỉ chương trình trên chính máy tính mới có thể gọi Local Control API. Agent không mở API điều khiển này ra Internet.

## AirPlay / mDNS

Trong thời gian một phòng Host hoạt động, UxPlay và mDNS được bật để iPhone có thể nhìn thấy `CastScreen-PC` trong cùng mạng LAN. Khi Host thoát phòng, receiver được tắt.

## Dữ liệu

Agent không có chức năng upload nội dung màn hình, file cá nhân, mật khẩu hoặc dữ liệu trình duyệt lên máy chủ Cast Screen. Media AirPlay được xử lý tại PC Host.

## Xác thực Local API

Agent cung cấp token phiên cho các lệnh điều khiển. Website dùng token đó cho các request `start`, `stop` và `authorize`.

## Tự động khởi động

Installer có thể đăng ký Agent chạy cùng Windows để người dùng không phải chạy thủ công. Agent ở trạng thái chờ và chỉ bật AirPlay khi có phòng Host.
