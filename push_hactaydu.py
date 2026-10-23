"""Tool to push accounts from HacTayDu tool machine to Telegram Shop Bot on VPS.

Usage:
    python push_hactaydu.py [--server 192.168.1.9] [--txt PATH] [--photos PATH]
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Push Hac Tay Du accounts to Telegram Shop Bot")
    parser.add_argument("--server", default="192.168.1.9", help="Server IP or hostname")
    parser.add_argument("--user", default="truong", help="SSH user")
    parser.add_argument("--txt", default=r"D:\tools\HacTayDu_Web_Auto_v79\DAN_NICK_TRUNG_TUONG.txt", help="Path to DAN_NICK_TRUNG_TUONG.txt")
    parser.add_argument("--photos", default=r"D:\tools\HacTayDu_Web_Auto_v79\anh_nick_trung", help="Path to photos directory")
    parser.add_argument("--no-purge", action="store_true", default=True, help="Do not purge existing stock")
    args = parser.parse_args()

    txt_path = Path(args.txt)
    photos_dir = Path(args.photos)

    # Check local fallback
    if not txt_path.exists():
        fallback_txt = Path("DAN_NICK_TRUNG_TUONG.txt")
        if fallback_txt.exists():
            txt_path = fallback_txt
        else:
            print(f"❌ Khong tim thay file nick tai: {txt_path}")
            sys.exit(1)

    print("==================================================")
    print("🚀 BƠM TÀI KHOẢN HẮC TÂY DU VÀO TELEGRAM SHOP BOT")
    print("==================================================")
    print(f"📄 File nick: {txt_path}")
    print(f"📸 Thu muc anh: {photos_dir}")
    print(f"🖥️ May chu dich: {args.user}@{args.server}")

    # 1. Sync photos via scp
    if photos_dir.exists():
        print("\n📸 [1/3] Dong bo anh chup doi hinh len server...")
        try:
            # Create remote photos dir
            subprocess.run(
                ["ssh", f"{args.user}@{args.server}", "mkdir -p /home/truong/hactaydu_photos"],
                check=True,
                capture_output=True,
            )
            # Copy all png files
            png_files = list(photos_dir.glob("*.png"))
            if png_files:
                scp_cmd = f"scp \"{photos_dir}\\*.png\" {args.user}@{args.server}:/home/truong/hactaydu_photos/"
                subprocess.run(scp_cmd, shell=True, check=True)
                print(f"   ✅ Da sao chep {len(png_files)} anh chup sang server.")

                # Copy to container volume
                subprocess.run(
                    [
                        "ssh",
                        f"{args.user}@{args.server}",
                        "docker exec deploy-app-1 mkdir -p /var/lib/telegram-shop/photos && "
                        "docker cp /home/truong/hactaydu_photos/. deploy-app-1:/var/lib/telegram-shop/photos/",
                    ],
                    check=True,
                    capture_output=True,
                )
                print("   ✅ Da copy anh vao persistent storage cua container.")
            else:
                print("   ⚠️ Khong co file anh .png nao trong thu muc.")
        except Exception as exc:
            print(f"   ⚠️ Dong bo anh that bai: {exc}")
    else:
        print("\n⚠️ Thu muc anh khong ton tai, bo qua buoc dong bo anh.")

    # 2. Copy DAN_NICK_TRUNG_TUONG.txt to server
    print("\n📄 [2/3] Day file nick len server...")
    try:
        subprocess.run(
            ["scp", str(txt_path), f"{args.user}@{args.server}:/home/truong/DAN_NICK_TRUNG_TUONG.txt"],
            check=True,
        )
        subprocess.run(
            [
                "ssh",
                f"{args.user}@{args.server}",
                "docker cp /home/truong/DAN_NICK_TRUNG_TUONG.txt deploy-app-1:/var/lib/telegram-shop/DAN_NICK_TRUNG_TUONG.txt",
            ],
            check=True,
            capture_output=True,
        )
        print("   ✅ Da tai file nick len server thanh cong.")
    except Exception as exc:
        print(f"   ❌ Loi copy file nick: {exc}")
        sys.exit(1)

    # 3. Trigger import on server container
    print("\n🔄 [3/3] Kich hoat nap kho tren container Bot...")
    try:
        res = subprocess.run(
            [
                "ssh",
                f"{args.user}@{args.server}",
                "docker exec deploy-app-1 python -c \""
                "from telegram_shop.ops.sync_hactaydu import sync_hactaydu_data;"
                "res = sync_hactaydu_data(purge_mock=False);"
                "print('KET_QUA:', res)"
                "\"",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        print(res.stdout)
        print("🎉 BƠM TÀI KHOẢN VÀO BOT HOÀN TẤT THÀNH CÔNG!")
    except Exception as exc:
        print(f"❌ Loi chay import: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
