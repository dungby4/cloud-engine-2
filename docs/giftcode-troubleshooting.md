# Kiểm tra giftcode thiếu ngẫu nhiên

Nếu cùng đợt chạy có nick nhận đủ danh sách nhưng nick khác thiếu, cần phân biệt
server chưa xử lý với tool chưa nhận được xác nhận. Tổng `Code: x/y` là số mã đã
xác nhận, không phải số request đã gửi. `Chưa xác nhận` ghi tên mã và thông báo
gần nhất để điều tra mà không đoán từ số lượng tướng.

Nhịp gửi và xử lý phản hồi nằm ở [GiftcodeClaims](../giftcode_claims.py).
Kết nối lại và nhận thư nằm trong
[`_reroll_single_account`](../chay_web_auto.py).
Game không trả tên mã trong ACK; khi request hết thời gian chờ, kết nối mới
giúp tránh gán phản hồi cũ cho mã tiếp theo. Khoảng nghỉ là lựa chọn thận trọng,
chưa phải ngưỡng giới hạn đã đo trên server.

Sau khi cập nhật, dừng lượt chạy bằng cơ chế sẵn có rồi mở lại tool để nạp code
Python mới. Theo dõi dòng cảnh báo giftcode nếu vẫn thiếu; giữ nguyên thông báo
server khi gửi log chẩn đoán. Danh sách tài khoản và mật khẩu không cần cho việc
đối chiếu lỗi giftcode.

Kiểm thử nằm ở [tests/test_giftcode_claims.py](../tests/test_giftcode_claims.py),
chạy bằng `python -m unittest discover -s tests -v`. WebSocket cục bộ kiểm chứng
nhịp gửi, phản hồi chậm, nhập bù và kết nối lại; tính hợp lệ của mã và giới hạn
server thật cần đối chiếu log thực tế.
