"""Auto-Refill Daemon for Hac Tay Du Account Hub with Duty-Cycle (Run 60m / Rest 30m).
Monitors the Account Hub queue. In the 60-minute Active window, triggers 20 parallel GitHub Actions
runners whenever queue drops below threshold. In the 30-minute Rest window, completely stops
calling Funtap registration to let IPs cool down and avoid anti-bot suspicion.
"""

import json
import os
import ssl
import subprocess
import sys
import time
import urllib.request

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HUB_STATS_URL = "https://152-69-209-107.sslip.io/api/accounts/stats"
FEEDER_REPO = "truongqv12/htd-account-feeder"
THRESHOLD = 550
COUNT_PER_JOB = 20  # 20 workers * 20 = 400 accounts per fast 1.5-min wave (auto-rotates Azure IP before rate limit)

# Duy trì bơm nick liên tục 24/7 trên repo public mỗi khi kho xuống dưới THRESHOLD
CYCLE_RUN_MINUTES = 60
CYCLE_REST_MINUTES = 0

def get_queue_stats():
    try:
        ctx = ssl._create_unverified_context()
        req = urllib.request.Request(HUB_STATS_URL, headers={"User-Agent": "AutoRefill/1.0"})
        with urllib.request.urlopen(req, timeout=5, context=ctx) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("queue_size", -1), data.get("total_pushed", 0), data.get("total_popped", 0)
    except Exception:
        return -1, 0, 0

def is_gh_running(q_size=999, last_trigger_ts=0.0):
    # Nếu lần kích hoạt gần nhất đã qua > 105s mà kho dưới 280 nick,
    # cho phép kích hoạt gối đầu đợt mới ngay lập tức (không đợi 1 runner chậm kéo dài)
    if q_size < 280 and (time.time() - last_trigger_ts) > 105.0:
        return False
    try:
        res = subprocess.run(
            ["gh", "run", "list", "--repo", FEEDER_REPO, "--workflow=reg_rotator.yml", "--limit", "1", "--json", "status"],
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

def trigger_gh_burst(count_per_job=80):
    try:
        res = subprocess.run(
            ["gh", "workflow", "run", "reg_rotator.yml", "--repo", FEEDER_REPO, "-f", f"count_per_job={count_per_job}"],
            capture_output=True,
            text=True,
            check=True
        )
        return True
    except Exception as e:
        print(f"[Auto-Refill] Lỗi kích hoạt GitHub Actions: {e}")
        return False

def main():
    print("=" * 75)
    print("🤖 HẮC TÂY DU — TỰ ĐỘNG BƠM NICK CHU KỲ AN TOÀN (RUN 60M / REST 30M)")
    print(f"⏱️ Cơ chế chu kỳ    : Chạy 60 phút ➔ Nghỉ 30 phút (Chống soi IP / Giữ an toàn Funtap)")
    print(f"🎯 Mục tiêu duy trì : Tối thiểu {THRESHOLD} nick tươi luôn sẵn sàng trong Hub")
    print(f"⚡ Quy mô mỗi đợt   : 20 máy chủ Azure độc lập × {COUNT_PER_JOB} nick = 1,600 nick/đợt")
    print(f"🌐 Hub giám sát     : {HUB_STATS_URL}")
    print("=" * 75, flush=True)

    cycle_start = time.time()
    last_trigger_ts = time.time()

    while True:
        try:
            elapsed_min = (time.time() - cycle_start) / 60.0

            # Hết 90 phút chu kỳ -> Bắt đầu chu kỳ mới
            if elapsed_min >= (CYCLE_RUN_MINUTES + CYCLE_REST_MINUTES):
                cycle_start = time.time()
                elapsed_min = 0.0
                print(f"\n🔔 [{time.strftime('%H:%M:%S')}] KẾT THÚC 30 PHÚT NGHỈ XẢ HƠI => BẮT ĐẦU CHU KỲ BƠM NICK 60 PHÚT MỚI!\n", flush=True)

            is_resting = elapsed_min >= CYCLE_RUN_MINUTES
            rest_remaining = max(0, int((CYCLE_RUN_MINUTES + CYCLE_REST_MINUTES) - elapsed_min))
            run_remaining = max(0, int(CYCLE_RUN_MINUTES - elapsed_min))

            q_size, pushed, popped = get_queue_stats()
            t_now = time.strftime("%H:%M:%S")

            if is_resting:
                print(f"[{t_now}] ☕ [ĐANG NGHỈ XẢ HƠI - Còn {rest_remaining}p] Tạm dừng kích hoạt reg nick mới để Funtap xả nhiệt IP & chống quét bot | Kho hiện tại: {q_size} nick (Đã bốc: {popped}/{pushed})", flush=True)
            elif q_size < 0:
                print(f"[{t_now}] ⚠️ Không thể kết nối tới Hub để kiểm tra số dư...", flush=True)
            elif q_size < THRESHOLD:
                running = is_gh_running(q_size, last_trigger_ts)
                if not running:
                    print(f"\n[{t_now}] ⚡ [Chu kỳ Bơm - Còn {run_remaining}p] Hàng đợi còn {q_size} nick (< {THRESHOLD})! Kích hoạt 20 runner Azure bơm thêm {COUNT_PER_JOB*20} nick mới...", flush=True)
                    if trigger_gh_burst(COUNT_PER_JOB):
                        last_trigger_ts = time.time()
                        print(f"[{t_now}] 🚀 Đã gửi lệnh thành công! 20 máy chủ đang tải & đẩy nick...", flush=True)
                else:
                    print(f"[{t_now}] ⏳ [Chu kỳ Bơm - Còn {run_remaining}p] Hàng đợi {q_size} nick | 20 runner Azure đang bơm dồn dập... (Đã đẩy: {pushed} | Đã bốc: {popped})", flush=True)
            else:
                print(f"[{t_now}] 🟢 [Chu kỳ Bơm - Còn {run_remaining}p] Hàng đợi dồi dào: {q_size} nick tươi sẵn sàng (Đã cày: {popped}/{pushed} nick)", flush=True)

        except Exception as ex:
            print(f"[Auto-Refill] Lỗi vòng lặp: {ex}", flush=True)

        time.sleep(15.0)

if __name__ == "__main__":
    main()
