"""Công cụ tra cứu tướng trong lịch sử quay (LICH_SU_QUAY.json).

Cách dùng:
  python tim_tuong.py                           -> Xem thống kê tổng quan lịch sử quay
  python tim_tuong.py "Na Tra"                 -> Tìm tất cả nick có Na Tra
  python tim_tuong.py "Na Tra" 2               -> Tìm tất cả nick có >= 2 Na Tra
  python tim_tuong.py "Dương Tiễn" 1 --sid 76   -> Tìm nick có Dương Tiễn trên Server S76
  python tim_tuong.py --top                    -> Xem các nick có nhiều tướng 5★ nhất
"""

import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path


def main():
    try:
        if sys.stdout and hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    parser = argparse.ArgumentParser(description="Tra cứu tướng trong lịch sử quay Hắc Tây Du")
    parser.add_argument("hero", nargs="?", default="", help="Tên tướng cần tìm (VD: 'Na Tra', 'Dương Tiễn', 'Đường Tam Tạng')")
    parser.add_argument("min_copies", nargs="?", type=int, default=1, help="Số lượng tướng tối thiểu (mặc định: 1)")
    parser.add_argument("--sid", type=str, default="", help="Lọc theo mã Server ID hoặc số Server (VD: '76' hoặc '610076')")
    parser.add_argument("--top", action="store_true", help="Hiển thị các nick nhiều tướng 5★ nhất")
    parser.add_argument("--file", default="LICH_SU_QUAY.json", help="Đường dẫn file lịch sử")
    args = parser.parse_args()

    hist_file = Path(args.file)
    if not hist_file.exists():
        alt = Path(__file__).parent / "LICH_SU_QUAY.json"
        if alt.exists():
            hist_file = alt

    if not hist_file.exists() or hist_file.stat().st_size == 0:
        print("⚠️ Chưa có file lịch sử quay 'LICH_SU_QUAY.json' hoặc file đang trống!")
        print("👉 Lịch sử sẽ tự động được ghi nhận khi tool quay tướng chạy.")
        return

    records = []
    with open(hist_file, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line_str = line.strip().rstrip(",")
            if not line_str or line_str in ("[", "]"):
                continue
            try:
                records.append(json.loads(line_str))
            except Exception:
                pass

    if not records:
        print("ℹ️ File lịch sử chưa có bản ghi nào hợp lệ.")
        return

    print("=" * 96)
    print(f"📊 NHẬT KÝ LỊCH SỬ QUAY TƯỚNG HẮC TÂY DU (TỔNG: {len(records)} NICK ĐÃ QUAY)")
    print("=" * 96)

    # 1. Thống kê tổng quan nếu không truyền tên tướng
    if not args.hero and not args.top:
        server_counts = Counter(r.get("server") or f"SID {r.get('sid')}" for r in records)
        dt_total = sum(int(r.get("dt") or 0) for r in records)
        tnk_total = sum(int(r.get("tnk") or 0) for r in records)
        nt_total = sum(int(r.get("nt") or 0) for r in records)
        lt_total = sum(int(r.get("lt") or 0) for r in records)
        dtt_total = sum(int(r.get("dtt") or 0) for r in records)
        jackpot_cnt = sum(1 for r in records if r.get("jackpot"))

        print(f"🔥 Số nick nổ 2x Jackpot (DT / TNK / Na Tra / Lý Tịnh / Đường Tăng): {jackpot_cnt} nick")
        print(f"⚔️ Tổng số Dương Tiễn quay ra : {dt_total}")
        print(f"🐒 Tổng số Ngộ Không quay ra  : {tnk_total}")
        print(f"🔥 Tổng số Na Tra quay ra     : {nt_total}")
        print(f"🗼 Tổng số Lý Tịnh quay ra   : {lt_total}")
        print(f"📿 Tổng số Đường Tăng quay ra : {dtt_total}")
        print("\n🌐 Phân bố theo Server:")
        for srv, cnt in server_counts.most_common(5):
            print(f"   • {srv}: {cnt} nick")
        print("\n👉 Gợi ý tìm kiếm:")
        print("   python tim_tuong.py \"Na Tra\" 2              (Tìm nick có >= 2 Na Tra)")
        print("   python tim_tuong.py \"Lý Tịnh\" 2             (Tìm nick có >= 2 Lý Tịnh)")
        print("   python tim_tuong.py \"Đường Tam Tạng\" 2       (Tìm nick có >= 2 Đường Tam Tạng)")
        print("   python tim_tuong.py \"Dương Tiễn\" 1 --sid 76  (Tìm nick có Dương Tiễn trên S76)")
        print("=" * 96)
        return

    # 2. Lọc theo Server
    filtered = records
    if args.sid:
        sid_clean = args.sid.strip()
        filtered = [
            r for r in filtered
            if sid_clean in str(r.get("sid", "")) or sid_clean in str(r.get("server", ""))
        ]

    # 3. Lọc theo Top tướng 5★
    if args.top:
        sorted_top = sorted(filtered, key=lambda x: int(x.get("total_5s") or 0), reverse=True)[:20]
        print(f"⭐ TOP 20 NICK NHIỀU TƯỚNG 5★ NHẤT (Tìm thấy {len(sorted_top)} nick):")
        print("-" * 96)
        for idx, r in enumerate(sorted_top, 1):
            h_str = ", ".join(r.get("heroes", []))
            print(f"{idx:02d}. [{r.get('total_5s')}★] TK: {r.get('u')} | MK: {r.get('p')} | {r.get('server')} ({r.get('sid')})")
            print(f"    Tướng: {h_str}")
        print("=" * 96)
        return

    # 4. Tìm kiếm theo tên tướng
    target_hero = args.hero.strip().lower()
    matches = []
    for r in filtered:
        heroes = r.get("heroes") or []
        count_h = sum(1 for h in heroes if target_hero in h.lower())
        # Hoặc đếm qua trường viết tắt
        if "dương tiễn" in target_hero or "duong tien" in target_hero:
            count_h = max(count_h, int(r.get("dt") or 0))
        elif "ngộ không" in target_hero or "ngo khong" in target_hero:
            count_h = max(count_h, int(r.get("tnk") or 0))
        elif "na tra" in target_hero or "natra" in target_hero:
            count_h = max(count_h, int(r.get("nt") or 0))
        elif "lý tịnh" in target_hero or "ly tinh" in target_hero:
            count_h = max(count_h, int(r.get("lt") or 0))
        elif "đường tam tạng" in target_hero or "duong tam tang" in target_hero or "đường tăng" in target_hero or "duong tang" in target_hero:
            count_h = max(count_h, int(r.get("dtt") or 0))

        if count_h >= args.min_copies:
            matches.append((r, count_h))

    matches.sort(key=lambda x: (x[1], int(x[0].get("total_5s") or 0)), reverse=True)

    print(f"🎯 KẾT QUẢ TÌM KIẾM '{args.hero.upper()}' (Số lượng >= {args.min_copies}):")
    print(f"👉 Tìm thấy: {len(matches)} nick phù hợp")
    print("-" * 96)

    if not matches:
        print(f"❌ Không tìm thấy nick nào có >= {args.min_copies} {args.hero}.")
    else:
        for idx, (r, cnt) in enumerate(matches, 1):
            other_heroes = [h for h in r.get("heroes", []) if target_hero not in h.lower()]
            c_other = Counter(other_heroes)
            other_str = " + ".join(f"{k} x{v}" if v > 1 else k for k, v in c_other.items()) or "-"
            print(f"{idx:02d}. [X{cnt} {args.hero.upper()}] TK: {r.get('u')} | MK: {r.get('p')} | {r.get('server')} ({r.get('sid')})")
            print(f"    ⭐ Tổng 5★: {r.get('total_5s')}★ | Phụ: {other_str} | Thời gian: {r.get('time')}")
    print("=" * 96)


if __name__ == "__main__":
    main()
