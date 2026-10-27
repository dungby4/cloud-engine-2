# Hắc Tây Du M2 — SDK 3.1.1 CLEAN

Đây là bản thay M2 cũ, chạy song song với M1. Không chạy đồng thời hai bản M2. Gồm 13.654 nick phần M2, Telegram ghi M2; 16 luồng / 180 ms và 1 worker tân thủ riêng. Chỉ dùng nick sẵn có, chỉ quay vé Thiên Mệnh 501; giữ 502/503. Tự chọn server mới nhất từ 610094; nick không nổ vẫn dùng lại ở server sau. Bảo vệ nick đã bán/két/đã lấy.

## Chuyển từ M2 cũ

1. Chạy DUNG ở M2 cũ và chờ dừng hẳn.
2. Giải nén bản mới vào thư mục riêng.
3. Chép nguyên thư mục `state` của chính máy M2 cũ vào bản mới để giữ checkpoint/két/hàng đợi. Không chép state hoặc machine.json từ M1. Không chép đè source JS/Python bằng bản cũ.
4. Cài Node.js 20+ và Python 3.9+ (thêm PATH).
5. Windows: chạy `CAI_DAT_WINDOWS.bat`, sau đó `KIEM_TRA_BAN_WINDOWS.bat` (phải báo 3.1.1 / OK), rồi `CHAY_WINDOWS.bat`.
6. Mac: chạy `CAI_DAT_MAC.command`, sau đó `CHAY_MAC.command`.

Bộ cài sẽ đặt lại M2/2, 16 luồng / 180 ms và server tối thiểu 610094 sau khi nhập state cũ. Đóng cửa sổ log không dừng runner; dùng DUNG để dừng an toàn. Giữ thư mục state khi chạy tiếp.

## Sửa login

SDK TK/MK -> checkLogin.php -> đối chiếu openid với AccID -> dùng đúng time/authkey/userIp để vào game. Không dùng token r hoặc khóa giả. Chưa xác nhận login thì không gửi code/quay vé; lỗi danh tính/xác thực sẽ dừng nhận nick mới.

Rule nổ giữ nguyên: X2/X3 cùng nòng cốt; Cang Kim chỉ trừ đúng 1 bản code tặng. Nick nổ khóa két, tân thủ riêng, xác nhận hoàn tất và Lv8+, ảnh túi tướng xếp cặp đầu rồi gửi Tele kèm tên máy M2. Lỗi không báo hoàn tất giả.

Nguồn đã chạy thực tế trên Mac với SDK login và phản hồi 28/28. Kiểm tra offline/ZIP được thực hiện trước bàn giao; chưa chạy thực tế trên Windows. Đây là source + launcher cài dependencies, không kèm Node/Python/Chromium. Cần Internet khi cài.

ZIP có tài khoản/mật khẩu và cấu hình Telegram của anh; chỉ chuyển riêng cho máy anh quản lý.

## Bản clean

Chỉ làm sạch đóng gói, không đổi logic runtime so với SDK 3.1.0 đã chạy. Không có node_modules, môi trường .venv, log, ảnh cũ, file thử nick, file tạm hoặc tiến trình chạy. Cài đặt sẽ tải dependencies. Có test/ để tự kiểm tra npm test. Có dữ liệu processed_accounts và protection để giữ lịch sử/bảo vệ; không xóa các file này.
