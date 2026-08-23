# Tải Cast Screen AirPlay Agent cho Windows

## Bạn đang tải gì?

`CastScreenAirPlayAgentSetup.exe` là **bộ cài của thành phần AirPlay Receiver** dành cho PC Host của Cast Screen.

Nó **không phải phần mềm theo dõi**, không phải remote-access tool và không yêu cầu Python.

### Thành phần được cài

- `CastScreenAirPlayAgent.exe`: dịch vụ nền điều khiển AirPlay.
- UxPlay + GStreamer/D3D11: nhận và xử lý luồng AirPlay trên chính PC.
- mDNS/Bonjour components: giúp iPhone nhìn thấy `CastScreen-PC` trong mạng LAN.
- Local Control API trên `127.0.0.1:8765`: website dùng để bật/tắt receiver khi Host tạo/thoát phòng.

### Luồng dữ liệu

`iPhone → AirPlay → LAN → PC Host → UxPlay/GStreamer`

Hình ảnh và âm thanh AirPlay không được upload lên Cloudflare làm relay media.

### Vì sao Windows có thể hiện cảnh báo?

Bộ cài là ứng dụng Windows có khả năng:

- lắng nghe kết nối mạng cục bộ;
- quảng bá dịch vụ mDNS;
- xử lý luồng media;
- chạy một tiến trình nền.

Đó là những đặc điểm khiến Windows Defender/SmartScreen có thể yêu cầu xác nhận.

**Bản phát hành hiện tại chưa được ký bằng chứng thư Code Signing**, vì vậy SmartScreen có thể hiển thị cảnh báo “Windows protected your PC” khi file chưa có danh tiếng. Đây không phải bằng chứng rằng file là virus.

Người dùng nên tải file từ nguồn phát hành chính thức của Cast Screen và đối chiếu SHA-256 được cung cấp cùng bản phát hành.

## Cài đặt

1. Chạy `CastScreenAirPlayAgentSetup.exe`.
2. Cho phép Windows cài ứng dụng khi được hỏi.
3. Agent sẽ được đăng ký chạy cùng Windows.
4. Mở Cast Screen Web và bấm **Tạo phòng**.
5. Chỉ khi Host có phòng, Agent mới bật AirPlay Receiver.

Không cần mở PowerShell và không cần chạy `.py`.

## Gỡ cài đặt

Vào Windows Settings → Apps → Installed apps → **Cast Screen AirPlay Agent** → Uninstall.
