"""Script tự động giám sát file DAN_NICK_TRUNG_TUONG.txt và bơm nick vào Bot 24/7.

Chạy ngầm trên máy treo tool auto reroll.
Cứ khi nào tool nổ nick mới (ghi thêm dòng vào DAN_NICK_TRUNG_TUONG.txt):
Script sẽ tự động đọc dòng mới + lấy ảnh chụp đội hình -> Bắn Webhook vào Bot bán hàng ngay lập tức!
"""

from __future__ import annotations

import argparse
import base64
import json
import sys
import time
import urllib.request
from pathlib import Path


def main() -> None:
    try:
        if sys.stdout and hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    parser = argparse.ArgumentParser(description="Tự động giám sát và bơm nick Hắc Tây Du 24/7")
    parser.add_argument(
        "--url",
        default="http://100.94.81.101:8082/api/v1/inventory/hactaydu-webhook",
        help="URL Webhook của Bot",
    )
    parser.add_argument(
        "--secret",
        default="d57be08c4bbbc9c7feda86285611ee41fc8016d4f1bf4a1a7a60502d123b0ab3",
        help="Mã bí mật xác thực webhook",
    )
    parser.add_argument("--txt", default="DAN_NICK_TRUNG_TUONG.txt", help="File nick cần theo dõi")
    parser.add_argument("--photos", default="anh_nick_trung", help="Thư mục ảnh")
    parser.add_argument("--poll-interval", type=float, default=3.0, help="Số giây kiểm tra lại file")
    args = parser.parse_args()

    txt_path = Path(args.txt)
    photos_dir = Path(args.photos)
    state_file = txt_path.parent / ".synced_accounts.txt"

    # Fallback to local tool directory
    if not txt_path.exists():
        alt_txt = Path(r"D:\tools\HacTayDu_Web_Auto_v79\DAN_NICK_TRUNG_TUONG.txt")
        if alt_txt.exists():
            txt_path = alt_txt
            photos_dir = Path(r"D:\tools\HacTayDu_Web_Auto_v79\anh_nick_trung")
            state_file = txt_path.parent / ".synced_accounts.txt"

    print("==================================================")
    print("🤖 HẮC TÂY DU 24/7 AUTO-SYNC WATCHER -> TELEGRAM BOT")
    print("==================================================")
    print(f"📄 Theo dõi file : {txt_path.resolve()}")
    print(f"📸 Thư mục ảnh   : {photos_dir.resolve()}")
    print(f"🌐 Webhook Bot   : {args.url}")
    print(f"⏱️ Chu kỳ quét   : {args.poll_interval}s")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    synced_accounts: set[str] = set()
    if state_file.exists():
        try:
            synced_accounts = set(state_file.read_text(encoding="utf-8").splitlines())
            print(f"ℹ️ Đã load {len(synced_accounts)} nick đã sync trước đó.")
        except Exception:
            pass

    print("🟢 Đang chạy giám sát 24/7... (Cứ có nick mới là tự động sync sang Bot)")

    while True:
        try:
            if txt_path.exists():
                lines = txt_path.read_text(encoding="utf-8", errors="ignore").splitlines()
                for line in lines:
                    line_str = line.strip()
                    if not line_str or "|" not in line_str:
                        continue
                    parts = [p.strip() for p in line_str.split("|")]
                    if len(parts) < 4:
                        continue

                    acc = parts[0]
                    pwd = parts[1]
                    server = parts[2]
                    tuong = parts[3]
                    so_sao = parts[4] if len(parts) > 4 else "5★"
                    danh_sach = parts[5] if len(parts) > 5 else ""
                    funtap_id = parts[6] if len(parts) > 6 else ""
                    photo_name = Path(parts[7]).name if len(parts) > 7 else f"{acc}.png"

                    if acc in synced_accounts:
                        continue

                    # New account detected!
                    print(f"\n⚡ Phát hiện nick mới: {acc} | {tuong} ({so_sao}) | {server}")

                    # Find photo and encode base64
                    photo_b64 = None
                    photo_candidate = photos_dir / photo_name
                    if photo_name == "-" or not photo_candidate.exists():
                        # Tool auto may take 20-40 seconds to auto-run tutorial to Lv.5+ and capture screenshot
                        print(f"   ⏳ Đang chờ tool chạy tân thủ Lv.5+ & lưu xong ảnh chụp cho {acc} (tối đa 45s)...")
                        for _ in range(45):
                            time.sleep(1.0)
                            matches = list(photos_dir.glob(f"*{acc}*.png"))
                            if matches:
                                photo_candidate = matches[0]
                                photo_name = photo_candidate.name
                                break

                    if not (photo_candidate.exists() and photo_candidate.is_file()):
                        print(f"   ⏳ Chưa có ảnh chụp cho {acc}, tạm hoãn để chờ tool lưu xong ảnh rồi mới bơm sang Bot...")
                        continue

                    try:
                        photo_b64 = base64.b64encode(photo_candidate.read_bytes()).decode("ascii")
                        print(f"   📸 Đã đính kèm ảnh: {photo_candidate.name}")
                    except Exception as e:
                        print(f"   ⚠️ Lỗi đọc ảnh: {e}")
                        continue

                    # Send payload to Webhook
                    payload = {
                        "machine_id": "auto_watcher",
                        "account": acc,
                        "password": pwd,
                        "funtap_id": funtap_id,
                        "server_id": 0,
                        "server_name": server,
                        "jackpot_type": tuong,
                        "total_5star": 5,
                        "target_heroes": [tuong],
                        "heroes_5star": [x.strip() for x in danh_sach.split(",") if x.strip()],
                        "screenshot_path": str(photo_candidate) if photo_candidate.exists() else "",
                        "screenshot_base64": photo_b64,
                        "screenshot_filename": photo_candidate.name if photo_candidate.exists() else photo_name,
                        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
                    }

                    try:
                        data_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                        headers = {
                            "Content-Type": "application/json; charset=utf-8",
                            "X-Webhook-Secret": args.secret,
                            "Authorization": f"Bearer {args.secret}",
                        }
                        req = urllib.request.Request(args.url, data=data_bytes, headers=headers, method="POST")
                        with urllib.request.urlopen(req, timeout=10) as resp:
                            res_json = json.loads(resp.read().decode("utf-8"))
                            status_code = resp.status
                            print(f"   ✅ [BƠM THÀNH CÔNG] Bot phản hồi: {res_json.get('status')} (HTTP {status_code})")
                    except Exception as err:
                        print(f"   ❌ Lỗi khi gửi Webhook lên Bot: {err}")
                        continue

                    # Mark synced
                    synced_accounts.add(acc)
                    try:
                        with open(state_file, "a", encoding="utf-8") as f:
                            f.write(f"{acc}\n")
                    except Exception:
                        pass

        except Exception as exc:
            print(f"⚠️ Lỗi vòng lặp giám sát: {exc}")

        time.sleep(args.poll_interval)


if __name__ == "__main__":
    main()
