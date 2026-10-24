"""Lightweight, thread-safe Account Buffer Hub for Hac Tay Du.
Maintains a FIFO queue of fresh registered accounts.
Provides endpoints for GitHub Actions / external generators to push accounts,
and for reroll workers (local machine + VPS) to pop fresh accounts in 0ms.
"""

import json
import os
import sys
import time
import threading
from collections import deque
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SECRET_KEY = "d57be08c4bbbc9c7feda86285611ee41fc8016d4f1bf4a1a7a60502d123b0ab3"
DATA_FILE = "fresh_account_pool.jsonl"
HISTORY_FILE = "popped_account_history.jsonl"

class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True

class AccountQueue:
    def __init__(self):
        self.lock = threading.Lock()
        self.queue = deque()
        self.seen_usernames = set()
        self.total_pushed = 0
        self.total_popped = 0
        self.start_time = time.time()
        self.load_persisted()

    def load_persisted(self):
        # Load existing seen usernames to avoid duplicates
        if os.path.exists(HISTORY_FILE):
            try:
                with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            data = json.loads(line)
                            u = data.get("username") or data.get("u")
                            if u:
                                self.seen_usernames.add(u)
            except Exception as e:
                print(f"[Hub] Error loading history: {e}")

        if os.path.exists(DATA_FILE):
            try:
                count = 0
                with open(DATA_FILE, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            acc = json.loads(line)
                            u = acc.get("username") or acc.get("u")
                            if u and u not in self.seen_usernames:
                                self.queue.append(acc)
                                self.seen_usernames.add(u)
                                count += 1
                self.total_pushed += count
                print(f"[Hub] Loaded {count} fresh accounts from {DATA_FILE}")
            except Exception as e:
                print(f"[Hub] Error loading pool: {e}")

    def push(self, accounts):
        added = 0
        with self.lock:
            with open(DATA_FILE, "a", encoding="utf-8") as f:
                for raw in accounts:
                    u = raw.get("username") or raw.get("u")
                    p = raw.get("password") or raw.get("p")
                    aid = str(raw.get("accountId") or raw.get("account_id") or raw.get("id") or "")
                    tok = raw.get("accessToken") or raw.get("access_token") or "r"
                    fid = str(raw.get("funId") or raw.get("fun_id") or "")

                    if not u or not aid or u in self.seen_usernames:
                        continue

                    acc_obj = {
                        "username": u,
                        "password": p,
                        "accountId": aid,
                        "accessToken": tok,
                        "funId": fid,
                        "added_at": time.time()
                    }
                    self.queue.append(acc_obj)
                    self.seen_usernames.add(u)
                    self.total_pushed += 1
                    added += 1
                    f.write(json.dumps(acc_obj) + "\n")
                    f.flush()
        return added, len(self.queue)

    def pop(self, count=1):
        popped = []
        with self.lock:
            for _ in range(count):
                if not self.queue:
                    break
                acc = self.queue.popleft()
                popped.append(acc)
                self.total_popped += 1

            if popped:
                # Log to history
                with open(HISTORY_FILE, "a", encoding="utf-8") as f:
                    for acc in popped:
                        record = dict(acc)
                        record["popped_at"] = time.time()
                        f.write(json.dumps(record) + "\n")
                # Rewrite DATA_FILE with remaining
                with open(DATA_FILE, "w", encoding="utf-8") as f:
                    for acc in self.queue:
                        f.write(json.dumps(acc) + "\n")

        return popped, len(self.queue)

    def stats(self):
        with self.lock:
            return {
                "ok": True,
                "queue_size": len(self.queue),
                "total_pushed": self.total_pushed,
                "total_popped": self.total_popped,
                "uptime_seconds": int(time.time() - self.start_time),
                "sample_usernames": [item["username"] for item in list(self.queue)[:3]]
            }

HUB_QUEUE = AccountQueue()

class HubHandler(BaseHTTPRequestHandler):
    def send_json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        # Suppress noisy access logs except errors
        pass

    def check_auth(self):
        secret = self.headers.get("X-Hub-Secret") or self.headers.get("X-Secret")
        if not secret:
            # Check query param
            if "secret=" in self.path:
                try:
                    secret = self.path.split("secret=")[1].split("&")[0]
                except Exception:
                    pass
        return secret == SECRET_KEY

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/api/accounts/stats" or path == "/stats":
            self.send_json(200, HUB_QUEUE.stats())
        elif path == "/api/accounts/pop":
            # Count param
            cnt = 1
            if "count=" in self.path:
                try:
                    cnt = int(self.path.split("count=")[1].split("&")[0])
                except Exception:
                    cnt = 1
            popped, remaining = HUB_QUEUE.pop(cnt)
            if popped:
                if cnt == 1:
                    self.send_json(200, {"ok": True, "account": popped[0], "remaining": remaining})
                else:
                    self.send_json(200, {"ok": True, "accounts": popped, "remaining": remaining})
            else:
                self.send_json(200, {"ok": False, "empty": True, "remaining": 0, "message": "Queue is currently empty"})
        elif path == "/api/accounts/health" or path == "/health":
            self.send_json(200, {"status": "ok", "time": time.time()})
        else:
            self.send_json(404, {"ok": False, "error": "Endpoint not found"})

    def do_POST(self):
        path = self.path.split("?")[0]
        if path == "/api/accounts/push":
            if not self.check_auth():
                self.send_json(401, {"ok": False, "error": "Unauthorized: invalid secret key"})
                return

            try:
                length = int(self.headers.get("Content-Length", 0))
                raw_body = self.rfile.read(length)
                data = json.loads(raw_body.decode("utf-8"))
            except Exception as e:
                self.send_json(400, {"ok": False, "error": f"Invalid JSON payload: {e}"})
                return

            acc_list = []
            if isinstance(data, list):
                acc_list = data
            elif isinstance(data, dict):
                if "accounts" in data and isinstance(data["accounts"], list):
                    acc_list = data["accounts"]
                else:
                    acc_list = [data]

            added, remaining = HUB_QUEUE.push(acc_list)
            print(f"[Hub] Received {len(acc_list)} accounts -> Added {added} fresh | Total in queue: {remaining}")
            self.send_json(200, {"ok": True, "added": added, "total_queue": remaining})
        else:
            self.send_json(404, {"ok": False, "error": "Endpoint not found"})

def run_server(port=8090):
    server = ThreadingHTTPServer(("0.0.0.0", port), HubHandler)
    print(f"[Account Hub] Running on 0.0.0.0:{port}...")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("[Hub] Stopping...")
        server.server_close()

if __name__ == "__main__":
    p = 8090
    if len(sys.argv) > 1 and sys.argv[1].isdigit():
        p = int(sys.argv[1])
    run_server(p)
