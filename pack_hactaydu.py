"""Tool đóng gói danh sách nick và ảnh chụp Hắc Tây Du thành file zip để nạp vào Bot.

Chạy trực tiếp trên máy treo tool auto reroll (không cần chung mạng LAN với bot).
Sau khi đóng gói, chỉ cần kéo thả file zip vào chat riêng với Bot Telegram!
"""

from __future__ import annotations

import argparse
import sys
import zipfile
from pathlib import Path


def main() -> None:
    try:
        if sys.stdout and hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    parser = argparse.ArgumentParser(description="Đóng gói nick và ảnh Hắc Tây Du gửi Bot Telegram")
    base_dir = Path(__file__).resolve().parent
    parser.add_argument("--txt", default=str(base_dir / "DAN_NICK_TRUNG_TUONG.txt"), help="Đường dẫn file txt nick")
    parser.add_argument("--photos", default=str(base_dir / "anh_nick_trung"), help="Thư mục chứa ảnh chụp")
    parser.add_argument("--output", default="hactaydu_sync.zip", help="Tên file zip đầu ra")
    args = parser.parse_args()

    txt_path = Path(args.txt)
    photos_dir = Path(args.photos)
    out_path = Path(args.output)

    # Fallback to absolute tool path if running elsewhere
    if not txt_path.exists():
        alt_txt = base_dir / "DAN_NICK_TRUNG_TUONG.txt"
        if alt_txt.exists():
            txt_path = alt_txt

    if not photos_dir.exists():
        alt_photos = base_dir / "anh_nick_trung"
        if alt_photos.exists():
            photos_dir = alt_photos

    if not txt_path.exists():
        print(f"❌ Không tìm thấy file nick tại: {txt_path}")
        print("Vui lòng để file script cùng thư mục với DAN_NICK_TRUNG_TUONG.txt")
        sys.exit(1)

    print("==================================================")
    print("📦 ĐÓNG GÓI DỮ LIỆU HẮC TÂY DU NẠP VÀO BOT")
    print("==================================================")
    print(f"📄 File nick: {txt_path}")
    print(f"📸 Thư mục ảnh: {photos_dir}")

    photo_count = 0
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        # Thêm file nick
        zf.write(txt_path, arcname="DAN_NICK_TRUNG_TUONG.txt")
        print("   ✅ Đã thêm DAN_NICK_TRUNG_TUONG.txt vào gói.")

        # Thêm các ảnh chụp
        if photos_dir.exists():
            for p in photos_dir.glob("*.png"):
                zf.write(p, arcname=f"anh_nick_trung/{p.name}")
                photo_count += 1
            print(f"   ✅ Đã thêm {photo_count} ảnh chụp đội hình vào gói.")
        else:
            print("   ⚠️ Không tìm thấy thư mục ảnh, chỉ đóng gói file nick.")

    size_kb = out_path.stat().st_size / 1024
    print("--------------------------------------------------")
    print(f"🎉 ĐÓNG GÓI THÀNH CÔNG: {out_path.resolve()} ({size_kb:.1f} KB)")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("👉 CÁCH NẠP VÀO BOT TELEGRAM:")
    print("   1. Mở Telegram (trên máy tính này hoặc điện thoại).")
    print("   2. Kéo thả file 'hactaydu_sync.zip' vào chat với Bot.")
    print("   3. Bot sẽ tự động giải nén, lưu ảnh và nạp toàn bộ nick mới!")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")


if __name__ == "__main__":
    main()
