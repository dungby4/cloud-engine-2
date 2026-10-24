"""Auto-Refill Daemon for Hac Tay Du Account Hub.
Monitors the Account Hub queue. Whenever queue_size drops below threshold,
automatically triggers 20 parallel GitHub Actions runners (Azure VMs) to produce 800 fresh accounts.
Ensures zero downtime and continuous supply for all rolling machines.
"""

import json
import os
import subprocess
import sys
import time
import urllib.request

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HUB_STATS_URL = "https://152-69-209-107.sslip.io/api/accounts/stats"
THRESHOLD = 180
COUNT_PER_JOB = 40  # 20 workers * 40 = 800 accounts per run

def get_queue_stats():
    try:
        req = urllib.request.Request(HUB_STATS_URL, headers={"User-Agent": "AutoRefill/1.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("queue_size", -1), data.get("total_pushed", 0), data.get("total_popped", 0)
    except Exception as e:
        return -1, 0, 0

def is_gh_running():
    try:
        res = subprocess.run(
            ["gh", "run", "list", "--workflow=reg_rotator.yml", "--limit", "1", "--json", "status"],
            capture_output=True,
            text=True,
            check=True
        )
        runs = json.loads(res.stdout)
        if runs and runs[0].get("status") in ("in_progress", "queued", "waiting", "pending"):
            return True
    except Exception:
        pass
    return False

def trigger_gh_burst(count_per_job=40):
    try:
        res = subprocess.run(
            ["gh", "workflow", "run", "reg_rotator.yml", "-f", f"count_per_job={count_per_job}"],
            capture_output=True,
            text=True,
            check=True
        )
        return True
    except Exception as e:
        print(f"[Auto-Refill] Lỗi kích hoạt GitHub Actions: {e}")
        return False

def main():
    print("=" * 65)
    print("🤖 HẮC TÂY DU — TỰ ĐỘNG BƠM NICK TẬP TRUNG 24/7 (AUTO-REFILL DAEMON)")
    print(f"🎯 Mục tiêu duy trì  : Tối thiểu {THRESHOLD} nick tươi luôn sẵn sàng trong Hub")
    print(f"⚡ Quy mô mỗi đợt   : 20 máy chủ Azure độc lập × {COUNT_PER_JOB} nick = 800 nick/đợt")
    print(f"🌐 Hub giám sát      : {HUB_STATS_URL}")
    print("=" * 65, flush=True)

    while True:
        try:
            q_size, pushed, popped = get_queue_stats()
            t_now = time.strftime("%H:%M:%S")

            if q_size < 0:
                print(f"[{t_now}] ⚠️ Không thể kết nối tới Hub để kiểm tra số dư...", flush=True)
            elif q_size < THRESHOLD:
                running = is_gh_running()
                if not running:
                    print(f"\n[{t_now}] ⚡ Hàng đợi còn {q_size} nick (< {THRESHOLD})! Kích hoạt 20 runner Azure bơm thêm 800 nick mới...", flush=True)
                    if trigger_gh_burst(COUNT_PER_JOB):
                        print(f"[{t_now}] 🚀 Đã gửi lệnh thành công! 20 máy chủ đang tải & đẩy nick...", flush=True)
                else:
                    print(f"[{t_now}] ⏳ Hàng đợi còn {q_size} nick | 20 runner Azure đang chạy ngầm bơm tiếp... (Đã đẩy: {pushed} | Đã bốc: {popped})", flush=True)
            else:
                print(f"[{t_now}] 🟢 Hàng đợi dồi dào: {q_size} nick tươi sẵn sàng (Đã cày: {popped}/{pushed} nick)", flush=True)

        except Exception as ex:
            print(f"[Auto-Refill] Lỗi vòng lặp: {ex}", flush=True)

        time.sleep(15.0)

if __name__ == "__main__":
    main()
