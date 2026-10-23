# HẮC TÂY DU WEB AUTO v7.9 — MULTI-MACHINE & AUTO REROLL

Tool auto reroll và web client tự động cho game Hắc Tây Du (Funtap), hỗ trợ chạy đa luồng cực nhanh, chạy đồng thời trên nhiều máy tính độc lập (Multi-Machine), tự động nhận diện server mới nhất và tích hợp đẩy tài khoản trúng vào Bot bán hàng (Telegram Shop Bot).

---

## 🚀 1. KIẾN TRÚC CHẠY ĐỒNG THỜI NHIỀU MÁY (MULTI-MACHINE)

Để 2 hoặc nhiều máy cùng cày reroll song song mà không bao giờ bị đụng độ:

1. **Phân tách không gian tên tài khoản (Prefix Isolation):**
   - **Máy 1:** Dùng tiền tố `htd_vip` $\rightarrow$ sinh nick: `htd_vip_a_001`, `htd_vip_a_002`...
   - **Máy 2:** Dùng tiền tố `htd_m2` $\rightarrow$ sinh nick: `htd_m2_a_001`, `htd_m2_a_002`...
   - **Máy 3:** Dùng tiền tố `htd_m3` $\rightarrow$ sinh nick: `htd_m3_a_001`, `htd_m3_a_002`...
   - Mỗi máy tạo ra dải nick hoàn toàn độc lập, không trùng nhau trên hệ thống Funtap.

2. **Cơ chế tái sử dụng phôi nick:**
   - Mỗi máy lưu trữ dữ liệu nick đã cày ở file local `DAN_NICK_DA_QUAY.json` (được `.gitignore` để không bị xung đột khi `git pull`/`git push`).
   - Khi Funtap mở server mới (ví dụ S72), cả 2 máy sẽ tự động phát hiện và đem toàn bộ phôi nick cũ của máy mình sang server mới để quay lại từ đầu, tối ưu 100% thời gian tạo nick.

3. **Thu hoạch tài khoản:**
   - Khi quay trúng tướng mục tiêu (≥2 Dương Tiễn hoặc ≥2 Tôn Ngộ Không), máy sẽ tự động:
     - Ghi vào `DAN_NICK_TRUNG_TUONG.txt` & `.csv`.
     - Chụp ảnh bằng chứng vào thư mục `anh_nick_trung/`.
     - Bơm trực tiếp tài khoản sang Bot Bán Hàng.

---

## 🛠️ 2. HƯỚNG DẪN CÀI ĐẶT & CHẠY

### Yêu cầu môi trường:
- Python 3.10 trở lên.
- Cài đặt thư viện:
  ```bash
  pip install aiohttp playwright requests
  playwright install chromium
  ```

### Khởi chạy trên từng máy:

#### 👉 Trên Máy 1:
- Nhấp đúp vào: **`Chay_May_1.bat`**
- Hoặc chạy lệnh:
  ```bash
  python chay_web_auto.py --machine 1 --prefix htd_vip --threads 24 --port 8088
  ```

#### 👉 Trên Máy 2:
- Clone repo về máy:
  ```bash
  git clone https://github.com/truongqv12/HacTayDu_Web_Auto_v79.git
  cd HacTayDu_Web_Auto_v79
  ```
- Nhấp đúp vào: **`Chay_May_2.bat`**
- Hoặc chạy lệnh:
  ```bash
  python chay_web_auto.py --machine 2 --prefix htd_m2 --threads 24 --port 8088
  ```

---

## ⚙️ 3. CẤU HÌNH HỆ THỐNG (`config.json` & `config_local.json`)

Nếu các nick nhận giftcode không đều, xem [hướng dẫn kiểm tra giftcode](docs/giftcode-troubleshooting.md).

Mỗi máy có thể cấu hình riêng thông qua file `config_local.json` (ưu tiên cao nhất, không bị git đè) hoặc file chung `config.json`:

```json
{
  "machine_id": "m1",
  "account_prefix": "htd_vip",
  "threads": 24,
  "port": 8088,
  "target_server": "latest",
  "min_copies": 2,
  "sales_bot": {
    "enabled": false,
    "webhook_url": "https://your-bot-domain.com/api/webhook/hactaydu",
    "auth_token": "YOUR_SECRET_TOKEN",
    "telegram_bot_token": "",
    "telegram_chat_id": ""
  }
}
```

---

## 🤖 4. ĐẤU NỐI BƠM TÀI KHOẢN VÀO BOT BÁN HÀNG

Hệ thống hỗ trợ 2 phương án đấu nối:

### Cách 1: Bơm Realtime qua Webhook (Khuyên dùng khi bot có API)
Khi bất kỳ máy nào nổ nick x2/x3, background worker sẽ tự động gửi HTTP POST payload JSON:
```json
{
  "event": "reroll_winner",
  "machine_id": "m1",
  "account": "htd_vip_a_127",
  "password": "...",
  "funtap_id": "...",
  "server_id": 610071,
  "server_name": "[S71 Mới Nhất] Nữ Nhi Quốc-S1",
  "target_hero": "Dương Tiễn",
  "count": 2,
  "heroes": ["Dương Tiễn", "Dương Tiễn", "Cang Kim Tinh Quân", ...],
  "screenshot_path": "anh_nick_trung/htd_vip_b_127_S71.png",
  "timestamp": 1729647000
}
```

### Cách 2: Đồng bộ hàng loạt vào Telegram Shop Bot trên VPS
Nhấp đúp vào **`push_to_bot.bat`** (hoặc chạy `python push_hactaydu.py`):
- Tự động đồng bộ ảnh chụp từ `anh_nick_trung/` sang VPS qua SSH/SCP.
- Copy `DAN_NICK_TRUNG_TUONG.txt` vào container bot.
- Kích hoạt lệnh nạp kho tự động trên bot: `sync_hactaydu_data(purge_mock=False)`.
