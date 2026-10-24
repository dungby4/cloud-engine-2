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
    parser.add_argument("--machine", default=None, help="Tên nguồn máy (vd: Máy 2, VPS 1, VPS 2)")
    args = parser.parse_args()

    machine_tag = args.machine
    if not machine_tag:
        try:
            with open("config_local.json", "r", encoding="utf-8") as f:
                cfg_local = json.load(f)
                machine_tag = cfg_local.get("machine_id")
        except Exception:
            pass
    if not machine_tag:
        import socket
        h = socket.gethostname().lower()
        if "vps" in h or "152" in h:
            machine_tag = "VPS 1"
        elif "160" in h:
            machine_tag = "VPS 2"
        else:
            machine_tag = "Máy 2"

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
                    time_col = parts[8] if len(parts) > 8 else ""
                    unconfirmed_str = parts[9] if len(parts) > 9 else ""
                    unconf_list = [c.strip() for c in unconfirmed_str.split(",") if c.strip() and c.strip() != "Đủ code"]
                    codes_stat = f"{28 - len(unconf_list)}/28" if unconf_list else "28/28"

                    if acc in synced_accounts:
                        continue

                    # New account detected!
                    print(f"\n⚡ Phát hiện nick mới: {acc} | {tuong} ({so_sao}) | {server}")
                    if unconf_list:
                        print(f"   ⚠️ Code chưa ăn: {', '.join(unconf_list)}")
                    else:
                        print(f"   ✅ Đã ăn đủ {codes_stat} Giftcode")

                    # Find photo and encode base64
                    photo_b64 = None
                    send_fn = f"{acc}.jpg"
                    jpg_cand = (photos_dir / photo_name).with_suffix(".jpg")
                    png_cand = (photos_dir / photo_name).with_suffix(".png")
                    photo_candidate = jpg_cand if jpg_cand.exists() else png_cand

                    if photo_name == "-" or not photo_candidate.exists():
                        # Tool auto may take 20-40 seconds to auto-run tutorial to Lv.5+ and capture screenshot
                        print(f"   ⏳ Đang chờ tool chạy tân thủ Lv.5+ & lưu xong ảnh chụp cho {acc} (tối đa 45s)...")
                        for _ in range(45):
                            time.sleep(1.0)
                            matches = list(photos_dir.glob(f"*{acc}*.jpg")) + list(photos_dir.glob(f"*{acc}*.png"))
                            if matches:
                                photo_candidate = matches[0]
                                photo_name = photo_candidate.name
                                break

                    if not (photo_candidate.exists() and photo_candidate.is_file()):
                        print(f"   ⏳ Chưa có ảnh chụp cho {acc}, tạm hoãn để chờ tool lưu xong ảnh rồi mới bơm sang Bot...")
                        continue

                    try:
                        from PIL import Image
                        import io
                        with Image.open(photo_candidate) as im:
                            if im.mode in ("RGBA", "LA", "P"):
                                im_rgb = im.convert("RGB")
                            else:
                                im_rgb = im
                            orig_w, orig_h = im_rgb.size
                            max_w = 540
                            if orig_w > max_w:
                                new_h = int(orig_h * (max_w / orig_w))
                                im_resized = im_rgb.resize((max_w, new_h), Image.Resampling.LANCZOS)
                            else:
                                im_resized = im_rgb
                            buf = io.BytesIO()
                            im_resized.save(buf, format="JPEG", quality=72, optimize=True, progressive=True)
                            img_bytes = buf.getvalue()
                        photo_b64 = base64.b64encode(img_bytes).decode("ascii")
                        orig_kb = photo_candidate.stat().st_size // 1024
                        comp_kb = len(img_bytes) // 1024
                        send_fn = f"{photo_candidate.stem}.jpg"
                        print(f"   📸 Đã nén ảnh siêu gọn ({orig_kb} KB ➔ {comp_kb} KB) & đính kèm: {send_fn}")
                        cached_jpg = photos_dir / send_fn
                        if not cached_jpg.exists():
                            try:
                                cached_jpg.write_bytes(img_bytes)
                            except Exception:
                                pass
                    except Exception as e:
                        print(f"   ⚠️ Lỗi nén ảnh với Pillow ({e}), đọc ảnh trực tiếp...")
                        try:
                            raw_b = photo_candidate.read_bytes()
                            photo_b64 = base64.b64encode(raw_b).decode("ascii")
                            send_fn = photo_candidate.name
                            print(f"   📸 Đã đính kèm ảnh hiện có ({len(raw_b)//1024} KB): {send_fn}")
                        except Exception as e2:
                            print(f"   ⚠️ Lỗi đọc ảnh: {e2}")
                            continue

                    # Send payload to Webhook
                    payload = {
                        "machine_id": machine_tag,
                        "account": acc,
                        "password": pwd,
                        "funtap_id": funtap_id,
                        "server_id": 0,
                        "server_name": server,
                        "jackpot_type": tuong,
                        "total_5star": int(so_sao.replace("★", "").strip()) if "★" in so_sao else 5,
                        "target_heroes": [tuong],
                        "heroes_5star": [x.strip() for x in danh_sach.split("+") if x.strip()],
                        "screenshot_path": str(photo_candidate) if photo_candidate.exists() else "",
                        "screenshot_base64": photo_b64,
                        "screenshot_filename": send_fn,
                        "codes_claimed": codes_stat,
                        "unconfirmed_codes": unconf_list,
                        "unconfirmed_codes_str": ", ".join(unconf_list),
                        "notes": f"Code chưa ăn: {', '.join(unconf_list)}" if unconf_list else "Đã ăn đủ 28/28 code",
                        "time": time_col or time.strftime("%Y-%m-%d %H:%M:%S"),
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
                            print(f"   ✅ [BƠM THÀNH CÔNG MÁY {machine_tag.upper()}] Bot phản hồi: {res_json.get('status')} (HTTP {status_code})")
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
