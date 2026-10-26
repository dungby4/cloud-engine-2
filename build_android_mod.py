#!/usr/bin/env python3
"""build_android_mod.py - Tự động tạo bản Mod APK Hắc Tây Du cho Android.

Quy trình tự động:
1. Tìm file APK gốc (từ file đầu vào, thư mục hiện tại, hoặc tự pull từ điện thoại qua ADB).
2. Tráo file js/game.js đã mod (x5 tốc độ, 1-frame skip, skip tân thủ, D-AUTO menu).
3. Tự động Zipalign và Ký bằng apksigner của Android SDK.
4. Tự động cài đặt lên điện thoại nếu có kết nối ADB.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

try:
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if sys.stderr and hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

# Paths to tools
ANDROID_SDK = Path(r"C:\Users\truon\AppData\Local\Android\Sdk")
BUILD_TOOLS_DIR = ANDROID_SDK / "build-tools"
PLATFORM_TOOLS_DIR = ANDROID_SDK / "platform-tools"
ADB_EXE = PLATFORM_TOOLS_DIR / "adb.exe"

def find_latest_build_tool(tool_name: str) -> Path | None:
    if not BUILD_TOOLS_DIR.exists():
        return None
    tools = sorted(BUILD_TOOLS_DIR.glob(f"*/{tool_name}"), reverse=True)
    return tools[0] if tools else None

def get_apksigner() -> Path | None:
    return find_latest_build_tool("apksigner.bat")

def get_zipalign() -> Path | None:
    return find_latest_build_tool("zipalign.exe")

def ensure_debug_keystore() -> Path:
    keystore_path = Path("debug.keystore")
    if keystore_path.exists():
        return keystore_path
    print("🔑 Đang tạo debug.keystore tự động...")
    cmd = [
        "keytool", "-genkeypair", "-v",
        "-keystore", str(keystore_path),
        "-alias", "androiddebugkey",
        "-keyalg", "RSA", "-keysize", "2048",
        "-validity", "10000",
        "-storepass", "android", "-keypass", "android",
        "-dname", "CN=Android Debug,O=Android,C=US"
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return keystore_path

def pull_apk_from_adb() -> Path | None:
    if not ADB_EXE.exists():
        return None
    
    packages = ["vn.ftg.hactaydu", "com.funtap.hactaydu"]
    for pkg in packages:
        print(f"🔍 Đang kiểm tra gói {pkg} trên điện thoại qua ADB...")
        res = subprocess.run([str(ADB_EXE), "shell", "pm", "path", pkg], capture_output=True, text=True)
        if res.returncode == 0 and "package:" in res.stdout:
            remote_path = res.stdout.strip().split("package:")[1].splitlines()[0].strip()
            local_apk = Path(f"{pkg}_base.apk")
            print(f"📥 Đang kéo APK gốc từ điện thoại ({remote_path})...")
            pull_res = subprocess.run([str(ADB_EXE), "pull", remote_path, str(local_apk)], capture_output=True, text=True)
            if pull_res.returncode == 0 and local_apk.exists():
                print(f"✅ Đã kéo APK gốc thành công: {local_apk} ({local_apk.stat().st_size / 1024 / 1024:.2f} MB)")
                return local_apk
    return None

def patch_apk(base_apk: Path, modded_js: Path, output_apk: Path):
    print(f"\n📦 BẮT ĐẦU PATCH FILE APK:")
    print(f"   • APK gốc: {base_apk}")
    print(f"   • File JS Mod: {modded_js}")
    
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_dir_p = Path(tmp_dir)
        unaligned_apk = tmp_dir_p / "unaligned.apk"
        
        # 1. Copy và thay thế file js trong APK (APK là file zip)
        print("⚡ [1/4] Thay thế mã nguồn game.js đã mod vào APK...")
        target_internal_paths = []
        with zipfile.ZipFile(base_apk, 'r') as zin:
            for item in zin.namelist():
                if item.endswith("game.js"):
                    target_internal_paths.append(item)
                    print(f"   📍 Tìm thấy game.js tại: {item}")
        
        if not target_internal_paths:
            # Mặc định thêm vào assets/shjAssets/js/game.js và assets/js/game.js
            target_internal_paths = ["assets/shjAssets/js/game.js", "assets/js/game.js"]
            print("   ⚠️ Không tìm thấy game.js có sẵn, sẽ thêm vào thư mục assets...")

        with zipfile.ZipFile(base_apk, 'r') as zin, zipfile.ZipFile(unaligned_apk, 'w', zipfile.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                if item.filename in target_internal_paths or item.filename.startswith("META-INF/"):
                    # Bỏ qua chữ ký cũ META-INF để ký lại
                    continue
                zout.writestr(item, zin.read(item.filename))
            
            # Ghi đè file mod
            with open(modded_js, 'rb') as f:
                mod_data = f.read()
            for p in target_internal_paths:
                zout.writestr(p, mod_data)
                print(f"   ✅ Đã chèn mã Mod vào: {p}")

        # 2. Zipalign
        zipalign_bin = get_zipalign()
        aligned_apk = tmp_dir_p / "aligned.apk"
        if zipalign_bin and zipalign_bin.exists():
            print(f"⚙️  [2/4] Zipalign căn chỉnh APK (4-byte alignment)...")
            cmd_align = [str(zipalign_bin), "-p", "-f", "4", str(unaligned_apk), str(aligned_apk)]
            subprocess.run(cmd_align, check=True, capture_output=True)
        else:
            print("⚠️ Không có zipalign, dùng file unaligned...")
            aligned_apk = unaligned_apk

        # 3. Ký APK bằng apksigner
        apksigner_bin = get_apksigner()
        keystore_path = ensure_debug_keystore()
        if apksigner_bin and apksigner_bin.exists():
            print(f"✍️  [3/4] Ký số APK bằng apksigner (V1 + V2 + V3 signature)...")
            if output_apk.exists():
                output_apk.unlink()
            shutil.copy(aligned_apk, output_apk)
            cmd_sign = [
                str(apksigner_bin), "sign",
                "--ks", str(keystore_path),
                "--ks-key-alias", "androiddebugkey",
                "--ks-pass", "pass:android",
                "--key-pass", "pass:android",
                str(output_apk)
            ]
            res = subprocess.run(cmd_sign, capture_output=True, text=True)
            if res.returncode != 0:
                print(f"❌ Lỗi ký APK: {res.stderr}")
                sys.exit(1)
        else:
            print("✍️  [3/4] Ký bằng jarsigner...")
            shutil.copy(aligned_apk, output_apk)
            cmd_sign = [
                "jarsigner", "-verbose",
                "-sigalg", "SHA256withRSA",
                "-digestalg", "SHA-256",
                "-keystore", str(keystore_path),
                "-storepass", "android",
                "-keypass", "android",
                str(output_apk), "androiddebugkey"
            ]
            subprocess.run(cmd_sign, check=True, capture_output=True)

        print(f"\n🎉 [4/4] TẠO BẢN MOD ANDROID THÀNH CÔNG!")
        print(f"📁 File APK xuất xưởng: {output_apk.resolve()}")
        print(f"📊 Kích thước: {output_apk.stat().st_size / 1024 / 1024:.2f} MB")

        # 4. Tự động cài đặt lên điện thoại nếu ADB kết nối
        if ADB_EXE.exists():
            devices_res = subprocess.run([str(ADB_EXE), "devices"], capture_output=True, text=True)
            if "\tdevice" in devices_res.stdout:
                print("\n📱 PHÁT HIỆN ĐIỆN THOẠI ANDROID ĐÃ SẴN SÀNG! ĐANG TỰ ĐỘNG CÀI ĐẶT...")
                install_cmd = [str(ADB_EXE), "install", "-r", "-d", str(output_apk)]
                inst_res = subprocess.run(install_cmd, capture_output=True, text=True)
                print(inst_res.stdout)
                if "Success" in inst_res.stdout:
                    print("✅ ĐÃ CÀI ĐẶT BẢN MOD VÀO ĐIỆN THOẠI THÀNH CÔNG! BẠN CÓ THỂ MỞ GAME ĐỂ CHƠI!")
                else:
                    print(f"⚠️ Kết quả cài đặt: {inst_res.stdout} {inst_res.stderr}")
            else:
                print("\n💡 Ghi chú: Điện thoại chưa cấp quyền USB Debugging ('unauthorized').")
                print("   Hãy nhìn vào màn hình điện thoại, chọn 'Cho phép gỡ lỗi USB' (Allow USB Debugging) rồi chạy lại lệnh.")

def main():
    parser = argparse.ArgumentParser(description="Build Android Mod APK cho Hắc Tây Du")
    parser.add_argument("--apk", help="Đường dẫn file APK gốc (nếu không có sẽ tự tìm hoặc kéo từ điện thoại)")
    parser.add_argument("--js", default="js/game.js", help="Đường dẫn file game.js đã mod")
    parser.add_argument("--output", default="HacTayDu_Auto_Mod.apk", help="Tên file APK đầu ra")
    args = parser.parse_args()

    base_apk = None
    if args.apk:
        base_apk = Path(args.apk)
    else:
        # Tìm trong thư mục
        apks = list(Path(".").glob("*.apk"))
        apks = [a for a in apks if "mod" not in a.name.lower()]
        if apks:
            base_apk = apks[0]
            print(f"🔍 Tìm thấy file APK có sẵn: {base_apk}")
        else:
            base_apk = pull_apk_from_adb()

    if not base_apk or not base_apk.exists():
        print("\n❌ CHƯA CÓ FILE APK GỐC ĐỂ PATCH!")
        print("👉 HÃY CHỌN 1 TRONG 2 CÁCH SAU:")
        print("   Cách 1: Nhìn vào màn hình điện thoại đang cắm cáp USB, bấm 'CHO PHÉP' (Allow USB Debugging)")
        print("           để script tự động kéo game Hắc Tây Du từ điện thoại sang patch.")
        print("   Cách 2: Tải file APK gốc của game về để vào thư mục này, rồi chạy lại:")
        print("           python build_android_mod.py --apk <ten_file.apk>")
        sys.exit(1)

    mod_js = Path(args.js)
    if not mod_js.exists():
        print(f"❌ Không tìm thấy file {mod_js}")
        sys.exit(1)

    patch_apk(base_apk, mod_js, Path(args.output))

if __name__ == "__main__":
    main()
