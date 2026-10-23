#!/usr/bin/env python3
"""server_esign.py - D-AUTO PRO MAX v7.9 (Web Client Màn Dọc 9:16 + Login TK Chính Funtap + ESign Server)

Runs on port 8080:
  - /                  : 1-Click ESign & TrollStore Installation Page
  - /play              : Web Client Màn Dọc (9:16 Portrait) + Đăng Nhập TK Chính Funtap & Đầy Đủ 39 Server
  - /play_frame        : Inner Portrait Game Viewport (720x1280 upright)
  - /dashboard         : Live AI Brain Telemetry Monitor
  - /live_ai_plugin.js : Hot-Reloadable D-AUTO v7.9 Plugin
  - /api/funtap_login  : Official Funtap MontarSDK Login (Email/Username/Phone + Password) & Character Finder
  - /api/server_list   : Complete 39-Server Official List (4 Clusters) + Last Played Character Lookup
  - /api/authkey       : Fetches fresh GLOBAL_TIMESTAMP & GLOBAL_AUTHKEY from Funtap igame.php
  - /api/telemetry     : Receives live game state from iPhone / Web
  - /api/state         : Returns current live game state
"""

import asyncio
import http.cookiejar
from http.server import HTTPServer, SimpleHTTPRequestHandler
import json
import os
import random
import re
import socket
from socketserver import ThreadingMixIn
import ssl
import struct
import sys
try:
  sys.stdout.reconfigure(encoding="utf-8", errors="replace")
  sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
  pass
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
try:
  import websockets
except ImportError:
  websockets = None

DIRECTORY = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(DIRECTORY, "config.json")
LOCAL_CONFIG_FILE = os.path.join(DIRECTORY, "config_local.json")

DEFAULT_CONFIG = {
    "machine_id": "m1",
    "account_prefix": "htd_vip",
    "threads": 24,
    "port": 8088,
    "target_server": "latest",
    "min_copies": 2,
    "sales_bot": {
        "enabled": False,
        "webhook_url": "",
        "auth_token": "",
        "telegram_bot_token": "",
        "telegram_chat_id": "",
    },
}

def load_app_config():
  cfg = dict(DEFAULT_CONFIG)
  if os.path.exists(CONFIG_FILE):
    try:
      with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
        if isinstance(data, dict):
          cfg.update(data)
    except Exception as e:
      print(f"⚠️ Lỗi đọc file config.json: {e}")
  if os.path.exists(LOCAL_CONFIG_FILE):
    try:
      with open(LOCAL_CONFIG_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
        if isinstance(data, dict):
          cfg.update(data)
    except Exception as e:
      print(f"⚠️ Lỗi đọc file config_local.json: {e}")

  # Parse CLI overrides (hỗ trợ --machine 2, --prefix htd_m2, --port 8089, --threads 24, --webhook <url>)
  args = sys.argv[1:]
  for i, a in enumerate(args):
    if a in ("--machine", "-m") and i + 1 < len(args):
      m_val = args[i + 1].strip()
      cfg["machine_id"] = f"m{m_val}" if m_val.isdigit() else m_val
      if cfg.get("account_prefix") in ("htd_vip", "", None):
        cfg["account_prefix"] = f"htd_{cfg['machine_id']}"
    elif a in ("--prefix", "-p") and i + 1 < len(args):
      cfg["account_prefix"] = args[i + 1].strip()
    elif a == "--port" and i + 1 < len(args):
      try:
        cfg["port"] = int(args[i + 1])
      except ValueError:
        pass
    elif a == "--threads" and i + 1 < len(args):
      try:
        cfg["threads"] = int(args[i + 1])
      except ValueError:
        pass
    elif a == "--webhook" and i + 1 < len(args):
      cfg.setdefault("sales_bot", {})["webhook_url"] = args[i + 1].strip()
      cfg["sales_bot"]["enabled"] = True

  # Environment variable overrides
  if os.environ.get("HTD_MACHINE"):
    m_env = os.environ["HTD_MACHINE"].strip()
    cfg["machine_id"] = f"m{m_env}" if m_env.isdigit() else m_env
    if cfg.get("account_prefix") in ("htd_vip", "", None):
      cfg["account_prefix"] = f"htd_{cfg['machine_id']}"
  if os.environ.get("HTD_PREFIX"):
    cfg["account_prefix"] = os.environ["HTD_PREFIX"].strip()
  if os.environ.get("HTD_PORT"):
    try:
      cfg["port"] = int(os.environ["HTD_PORT"])
    except ValueError:
      pass

  return cfg

APP_CONFIG = load_app_config()
PORT = int(APP_CONFIG.get("port") or 8088)
MACHINE_ID = str(APP_CONFIG.get("machine_id") or "m1")
ACCOUNT_PREFIX = str(APP_CONFIG.get("account_prefix") or "htd_vip")
PARALLEL_REROLL_WORKERS = int(APP_CONFIG.get("threads") or 24)

CDN_BASE = "https://rescdnft105vn.ridvqqxa.com/13528/"
CDN_CACHE_DIR = os.path.join(DIRECTORY, "cdn_cache")
PATCHED_GAME_JS = os.path.join(DIRECTORY, "js", "game.js")
STATE_FILE = os.path.join(DIRECTORY, "ai_state.json")

os.makedirs(CDN_CACHE_DIR, exist_ok=True)

STATE_LOCK = threading.Lock()
COMMAND_QUEUE = []

# Complete Official Live Server List across all Clusters of Hắc Tây Du Funtap (Auto-synced from Funtap API)
ALL_SERVERS_DATA = [
    # Cụm 5: Lưu Sa Hà (S41 -> S48+)
    {"sid": "610048", "id": 48, "name": "[S48 Mới Nhất] Lưu Sa Hà-S8", "server": "wss://wss-funtap-xy.xinliugame.net:9074/", "status": "1", "recommend": 1, "cluster": "Lưu Sa Hà"},
    {"sid": "610047", "id": 47, "name": "[S47] Lưu Sa Hà-S7", "server": "wss://wss-funtap-xy.xinliugame.net:9073/", "status": "2", "recommend": 1, "cluster": "Lưu Sa Hà"},
    {"sid": "610046", "id": 46, "name": "[S46] Lưu Sa Hà-S6", "server": "wss://wss-funtap-xy.xinliugame.net:9072/", "status": "2", "recommend": 0, "cluster": "Lưu Sa Hà"},
    {"sid": "610045", "id": 45, "name": "[S45] Lưu Sa Hà-S5", "server": "wss://wss-funtap-xy.xinliugame.net:9071/", "status": "2", "recommend": 0, "cluster": "Lưu Sa Hà"},
    {"sid": "610044", "id": 44, "name": "[S44] Lưu Sa Hà-S4", "server": "wss://wss-funtap-xy.xinliugame.net:9070/", "status": "2", "recommend": 0, "cluster": "Lưu Sa Hà"},
    {"sid": "610043", "id": 43, "name": "[S43] Lưu Sa Hà-S3", "server": "wss://wss-funtap-xy.xinliugame.net:9069/", "status": "2", "recommend": 0, "cluster": "Lưu Sa Hà"},
    {"sid": "610042", "id": 42, "name": "[S42] Lưu Sa Hà-S2", "server": "wss://wss-funtap-xy.xinliugame.net:9068/", "status": "2", "recommend": 0, "cluster": "Lưu Sa Hà"},
    {"sid": "610041", "id": 41, "name": "[S41] Lưu Sa Hà-S1", "server": "wss://wss-funtap-xy.xinliugame.net:9067/", "status": "2", "recommend": 0, "cluster": "Lưu Sa Hà"},
    # Cụm 4: Hoàng Phong Lĩnh (S31 -> S40)
    {"sid": "610040", "id": 40, "name": "[S40] Hoàng Phong Lĩnh-S10", "server": "wss://wss-funtap-xy.xinliugame.net:9066/", "status": "2", "recommend": 0, "cluster": "Hoàng Phong Lĩnh"},
    {"sid": "610039", "id": 39, "name": "[S39] Hoàng Phong Lĩnh-S9", "server": "wss://wss-funtap-xy.xinliugame.net:9065/", "status": "2", "recommend": 1, "cluster": "Hoàng Phong Lĩnh"},
    {"sid": "610038", "id": 38, "name": "Hoàng Phong Lĩnh-S8", "server": "wss://wss-funtap-xy.xinliugame.net:9064/", "status": "2", "recommend": 0, "cluster": "Hoàng Phong Lĩnh"},
    {"sid": "610037", "id": 37, "name": "Hoàng Phong Lĩnh-S7", "server": "wss://wss-funtap-xy.xinliugame.net:9063/", "status": "2", "recommend": 0, "cluster": "Hoàng Phong Lĩnh"},
    {"sid": "610036", "id": 36, "name": "Hoàng Phong Lĩnh-S6", "server": "wss://wss-funtap-xy.xinliugame.net:9062/", "status": "2", "recommend": 0, "cluster": "Hoàng Phong Lĩnh"},
    {"sid": "610035", "id": 35, "name": "Hoàng Phong Lĩnh-S5", "server": "wss://wss-funtap-xy.xinliugame.net:9061/", "status": "2", "recommend": 0, "cluster": "Hoàng Phong Lĩnh"},
    {"sid": "610034", "id": 34, "name": "Hoàng Phong Lĩnh-S4", "server": "wss://wss-funtap-xy.xinliugame.net:9060/", "status": "2", "recommend": 0, "cluster": "Hoàng Phong Lĩnh"},
    {"sid": "610033", "id": 33, "name": "Hoàng Phong Lĩnh-S3", "server": "wss://wss-funtap-xy.xinliugame.net:9048/", "status": "2", "recommend": 0, "cluster": "Hoàng Phong Lĩnh"},
    {"sid": "610032", "id": 32, "name": "Hoàng Phong Lĩnh-S2", "server": "wss://wss-funtap-xy.xinliugame.net:9047/", "status": "2", "recommend": 0, "cluster": "Hoàng Phong Lĩnh"},
    {"sid": "610031", "id": 31, "name": "Hoàng Phong Lĩnh-S1", "server": "wss://wss-funtap-xy.xinliugame.net:9046/", "status": "2", "recommend": 0, "cluster": "Hoàng Phong Lĩnh"},
    # Cụm 3: Cao Lão Trang (S1 -> S10)
    {"sid": "610030", "id": 30, "name": "Cao Lão Trang-S10", "server": "wss://wss-funtap-xy.xinliugame.net:9045/", "status": "2", "recommend": 0, "cluster": "Cao Lão Trang"},
    {"sid": "610029", "id": 29, "name": "Cao Lão Trang-S9", "server": "wss://wss-funtap-xy.xinliugame.net:9044/", "status": "2", "recommend": 0, "cluster": "Cao Lão Trang"},
    {"sid": "610028", "id": 28, "name": "Cao Lão Trang-S8", "server": "wss://wss-funtap-xy.xinliugame.net:9043/", "status": "2", "recommend": 0, "cluster": "Cao Lão Trang"},
    {"sid": "610027", "id": 27, "name": "Cao Lão Trang-S7", "server": "wss://wss-funtap-xy.xinliugame.net:9042/", "status": "2", "recommend": 0, "cluster": "Cao Lão Trang"},
    {"sid": "610026", "id": 26, "name": "Cao Lão Trang-S6", "server": "wss://wss-funtap-xy.xinliugame.net:9041/", "status": "2", "recommend": 0, "cluster": "Cao Lão Trang"},
    {"sid": "610025", "id": 25, "name": "Cao Lão Trang-S5", "server": "wss://wss-funtap-xy.xinliugame.net:9040/", "status": "2", "recommend": 0, "cluster": "Cao Lão Trang"},
    {"sid": "610024", "id": 24, "name": "Cao Lão Trang-S4", "server": "wss://wss-funtap-xy.xinliugame.net:9039/", "status": "2", "recommend": 0, "cluster": "Cao Lão Trang"},
    {"sid": "610023", "id": 23, "name": "Cao Lão Trang-S3", "server": "wss://wss-funtap-xy.xinliugame.net:9038/", "status": "2", "recommend": 0, "cluster": "Cao Lão Trang"},
    {"sid": "610022", "id": 22, "name": "Cao Lão Trang-S2", "server": "wss://wss-funtap-xy.xinliugame.net:9037/", "status": "2", "recommend": 1, "cluster": "Cao Lão Trang"},
    {"sid": "610021", "id": 21, "name": "Cao Lão Trang-S1", "server": "wss://wss-funtap-xy.xinliugame.net:9036/", "status": "2", "recommend": 0, "cluster": "Cao Lão Trang"},
    # Cụm 2: Ngũ Chỉ Sơn (S1 -> S10)
    {"sid": "610020", "id": 20, "name": "Ngũ Chỉ Sơn-S10", "server": "wss://wss-funtap-xy.xinliugame.net:9035/", "status": "2", "recommend": 0, "cluster": "Ngũ Chỉ Sơn"},
    {"sid": "610019", "id": 19, "name": "Ngũ Chỉ Sơn-S9", "server": "wss://wss-funtap-xy.xinliugame.net:9034/", "status": "2", "recommend": 0, "cluster": "Ngũ Chỉ Sơn"},
    {"sid": "610018", "id": 18, "name": "Ngũ Chỉ Sơn-S8", "server": "wss://wss-funtap-xy.xinliugame.net:9033/", "status": "2", "recommend": 0, "cluster": "Ngũ Chỉ Sơn"},
    {"sid": "610017", "id": 17, "name": "Ngũ Chỉ Sơn-S7", "server": "wss://wss-funtap-xy.xinliugame.net:9032/", "status": "2", "recommend": 0, "cluster": "Ngũ Chỉ Sơn"},
    {"sid": "610016", "id": 16, "name": "Ngũ Chỉ Sơn-S6", "server": "wss://wss-funtap-xy.xinliugame.net:9031/", "status": "2", "recommend": 0, "cluster": "Ngũ Chỉ Sơn"},
    {"sid": "610015", "id": 15, "name": "Ngũ Chỉ Sơn-S5", "server": "wss://wss-funtap-xy.xinliugame.net:9030/", "status": "2", "recommend": 0, "cluster": "Ngũ Chỉ Sơn"},
    {"sid": "610014", "id": 14, "name": "Ngũ Chỉ Sơn-S4", "server": "wss://wss-funtap-xy.xinliugame.net:9029/", "status": "2", "recommend": 0, "cluster": "Ngũ Chỉ Sơn"},
    {"sid": "610013", "id": 13, "name": "Ngũ Chỉ Sơn-S3", "server": "wss://wss-funtap-xy.xinliugame.net:9028/", "status": "2", "recommend": 0, "cluster": "Ngũ Chỉ Sơn"},
    {"sid": "610012", "id": 12, "name": "Ngũ Chỉ Sơn-S2", "server": "wss://wss-funtap-xy.xinliugame.net:9027/", "status": "2", "recommend": 0, "cluster": "Ngũ Chỉ Sơn"},
    {"sid": "610011", "id": 11, "name": "Ngũ Chỉ Sơn-S1", "server": "wss://wss-funtap-xy.xinliugame.net:9026/", "status": "2", "recommend": 0, "cluster": "Ngũ Chỉ Sơn"},
    # Cụm 1: Hoa Quả Sơn (S1 -> S10)
    {"sid": "610010", "id": 10, "name": "Hoa Quả Sơn-S10", "server": "wss://wss-funtap-xy.xinliugame.net:9025/", "status": "2", "recommend": 0, "cluster": "Hoa Quả Sơn"},
    {"sid": "610009", "id": 9, "name": "Hoa Quả Sơn-S9", "server": "wss://wss-funtap-xy.xinliugame.net:9024/", "status": "2", "recommend": 0, "cluster": "Hoa Quả Sơn"},
    {"sid": "610008", "id": 8, "name": "Hoa Quả Sơn-S8", "server": "wss://wss-funtap-xy.xinliugame.net:9023/", "status": "2", "recommend": 0, "cluster": "Hoa Quả Sơn"},
    {"sid": "610007", "id": 7, "name": "Hoa Quả Sơn-S7", "server": "wss://wss-funtap-xy.xinliugame.net:9022/", "status": "2", "recommend": 0, "cluster": "Hoa Quả Sơn"},
    {"sid": "610006", "id": 6, "name": "Hoa Quả Sơn-S6", "server": "wss://wss-funtap-xy.xinliugame.net:9021/", "status": "2", "recommend": 0, "cluster": "Hoa Quả Sơn"},
    {"sid": "610005", "id": 5, "name": "Hoa Quả Sơn-S5", "server": "wss://wss-funtap-xy.xinliugame.net:9020/", "status": "2", "recommend": 0, "cluster": "Hoa Quả Sơn"},
    {"sid": "610004", "id": 4, "name": "Hoa Quả Sơn-S4", "server": "wss://wss-funtap-xy.xinliugame.net:9019/", "status": "2", "recommend": 0, "cluster": "Hoa Quả Sơn"},
    {"sid": "610003", "id": 3, "name": "Hoa Quả Sơn-S3", "server": "wss://wss-funtap-xy.xinliugame.net:9018/", "status": "2", "recommend": 0, "cluster": "Hoa Quả Sơn"},
    {"sid": "610002", "id": 2, "name": "Hoa Quả Sơn-S2", "server": "wss://wss-funtap-xy.xinliugame.net:9007/", "status": "2", "recommend": 0, "cluster": "Hoa Quả Sơn"},
    {"sid": "610001", "id": 1, "name": "Hoa Quả Sơn-S1", "server": "wss://wss-funtap-xy.xinliugame.net:9006/", "status": "2", "recommend": 0, "cluster": "Hoa Quả Sơn"},
]

AI_STATE = {
    "lastUpdate": 0,
    "clientType": "Đang khởi động...",
    "account": "720452341",
    "roleName": "",
    "level": 1,
    "lv": 1,
    "combatPower": 0,
    "zhandouli": 0,
    "zuanshi": 0,
    "jinbi": 0,
    "totalHeroes": 0,
    "stageId": 0,
    "stageName": "",
    "serverName": "Cao Lão Trang-S2",
    "serverId": 610022,
    "serverIndex": 22,
    "wsUrl": "wss://wss-funtap-xy.xinliugame.net:9037/",
    "timestamp": "1792636795",
    "authKey": "830c88a40d7bbeb624e3b6f1f7a86315",
    "loginToken": "",
    "aiAutoPlay": False,
    "autoCampaign": False,
    "autoTower": False,
    "autoRerollS2": False,
    "rerollAttempt": 0,
    "rerollIdx": 0,
    "topHeroes": [],
    "ownedTamThanh": [],
    "aiPhaseMsg": "⚡ D-AUTO PRO MAX v7.9 Sẵn sàng!",
    "aiLogs": [
        "[Hệ thống] ⚡ D-AUTO PRO MAX v7.9 (Màn Dọc 9:16 + Login TK Chính) đã sẵn sàng!"
    ],
    "vault": [],
    "brainTick": 0,
    "lastPower": 0,
    "stagnantTicks": 0,
}


def fetch_fresh_authkey(account_id="230519465", token="r"):
  """Fetches fresh GLOBAL_TIMESTAMP and GLOBAL_AUTHKEY from Funtap igame.php."""
  try:
    q_acc = urllib.parse.quote(str(account_id or "230519465"))
    q_tok = urllib.parse.quote(str(token or "r"))
    url = f"https://funtap-xy.xinliugame.net/funtap/igame.php?accountID={q_acc}&token={q_tok}&v=1&appVersion=1.0.1"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=6) as resp:
      txt = resp.read().decode("utf-8", errors="ignore")
    m_ts = re.search(r'GLOBAL_TIMESTAMP\s*=\s*"([^"]+)"', txt)
    m_ak = re.search(r'GLOBAL_AUTHKEY\s*=\s*"([^"]+)"', txt)
    if m_ts and m_ak:
      with STATE_LOCK:
        AI_STATE["timestamp"] = m_ts.group(1)
        AI_STATE["authKey"] = m_ak.group(1)
      return {"timestamp": m_ts.group(1), "authKey": m_ak.group(1)}
  except Exception:
    pass
  with STATE_LOCK:
    return {
        "timestamp": AI_STATE.get("timestamp", "1792636795"),
        "authKey": AI_STATE.get("authKey", "830c88a40d7bbeb624e3b6f1f7a86315"),
    }


def query_account_characters(account_id):
  """Queries Funtap getServerList2.php?lst=last for an account ID to find existing characters."""
  chars = []
  if not account_id:
    return chars
  try:
    url = (
        "https://funtap-xy.ridvqqxa.com/game/getServerList2.php?lst=last&ac="
        + urllib.parse.quote(str(account_id))
        + "&plt=ios&v=1&platform=funtap&appid=ios"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=5) as resp:
      raw = resp.read().decode("utf-8", errors="ignore")
    arr = json.loads(raw)
    if isinstance(arr, list):
      for item in arr:
        role_lv = int(item.get("roleLv") or 0)
        role_name = str(item.get("roleName") or "")
        is_new = str(item.get("isNewAccount") or "0") == "1"
        if role_lv > 0 or (role_name and role_name != "未创角" and not is_new):
          chars.append({
              "account": str(account_id),
              "sid": str(item.get("sid") or "610022"),
              "id": int(item.get("id") or 22),
              "serverName": str(item.get("name") or "Cao Lão Trang-S2"),
              "wsUrl": str(item.get("server") or "wss://wss-funtap-xy.xinliugame.net:9037/"),
              "roleName": role_name,
              "roleLv": role_lv,
          })
  except Exception:
    pass
  return chars


def funtap_login_authenticate(username, password):
  """Logs into Funtap MontarSDK via core.sdkmain.com and finds existing characters."""
  username = (username or "").strip()
  password = (password or "").strip()
  if not username or not password:
    return {"ok": False, "error": "Vui lòng nhập đầy đủ Tài khoản/Email và Mật khẩu!"}

  endpoints = [
      "https://core.sdkmain.com/api/v1/apps/f0d9c5e4b5d0de9bd966ed884c72e5ad/vi/auth/login",
      "https://core.sdkmain.com/api/v1/apps/f0d9c5e4b5d0de9bd966ed884c72e5ad/com.loinguyen.nguoigiuuuuu.ftg/auth/login",
  ]
  form_body = urllib.parse.urlencode({
      "email": username,
      "password": password,
      "device_os": "18.0",
      "device_name": "iPhone",
      "device_resolution": "1170x2532",
      "device_network": "1",
      "sdk_version": "7.0.0",
  }).encode("utf-8")

  resp_json = None
  last_err = "Thông tin đăng nhập không chính xác."
  for ep in endpoints:
    try:
      req = urllib.request.Request(
          ep,
          data=form_body,
          headers={
              "Content-Type": "application/x-www-form-urlencoded",
              "Accept": "application/json",
              "User-Agent": "HacTayDu/1.0.1 (iPhone; iOS 18.0; Scale/3.00)",
          },
          method="POST",
      )
      with urllib.request.urlopen(req, timeout=8) as resp:
        raw = resp.read().decode("utf-8", errors="ignore")
      data = json.loads(raw)
      if data.get("data") and (data.get("access_token") or data["data"].get("id")):
        resp_json = data
        break
      if data.get("message"):
        last_err = data["message"]
    except urllib.error.HTTPError as he:
      try:
        err_body = he.read().decode("utf-8", errors="ignore")
        err_data = json.loads(err_body)
        if err_data.get("message"):
          last_err = err_data["message"]
      except Exception:
        pass
    except Exception as e:
      last_err = str(e)

  if not resp_json:
    return {"ok": False, "error": last_err}

  d = resp_json.get("data") or {}
  acc_obj = d.get("account") or {}
  account_id = str(acc_obj.get("account_id") or d.get("id") or username)
  fun_id = str(d.get("id") or account_id)
  fun_name = str(d.get("name") or username)
  access_token = str(resp_json.get("access_token") or "r")

  ak_info = fetch_fresh_authkey(account_id, access_token)

  # Check existing characters across candidate IDs (account_id, fun_id, fun_name)
  all_chars = []
  seen = set()
  for cand in [account_id, fun_id, fun_name]:
    if cand and cand not in seen:
      seen.add(cand)
      found = query_account_characters(cand)
      for c in found:
        all_chars.append(c)

  primary_acc = account_id
  if all_chars:
    primary_acc = all_chars[0]["account"]

  return {
      "ok": True,
      "accountId": primary_acc,
      "montarAccountId": account_id,
      "funId": fun_id,
      "username": fun_name,
      "accessToken": access_token,
      "timestamp": ak_info["timestamp"],
      "authKey": ak_info["authKey"],
      "characters": all_chars,
  }


def _get_recaptcha_enterprise_token():
  """Generates a valid reCAPTCHA Enterprise v3 token via pure HTTP anchor->reload in ~0.2s."""
  try:
    site_key = "6Lc7WFYsAAAAAIZ1uFlJpFgSlbcFFdGYHXgaVcVU"
    co = "aHR0cHM6Ly9jb3JlLnNka21haW4uY29tOjQ0Mw.."
    anchor_url = (
        f"https://www.google.com/recaptcha/enterprise/anchor?ar=1&k={site_key}"
        f"&co={co}&hl=vi&v=rPvs0Nyx3sANE-ZHUN-0nM85&size=invisible&cb={random.randint(100000, 999999)}"
    )
    req = urllib.request.Request(
        anchor_url,
        headers={
            "User-Agent": "Mozilla/5.0 (Linux; Android 12; Pixel 6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"
        },
    )
    html = urllib.request.urlopen(req, timeout=6).read().decode("utf-8", errors="ignore")
    m = re.search(r'id="recaptcha-token"\s+value="([^"]+)"', html)
    if not m:
      return ""
    c_tok = m.group(1)
    reload_url = f"https://www.google.com/recaptcha/enterprise/reload?k={site_key}"
    post_data = urllib.parse.urlencode({
        "v": "rPvs0Nyx3sANE-ZHUN-0nM85",
        "reason": "q",
        "c": c_tok,
        "k": site_key,
        "co": co,
        "hl": "vi",
        "size": "invisible",
        "chr": "[89,64,27]",
        "vh": "13599012192",
        "bg": "",
    }).encode("utf-8")
    req2 = urllib.request.Request(
        reload_url,
        data=post_data,
        headers={
            "User-Agent": "Mozilla/5.0 (Linux; Android 12; Pixel 6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    r2 = urllib.request.urlopen(req2, timeout=6).read().decode("utf-8", errors="ignore")
    m_rresp = re.search(r'"rresp","([^"]+)"', r2)
    return m_rresp.group(1) if m_rresp else ""
  except Exception:
    return ""


def funtap_register_real_account(username, password="tphtd123"):
  """Registers a real Funtap FunID account via core.sdkmain.com/v1/apps/.../register/phone with auto reCAPTCHA v3 token."""
  import uuid
  username = (username or "").strip()
  password = (password or "tphtd123").strip()
  if len(password) < 8:
    password = password + "12345678"[: 8 - len(password)]
  for attempt in range(3):
    try:
      cj = http.cookiejar.CookieJar()
      opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
      opener.addheaders = [
          ("User-Agent", f"Mozilla/5.0 (Linux; Android 12; Pixel {random.randint(4, 8)}) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36")
      ]
      af_id = f"{random.randint(1700000000000, 1790000000000)}-{random.randint(1000000000000000000, 9999999999999999999)}"
      ad_id = str(uuid.uuid4())
      get_url = (
          "https://core.sdkmain.com/v1/apps/2a456b78cf5122cd9278ef24b4d7bfb9/9.9.9.5/register/phone"
          f"?sdk_version=6.1.2&device_network=wifi&appsflyer_id={af_id}"
          f"&advertising_id={ad_id}&device_os=Android%2012&device_name=Pixel%206"
      )
      html = opener.open(get_url, timeout=8).read().decode("utf-8", errors="ignore")
      m_tok = re.search(r'name="_token"\s+value="([^"]+)"', html)
      m_act = re.search(r'action="([^"]+)"', html)
      if not m_tok or not m_act:
        time.sleep(0.2)
        continue
      token = m_tok.group(1)
      action_url = m_act.group(1).replace("&amp;", "&")
      g_tok = _get_recaptcha_enterprise_token() if "g-recaptcha" in html else ""

      post_data = urllib.parse.urlencode({
          "_token": token,
          "username": username,
          "fullname": "Đặng Minh Nam",
          "birthday": "2000-01-04",
          "phone": f"09{random.choice(['6', '7', '8', '3'])}{random.randint(1000000, 9999999)}",
          "password": password,
          "g-recaptcha-response": g_tok,
          "btn-Register": "",
      }).encode("utf-8")

      resp = opener.open(urllib.request.Request(action_url, data=post_data, method="POST"), timeout=8)
      res_html = resp.read().decode("utf-8", errors="ignore")
      m_json = re.search(r"appSDKexecute\('loginSuccess',\s*(\{.*?\})\);", res_html)
      if m_json:
        info = json.loads(m_json.group(1))
        d = info.get("data") or {}
        acc_obj = d.get("account") or {}
        acc_id = str(acc_obj.get("account_id") or d.get("id") or "")
        fun_id = str(d.get("id") or acc_id)
        acc_tok = str(info.get("access_token") or "r")
        if acc_id:
          return {
              "ok": True,
              "username": username,
              "password": password,
              "accountId": acc_id,
              "funId": fun_id,
              "accessToken": acc_tok,
          }
      if "username" in res_html and ("tồn tại" in res_html or "taken" in res_html or "đã được sử dụng" in res_html or "err_username" in res_html):
        return {"ok": False, "taken": True, "error": "Tên tài khoản đã tồn tại trên Funtap"}
      # Nếu lỗi do token/recaptcha tạm thời thì thử lại cùng tên tài khoản đó
      time.sleep(0.25)
    except Exception as e:
      if attempt == 2:
        return {"ok": False, "error": str(e)}
      time.sleep(0.25)
  return {"ok": False, "taken": True, "error": "Không đăng ký được tên này"}


def build_all_server_list_response(origin_url):
  """Builds the Re.onAllList JSON containing all 39 servers grouped by cluster."""
  clusters = [
      ("Đề Xuất & Mới Nhất", [s for s in ALL_SERVERS_DATA if s["id"] >= 31]),
      ("Cao Lão Trang (S1-S10)", [s for s in ALL_SERVERS_DATA if 21 <= s["id"] <= 30]),
      ("Ngũ Chỉ Sơn (S1-S10)", [s for s in ALL_SERVERS_DATA if 11 <= s["id"] <= 20]),
      ("Hoa Quả Sơn (S1-S10)", [s for s in ALL_SERVERS_DATA if 1 <= s["id"] <= 10]),
  ]
  result = []
  for region_name, srv_list in clusters:
    result.append({
        "area": None,
        "region": "VN",
        "regionName": region_name,
        "gamePlatform": "funtap",
        "entry_domain": "https://funtap-xy.ridvqqxa.com/",
        "log_login": "https://funtap-xy.ridvqqxa.com/game/login.php",
        "noEntry": 0,
        "regionRecommend": 1,
        "all": srv_list,
    })
  return result


def build_last_server_list_response(account_id, preferred_sid=None):
  """Builds the Re.onLastList JSON for the given account, preserving real characters."""
  chars = query_account_characters(account_id)
  result = []
  if preferred_sid:
    for s in ALL_SERVERS_DATA:
      if str(s["sid"]) == str(preferred_sid):
        role_name = "未创角"
        role_lv = 0
        for c in chars:
          if str(c["sid"]) == str(preferred_sid):
            role_name = c["roleName"]
            role_lv = c["roleLv"]
            break
        result.append({
            "sid": s["sid"],
            "name": s["name"],
            "status": s["status"],
            "isNewAccount": "0" if role_lv > 0 else "1",
            "minSid": 1,
            "maxSid": 39,
            "channel": "",
            "gdt_vid": "",
            "weixinadinfo": "",
            "roleName": role_name,
            "roleLv": role_lv,
            "roleHead": 1 if role_lv > 0 else 0,
            "privatePolicy": 0,
            "directEnter": 0,
            "notice": 0,
            "cadpa": 0,
            "tips": "",
            "isTishen": 0,
            "showNotice": 0,
            "id": s["id"],
            "server": s["server"],
            "recommend": s["recommend"],
            "area": None,
            "region": "VN",
            "regionName": "推荐",
            "gamePlatform": "funtap",
            "entry_domain": "https://funtap-xy.ridvqqxa.com/",
            "log_login": "https://funtap-xy.ridvqqxa.com/game/login.php",
        })
        break

  for c in chars:
    if any(str(r["sid"]) == str(c["sid"]) for r in result):
      continue
    result.append({
        "sid": c["sid"],
        "name": c["serverName"],
        "status": "2",
        "isNewAccount": "0",
        "minSid": 1,
        "maxSid": 39,
        "channel": "",
        "gdt_vid": "",
        "weixinadinfo": "",
        "roleName": c["roleName"],
        "roleLv": c["roleLv"],
        "roleHead": 1,
        "privatePolicy": 0,
        "directEnter": 0,
        "notice": 0,
        "cadpa": 0,
        "tips": "",
        "isTishen": 0,
        "showNotice": 0,
        "id": c["id"],
        "server": c["wsUrl"],
        "recommend": 1,
        "area": None,
        "region": "VN",
        "regionName": "推荐",
        "gamePlatform": "funtap",
        "entry_domain": "https://funtap-xy.ridvqqxa.com/",
        "log_login": "https://funtap-xy.ridvqqxa.com/game/login.php",
    })

  if not result:
    # Default to Cao Lão Trang-S2 (610022) and Hoàng Phong Lĩnh-S9 (610039) with directEnter=0
    for default_sid in ("610022", "610039"):
      for s in ALL_SERVERS_DATA:
        if s["sid"] == default_sid:
          result.append({
              "sid": s["sid"],
              "name": s["name"],
              "status": s["status"],
              "isNewAccount": "0",
              "minSid": 1,
              "maxSid": 39,
              "channel": "",
              "gdt_vid": "",
              "weixinadinfo": "",
              "roleName": "未创角",
              "roleLv": 0,
              "roleHead": 0,
              "privatePolicy": 0,
              "directEnter": 0,
              "notice": 0,
              "cadpa": 0,
              "tips": "",
              "isTishen": 0,
              "showNotice": 0,
              "id": s["id"],
              "server": s["server"],
              "recommend": s["recommend"],
              "area": None,
              "region": "VN",
              "regionName": "推荐",
              "gamePlatform": "funtap",
              "entry_domain": "https://funtap-xy.ridvqqxa.com/",
              "log_login": "https://funtap-xy.ridvqqxa.com/game/login.php",
          })
  return result


def add_brain_log(msg):
  ts = time.strftime("%H:%M:%S")
  entry = f"[{ts}] ⚡ {msg}"
  logs = AI_STATE.setdefault("aiLogs", [])
  if not logs or logs[0] != entry:
    logs.insert(0, entry)
    if len(logs) > 45:
      del logs[45:]
  AI_STATE["aiPhaseMsg"] = msg


# ==============================================================================
# TÍCH HỢP TRỰC TIẾP: HỆ THỐNG TỰ ĐỘNG TẠO DÀN NICK & QUAY DƯƠNG TIỄN / NGỘ KHÔNG
# (Full Combo: 27 Giftcode + Mở 250 Mảnh 5★ (5 tướng) + Quay 60 lần Thiên Mệnh + 14 vé Tam Giới)
# ==============================================================================
VN_LANG_MAP = {}
VN_JSON_FILE = os.path.join(CDN_CACHE_DIR, "res", "lang", "vn", "vn.json")
if os.path.exists(VN_JSON_FILE):
  try:
    with open(VN_JSON_FILE, "r", encoding="utf-8") as _vf:
      VN_LANG_MAP = json.load(_vf).get("lang", {})
  except Exception:
    pass

REROLL_GIFTCODES = [
    # Ưu tiên gửi 9 Code chứa 250 Mảnh Tướng 5★ lên đầu tiên để Server trả mảnh về túi ngay lập tức
    "45THANTUONG", "DUONGTIEN", "NGOKHONG", "NATRA",
    "DAT100KDKT", "DKT50K", "DKT30K", "THANCAN555", "YCAN666",
    # Các Code Vé Quay Thiên Mệnh, Vé Tam Giới & KNB
    "HACTAYDU888", "TAYDUKI", "CHUONGCAM", "HTDCC999",
    "HOICHIEUTROIMUA", "THUANPHAM", "VAN97", "HOANGDZ",
    "NHANCAN111", "NHICAN222", "TICAN333", "THIETCAN444",
    "DKT5K", "DKT10K", "DKT20K", "CCC2026", "NGOCKEN", "DOITAC666"
]

REROLL_VAULT_FILE = os.path.join(DIRECTORY, "DAN_NICK_DA_QUAY.json")
SCREENSHOT_DIR = os.path.join(DIRECTORY, "anh_nick_trung")
os.makedirs(SCREENSHOT_DIR, exist_ok=True)

REROLL_LOCK = threading.Lock()
REUSABLE_POOL = {}  # username -> {"u": str, "p": str, "id": str, "sid": int}
IN_FLIGHT_USERS = set()
REROLL_STATE = {
    "running": False,
    "stopRequested": False,
    "currentIdx": 0,
    "totalCount": 0,
    "reusableCount": 0,
    "currentAcc": "",
    "stepMsg": "Sẵn sàng tạo dàn nick & quay tướng!",
    "accounts": [],
}


def _gen_strong_password(length=10):
  """Sinh mật khẩu ngẫu nhiên phức tạp (Chữ Hoa + chữ thường + Số) chống dò nick."""
  uppers = "ABCDEFGHJKLMNPQRSTUVWXYZ"
  lowers = "abcdefghijkmnpqrstuvwxyz"
  digits = "23456789"
  chars = (
      [random.choice(uppers) for _ in range(3)]
      + [random.choice(lowers) for _ in range(3)]
      + [random.choice(digits) for _ in range(max(1, length - 6))]
  )
  random.shuffle(chars)
  return "".join(chars)


def _batch_idx_to_letters(idx):
  """0 -> 'a', 25 -> 'z', 26 -> 'aa', 27 -> 'ab'..."""
  res = ""
  n = idx
  while True:
    res = chr(ord("a") + (n % 26)) + res
    n = (n // 26) - 1
    if n < 0:
      break
  return res


def _letters_to_batch_idx(letters):
  idx = 0
  for ch in letters.lower():
    if "a" <= ch <= "z":
      idx = idx * 26 + (ord(ch) - ord("a") + 1)
  return max(0, idx - 1)


def _normalize_base_prefix(prefix=None):
  p = (prefix or ACCOUNT_PREFIX or "htd_vip").strip().strip("_")
  if p.lower() == "tphtd":
    p = "htd_vip"
  if re.search(r"_[a-z]$", p, flags=re.I) and len(p.split("_")) > 2:
    p = re.sub(r"_[a-z]$", "", p, flags=re.I)
  return p or ACCOUNT_PREFIX or "htd_vip"


def _format_vip_username(base_prefix, seq_num):
  """Định dạng <prefix>_a_001 -> <prefix>_a_999, sau đó sang <prefix>_b_001..."""
  base = _normalize_base_prefix(base_prefix)
  seq = max(1, int(seq_num))
  batch_idx = (seq - 1) // 999
  num_in_batch = ((seq - 1) % 999) + 1
  letters = _batch_idx_to_letters(batch_idx)
  return f"{base}_{letters}_{num_in_batch:03d}"


def _parse_vip_seq(username, base_prefix=None):
  base = _normalize_base_prefix(base_prefix)
  m = re.match(rf"^{re.escape(base)}_([a-z]+)_(\d{{3}})$", str(username or "").strip(), flags=re.I)
  if not m:
    return 0
  b_idx = _letters_to_batch_idx(m.group(1))
  num = int(m.group(2))
  return b_idx * 999 + num


TAYDU_PROUD_PREFIXES = [
    "TềThiênĐế",
    "ĐộcBộTâyDu",
    "NgạoThiênTôn",
    "ĐấuChiếnThánh",
    "TamGiớiBáChủ",
    "VạnYêuĐếTôn",
    "HắcTâyDuĐế",
    "LăngTiêuĐế",
    "NghịchThiênĐế",
    "SátThầnTâyDu",
    "ChíTônMaĐế",
    "ThiênMệnhChủ",
    "NhịLangThần",
    "HỗnĐộnMaTôn",
    "ĐạiThánhGia",
    "TruTiênĐếQuân",
    "PháThiênMaTôn",
    "BấtBạiThánh",
    "ThônThiênĐế",
    "TuyệtThếYêu",
    "ĐạpToáiLinhSơn",
    "NgạoThịTamGiới",
    "VôThượngMaTôn",
    "CửuThiênBáChủ",
    "HuyếtLinhSơn",
    "TâyDuĐộcTôn",
    "MaThầnNgộKhông",
    "ChiếnThầnNaTra",
    "ChânQuânĐế",
    "ThiênĐìnhBáChủ",
]


def _game_strlength(s):
  return sum(1 if ord(ch) <= 128 else 2 for ch in s)


def _gen_cool_taydu_role_name(force_num=False):
  """Sinh tên nhân vật trong game kiêu ngạo, đậm chất Hắc Tây Du và vừa khít giới hạn 18 ký tự của server."""
  base = random.choice(TAYDU_PROUD_PREFIXES)
  rem = 18 - _game_strlength(base)
  if rem >= 3:
    suffix = str(random.randint(10, 999) if not force_num else random.randint(100, 999))
    if len(suffix) > rem:
      suffix = suffix[:rem]
    return base + suffix
  elif rem >= 2:
    return base + str(random.randint(10, 99))
  return base


def _pkt_str(s):
  b = s.encode("utf-8")
  return struct.pack(">H", len(b)) + b


def _pkt_msg(msg_id, payload=b""):
  return struct.pack(">HH", len(payload), msg_id) + payload


def _parse_hero_gt(data, offset):
  try:
    if offset + 4 > len(data):
      return None, offset
    h_id = struct.unpack(">i", data[offset : offset + 4])[0]
    offset += 4
    if offset + 2 > len(data):
      return None, offset
    u_len = struct.unpack(">H", data[offset : offset + 2])[0]
    offset += 2 + u_len
    if offset + 2 > len(data):
      return None, offset
    n_len = struct.unpack(">H", data[offset : offset + 2])[0]
    offset += 2
    name_cn = data[offset : offset + n_len].decode("utf-8", errors="ignore")
    offset += n_len
    if offset + 2 > len(data):
      return None, offset
    n2_len = struct.unpack(">H", data[offset : offset + 2])[0]
    offset += 2 + n2_len
    offset += 4 + 4 + 2 + 1 + 1 + 8
    star = data[offset] if offset < len(data) else 0
    offset += 3
    return {
        "id": h_id,
        "name_cn": name_cn,
        "name": VN_LANG_MAP.get(name_cn, name_cn),
        "star": star,
    }, offset
  except Exception:
    return None, offset


def _parse_hero_packet(pkt_bytes):
  heroes = []
  if len(pkt_bytes) < 4:
    return heroes
  _, msg_id = struct.unpack(">HH", pkt_bytes[:4])
  data = pkt_bytes[4:]
  if msg_id == 21:
    h, _ = _parse_hero_gt(data, 0)
    if h and h.get("name"):
      heroes.append(h)
  elif msg_id == 38:
    try:
      cnt = struct.unpack(">H", data[:2])[0]
      offset = 2
      for _ in range(cnt):
        h, offset = _parse_hero_gt(data, offset)
        if h and h.get("name"):
          heroes.append(h)
    except Exception:
      pass
  return heroes


KNOWN_SAVED_WINNERS = set()


def _parse_heroes_from_target_and_sub(target_raw, other_raw):
  dt_c = 0
  tnk_c = 0
  nt_c = 0
  dtt_c = 0
  m_dt = re.search(r"(\d+)x\s*Dương Tiễn", target_raw)
  if m_dt:
    dt_c = int(m_dt.group(1))
  m_tnk = re.search(r"(\d+)x\s*Tôn Ngộ Không", target_raw)
  if m_tnk:
    tnk_c = int(m_tnk.group(1))
  m_nt = re.search(r"(\d+)x\s*Na Tra", target_raw)
  if m_nt:
    nt_c = int(m_nt.group(1))
  m_dtt = re.search(r"(\d+)x\s*Đường Tam Tạng", target_raw)
  if m_dtt:
    dtt_c = int(m_dtt.group(1))

  h5_list = (
      ["Dương Tiễn"] * dt_c
      + ["Tôn Ngộ Không"] * tnk_c
      + ["Na Tra"] * nt_c
      + ["Đường Tam Tạng"] * dtt_c
  )
  if other_raw and other_raw not in ("-", "Không", "None"):
    for part in other_raw.split("+"):
      p_clean = part.strip()
      if not p_clean:
        continue
      m_mul = re.match(r"^(.+?)\s+x(\d+)$", p_clean)
      if m_mul:
        h_name = m_mul.group(1).strip()
        h_cnt = int(m_mul.group(2))
      else:
        h_name = p_clean
        h_cnt = 1
      if h_name == "Đường Tam Tạng" and dtt_c > 0:
        continue
      h5_list.extend([h_name] * h_cnt)

  dtt_total = h5_list.count("Đường Tam Tạng")
  badges = []
  if dt_c >= 1:
    badges.append(f"{dt_c}x Dương Tiễn")
  if tnk_c >= 1:
    badges.append(f"{tnk_c}x Tôn Ngộ Không")
  if nt_c >= 1:
    badges.append(f"{nt_c}x Na Tra")
  if dtt_total >= 1:
    badges.append(f"{dtt_total}x Đường Tam Tạng")
  return dt_c, tnk_c, nt_c, h5_list, badges


def _format_winner_pipe_line(r):
  """Định dạng chuẩn 1 dòng (ngăn cách bằng dấu |) gọn nhẹ, không lưu link thừa:
  user | pass | server (sid) | [X2/X3] tuong_trung | tong_5s | tuong_5s_phu | uid_nap | anh_chup | thoi_gian"""
  from collections import Counter
  h5 = r.get("heroes5Star") or r.get("heroes") or []
  c = Counter(h5)
  other_str = " + ".join([
      f"{k} x{v}" if v > 1 else k
      for k, v in c.items()
      if k not in ("Dương Tiễn", "Tôn Ngộ Không", "Na Tra", "Đường Tam Tạng")
  ]) or "-"
  max_single = max(int(r.get("dtCount") or 0), int(r.get("tnkCount") or 0), int(r.get("ntCount") or 0))
  tier_tag = f"[X{max_single}] " if max_single >= 2 else ""
  badges = list(r.get("targetHeroes") or [])
  dtt_cnt = c.get("Đường Tam Tạng", 0)
  if dtt_cnt >= 1 and not any("Đường Tam Tạng" in b for b in badges):
    badges.append(f"{dtt_cnt}x Đường Tam Tạng")
  target_str = tier_tag + " + ".join(badges)
  srv_name = str(r.get("serverName") or "").replace(" Mới Nhất]", "]")
  sid_val = int(r.get("serverId") or 610065)
  if str(sid_val) not in srv_name:
    srv_col = f"{srv_name} ({sid_val})".strip()
  else:
    srv_col = srv_name
  acc_u = str(r.get("account") or "")
  pwd = str(r.get("password") or "tphtd123")
  fid = str(r.get("funtapId") or "")
  img = str(r.get("screenshot") or "-")
  t_str = str(r.get("time") or time.strftime("%Y-%m-%d %H:%M:%S"))
  return f"{acc_u} | {pwd} | {srv_col} | {target_str} | {len(h5)}★ | {other_str} | {fid} | {img} | {t_str}"


def _sync_winners_from_txt():
  """Đọc toàn bộ nick trúng 2x/3x từ DAN_NICK_TRUNG_TUONG.txt.
  Hỗ trợ cả định dạng mới 1 dòng (user | pass | server | x2_tuong | ...) lẫn định dạng nhiều dòng cũ,
  và tự động ghép directLink trong RAM từ UID + SID."""
  txt_path = os.path.join(DIRECTORY, "DAN_NICK_TRUNG_TUONG.txt")
  if not os.path.exists(txt_path):
    return []
  restored = []
  seen_acc = set()
  try:
    with open(txt_path, "r", encoding="utf-8", errors="ignore") as f:
      content = f.read()

    # 1. Đọc định dạng chuẩn 1 dòng: user | pass | server | x2_tuong | tong_5s | tuong_5s_phu | uid_nap | anh_chup | thoi_gian
    for raw_line in content.splitlines():
      line = raw_line.strip()
      if not line or line.startswith("=") or line.startswith("#") or line.startswith("TÀI KHOẢN") or line.startswith("USER"):
        continue
      if line.startswith("[") or line.startswith("●"):
        continue
      parts = [p.strip() for p in line.split("|")]
      if len(parts) >= 7 and not parts[0].startswith("Tài khoản"):
        acc_name = parts[0]
        pwd = parts[1]
        srv_col = parts[2]
        target_raw = parts[3]
        other_raw = parts[5] if len(parts) > 5 else ""
        fid = parts[6] if len(parts) > 6 else ""
        img_path = parts[7] if len(parts) > 7 and parts[7] != "-" else ""
        # Hỗ trợ cả bản 9 cột (không link) và 10 cột (có link)
        if len(parts) >= 10 and parts[8].startswith("http"):
          lnk_raw = parts[8]
          t_str = parts[9]
        else:
          lnk_raw = ""
          t_str = parts[8] if len(parts) > 8 else ""

        m_sid = re.search(r"(61\d{4})", srv_col) or re.search(r"sid=(\d+)", lnk_raw)
        sid_val = int(m_sid.group(1)) if m_sid else 610065
        srv_name = re.sub(r"\s*\(61\d{4}\)\s*$", "", srv_col).strip()

        dt_c, tnk_c, nt_c, h5_list, badges = _parse_heroes_from_target_and_sub(target_raw, other_raw)
        if not badges:
          continue
        if not img_path:
          cand_img = os.path.join(SCREENSHOT_DIR, f"{acc_name}_S{sid_val - 610000}.png")
          if os.path.exists(cand_img):
            img_path = f"anh_nick_trung/{acc_name}_S{sid_val - 610000}.png"
        lnk = f"http://localhost:8088/play?acc={fid}&sid={sid_val}&direct=1" if fid else lnk_raw

        seen_acc.add(acc_name)
        restored.append({
            "account": acc_name,
            "password": pwd,
            "funtapId": fid,
            "serverId": sid_val,
            "serverName": srv_name,
            "directLink": lnk,
            "screenshot": img_path,
            "heroes5Star": h5_list,
            "dtCount": dt_c,
            "tnkCount": tnk_c,
            "ntCount": nt_c,
            "targetHeroes": badges,
            "hasTarget": True,
            "isJackpot2x": True,
            "time": t_str,
        })

    # 2. Tương thích ngược: Đọc định dạng block nhiều dòng cũ (nếu còn trong file)
    blocks = re.split(r"(?=\[\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\])", content)
    for b in blocks:
      m_time = re.search(r"\[(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\]\s*🔥🔥\s*TRÚNG[^:]*:\s*(.+)", b)
      m_acc = re.search(r"Tài khoản Funtap\s*:\s*(\S+)\s*\|\s*Mật khẩu:\s*(\S+)\s*\|\s*ID Nạp:\s*(\d+)", b)
      m_srv = re.search(r"Server\s*:\s*(.+)", b)
      m_h5 = re.search(r"Tướng 5★ phụ\s*\([^)]*\):\s*(.+)", b)
      m_lnk = re.search(r"Link vào thẳng\s*:\s*(\S+)", b)
      m_img = re.search(r"Ảnh Thần Tướng\s*:\s*(.+)", b)
      if not (m_time and m_acc):
        continue
      acc_name = m_acc.group(1).strip()
      if acc_name in seen_acc:
        continue
      t_str = m_time.group(1).strip()
      target_raw = m_time.group(2).strip()
      pwd = m_acc.group(2).strip()
      fid = m_acc.group(3).strip()
      srv_name = m_srv.group(1).strip() if m_srv else ""
      other_raw = m_h5.group(1).strip() if m_h5 else ""
      lnk_raw = m_lnk.group(1).strip() if m_lnk else ""
      img_path = m_img.group(1).strip() if m_img else ""
      m_sid = re.search(r"sid=(\d+)", lnk_raw) or re.search(r"\[S(\d+)", srv_name)
      if m_sid:
        val_s = int(m_sid.group(1))
        sid_val = val_s if val_s > 600000 else (610000 + val_s)
      else:
        sid_val = 610065

      dt_c, tnk_c, nt_c, h5_list, badges = _parse_heroes_from_target_and_sub(target_raw, other_raw)
      if not img_path:
        cand_img = os.path.join(SCREENSHOT_DIR, f"{acc_name}_S{sid_val - 610000}.png")
        if os.path.exists(cand_img):
          img_path = f"anh_nick_trung/{acc_name}_S{sid_val - 610000}.png"
      lnk = f"http://localhost:8088/play?acc={fid}&sid={sid_val}&direct=1"

      seen_acc.add(acc_name)
      restored.append({
          "account": acc_name,
          "password": pwd,
          "funtapId": fid,
          "serverId": sid_val,
          "serverName": srv_name,
          "directLink": lnk,
          "screenshot": img_path,
          "heroes5Star": h5_list,
          "dtCount": dt_c,
          "tnkCount": tnk_c,
          "ntCount": nt_c,
          "targetHeroes": badges,
          "hasTarget": True,
          "isJackpot2x": True,
          "time": t_str,
      })
  except Exception:
    pass
  return restored


def _load_and_migrate_vault():
  """Đọc DAN_NICK_DA_QUAY.json (hỗ trợ cả định dạng cũ 13 trường lẫn định dạng mới 4 trường u/p/id/sid),
  loại bỏ các nick đã trúng 2x khỏi kho phôi tái sử dụng, và đồng bộ danh sách trúng sang dạng 1 dòng + CSV."""
  winners = _sync_winners_from_txt()
  winner_users = {w["account"] for w in winners if w.get("account")}
  winner_ids = {str(w["funtapId"]) for w in winners if w.get("funtapId")}
  for w_u in winner_users:
    KNOWN_SAVED_WINNERS.add(w_u)

  pool = {}
  if os.path.exists(REROLL_VAULT_FILE):
    try:
      with open(REROLL_VAULT_FILE, "r", encoding="utf-8") as rf:
        loaded = json.load(rf)
      if isinstance(loaded, list):
        for item in loaded:
          if not isinstance(item, dict):
            continue
          if item.get("isJackpot2x"):
            continue
          u = str(item.get("u") or item.get("account") or "").strip()
          p = str(item.get("p") or item.get("password") or "tphtd123").strip()
          fid = str(item.get("id") or item.get("funtapId") or "").strip()
          sid = int(item.get("sid") or item.get("serverId") or 0)
          if not u or not fid:
            continue
          if u in winner_users or fid in winner_ids:
            continue
          prev = pool.get(u)
          if not prev or sid > prev["sid"]:
            pool[u] = {"u": u, "p": p, "id": fid, "sid": sid}
    except Exception:
      pass

  with REROLL_LOCK:
    REUSABLE_POOL.clear()
    REUSABLE_POOL.update(pool)
    REROLL_STATE["reusableCount"] = len(REUSABLE_POOL)
    REROLL_STATE["accounts"] = winners


LAST_DISK_SAVE_TS = [0]


def _save_reroll_files(force=False):
  """Lưu kho phôi tái sử dụng siêu gọn (1 dòng 4 trường u, p, id, sid) vào DAN_NICK_DA_QUAY.json
  và xuất danh sách nick trúng 2x ra:
    1) DAN_NICK_TRUNG_TUONG.txt (1 dòng/nick ngăn cách bằng dấu | dễ xem và xóa nhanh)
    2) DAN_NICK_TRUNG_TUONG.csv (Chuẩn Excel UTF-8 BOM để lọc theo Server/Tướng/Thống kê)
    3) DANH_SACH_NICK_D_AUTO.txt (Bản đồng bộ 1 dòng/nick sắp xếp theo độ hiếm)"""
  import csv
  from collections import Counter
  now_ts = time.time()
  if not force and (now_ts - LAST_DISK_SAVE_TS[0] < 3.5):
    return
  LAST_DISK_SAVE_TS[0] = now_ts

  restored_winners = _sync_winners_from_txt()
  with REROLL_LOCK:
    by_winner = {}
    for w in restored_winners:
      by_winner[w["account"]] = w
      KNOWN_SAVED_WINNERS.add(w["account"])
    recent_non_winners = []
    for r in REROLL_STATE["accounts"]:
      acc_k = str(r.get("account") or "")
      if not acc_k:
        continue
      if r.get("isJackpot2x"):
        # Nếu nick này đã từng lưu trong file mà giờ không còn trong restored_winners -> người dùng đã xóa vì bán rồi!
        if acc_k in KNOWN_SAVED_WINNERS and acc_k not in by_winner:
          continue
        if acc_k in by_winner and not r.get("screenshot") and by_winner[acc_k].get("screenshot"):
          r["screenshot"] = by_winner[acc_k]["screenshot"]
        by_winner[acc_k] = r
        KNOWN_SAVED_WINNERS.add(acc_k)
      elif len(recent_non_winners) < 20:
        recent_non_winners.append(r)

    # Đảm bảo nick đã trúng 2x không bao giờ nằm trong REUSABLE_POOL
    for w_acc in KNOWN_SAVED_WINNERS:
      REUSABLE_POOL.pop(w_acc, None)

    winners_only = sorted(
        list(by_winner.values()),
        key=lambda x: (
            int(x.get("serverId") or 0),
            max(int(x.get("dtCount") or 0), int(x.get("tnkCount") or 0), int(x.get("ntCount") or 0)),
            (int(x.get("dtCount") or 0) + int(x.get("tnkCount") or 0) + int(x.get("ntCount") or 0)),
            1 if "Đường Tam Tạng" in (x.get("heroes5Star") or []) else 0,
            str(x.get("time") or ""),
        ),
        reverse=True,
    )
    REROLL_STATE["accounts"] = winners_only + recent_non_winners
    REROLL_STATE["reusableCount"] = len(REUSABLE_POOL)
    pool_snapshot = list(REUSABLE_POOL.values())

  try:
    # 1. Lưu kho phôi tái sử dụng DAN_NICK_DA_QUAY.json (4 trường/dòng)
    tmp_json = REROLL_VAULT_FILE + ".tmp"
    with open(tmp_json, "w", encoding="utf-8") as f:
      f.write("[\n")
      for idx_p, item in enumerate(pool_snapshot):
        comma = "," if idx_p < len(pool_snapshot) - 1 else ""
        line_str = json.dumps(
            {"u": item["u"], "p": item["p"], "id": item["id"], "sid": int(item["sid"])},
            ensure_ascii=False,
        )
        f.write(f"  {line_str}{comma}\n")
      f.write("]\n")
    os.replace(tmp_json, REROLL_VAULT_FILE)

    # 2. Lưu DAN_NICK_TRUNG_TUONG.txt và DANH_SACH_NICK_D_AUTO.txt dạng 1 dòng/nick ngăn cách bằng dấu |
    header_lines = (
        "# =========================================================================================================================\n"
        f"# DANH SÁCH NICK TRÚNG 2x/3x DƯƠNG TIỄN - TÔN NGỘ KHÔNG - NA TRA (TỔNG: {len(winners_only)} NICK) — BÁN NICK NÀO CHỈ CẦN XÓA 1 DÒNG ĐÓ\n"
        "# CẤU TRÚC: USER | PASS | SERVER (SID) | [X2/X3] TƯỚNG TRÚNG | TỔNG 5★ | TƯỚNG 5★ PHỤ | UID NẠP | ẢNH CHỤP | THỜI GIAN\n"
        "# =========================================================================================================================\n"
    )
    body_lines = "\n".join(_format_winner_pipe_line(r) for r in winners_only) + ("\n" if winners_only else "")

    for fname in ("DAN_NICK_TRUNG_TUONG.txt", "DANH_SACH_NICK_D_AUTO.txt"):
      tmp_p = os.path.join(DIRECTORY, fname + ".tmp")
      with open(tmp_p, "w", encoding="utf-8") as f:
        f.write(header_lines + body_lines)
      os.replace(tmp_p, os.path.join(DIRECTORY, fname))

    # 3. Lưu DAN_NICK_TRUNG_TUONG.csv (Chuẩn UTF-8-SIG có BOM để mở trực tiếp bằng Excel tiếng Việt, lọc/thống kê theo cột)
    tmp_csv = os.path.join(DIRECTORY, "DAN_NICK_TRUNG_TUONG.csv.tmp")
    with open(tmp_csv, "w", encoding="utf-8-sig", newline="") as cf:
      writer = csv.writer(cf)
      writer.writerow([
          "Tài Khoản",
          "Mật Khẩu",
          "Server",
          "Mã SID",
          "Tướng Trúng (X2/X3)",
          "Tổng 5 Sao",
          "Tướng 5 Sao Phụ",
          "UID Nạp",
          "Ảnh Thần Tướng",
          "Thời Gian",
      ])
      for r in winners_only:
        h5 = r.get("heroes5Star") or r.get("heroes") or []
        c = Counter(h5)
        other_str = " + ".join([
            f"{k} x{v}" if v > 1 else k
            for k, v in c.items()
            if k not in ("Dương Tiễn", "Tôn Ngộ Không", "Na Tra", "Đường Tam Tạng")
        ]) or "-"
        srv_clean = str(r.get("serverName") or "").replace(" Mới Nhất]", "]")
        sid_val = int(r.get("serverId") or 610065)
        fid = str(r.get("funtapId") or "")
        max_single = max(int(r.get("dtCount") or 0), int(r.get("tnkCount") or 0), int(r.get("ntCount") or 0))
        tier_tag = f"[X{max_single}] " if max_single >= 2 else ""
        badges = list(r.get("targetHeroes") or [])
        dtt_cnt = c.get("Đường Tam Tạng", 0)
        if dtt_cnt >= 1 and not any("Đường Tam Tạng" in b for b in badges):
          badges.append(f"{dtt_cnt}x Đường Tam Tạng")
        writer.writerow([
            r.get("account", ""),
            r.get("password", "tphtd123"),
            srv_clean,
            sid_val,
            tier_tag + " + ".join(badges),
            len(h5),
            other_str,
            fid,
            r.get("screenshot") or "-",
            r.get("time") or "",
        ])
    os.replace(tmp_csv, os.path.join(DIRECTORY, "DAN_NICK_TRUNG_TUONG.csv"))
  except Exception:
    pass


_load_and_migrate_vault()
_save_reroll_files()



def fetch_latest_server_live():
  """Fetches the live server list directly from Funtap API and returns the newest server (highest sid/id)."""
  try:
    url = "https://funtap-xy.ridvqqxa.com/game/getServerList2.php?lst=all&ac=720524013&plt=ios&v=1&platform=funtap&appid=ios"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=6) as resp:
      raw = resp.read().decode("utf-8", errors="ignore")
    arr = json.loads(raw)
    live_map = {}
    for existing in ALL_SERVERS_DATA:
      sid_e = str(existing.get("sid") or "")
      if sid_e:
        live_map[sid_e] = dict(existing)
    if isinstance(arr, list):
      for grp in arr:
        for s in grp.get("all") or []:
          sid_str = str(s.get("sid") or "")
          if sid_str:
            live_map[sid_str] = s
    if live_map:
      max_sid_int = max(int(k) for k in live_map.keys() if k.isdigit())
      # Điền đầy đủ các server trung gian từ 610041 -> max_sid_int nếu API chỉ trả về cụm mới nhất
      for sid_num in range(610041, max_sid_int + 1):
        s_key = str(sid_num)
        if s_key not in live_map:
          srv_idx = sid_num - 610000
          if srv_idx <= 50:
            c_name = f"Lưu Sa Hà-S{srv_idx - 40}"
          elif srv_idx <= 60:
            c_name = f"Ô Kê Quốc-S{srv_idx - 50}"
          else:
            c_name = f"Xa Trì Quốc-S{srv_idx - 60}"
          live_map[s_key] = {
              "sid": s_key,
              "id": srv_idx,
              "name": c_name,
              "server": f"wss://wss-funtap-xy.xinliugame.net:{srv_idx + 9026}/",
              "status": "2",
              "recommend": 0,
          }
      sorted_sids = sorted(live_map.keys(), key=lambda x: int(x) if x.isdigit() else 0, reverse=True)
      new_list = []
      max_sid = sorted_sids[0]
      for sid_str in sorted_sids:
        item = live_map[sid_str]
        srv_id = int(item.get("id") or (int(sid_str) - 610000 if sid_str.isdigit() else 0))
        raw_name = str(item.get("name") or f"Server S{srv_id}")
        clean_base = re.sub(r"^\[S\d+[^\]]*\]\s*", "", raw_name).strip()
        if sid_str == max_sid:
          disp_name = f"[S{srv_id} Mới Nhất] {clean_base}"
        elif srv_id >= 39:
          disp_name = f"[S{srv_id}] {clean_base}"
        else:
          disp_name = clean_base
        cluster_name = clean_base.split("-")[0].strip() if "-" in clean_base else "Lưu Sa Hà"
        ws_srv = str(item.get("server") or f"wss://wss-funtap-xy.xinliugame.net:{srv_id + 9026}/").replace("\\/", "/")
        new_list.append({
            "sid": sid_str,
            "id": srv_id,
            "name": disp_name,
            "server": ws_srv,
            "status": str(item.get("status") or "2"),
            "recommend": int(item.get("recommend") or (1 if sid_str == max_sid else 0)),
            "cluster": cluster_name,
        })
      if new_list:
        ALL_SERVERS_DATA[:] = new_list
        return ALL_SERVERS_DATA[0]
  except Exception:
    pass
  return ALL_SERVERS_DATA[0]


async def _reroll_single_account(reg_info, srv_info, idx_label, seq_num=1):
  acc_id = reg_info["username"]
  acc_pwd = reg_info["password"]
  real_acc_id = reg_info["accountId"]
  access_tok = reg_info.get("accessToken") or "r"
  sid = int(srv_info["sid"])
  ws_url = srv_info["server"]
  srv_name = srv_info["name"]

  def set_step(msg):
    with REROLL_LOCK:
      REROLL_STATE["stepMsg"] = f"[{idx_label}] {acc_id} (ID:{real_acc_id} | {srv_name}): {msg}"

  ak_info = await asyncio.to_thread(fetch_fresh_authkey, real_acc_id, access_tok)
  ts = ak_info["timestamp"]
  ak = ak_info["authKey"]

  json_datas = json.dumps({"gamePlatform": "funtap", "appid": "ios", "pf": "ios_funtap", "phoneSystem": 2})
  login_payload = bytearray()
  login_payload.extend(_pkt_str(f"{sid}-{real_acc_id}"))
  login_payload.extend(struct.pack(">i", int(ts)))
  login_payload.extend(_pkt_str(ak))
  login_payload.extend(_pkt_str("vn"))
  login_payload.extend(_pkt_str(""))
  login_payload.extend(_pkt_str("127.0.0.1"))
  login_payload.extend(_pkt_str(json_datas))
  login_payload.extend(_pkt_str(""))
  login_pkt = _pkt_msg(56, login_payload)

  ctx = ssl.create_default_context()
  ctx.check_hostname = False
  ctx.verify_mode = ssl.CERT_NONE

  heroes_5star = []
  dt_count = 0
  tnk_count = 0
  nt_count = 0
  seen_bag_list = False
  guide_state = {"gid": 0, "code": 0, "done": False}
  guide_ev = asyncio.Event()

  def record_packet(resp):
    nonlocal dt_count, tnk_count, nt_count, seen_bag_list
    if not isinstance(resp, bytes) or len(resp) < 4:
      return
    _, msg_id = struct.unpack(">HH", resp[:4])
    if msg_id == 599:
      if len(resp) >= 5 and resp[4] == 0:
        guide_state["done"] = True
        guide_ev.set()
      elif len(resp) >= 12:
        gid, gcode, _ = struct.unpack(">ihb", resp[5:12])
        guide_state["gid"] = gid
        guide_state["code"] = gcode
        guide_ev.set()
      return
    if msg_id == 38:
      if seen_bag_list:
        return
      seen_bag_list = True
    elif msg_id != 21:
      return
    for h in _parse_hero_packet(resp):
      if h["star"] >= 5:
        heroes_5star.append(h["name"])
      if h["id"] == 1014 or "Dương Tiễn" in h["name"] or h["name_cn"] == "杨戬":
        dt_count += 1
      if h["id"] == 2014 or "Ngộ Không" in h["name"] or h["name_cn"] == "孙悟空":
        tnk_count += 1
      if h["id"] == 1013 or "Na Tra" in h["name"] or h["name_cn"] == "哪吒":
        nt_count += 1

  try:
    async with websockets.connect(ws_url, ssl=ctx, open_timeout=12, ping_interval=None, ping_timeout=None) as ws:
      async def _reader():
        try:
          async for resp in ws:
            record_packet(resp)
        except Exception:
          pass

      reader_task = asyncio.create_task(_reader())
      try:
        set_step("Đang tạo nhân vật & Skip tân thủ...")
        await ws.send(login_pkt)
        await asyncio.sleep(0.26)

        # Đặt tên nhân vật theo đúng username (bỏ dấu '_' thành htdvipa001 để không bao giờ trùng & nhận 100% ngay lập tức)
        clean_role_name = re.sub(r"[^a-zA-Z0-9]", "", acc_id)[:14] or acc_id[:14]
        await ws.send(_pkt_msg(122, _pkt_str(clean_role_name) + b"\x00"))
        await asyncio.sleep(0.18)
        if not seen_bag_list:
          await ws.send(_pkt_msg(122, _pkt_str(f"{clean_role_name[:10]}{random.randint(10, 99)}") + b"\x00"))
          await asyncio.sleep(0.18)
        if guide_state["gid"]:
          await ws.send(_pkt_msg(91, struct.pack(">i", guide_state["gid"])))
          await ws.send(_pkt_msg(598, struct.pack(">i", guide_state["gid"])))
        await asyncio.sleep(0.12)

        for c_idx, code in enumerate(REROLL_GIFTCODES, 1):
          if REROLL_STATE["stopRequested"]:
            break
          if c_idx % 9 == 1 or c_idx == len(REROLL_GIFTCODES):
            set_step(f"Đang nhập 27 Giftcode ({c_idx}/{len(REROLL_GIFTCODES)})...")
          await ws.send(_pkt_msg(143, _pkt_str(code)))
          await asyncio.sleep(0.22)

        set_step("Đang nhận Thư phúc lợi & Mở 250 Mảnh 5★ (5 tướng)...")
        await ws.send(_pkt_msg(64, b"\x01"))
        await ws.send(_pkt_msg(64, b"\x02"))
        await ws.send(_pkt_msg(61))
        await asyncio.sleep(0.32)
        await ws.send(_pkt_msg(61))
        await asyncio.sleep(0.22)

        # Mở 250 mảnh 5★: 100 mảnh 703 (2 tướng) + 100 mảnh 704 Core SSR (2 tướng) + 50 mảnh 1012 (1 tướng)
        for item_id, qty in [(703, 2), (703, 1), (704, 2), (704, 1), (1012, 1)]:
          await ws.send(_pkt_msg(87, struct.pack(">ii", item_id, qty)))
          await asyncio.sleep(0.16)
        await asyncio.sleep(0.18)

        # Nếu chưa mở đủ 5 tướng từ 250 mảnh (do server trễ), mở vét nhanh
        if len(heroes_5star) < 5:
          for retry_code in ("45THANTUONG", "DUONGTIEN", "NGOKHONG", "DAT100KDKT", "DKT50K", "DKT30K", "THANCAN555", "YCAN666"):
            await ws.send(_pkt_msg(143, _pkt_str(retry_code)))
            await asyncio.sleep(0.22)
          await ws.send(_pkt_msg(61))
          await asyncio.sleep(0.28)
          for item_id, qty in [(703, 1), (704, 2), (704, 1), (1012, 1)]:
            await ws.send(_pkt_msg(87, struct.pack(">ii", item_id, qty)))
            await asyncio.sleep(0.16)

        # PHƯƠNG ÁN 3 (VẮT FULL THÔNG MINH 2 TẦNG):
        # Tầng 1: Mọi nick (100%) đều mở 250 mảnh (5 tướng) + xả luôn 1 đơn & 6 lần x10 Thiên Mệnh (61 lượt quay = ~10 tướng 5★, chỉ mất ~3.2s)
        await ws.send(_pkt_msg(1320, b"\x01"))
        await asyncio.sleep(0.08)

        set_step(f"Đang xả 61 lượt Thiên Mệnh (6x10) tìm Dương Tiễn / Ngộ Không (DT:{dt_count} | TNK:{tnk_count})...")
        await ws.send(_pkt_msg(213, struct.pack(">bbb", 1, 1, 1)))
        await asyncio.sleep(0.46)

        for p_idx in range(1, 7):
          if REROLL_STATE["stopRequested"]:
            break
          set_step(f"Đang quay Thiên Mệnh x10 lần {p_idx}/6 (DT:{dt_count} | TNK:{tnk_count})...")
          await ws.send(_pkt_msg(213, struct.pack(">bbb", 1, 2, 1)))
          await asyncio.sleep(0.46)

        await asyncio.sleep(0.18)

        # Tầng 2: Sau 250 mảnh + 61 lượt Thiên Mệnh (~66 tướng), hễ có >= 1 Dương Tiễn hoặc Ngộ Không -> Dồn 100% 14 vé Tam Giới đúng hệ + 7 vé lẻ để chốt 2x/3x!
        if (dt_count + tnk_count) >= 1:
          if dt_count >= tnk_count and dt_count >= 1:
            camp_id = 4
            camp_label = "Hệ Tiên (Chốt 2x/3x Dương Tiễn)"
          else:
            camp_id = 5
            camp_label = "Hệ Yêu (Chốt 2x/3x Tôn Ngộ Không)"

          set_step(f"Đã có phôi! Đang dồn 14 vé Tam Giới vào {camp_label} + vét 7 vé lẻ (DT:{dt_count} | TNK:{tnk_count})...")
          await ws.send(_pkt_msg(213, struct.pack(">bbb", camp_id, 2, 1)))
          await asyncio.sleep(0.48)

          for _ in range(7):
            if REROLL_STATE["stopRequested"]:
              break
            await ws.send(_pkt_msg(213, struct.pack(">bbb", 1, 1, 1)))
            await asyncio.sleep(0.40)
          for _ in range(4):
            if REROLL_STATE["stopRequested"]:
              break
            await ws.send(_pkt_msg(213, struct.pack(">bbb", camp_id, 1, 1)))
            await asyncio.sleep(0.40)

          await asyncio.sleep(0.28)

        # NẾU NICK TRÚNG >= 2x DƯƠNG TIỄN HOẶC >= 2x TÔN NGỘ KHÔNG: Tự động Skip Tân Thủ 100%
        if (dt_count >= 2) or (tnk_count >= 2):
          set_step("🔥 Trúng 2x/3x Dương Tiễn / Ngộ Không! Đang Skip Tân Thủ 100%...")
          await ws.send(_pkt_msg(598, struct.pack(">b", 1)))
          await ws.send(_pkt_msg(598, struct.pack(">b", 0)))
          await ws.send(_pkt_msg(91, struct.pack(">i", 1)))
          if guide_state["gid"]:
            await ws.send(_pkt_msg(598, struct.pack(">i", guide_state["gid"])))
          t_guide_start = time.time()
          while not guide_state["done"] and (time.time() - t_guide_start) < 22.0:
            guide_ev.clear()
            try:
              await asyncio.wait_for(guide_ev.wait(), timeout=0.16)
              if guide_state["done"]:
                break
              gid = guide_state["gid"]
              gcode = guide_state["code"]
              if gid:
                if gcode == 899:
                  await ws.send(_pkt_msg(164, struct.pack(">b", 1) + _pkt_str("") + struct.pack(">bb", 0, 0)))
                elif gcode == 907:
                  await ws.send(_pkt_msg(863, struct.pack(">ibh", 1002, 4, 1)))
                elif gcode == 911:
                  await ws.send(_pkt_msg(863, struct.pack(">ibh", 2004, 5, 1)))
                elif gcode in (44, 46):
                  await ws.send(_pkt_msg(356))
                await ws.send(_pkt_msg(91, struct.pack(">i", gid)))
            except asyncio.TimeoutError:
              if guide_state["gid"]:
                await ws.send(_pkt_msg(598, struct.pack(">i", guide_state["gid"])))
                await ws.send(_pkt_msg(91, struct.pack(">i", guide_state["gid"])))
      finally:
        reader_task.cancel()
  except Exception as e:
    set_step(f"Lỗi kết nối: {e}")

  # CHỈ LẤY NICK NỔ >= 2x DƯƠNG TIỄN HOẶC >= 2x TÔN NGỘ KHÔNG (Kèm hiển thị thêm Na Tra / Đường Tam Tạng nếu có cùng trong nick)
  is_jackpot_2x = (dt_count >= 2) or (tnk_count >= 2)
  dtt_count = heroes_5star.count("Đường Tam Tạng")
  target_badges = []
  if is_jackpot_2x:
    if dt_count >= 1:
      target_badges.append(f"{dt_count}x Dương Tiễn")
    if tnk_count >= 1:
      target_badges.append(f"{tnk_count}x Tôn Ngộ Không")
    if nt_count >= 1:
      target_badges.append(f"{nt_count}x Na Tra")
    if dtt_count >= 1:
      target_badges.append(f"{dtt_count}x Đường Tam Tạng")

  return {
      "account": acc_id,
      "password": acc_pwd,
      "funtapId": real_acc_id,
      "serverId": sid,
      "serverName": srv_name,
      "directLink": f"http://localhost:{PORT}/play?acc={real_acc_id}&sid={sid}&direct=1",
      "screenshot": "",
      "heroes5Star": heroes_5star,
      "dtCount": dt_count,
      "tnkCount": tnk_count,
      "ntCount": nt_count,
      "targetHeroes": target_badges,
      "hasTarget": is_jackpot_2x,
      "isJackpot2x": is_jackpot_2x,
      "time": time.strftime("%Y-%m-%d %H:%M:%S"),
  }


SCREENSHOT_SEMAPHORE = None


async def _capture_winner_screenshot_async(res):
  """Tự động vào mục Thần Tướng, sắp xếp Dương Tiễn / Ngộ Không / Na Tra / Đường Tam Tạng lên Hàng 1 và chụp ảnh bằng chứng."""
  global SCREENSHOT_SEMAPHORE
  if SCREENSHOT_SEMAPHORE is None:
    SCREENSHOT_SEMAPHORE = asyncio.Semaphore(1)
  async with SCREENSHOT_SEMAPHORE:
    try:
      from playwright.async_api import async_playwright
    except ImportError:
      return ""
    acc_name = str(res.get("account") or "nick")
    fid = str(res.get("funtapId") or "")
    sid = int(res.get("serverId") or 610070)
    srv_num = sid - 610000 if sid > 610000 else sid
    rel_path = f"anh_nick_trung/{acc_name}_S{srv_num}.png"
    out_path = os.path.join(DIRECTORY, "anh_nick_trung", f"{acc_name}_S{srv_num}.png")

    chrome_paths = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ]
    exe_path = next((p for p in chrome_paths if os.path.exists(p)), None)
    try:
      async with async_playwright() as p:
        launch_kwargs = {"headless": True, "args": ["--mute-audio", "--disable-gpu-vsync"]}
        if exe_path:
          launch_kwargs["executable_path"] = exe_path
        browser = await p.chromium.launch(**launch_kwargs)
        page = await browser.new_page(viewport={"width": 720, "height": 1280})
        url = f"http://localhost:{PORT}/play_frame?acc={fid}&sid={sid}&direct=1"
        await page.goto(url, wait_until="domcontentloaded", timeout=25000)
        for _ in range(45):
          await asyncio.sleep(0.5)
          cnt = await page.evaluate("() => (window.tt && window.tt.heros) ? window.tt.heros.length : 0")
          if cnt > 0:
            break
        await asyncio.sleep(1.0)
        open_script = """() => {
          if (window.eb && window.eb.getInstance && window.eb.getInstance().inStage()) window.eb.getInstance().close();
          if (window.at) {
            window.at.data = null;
            if (window.at.guide && window.at.guide.close) window.at.guide.close();
          }
          if (window.tt) {
            var priorityWeight = function(h) {
              if (!h) return 0;
              if (h.id === 1014 || (h.name && h.name.indexOf("Dương Tiễn") >= 0)) return 100000;
              if (h.id === 2014 || (h.name && h.name.indexOf("Ngộ Không") >= 0)) return 90000;
              if (h.id === 1013 || (h.name && h.name.indexOf("Na Tra") >= 0)) return 80000;
              if (h.name && h.name.indexOf("Đường Tam Tạng") >= 0) return 70000;
              return (h.star || 0) * 1000 + (h.lv || 1);
            };
            window.tt.combatheroSort = function(a, b) {
              return priorityWeight(b) - priorityWeight(a);
            };
          }
          if (window.si && window.si.getInstance) {
            var heroPanel = window.si.getInstance();
            heroPanel.showLoading = false;
            heroPanel.open(0);
          }
          if (window.HacTayDuAuto) {
            if (window.HacTayDuAuto.layaMenu) window.HacTayDuAuto.layaMenu.visible = false;
            if (window.HacTayDuAuto.layaBtn) window.HacTayDuAuto.layaBtn.visible = false;
          }
        }"""
        await page.evaluate(open_script)
        for _ in range(30):
          await asyncio.sleep(0.4)
          in_stage = await page.evaluate("() => !!(window.si && window.si.getInstance && window.si.getInstance().inStage())")
          if in_stage:
            break
          await page.evaluate(open_script)
        await asyncio.sleep(1.0)
        await page.evaluate("() => { if (window.si && window.si.getInstance) window.si.getInstance().setList(0, 0); }")
        await asyncio.sleep(1.0)
        await page.screenshot(path=out_path)
        await browser.close()
        return rel_path
    except Exception:
      return ""


async def _push_winner_to_sales_bot_async(res):
  """Bơm tự động thông tin tài khoản trúng 2x/3x sang Bot bán hàng (Shop Bot) hoặc Telegram."""
  bot_cfg = APP_CONFIG.get("sales_bot") or {}
  is_enabled = bot_cfg.get("enabled", False)
  webhook_url = str(bot_cfg.get("webhook_url") or "").strip()
  tg_token = str(bot_cfg.get("telegram_bot_token") or "").strip()
  tg_chat = str(bot_cfg.get("telegram_chat_id") or "").strip()

  if not is_enabled and not webhook_url and not tg_token:
    return

  import base64

  snap_path = res.get("screenshot") or ""
  photo_b64 = None
  photo_fn = os.path.basename(snap_path) if snap_path else f"{res.get('account')}.png"
  if snap_path:
    full_snap = os.path.join(DIRECTORY, snap_path) if not os.path.isabs(snap_path) else snap_path
    if os.path.exists(full_snap):
      try:
        with open(full_snap, "rb") as f_img:
          photo_b64 = base64.b64encode(f_img.read()).decode("ascii")
      except Exception:
        pass

  payload = {
      "machine_id": MACHINE_ID,
      "account": res.get("account"),
      "password": res.get("password"),
      "funtap_id": str(res.get("funtapId") or ""),
      "server_id": int(res.get("serverId") or 0),
      "server_name": res.get("serverName") or "",
      "jackpot_type": ", ".join(res.get("targetHeroes") or []) or "2x Thần Tướng",
      "total_5star": len(res.get("heroes5Star") or []),
      "target_heroes": res.get("targetHeroes") or [],
      "heroes_5star": res.get("heroes5Star") or [],
      "screenshot_path": snap_path,
      "screenshot_base64": photo_b64,
      "screenshot_filename": photo_fn,
      "time": res.get("time") or time.strftime("%Y-%m-%d %H:%M:%S"),
  }

  def _do_http_push():
    if webhook_url:
      try:
        data_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        token = str(bot_cfg.get("auth_token") or bot_cfg.get("api_key") or "").strip()
        headers = {"Content-Type": "application/json; charset=utf-8"}
        if token:
          headers["X-Webhook-Secret"] = token
          headers["Authorization"] = f"Bearer {token}"
          headers["X-API-Key"] = token
        req = urllib.request.Request(webhook_url, data=data_bytes, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=10) as resp:
          res_json = {}
          try:
            res_json = json.loads(resp.read().decode("utf-8"))
          except Exception:
            pass
          status_msg = res_json.get("status") or "SUCCESS"
          print(f"🤖 [Bot Bán Hàng] Đã tự động bơm nick {res.get('account')} lên Bot thành công! ({status_msg})", flush=True)
      except Exception as e:
        print(f"⚠️ [Bot Bán Hàng] Lỗi bơm nick {res.get('account')} lên Webhook: {e}", flush=True)

    if tg_token and tg_chat:
      try:
        tg_url = f"https://api.telegram.org/bot{tg_token}/sendMessage"
        tg_text = (
            f"🎉 <b>[NỔ NICK 2x MÁY {MACHINE_ID.upper()}]</b>\n"
            f"🎯 <b>Tướng:</b> {payload['jackpot_type']}\n"
            f"🔑 <b>TK:</b> <code>{payload['account']}</code>\n"
            f"🔒 <b>MK:</b> <code>{payload['password']}</code>\n"
            f"🖥️ <b>Server:</b> {payload['server_name']}\n"
            f"⭐ <b>Tổng 5★:</b> {payload['total_5star']}\n"
            f"🆔 <b>UID:</b> {payload['funtap_id']}\n"
            f"⏰ <b>Giờ:</b> {payload['time']}"
        )
        tg_data = json.dumps({"chat_id": tg_chat, "text": tg_text, "parse_mode": "HTML"}).encode("utf-8")
        req_tg = urllib.request.Request(tg_url, data=tg_data, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req_tg, timeout=6) as resp_tg:
          print(f"🤖 [Telegram Bot] Đã gửi thông báo nick {res.get('account')} vào nhóm Telegram!", flush=True)
      except Exception as e:
        print(f"⚠️ [Telegram Bot] Gửi tin nhắn thất bại: {e}", flush=True)

  try:
    await asyncio.to_thread(_do_http_push)
  except Exception:
    pass


def start_reroll_background(count=1000, sid_str="latest", stop_on_win=False, prefix=None, min_copies=2, clear_old=False):
  if websockets is None:
    return {"ok": False, "error": "Thiếu thư viện websockets (pip install websockets)"}
  base_prefix = _normalize_base_prefix(prefix or ACCOUNT_PREFIX)
  stop_on_win = False  # Luôn chạy xuyên suốt không dừng khi trúng tướng theo yêu cầu

  # Luôn tự động lấy Server Mới Nhất trực tiếp từ API Funtap (không fix cứng mã ID)
  newest_srv = fetch_latest_server_live()
  srv_info = newest_srv
  if sid_str and str(sid_str) not in ("latest", "auto", "0"):
    for s in ALL_SERVERS_DATA:
      if str(s["sid"]) == str(sid_str):
        srv_info = s
        break

  _save_reroll_files()
  with REROLL_LOCK:
    if REROLL_STATE["running"]:
      return {"ok": False, "error": "Hệ thống đang chạy tạo nick & quay tướng rồi!"}
    if clear_old:
      REROLL_STATE["accounts"] = _sync_winners_from_txt()
    REROLL_STATE["running"] = True
    REROLL_STATE["stopRequested"] = False
    REROLL_STATE["currentIdx"] = 0
    REROLL_STATE["totalCount"] = count
    reusable_now = sum(1 for item in REUSABLE_POOL.values() if int(item.get("sid") or 0) < int(srv_info["sid"]))
    REROLL_STATE["stepMsg"] = (
        f"🚀 Đang cày {PARALLEL_REROLL_WORKERS} luồng tại {srv_info['name']} ({srv_info['sid']}) "
        f"[Kho tái sử dụng sẵn có: {reusable_now} nick]..."
    )

  def _worker():
    import concurrent.futures
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=32)
    loop.set_default_executor(executor)

    async def _run_pool():
      nonlocal srv_info, count
      existing_names = set()
      used_funtap_ids = set()
      max_seen_seq = 0
      with REROLL_LOCK:
        IN_FLIGHT_USERS.clear()
        for a in REROLL_STATE["accounts"]:
          acc_s = str(a.get("account") or "")
          if acc_s:
            existing_names.add(acc_s)
            max_seen_seq = max(max_seen_seq, _parse_vip_seq(acc_s, base_prefix))
          if a.get("funtapId"):
            used_funtap_ids.add(str(a.get("funtapId")))
        for u_key, item in REUSABLE_POOL.items():
          existing_names.add(u_key)
          max_seen_seq = max(max_seen_seq, _parse_vip_seq(u_key, base_prefix))
          if item.get("id"):
            used_funtap_ids.add(str(item["id"]))

      num_lock = threading.Lock()
      num_cursor = [max(1, max_seen_seq + 1)]

      def _acquire_or_register_account(target_sid):
        """Ưu tiên 1: Nếu có server mới (sid > phôi cũ) -> Bốc ngay phôi nick cũ chưa quay ở target_sid (0ms).
        Ưu tiên 2: Nếu chưa có server mới -> Nhảy thẳng vào số thứ tự đang dở dang (htd_vip_a_...) chạy tiếp ngay lập tức."""
        target_sid_int = int(target_sid)
        with REROLL_LOCK:
          if REROLL_STATE["stopRequested"]:
            return None
          # Nếu có phôi cũ chưa từng cày ở target_sid -> bốc ngay
          for u_k, item in REUSABLE_POOL.items():
            if u_k not in IN_FLIGHT_USERS and int(item.get("sid") or 0) < target_sid_int and item.get("id"):
              IN_FLIGHT_USERS.add(u_k)
              return {
                  "ok": True,
                  "username": item["u"],
                  "password": item["p"],
                  "accountId": item["id"],
                  "accessToken": "r",
                  "reused": True,
                  "prevSid": int(item.get("sid") or 0),
              }

        # Nếu chưa có server mới -> Đăng ký nick mới tiếp tục con số đang dở dang mà không mất thời gian dò lại kho cũ
        while True:
          with REROLL_LOCK:
            if REROLL_STATE["stopRequested"]:
              return None
          with num_lock:
            while _format_vip_username(base_prefix, num_cursor[0]) in existing_names:
              num_cursor[0] += 1
            cand_name = _format_vip_username(base_prefix, num_cursor[0])
            existing_names.add(cand_name)
            num_cursor[0] += 1
          strong_pwd = _gen_strong_password(10)
          reg = funtap_register_real_account(cand_name, strong_pwd)
          if reg.get("ok"):
            fid = str(reg.get("accountId") or "")
            with num_lock:
              if fid and fid not in used_funtap_ids:
                used_funtap_ids.add(fid)
                with REROLL_LOCK:
                  IN_FLIGHT_USERS.add(cand_name)
                reg["reused"] = False
                return reg

      completed_cnt = 0
      jackpot_cnt = 0
      active_cnt = 0
      next_job_idx = 0
      last_print_ts = [time.time()]
      last_srv_check_ts = [time.time()]

      async def _heartbeat():
        nonlocal srv_info
        while True:
          await asyncio.sleep(4.5)
          with REROLL_LOCK:
            if not REROLL_STATE["running"] or REROLL_STATE["stopRequested"]:
              break
            step_now = REROLL_STATE.get("stepMsg") or ""
          # Tự động quét Server mới mỗi 15 giây ngay trong lúc đang chạy!
          if sid_str in ("latest", "auto", "0", "") and (time.time() - last_srv_check_ts[0] >= 15.0):
            last_srv_check_ts[0] = time.time()
            try:
              latest_cand = await asyncio.to_thread(fetch_latest_server_live)
              if latest_cand and int(latest_cand.get("sid") or 0) > int(srv_info.get("sid") or 0):
                srv_info = latest_cand
                with REROLL_LOCK:
                  reusable_ready = sum(
                      1 for item in REUSABLE_POOL.values() if int(item.get("sid") or 0) < int(srv_info["sid"])
                  )
                print(
                    f"\n🆕 PHÁT HIỆN SERVER MỚI MỞ: {srv_info['name']} ({srv_info['sid']}) "
                    f"=> Tự động chuyển toàn bộ 24 luồng sang Server mới & TÁI SỬ DỤNG NGAY {reusable_ready} phôi nick có sẵn!\n",
                    flush=True,
                )
            except Exception:
              pass
          if time.time() - last_print_ts[0] >= 4.3:
            with REROLL_LOCK:
              rem_pool = sum(
                  1 for u_k, item in REUSABLE_POOL.items()
                  if u_k not in IN_FLIGHT_USERS and int(item.get("sid") or 0) < int(srv_info["sid"])
              )
            print(
                f"⚡ [Đang cày {active_cnt} luồng tại {srv_info['name']} | Phôi sẵn: {rem_pool} | Nổ 2x: {jackpot_cnt}] Đã xong: {completed_cnt}/{count} | {step_now}",
                flush=True,
            )
            last_print_ts[0] = time.time()

      hb_task = asyncio.create_task(_heartbeat())

      async def _worker_loop(worker_id):
        nonlocal completed_cnt, jackpot_cnt, active_cnt, next_job_idx, count, srv_info
        await asyncio.sleep(worker_id * 0.22)
        while True:
          with REROLL_LOCK:
            if REROLL_STATE["stopRequested"]:
              return
          next_job_idx += 1
          idx_order = next_job_idx
          if idx_order > count:
            count += 1000
            with REROLL_LOCK:
              REROLL_STATE["totalCount"] = count
            print(
                f"\n🔄 Đã đạt mốc {idx_order - 1} nick => Tự động mở rộng mốc lên {count} nick (Chạy liên tục không dừng) tại {srv_info['name']}...\n",
                flush=True,
            )

          active_cnt += 1
          try:
            res = None
            reg_info = None
            cur_srv = srv_info
            cur_sid_int = int(cur_srv["sid"])
            for _try_roll in range(2):
              with REROLL_LOCK:
                if REROLL_STATE["stopRequested"]:
                  return
              reg_info = await asyncio.to_thread(_acquire_or_register_account, cur_sid_int)
              if not reg_info:
                return
              try:
                res = await _reroll_single_account(reg_info, cur_srv, f"{idx_order}/{count}", seq_num=idx_order)
              finally:
                with REROLL_LOCK:
                  IN_FLIGHT_USERS.discard(reg_info["username"])
              if res and len(res.get("heroes5Star") or []) >= 4:
                break
              # Nếu phôi cũ đã từng quay ở server này rồi (không nhận lại được mảnh), đánh dấu sid=cur_sid_int để không bốc lại ở server này nữa
              if reg_info.get("reused") and (not res or len(res.get("heroes5Star") or []) == 0):
                with REROLL_LOCK:
                  if reg_info["username"] in REUSABLE_POOL:
                    REUSABLE_POOL[reg_info["username"]]["sid"] = cur_sid_int

            if not res or len(res.get("heroes5Star") or []) == 0:
              continue

            completed_cnt += 1
            last_print_ts[0] = time.time()
            acc_u = res["account"]
            with REROLL_LOCK:
              REROLL_STATE["currentIdx"] = completed_cnt
              REROLL_STATE["currentAcc"] = acc_u
              if res["isJackpot2x"]:
                # Nick đã trúng 2x -> Xóa vĩnh viễn khỏi kho phôi tái sử dụng!
                REUSABLE_POOL.pop(acc_u, None)
              else:
                # Nick chưa trúng 2x -> Lưu/cập nhật vào kho phôi với sid=cur_sid_int để dành cho Server mới tiếp theo!
                REUSABLE_POOL[acc_u] = {
                    "u": acc_u,
                    "p": res["password"],
                    "id": str(res["funtapId"]),
                    "sid": cur_sid_int,
                }
              REROLL_STATE["reusableCount"] = len(REUSABLE_POOL)
              REROLL_STATE["accounts"].insert(0, res)
            _save_reroll_files()

            from collections import Counter
            h_counts = Counter(res["heroes5Star"])
            other_items = [
                f"{k} x{v}" if v > 1 else k
                for k, v in h_counts.items()
                if k not in ("Dương Tiễn", "Tôn Ngộ Không", "Na Tra", "Đường Tam Tạng")
            ]
            other_summary = " + ".join(other_items)
            mode_tag = "♻️ TÁI SỬ DỤNG" if (reg_info and reg_info.get("reused")) else "🆕 ĐK MỚI"
            is_gh = os.environ.get("GITHUB_ACTIONS", "").lower() == "true"
            disp_acc = "***AN_BAO_MAT***" if is_gh else res["account"]
            disp_pwd = "***" if is_gh else res["password"]
            disp_uid = "***" if is_gh else res["funtapId"]
            if res["isJackpot2x"]:
              jackpot_cnt += 1
              # Chụp ảnh mục Thần Tướng (Dương Tiễn / Ngộ Không / Na Tra / Đường Tam Tạng đứng đầu Hàng 1)
              snap_rel = await _capture_winner_screenshot_async(res)
              if snap_rel:
                res["screenshot"] = snap_rel
              print(
                  f"\n{'='*88}\n"
                  f"🔥🔥 [TRÚNG 2x/3x DƯƠNG TIỄN / NGỘ KHÔNG #{jackpot_cnt}] [{completed_cnt:02d}/{count}] ({mode_tag})\n"
                  f"   🎯 TRÚNG TƯỚNG : {', '.join(res['targetHeroes'])}\n"
                  f"   🔑 TÀI KHOẢN   : {disp_acc}   |   MẬT KHẨU: {disp_pwd}   (ID Nạp: {disp_uid})\n"
                  f"   🖥️ MÁY CHỦ     : {res['serverName']}\n"
                  f"   ⭐ TƯỚNG 5★ PHỤ ({len(res['heroes5Star'])} tổng): {other_summary}\n"
                  f"   📸 ẢNH CHỨNG MINH: {snap_rel or 'Đang lưu...'}\n"
                  f"{'='*88}\n",
                  flush=True,
              )
              _save_reroll_files()
              asyncio.create_task(_push_winner_to_sales_bot_async(res))
            else:
              single_info = []
              if res["dtCount"] == 1:
                single_info.append("Dương Tiễn: 1")
              if res["tnkCount"] == 1:
                single_info.append("Tôn Ngộ Không: 1")
              note_str = f"Có {', '.join(single_info)} (Chưa đủ 2x)" if single_info else "Không có DT/TNK (Đã bỏ qua nhanh)"
              print(
                  f"✔ [{completed_cnt:02d}/{count}] [{mode_tag}] [{res['serverName']}] TK: {disp_acc} | MK: {disp_pwd} — {len(res['heroes5Star'])} tướng 5★ ({note_str})",
                  flush=True,
              )
          finally:
            active_cnt -= 1

      workers = [asyncio.create_task(_worker_loop(w_id)) for w_id in range(PARALLEL_REROLL_WORKERS)]
      await asyncio.gather(*workers, return_exceptions=True)
      hb_task.cancel()

      with REROLL_LOCK:
        REROLL_STATE["stepMsg"] = f"🛑 Đã dừng tại {completed_cnt}/{count} nick (Tổng nổ 2x: {jackpot_cnt} nick)."
        final_msg = REROLL_STATE["stepMsg"]
      print(f"\n{'='*88}\n{final_msg}", flush=True)
      print("👉 Bấm [ENTER] tại cửa sổ CMD này (hoặc gõ số lượng như 10000 rồi Enter) để chạy tiếp mẻ mới!", flush=True)
      print("=" * 88, flush=True)

    try:
      loop.run_until_complete(_run_pool())
    finally:
      with REROLL_LOCK:
        REROLL_STATE["running"] = False
      executor.shutdown(wait=False)
      loop.close()

  t = threading.Thread(target=_worker, daemon=True)
  t.start()
  return {"ok": True}



class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
  daemon_threads = True

  def handle_error(self, request, client_address):
    # Bỏ qua lỗi trình duyệt tự ngắt kết nối (WinError 10053 / 10054) để không làm bẩn màn hình CMD
    exc_type, _, _ = sys.exc_info()
    if exc_type and issubclass(exc_type, (ConnectionAbortedError, ConnectionResetError, BrokenPipeError, OSError)):
      return
    super().handle_error(request, client_address)


class DAutoAIRequestHandler(SimpleHTTPRequestHandler):

  def __init__(self, *args, **kwargs):
    super().__init__(*args, directory=DIRECTORY, **kwargs)

  def log_message(self, fmt, *args):
    # Tắt log HTTP tĩnh để màn hình CMD chỉ hiển thị tiến trình đăng ký & quay tướng sạch sẽ
    return

  def guess_type(self, path):
    if path.endswith(".ipa"):
      return "application/octet-stream"
    if path.endswith(".plist"):
      return "application/xml"
    if path.endswith(".json") or path.endswith(".atlas"):
      return "application/json; charset=utf-8"
    if path.endswith(".js"):
      return "application/javascript; charset=utf-8"
    if path.endswith(".png"):
      return "image/png"
    if path.endswith(".jpg") or path.endswith(".jpeg"):
      return "image/jpeg"
    if path.endswith(".woff"):
      return "font/woff"
    return super().guess_type(path)

  def end_headers(self):
    self.send_header("Access-Control-Allow-Origin", "*")
    self.send_header("Access-Control-Allow-Methods", "GET, POST, HEAD, OPTIONS")
    self.send_header("Access-Control-Allow-Headers", "*")
    if (
        not self.path.startswith("/cdn/")
        or "lib.js" in self.path
        or "game.js" in self.path
    ):
      self.send_header(
          "Cache-Control", "no-store, no-cache, must-revalidate, max-age=0"
      )
    super().end_headers()

  def do_OPTIONS(self):
    self.send_response(200)
    self.end_headers()

  def _send_json(self, data, status=200):
    raw = json.dumps(data, ensure_ascii=False).encode("utf-8")
    try:
      self.send_response(status)
      self.send_header("Content-Type", "application/json; charset=utf-8")
      self.send_header("Content-Length", str(len(raw)))
      self.end_headers()
      self.wfile.write(raw)
    except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError, OSError):
      pass

  def do_HEAD(self):
    parsed = urllib.parse.urlparse(self.path)
    clean_path = parsed.path.rstrip(").,;")
    if clean_path in ("/play", "/play_frame"):
      self.send_response(200)
      self.send_header("Content-Type", "text/html; charset=utf-8")
      self.end_headers()
      return
    if clean_path == "/dashboard":
      self.path = "/dashboard.html"
    return super().do_HEAD()

  def do_GET(self):
    parsed = urllib.parse.urlparse(self.path)
    clean_path = parsed.path.rstrip(").,;")
    params = urllib.parse.parse_qs(parsed.query)

    if clean_path == "/favicon.ico":
      self.path = "/icon.png"
      return super().do_GET()

    if clean_path == "/api/state":
      with STATE_LOCK:
        self._send_json(AI_STATE)
      return

    if clean_path == "/api/reroll_status":
      with REROLL_LOCK:
        self._send_json(REROLL_STATE)
      return

    if clean_path == "/api/authkey":
      acc = params.get("acc", ["230519465"])[0]
      tok = params.get("token", ["r"])[0]
      ak = fetch_fresh_authkey(acc, tok)
      self._send_json(ak)
      return

    if clean_path == "/api/check_chars":
      acc = params.get("acc", [""])[0].strip()
      chars = query_account_characters(acc)
      self._send_json({"ok": True, "account": acc, "characters": chars})
      return

    if clean_path == "/api/server_list":
      lst_type = params.get("lst", ["all"])[0]
      acc = params.get("ac", ["230519465"])[0]
      sid = params.get("sid", [None])[0]
      if lst_type == "last":
        self._send_json(build_last_server_list_response(acc, sid))
      else:
        self._send_json(build_all_server_list_response(""))
      return

    if clean_path == "/dashboard":
      self.path = "/dashboard.html"
      return super().do_GET()

    if clean_path in ("/", "/play", "/index.html"):
      self._serve_portrait_shell(parsed.query)
      return

    if clean_path == "/play_frame":
      self._serve_inner_game_frame(parsed.query)
      return

    if clean_path.startswith("/cdn/"):
      rel_asset = clean_path[len("/cdn/") :]
      self._serve_cdn_asset(rel_asset)
      return

    return super().do_GET()

  def do_OPTIONS(self):
    self.send_response(200)
    self.end_headers()

  def do_POST(self):
    parsed = urllib.parse.urlparse(self.path)
    clean_path = parsed.path.rstrip(").,;")
    params = urllib.parse.parse_qs(parsed.query)
    length = int(self.headers.get("Content-Length", "0") or "0")
    body_bytes = self.rfile.read(length) if length > 0 else b"{}"
    try:
      payload = json.loads(body_bytes.decode("utf-8"))
    except Exception:
      payload = {}

    if clean_path == "/api/server_list":
      lst_type = params.get("lst", ["all"])[0]
      acc = params.get("ac", ["720524013"])[0]
      sid = params.get("sid", [None])[0]
      if lst_type == "last":
        self._send_json(build_last_server_list_response(acc, sid))
      else:
        self._send_json(build_all_server_list_response(""))
      return

    if clean_path == "/api/funtap_login":
      user = payload.get("username") or payload.get("email") or ""
      pw = payload.get("password") or ""
      res = funtap_login_authenticate(user, pw)
      self._send_json(res)
      return

    if clean_path == "/api/reroll_start":
      cnt = int(payload.get("count") or 1000)
      sid_val = str(payload.get("sid") or "latest")
      stop_win = bool(payload.get("stopOnWin", True))
      prefix = str(payload.get("prefix") or "tphtd").strip()
      min_copies = int(payload.get("minCopies") or 2)
      clear_old = bool(payload.get("clearOld", False))
      res = start_reroll_background(
          count=cnt,
          sid_str=sid_val,
          stop_on_win=stop_win,
          prefix=prefix,
          min_copies=min_copies,
          clear_old=clear_old,
      )
      self._send_json(res)
      return

    if clean_path == "/api/reroll_stop":
      with REROLL_LOCK:
        REROLL_STATE["stopRequested"] = True
        REROLL_STATE["stepMsg"] = "⏳ Đang dừng sau khi hoàn tất nick hiện tại..."
      self._send_json({"ok": True})
      return

    if clean_path == "/api/telemetry":
      now_ms = int(time.time() * 1000)
      is_conn = (
          bool(payload.get("isConnect"))
          or int(payload.get("lv") or 0) > 0
          or int(payload.get("zhandouli") or 0) > 0
      )
      with STATE_LOCK:
        last_conn_ms = int(AI_STATE.get("lastConnectedUpdate") or 0)
        if (
            not is_conn
            and (now_ms - last_conn_ms < 12000)
            and int(AI_STATE.get("level") or 0) > 1
        ):
          self._send_json({"ok": True, "commands": []})
          return

        if is_conn:
          AI_STATE["lastConnectedUpdate"] = now_ms

        for k, v in payload.items():
          if v is not None and v != "" and k != "aiLogs":
            if (
                k in ("topHeroes", "ownedTamThanh")
                and isinstance(v, list)
                and len(v) == 0
                and len(AI_STATE.get(k) or []) > 0
                and not is_conn
            ):
              continue
            AI_STATE[k] = v
        if payload.get("lv"):
          AI_STATE["level"] = payload["lv"]
        if payload.get("zhandouli"):
          AI_STATE["combatPower"] = payload["zhandouli"]
        if payload.get("topHeroes") is not None and (
            len(payload["topHeroes"]) > 0 or is_conn
        ):
          AI_STATE["totalHeroes"] = len(payload["topHeroes"])
        if payload.get("aiLogs"):
          for lg in reversed(payload["aiLogs"][:5]):
            if lg not in AI_STATE.setdefault("aiLogs", []):
              AI_STATE["aiLogs"].insert(0, lg)
          if len(AI_STATE["aiLogs"]) > 45:
            del AI_STATE["aiLogs"][45:]

        AI_STATE["lastUpdate"] = now_ms
        cmds = list(COMMAND_QUEUE)
        COMMAND_QUEUE.clear()

        try:
          with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(AI_STATE, f, ensure_ascii=False, indent=2)
        except Exception:
          pass

      self._send_json({"ok": True, "commands": cmds})
      return

    if clean_path == "/api/command":
      cmd = payload.get("cmd")
      cmd_arg = payload.get("arg") or payload.get("payload") or ""
      if cmd:
        with STATE_LOCK:
          COMMAND_QUEUE.append(
              {"cmd": cmd, "arg": cmd_arg, "ts": int(time.time())}
          )
          add_brain_log(f"Thực thi lệnh: {cmd}")
      self._send_json(
          {"ok": True, "queued": cmd, "queueLen": len(COMMAND_QUEUE)}
      )
      return

    self._send_json({"error": "Not found"}, status=404)

  def _serve_portrait_shell(self, query_str):
    """Serves the outer Portrait Shell (9:16 Màn Dọc Phone Frame + Main Account Login Panel)."""
    options_html = []
    for s in ALL_SERVERS_DATA:
      val = f"{s['sid']}|{s['id']}|{s['name']}|{s['server']}"
      sel = ' selected="selected"' if s["sid"] == "610046" else ""
      label_prefix = f"[S{s['id']}] "
      options_html.append(
          f'<option value="{val}"{sel}>{label_prefix}{s["name"]} ({s["sid"]})</option>'
      )
    server_options_str = "\n".join(options_html)

    html = f"""<!DOCTYPE html>
<html lang="vi">
<head>
  <meta charset="utf-8" />
  <title>Hắc Tây Du — Chơi Web Màn Dọc (9:16) + Đăng Nhập TK Chính S39 • D-AUTO v7.9</title>
  <meta name="viewport" content="width=device-width,initial-scale=1.0,minimum-scale=1.0,maximum-scale=1.0,user-scalable=no" />
  <style>
    * {{ box-sizing: border-box; }}
    html, body {{
      width: 100%; height: 100%; margin: 0; padding: 0;
      overflow: hidden; background: radial-gradient(circle at center, #0F172A 0%, #050811 100%);
      color: #F8FAFC; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    }}
    .app-layout {{
      display: flex; align-items: center; justify-content: center;
      width: 100vw; height: 100vh; gap: 18px; padding: 8px;
    }}
    /* Khung Màn Dọc 9:16 Chuẩn Điện Thoại (Không bao giờ nằm ngang) */
    .phone-shell {{
      position: relative;
      height: 98vh;
      width: calc(98vh * 9 / 16);
      min-width: 340px;
      max-width: 56.25vh;
      max-height: 100vh;
      background: #000;
      border-radius: 22px;
      border: 2.5px solid #10B981;
      box-shadow: 0 20px 60px rgba(0,0,0,0.85), 0 0 25px rgba(16,185,129,0.22);
      overflow: hidden;
      flex-shrink: 0;
    }}
    #gameFrame {{
      width: 100%; height: 100%; border: none; display: block; background: #000;
    }}
    /* Bảng Điều Khiển & Login TK Chính bên cạnh */
    .side-panel {{
      width: 380px; max-height: 96vh; overflow-y: auto;
      background: rgba(11, 17, 30, 0.96);
      border: 1.5px solid #10B981;
      border-radius: 18px; padding: 15px;
      box-shadow: 0 16px 40px rgba(0,0,0,0.75);
      display: flex; flex-direction: column; gap: 11px;
    }}
    .side-panel.hidden {{ display: none; }}
    .panel-header {{
      display: flex; align-items: center; justify-content: space-between;
      border-bottom: 1px solid #1E293B; padding-bottom: 8px;
    }}
    .panel-title {{ font-size: 14.5px; font-weight: 800; color: #34D399; }}
    .card-box {{
      background: #0F172A; border: 1px solid #1E293B; border-radius: 12px;
      padding: 11px; display: flex; flex-direction: column; gap: 7px;
    }}
    .card-title {{
      font-size: 12.5px; font-weight: 800; color: #FBBF24;
      display: flex; align-items: center; gap: 6px;
    }}
    .guide-tip {{
      font-size: 11.5px; color: #CBD5E1; line-height: 1.42;
      background: rgba(30, 41, 59, 0.65); padding: 7px 9px; border-radius: 8px;
      border-left: 3px solid #38BDF8;
    }}
    .inp {{
      width: 100%; background: #070B14; color: #F8FAFC;
      border: 1px solid #334155; border-radius: 8px;
      padding: 8px 10px; font-size: 13px; font-weight: 600; outline: none;
    }}
    .inp:focus {{ border-color: #10B981; }}
    .btn {{
      width: 100%; border: none; border-radius: 9px; padding: 9px 12px;
      font-size: 12.5px; font-weight: 800; cursor: pointer; color: #fff;
      transition: opacity 0.15s; text-align: center;
    }}
    .btn:hover {{ opacity: 0.92; }}
    .btn-green {{ background: linear-gradient(135deg, #059669, #10B981); }}
    .btn-blue {{ background: linear-gradient(135deg, #0284C7, #38BDF8); }}
    .btn-amber {{ background: linear-gradient(135deg, #D97706, #F59E0B); }}
    .btn-slate {{ background: #1E293B; color: #CBD5E1; border: 1px solid #334155; }}
    .btn-row {{ display: flex; gap: 6px; }}
    .chip-list {{ display: flex; flex-wrap: wrap; gap: 5px; }}
    .chip {{
      background: #1E293B; color: #38BDF8; border: 1px solid #334155;
      border-radius: 6px; padding: 4px 8px; font-size: 11px; font-weight: 700;
      cursor: pointer; user-select: none;
    }}
    .chip:hover {{ background: #0F172A; border-color: #38BDF8; }}
    .status-msg {{
      font-size: 12px; line-height: 1.45; padding: 8px 10px;
      border-radius: 8px; background: rgba(16, 185, 129, 0.12);
      border: 1px solid rgba(16, 185, 129, 0.35); color: #A7F3D0;
      display: none;
    }}
    .char-item {{
      background: rgba(15, 23, 42, 0.9); border: 1px solid #10B981;
      border-radius: 8px; padding: 7px 9px; margin-top: 4px;
      display: flex; align-items: center; justify-content: space-between;
      font-size: 11.5px; cursor: pointer;
    }}
    .char-item:hover {{ background: rgba(16, 185, 129, 0.18); }}
    #floatingToggleBtn {{
      position: fixed; top: 10px; right: 10px; z-index: 999999;
      background: rgba(9, 13, 22, 0.92); color: #34D399;
      border: 1.5px solid #10B981; border-radius: 10px;
      padding: 7px 12px; font-size: 12px; font-weight: 800;
      cursor: pointer; box-shadow: 0 6px 20px rgba(0,0,0,0.7);
    }}
    @media (max-width: 768px) {{
      .app-layout {{ padding: 0; gap: 0; }}
      .phone-shell {{
        width: 100vw; max-width: 100vw; height: 100vh; border-radius: 0; border: none;
      }}
      .side-panel {{
        position: fixed; top: 48px; right: 8px; left: 8px; width: auto; z-index: 999998;
      }}
    }}
  </style>
</head>
<body>
  <button id="floatingToggleBtn" onclick="togglePanel()">🔑 ĐĂNG NHẬP TK THẬT / S39</button>

  <div class="app-layout">
    <!-- KHUNG GAME MÀN DỌC 9:16 CHUẨN -->
    <div class="phone-shell">
      <iframe id="gameFrame" src="/play_frame" allow="autoplay; fullscreen"></iframe>
    </div>

    <!-- BẢNG ĐĂNG NHẬP TK THẬT FUNTAP & CHỌN SERVER S39 -->
    <div id="sidePanel" class="side-panel">
      <div class="panel-header">
        <div class="panel-title">📱 HẮC TÂY DU — MÀN DỌC 9:16 (v7.9)</div>
        <button class="btn btn-slate" style="width:auto;padding:4px 9px;font-size:11px;" onclick="togglePanel()">Thu gọn</button>
      </div>

      <div id="statusBox" class="status-msg"></div>

      <!-- 0. TÍCH HỢP TRỰC TIẾP: TẠO DÀN NICK & SĂN 2x DƯƠNG TIỄN / 2x NGỘ KHÔNG (8 LUỒNG SONG SONG) -->
      <div class="card-box" style="border-color:#F59E0B;background:linear-gradient(180deg,#131C31 0%,#0B1120 100%);">
        <div class="card-title" style="color:#FBBF24;">🎰 Tự Động Săn 2x Dương Tiễn / 2x Ngộ Không (8 Luồng)</div>
        <div class="guide-tip" style="border-left-color:#F59E0B;font-size:11px;">
          Mỗi nick tự động: <b>27 Code VIP</b> ➜ <b>Mở 250 mảnh 5★ (5 tướng)</b> ➜ <b>68 lượt Thiên Mệnh</b> + <b>Dồn 14 vé Tam Giới</b> săn cặp <b>2x Dương Tiễn</b> hoặc <b>2x Ngộ Không</b>.
        </div>
        <div class="btn-row" style="align-items:center;">
          <input id="inpRerollPrefix" class="inp" style="width:36%;color:#38BDF8;" value="htd_vip" placeholder="Tên: htd_vip" title="Tiền tố đặt tên nick (VD: htd_vip -> htd_vip_a_001..999)" />
          <select id="selRerollCount" class="inp" style="width:34%;color:#FBBF24;">
            <option value="50">50 Nick</option>
            <option value="100">100 Nick</option>
            <option value="300">300 Nick</option>
            <option value="500">500 Nick</option>
            <option value="1000" selected="selected">1000 Nick</option>
            <option value="2000">2000 Nick</option>
            <option value="5000">5000 Nick</option>
          </select>
          <select id="selMinCopies" class="inp" style="width:30%;color:#34D399;">
            <option value="2" selected="selected">Mục tiêu: 2x</option>
            <option value="1">Mục tiêu: 1x</option>
          </select>
        </div>
        <div class="btn-row" style="align-items:center;justify-content:space-between;">
          <label style="font-size:11.5px;color:#E2E8F0;display:flex;align-items:center;gap:4px;cursor:pointer;">
            <input id="chkStopOnWin" type="checkbox" checked="checked" /> Tự dừng ngay khi nổ đủ mục tiêu (2x DT / 2x TNK)
          </label>
        </div>
        <div class="btn-row">
          <button id="btnStartReroll" class="btn btn-amber" onclick="startWebReroll()">🔥 BẮT ĐẦU SĂN 2x DT / 2x TNK</button>
          <button id="btnStopReroll" class="btn btn-slate" style="width:90px;display:none;border-color:#EF4444;color:#FCA5A5;" onclick="stopWebReroll()">🛑 DỪNG</button>
        </div>
        <div id="rerollStepBox" style="font-size:11.5px;color:#38BDF8;background:#070B14;padding:6px 8px;border-radius:7px;border:1px solid #1E293B;">
          ⚡ Sẵn sàng tạo dàn nick & quay tướng!
        </div>
        <div id="rerollAccountsBox" style="max-height:210px;overflow-y:auto;display:flex;flex-direction:column;gap:5px;"></div>
      </div>

      <!-- CÁCH 1: VÀO NICK THẬT S39 BẰNG ID NẠP TRONG AVATAR (DÙNG CHO MỌI NICK GOOGLE/FB/APPLE/FUNTAP) -->
      <div class="card-box" style="border-color:#10B981;">
        <div class="card-title">🎯 Cách 1: Vào TK Thật S39 bằng "ID Nạp" (100% chuẩn cho Google/FB/Apple/FunID)</div>
        <div class="guide-tip">
          👉 Trên điện thoại đang ở nick chính <b>S39</b>, anh bấm vào <b>Avatar nhân vật (góc trái trên cùng)</b>:<br/>
          • Nhìn dòng <b>ID Nạp:</b> <code style="color:#FBBF24;">xxxxxxxxx</code> (hoặc <b>ID:</b> <code style="color:#38BDF8;">610039-xxxxxxxxx</code>).<br/>
          • Gõ/dán mã số đó vào ô dưới đây rồi bấm <b>[🚀 VÀO THẲNG SERVER ĐÃ CHỌN]</b> là vào đúng nick chính!
        </div>
        <input id="inpAcc" class="inp" type="text" placeholder="Nhập ID Nạp (VD: 720524013 hoặc 610039-xxxx)..." />
        <div class="chip-list">
          <span class="chip" onclick="pickQuickAcc('610008-720325781')" style="border-color:#F59E0B;color:#FBBF24;">🔥 720325781 (Smile Lv.35 - S8)</span>
          <span class="chip" onclick="pickQuickAcc('720524013')" style="border-color:#10B981;color:#34D399;">👑 720524013 (PhíSát - S39)</span>
          <span class="chip" onclick="pickQuickAcc('720452341')">🆔 720452341</span>
          <span class="chip" onclick="pickQuickAcc('386576319')">🆔 386576319</span>
          <span class="chip" onclick="pickQuickAcc('230519465')">🆔 230519465</span>
          <span class="chip" onclick="syncFromIphone()" style="color:#34D399;border-color:#10B981;">📲 Đồng bộ từ iPhone</span>
        </div>
      </div>

      <!-- CÁCH 2: ĐĂNG NHẬP TÀI KHOẢN FUNTAP (EMAIL / TÊN ĐN + MẬT KHẨU) -->
      <div class="card-box">
        <div class="card-title">🔑 Cách 2: Đăng nhập bằng TK / Email & Mật khẩu Funtap</div>
        <input id="ftUser" class="inp" type="text" placeholder="Tài khoản / Email / SĐT Funtap..." />
        <input id="ftPass" class="inp" type="password" placeholder="Mật khẩu Funtap..." />
        <button id="btnFtLogin" class="btn btn-green" onclick="doFuntapLogin()">🔑 ĐĂNG NHẬP FUNTAP & LẤY ID VÀO S39</button>
        <div id="charListContainer"></div>
      </div>

      <!-- 3. CHỌN MÁY CHỦ (MẶC ĐỊNH S39 - HOÀNG PHONG LĨNH S9) & VÀO GAME -->
      <div class="card-box">
        <div class="card-title">🖥️ 3. Máy Chủ Đang Chọn (Đầy đủ S1 → S39)</div>
        <select id="selSrv" class="inp" style="color:#38BDF8;">
          {server_options_str}
        </select>
        <div class="btn-row">
          <button class="btn btn-green" onclick="enterGameNow(1)">🚀 VÀO THẲNG SERVER ĐÃ CHỌN</button>
          <button class="btn btn-blue" onclick="enterGameNow(0)" title="Mở màn hình Chọn Server trong game">🖥️ MÀN HÌNH ĐĂNG NHẬP GAME</button>
        </div>
        <button class="btn btn-amber" onclick="randomNewAccount()">🎲 TẠO NICK MỚI NGẪU NHIÊN TRÊN SERVER NÀY</button>
      </div>
    </div>
  </div>

  <script>
    var savedAcc = localStorage.getItem("DAUTO_WEB_ACC") || "720524013";
    var savedSrv = localStorage.getItem("DAUTO_WEB_SRV_S46") || "610046|46|[S46 Mới Nhất] Lưu Sa Hà-S6|wss://wss-funtap-xy.xinliugame.net:9072/";
    var savedFtUser = localStorage.getItem("DAUTO_FT_USER") || "";

    document.getElementById("inpAcc").value = savedAcc;
    if (savedFtUser) document.getElementById("ftUser").value = savedFtUser;

    var selEl = document.getElementById("selSrv");
    for (var i = 0; i < selEl.options.length; i++) {{
      if (selEl.options[i].value === savedSrv || selEl.options[i].value.indexOf(savedSrv.split("|")[0] + "|") === 0) {{
        selEl.selectedIndex = i;
        break;
      }}
    }}

    function showStatus(msg, isErr) {{
      var box = document.getElementById("statusBox");
      box.style.display = "block";
      box.style.background = isErr ? "rgba(239, 68, 68, 0.15)" : "rgba(16, 185, 129, 0.14)";
      box.style.borderColor = isErr ? "#EF4444" : "#10B981";
      box.style.color = isErr ? "#FCA5A5" : "#A7F3D0";
      box.innerHTML = msg;
    }}

    function togglePanel() {{
      var p = document.getElementById("sidePanel");
      p.classList.toggle("hidden");
    }}

    function selectServerBySid(sid) {{
      var sel = document.getElementById("selSrv");
      for (var i = 0; i < sel.options.length; i++) {{
        if (sel.options[i].value.indexOf(String(sid) + "|") === 0) {{
          sel.selectedIndex = i;
          localStorage.setItem("DAUTO_WEB_SRV", sel.options[i].value);
          return;
        }}
      }}
    }}

    function normalizeAccInput(rawStr) {{
      var s = (rawStr || "").trim();
      // If user pasted "Hoàng Phong Lĩnh-S9:Name:610039-720452341" from Avatar Copy button
      if (s.indexOf(":") >= 0) {{
        var colonParts = s.split(":");
        s = colonParts[colonParts.length - 1].trim();
      }}
      // If user pasted "610039-720452341"
      var m = s.match(/^(6100\\d\\d)-(.+)$/);
      if (m) {{
        selectServerBySid(m[1]);
        s = m[2].trim();
      }}
      return s;
    }}

    function pickQuickAcc(acc) {{
      var cleanAcc = normalizeAccInput(acc);
      document.getElementById("inpAcc").value = cleanAcc;
      localStorage.setItem("DAUTO_WEB_ACC", cleanAcc);
      enterGameNow(1);
    }}

    function renderCharList(chars, extraIds) {{
      var box = document.getElementById("charListContainer");
      var html = "";
      if (chars && chars.length > 0) {{
        for (var i = 0; i < chars.length; i++) {{
          var c = chars[i];
          html += '<div class="char-item" onclick="loginSpecificChar(\\'' + c.account + '\\', \\'' + c.sid + '\\')">' +
                  '<div><b>👤 ' + c.roleName + '</b> (Lv.' + c.roleLv + ')<br/><span style="color:#38BDF8">' + c.serverName + '</span></div>' +
                  '<span style="color:#34D399;font-weight:800;">Vào ngay ▶</span></div>';
        }}
      }}
      if (extraIds && extraIds.length > 0) {{
        html += '<div style="margin-top:6px;font-size:11px;color:#94A3B8;">Bấm thử đổi sang mã ID khác của TK này: ';
        for (var j = 0; j < extraIds.length; j++) {{
          var eid = extraIds[j];
          html += '<span class="chip" style="margin-right:4px;" onclick="pickQuickAcc(\\'' + eid.id + '\\')">' + eid.label + ': ' + eid.id + '</span>';
        }}
        html += '</div>';
      }}
      box.innerHTML = html;
    }}

    function loginSpecificChar(acc, sid) {{
      document.getElementById("inpAcc").value = acc;
      selectServerBySid(sid);
      enterGameNow(1);
    }}

    function doFuntapLogin() {{
      var u = (document.getElementById("ftUser").value || "").trim();
      var p = (document.getElementById("ftPass").value || "").trim();
      if (!u || !p) {{
        showStatus("⚠️ Vui lòng nhập Tài khoản/Email và Mật khẩu Funtap!", true);
        return;
      }}
      localStorage.setItem("DAUTO_FT_USER", u);
      var btn = document.getElementById("btnFtLogin");
      btn.textContent = "⏳ ĐANG XÁC THỰC FUNTAP...";
      fetch("/api/funtap_login", {{
        method: "POST",
        headers: {{ "Content-Type": "application/json" }},
        body: JSON.stringify({{ username: u, password: p }})
      }})
        .then(function(r) {{ return r.json(); }})
        .then(function(res) {{
          btn.textContent = "🔑 ĐĂNG NHẬP FUNTAP & LẤY ID VÀO S39";
          if (!res || !res.ok) {{
            showStatus("❌ " + ((res && res.error) ? res.error : "Đăng nhập thất bại!"), true);
            return;
          }}
          var accId = res.accountId;
          document.getElementById("inpAcc").value = accId;
          localStorage.setItem("DAUTO_WEB_ACC", accId);
          if (res.accessToken) localStorage.setItem("DAUTO_WEB_TOKEN", res.accessToken);

          var extraIds = [
            {{ label: "ID Nạp (AccountID)", id: res.montarAccountId }},
            {{ label: "FunID", id: res.funId }}
          ];
          renderCharList(res.characters || [], extraIds);

          if (res.characters && res.characters.length > 0) {{
            var firstChar = res.characters[0];
            selectServerBySid(firstChar.sid);
            showStatus("✅ Đăng nhập thành công <b>" + res.username + "</b>! Đã vào nhân vật <b>" + firstChar.roleName + " (Lv." + firstChar.roleLv + ")</b> tại <b>" + firstChar.serverName + "</b>.", false);
            enterGameNow(1);
          }} else {{
            showStatus("✅ Đăng nhập Funtap thành công: <b>" + res.username + "</b> (ID Nạp: <b>" + res.montarAccountId + "</b> | FunID: <b>" + res.funId + "</b>). Đang kết nối vào Server đã chọn...", false);
            enterGameNow(1);
          }}
        }})
        .catch(function(err) {{
          btn.textContent = "🔑 ĐĂNG NHẬP FUNTAP & LẤY ID VÀO S39";
          showStatus("❌ Lỗi kết nối tới máy chủ xác thực: " + err.message, true);
        }});
    }}

    function syncFromIphone() {{
      fetch("/api/state")
        .then(function(r) {{ return r.json(); }})
        .then(function(st) {{
          if (st && st.account) {{
            document.getElementById("inpAcc").value = st.account;
            if (st.serverId) selectServerBySid(st.serverId);
            showStatus("📲 Đã đồng bộ TK <b>" + st.account + "</b> (" + (st.roleName || "Nhân vật") + " - " + (st.serverName || "S39") + ")!", false);
            enterGameNow(1);
          }}
        }});
    }}

    function enterGameNow(directMode) {{
      var rawInput = document.getElementById("inpAcc").value || "";
      var acc = normalizeAccInput(rawInput);
      document.getElementById("inpAcc").value = acc;
      if (!acc) {{
        showStatus("⚠️ Vui lòng nhập ID Nạp hoặc Tên Tài Khoản!", true);
        return;
      }}
      var srvRaw = document.getElementById("selSrv").value;
      localStorage.setItem("DAUTO_WEB_ACC", acc);
      localStorage.setItem("DAUTO_WEB_SRV", srvRaw);

      var parts = srvRaw.split("|");
      var sid = parts[0] || "610039";
      var srvName = parts[2] || "Hoàng Phong Lĩnh-S9";
      showStatus("🚀 Đang vào <b>" + srvName + "</b> với ID Tài Khoản: <b>" + acc + "</b>...", false);

      var frame = document.getElementById("gameFrame");
      frame.src = "/play_frame?acc=" + encodeURIComponent(acc) +
                  "&sid=" + encodeURIComponent(sid) +
                  "&direct=" + (directMode ? "1" : "0") +
                  "&t=" + Date.now();
    }}

    function randomNewAccount() {{
      var rnd = "htdvip_" + Math.floor(10000 + Math.random() * 89999);
      document.getElementById("inpAcc").value = rnd;
      enterGameNow(1);
    }}

    function startWebReroll() {{
      var cnt = parseInt(document.getElementById("selRerollCount").value || "1000", 10);
      var prefix = (document.getElementById("inpRerollPrefix").value || "tphtd").trim();
      var minCopies = parseInt(document.getElementById("selMinCopies").value || "2", 10);
      var stopWin = document.getElementById("chkStopOnWin").checked;
      var srvRaw = document.getElementById("selSrv").value || "";
      var sid = srvRaw.split("|")[0] || "610046";
      if (sid === "610039") sid = "610046";
      fetch("/api/reroll_start", {{
        method: "POST",
        headers: {{ "Content-Type": "application/json" }},
        body: JSON.stringify({{ count: cnt, sid: sid, stopOnWin: stopWin, prefix: prefix, minCopies: minCopies }})
      }})
        .then(function(r) {{ return r.json(); }})
        .then(function(res) {{
          if (!res || !res.ok) {{
            showStatus("⚠️ " + ((res && res.error) ? res.error : "Không thể bắt đầu!"), true);
          }} else {{
            pollRerollStatus();
          }}
        }});
    }}

    function stopWebReroll() {{
      fetch("/api/reroll_stop", {{ method: "POST" }})
        .then(function() {{ pollRerollStatus(); }});
    }}

    function pollRerollStatus() {{
      fetch("/api/reroll_status")
        .then(function(r) {{ return r.json(); }})
        .then(function(st) {{
          if (!st) return;
          var stepEl = document.getElementById("rerollStepBox");
          var btnStart = document.getElementById("btnStartReroll");
          var btnStop = document.getElementById("btnStopReroll");
          if (stepEl && st.stepMsg) {{
            var progTxt = st.running ? ("[" + (st.currentIdx || 0) + "/" + (st.totalCount || 0) + " nick] ") : "";
            stepEl.textContent = (st.running ? "⏳ " : "⚡ ") + progTxt + st.stepMsg;
            stepEl.style.color = st.running ? "#FBBF24" : "#34D399";
          }}
          if (btnStart && btnStop) {{
            btnStart.style.display = st.running ? "none" : "block";
            btnStop.style.display = st.running ? "block" : "none";
          }}
          var listEl = document.getElementById("rerollAccountsBox");
          if (listEl && Array.isArray(st.accounts)) {{
            var html = "";
            for (var i = 0; i < st.accounts.length; i++) {{
              var a = st.accounts[i];
              var h5 = a.heroes5Star || a.heroes || [];
              var is2x = !!a.isJackpot2x;
              var is1x = !!a.hasTarget && !is2x;
              var borderCol = is2x ? "#EF4444" : (is1x ? "#F59E0B" : "#1E293B");
              var bgCol = is2x ? "rgba(239, 68, 68, 0.22)" : (is1x ? "rgba(245, 158, 11, 0.14)" : "rgba(15, 23, 42, 0.85)");
              var winBadge = is2x
                ? '<span style="color:#FBBF24;font-weight:900;font-size:11.5px;">🔥🔥 NỔ CẶP 2x: ' + (a.targetHeroes || []).join(" + ") + '</span><br/>'
                : (is1x
                    ? '<span style="color:#34D399;font-weight:800;">⭐ CÓ 1x: ' + (a.targetHeroes || []).join(" + ") + '</span><br/>'
                    : '');
              var loginAccId = a.funtapId || a.account;
              html += '<div style="background:' + bgCol + ';border:1.5px solid ' + borderCol + ';border-radius:8px;padding:6px 8px;font-size:11px;display:flex;align-items:center;justify-content:space-between;gap:6px;">' +
                      '<div style="flex:1;min-width:0;">' +
                      winBadge +
                      '<b>👤 TK: ' + a.account + '</b> <span style="color:#FBBF24;">(MK: ' + (a.password || 'tphtd123') + ')</span> <span style="color:#94A3B8;">[' + (a.serverName || 'S46') + ']</span><br/>' +
                      '<span style="color:#CBD5E1;">5★ (' + h5.length + '): ' + (h5.join(", ") || "Chưa mở") + '</span>' +
                      '</div>' +
                      '<button class="btn btn-green" style="width:auto;padding:5px 8px;font-size:11px;flex-shrink:0;" onclick="loginSpecificChar(\\'' + loginAccId + '\\', \\'' + (a.serverId || 610046) + '\\')">🚀 Vào Chơi</button>' +
                      '</div>';
            }}
            listEl.innerHTML = html;
          }}
        }})
        .catch(function() {{}});
    }}
    setInterval(pollRerollStatus, 1200);
    pollRerollStatus();

    // Khởi tạo frame với tài khoản & server từ URL query hoặc đã lưu
    (function initBootFrame() {{
      var qs = new URLSearchParams(window.location.search);
      var qAcc = (qs.get("acc") || "").trim();
      var qSid = (qs.get("sid") || "").trim();
      var qDirect = qs.get("direct");
      var parts = savedSrv.split("|");
      var sid = qSid || parts[0] || "610008";
      var accToLoad = qAcc || savedAcc;
      if (qAcc) {{
        document.getElementById("inpAcc").value = qAcc;
        localStorage.setItem("DAUTO_WEB_ACC", qAcc);
      }}
      if (qSid) {{
        selectServerBySid(qSid);
      }}
      var dirFlag = (qDirect !== null && qDirect !== "") ? qDirect : "0";
      document.getElementById("gameFrame").src =
        "/play_frame?acc=" + encodeURIComponent(accToLoad) +
        "&sid=" + encodeURIComponent(sid) +
        "&direct=" + encodeURIComponent(dirFlag) +
        "&t=" + Date.now();
    }})();
  </script>
</body>
</html>"""
    raw = html.encode("utf-8")
    self.send_response(200)
    self.send_header("Content-Type", "text/html; charset=utf-8")
    self.send_header("Content-Length", str(len(raw)))
    self.end_headers()
    self.wfile.write(raw)

  def _serve_inner_game_frame(self, query_str):
    """Serves the upright 720x1280 Portrait Game Frame (/play_frame)."""
    params = urllib.parse.parse_qs(query_str)
    acc = params.get("acc", [AI_STATE.get("account") or "720452341"])[0].strip()
    sid_str = params.get("sid", ["610039"])[0].strip()
    direct_mode = int(params.get("direct", ["0"])[0] or "0")

    srv_info = ALL_SERVERS_DATA[0]
    for s in ALL_SERVERS_DATA:
      if str(s["sid"]) == sid_str:
        srv_info = s
        break

    ak_info = fetch_fresh_authkey(acc)
    ts = ak_info["timestamp"]
    auth_key = ak_info["authKey"]

    html = f"""<!DOCTYPE html>
<html lang="vi">
<head>
  <meta charset="utf-8" />
  <title>Hắc Tây Du — Màn Dọc 720x1280</title>
  <meta name="viewport" content="width=device-width,initial-scale=1.0,minimum-scale=1.0,maximum-scale=1.0,user-scalable=no" />
  <base href="/cdn/" />
  <style>
    html, body {{
      width: 100%; height: 100%; margin: 0; padding: 0;
      overflow: hidden; background-color: #000000;
    }}
    @font-face {{ font-family: Microsoft YaHei; src: url('res/font/msyh_vn.woff'); }}
    @font-face {{ font-family: MyFont; src: url('res/font/msyh2_vn.woff'); }}
  </style>
</head>
<body>
  <script src="libs/min/lib.js?v=80_portrait"></script>
  <script>
    window.DAUTO_FORCE_PORTRAIT = true;
    window.DAUTO_CLIENT_TYPE = "WebClient-Portrait-v7.9";
    window.DAUTO_BOOT_CONFIG = {{
      account: {json.dumps(acc)},
      wsUrl: {json.dumps(srv_info["server"])},
      serverId: {int(srv_info["sid"])},
      serverIndex: {int(srv_info["id"])},
      serverName: {json.dumps(srv_info["name"])},
      timestamp: {json.dumps(ts)},
      authKey: {json.dumps(auth_key)},
      directEnter: {direct_mode}
    }};

    function loadGame() {{
      var script = document.createElement("script");
      script.src = "js/game.js?v=80_portrait_" + Date.now();
      script.type = "text/javascript";
      document.body.appendChild(script);
      script.onload = function() {{
        startGame();
      }};
    }}

    function startGame() {{
      var cfg = window.DAUTO_BOOT_CONFIG;
      var origin = window.location.origin;

      Global.GLOBAL_PLATEFORM = true;
      Global.GLOBAL_HIDE_IP = "1";
      Global.GLOBAL_SHOW_IP = false;
      Global.SHOW_DEBUG_LOGIN = false;
      Global.GLOBAL_ACCOUNT = cfg.account;
      Global.ACCOUNT = cfg.account;
      Global.GLOBAL_OPENID = cfg.account;
      Global.GLOBAL_USER_IP = "127.0.0.1";
      Global.GLOBAL_REGION = "VN";
      Global.GLOBAL_PF = "ios_funtap";
      Global.GAME_PLATFORM = "funtap";
      Global.GLOBAL_APPID = "ios";
      Global.GLOBAL_VERSION = "13528";
      Global.GLOBAL_LANG = "vn";
      Global.RESHOST = origin + "/cdn/";
      Global.GLOBAL_ENTRY_DOMAIN = "https://funtap-xy.ridvqqxa.com/";
      Global.GLOBAL_LOG_LOGIN = "https://funtap-xy.ridvqqxa.com/game/login.php";
      Global.GLOBAL_ALL_SERVER_LIST = origin + "/api/server_list";
      Global.GLOBAL_LAST_SERVER_LIST = origin + "/api/server_list";
      Global.TARGET_SERVER_ID = cfg.serverId;

      Global.GLOBAL_SERVER_ID = cfg.serverId;
      Global.GLOBAL_SERVER_INDEX = cfg.serverIndex;
      Global.GLOBAL_SERVER_NAME = cfg.serverName;
      Global.IP = cfg.wsUrl;
      Global.GLOBAL_TIMESTAMP = cfg.timestamp;
      Global.GLOBAL_AUTHKEY = cfg.authKey;
      Global.LOGIN_TOKEN = "";
      Global.font1 = "Microsoft YaHei";
      Global.font2 = "MyFont";
      Global.GLOBAL_SDK_LOGIN = 0;
      Global.IS_TISHEN = 0;
      Global.censor = null;
      Global.GLOBAL_LOGIN_AUDIO = 0;
      Global.GLOBAL_LOGIN_MUSIC = 0;
      Global.GLOBAL_VN_AGE_TIP = 0;
      Global.GLOBAL_DIRECT_ENTER = cfg.directEnter;

      window.start(1, 1, 1, 1);

      // Load live_ai_plugin.js to ensure v7.9 anti-drop giftcode & main account hooks
      var plug = document.createElement("script");
      plug.src = origin + "/live_ai_plugin.js?v=" + Date.now();
      document.body.appendChild(plug);

      if (cfg.directEnter === 1) {{
        setTimeout(function() {{
          try {{
            var nm = window.NetMsg || (window.HacTayDuAuto && window.HacTayDuAuto.getNetMsg && window.HacTayDuAuto.getNetMsg());
            if (nm && nm.connect && !nm.isConnect && !nm.isConnecting) {{
              Global.ACCOUNT = cfg.account;
              Global.GLOBAL_SERVER_ID = cfg.serverId;
              Global.IP = cfg.wsUrl;
              nm.connect(Global.IP, cfg.serverId + "-" + cfg.account);
            }}
          }} catch (e) {{ console.error(e); }}
        }}, 1600);
      }}
    }}

    window.onload = loadGame;
  </script>
</body>
</html>"""
    raw = html.encode("utf-8")
    self.send_response(200)
    self.send_header("Content-Type", "text/html; charset=utf-8")
    self.send_header("Content-Length", str(len(raw)))
    self.end_headers()
    self.wfile.write(raw)

  def _serve_cdn_asset(self, rel_asset):
    rel_asset = rel_asset.lstrip("/")
    if rel_asset == "js/game.js" and os.path.exists(PATCHED_GAME_JS):
      with open(PATCHED_GAME_JS, "rb") as f:
        data = f.read()
      self.send_response(200)
      self.send_header("Content-Type", "application/javascript; charset=utf-8")
      self.send_header("Content-Length", str(len(data)))
      self.end_headers()
      self.wfile.write(data)
      return

    local_cache_path = os.path.join(CDN_CACHE_DIR, rel_asset)
    if not os.path.exists(local_cache_path):
      remote_url = CDN_BASE + urllib.parse.quote(rel_asset, safe="/-_.~")
      try:
        os.makedirs(os.path.dirname(local_cache_path), exist_ok=True)
        req = urllib.request.Request(
            remote_url, headers={"User-Agent": "Mozilla/5.0"}
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
          data = resp.read()
        with open(local_cache_path, "wb") as f:
          f.write(data)
      except Exception:
        self.send_response(404)
        self.end_headers()
        return

    try:
      with open(local_cache_path, "rb") as f:
        data = f.read()
      self.send_response(200)
      self.send_header("Content-Type", self.guess_type(local_cache_path))
      self.send_header("Content-Length", str(len(data)))
      self.end_headers()
      self.wfile.write(data)
    except Exception:
      self.send_response(404)
      self.end_headers()


def get_ip_addresses():
  ips = []
  try:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect(("8.8.8.8", 80))
    primary = s.getsockname()[0]
    s.close()
    ips.append(primary)
  except Exception:
    pass
  return ips


def print_cmd_reroll_dashboard():
  from collections import Counter
  newest_srv = fetch_latest_server_live()
  try:
    with urllib.request.urlopen(f"http://localhost:{PORT}/api/reroll_status", timeout=4) as r:
      st = json.loads(r.read().decode("utf-8"))
  except Exception:
    st = REROLL_STATE
  accs = st.get("accounts") or []
  running = st.get("running", False)
  step_msg = st.get("stepMsg", "")
  wins_2x = [a for a in accs if a.get("isJackpot2x")]

  print("=" * 88)
  print(f"📊 BẢNG THEO DÕI CMD TRỰC TIẾP — SERVER MỚI NHẤT ĐỘNG ({newest_srv['name']} • {newest_srv['sid']})")
  print(f"● Trạng thái : {'⏳ ĐANG CHẠY ' + str(PARALLEL_REROLL_WORKERS) + ' LUỒNG SIÊU TỐC' if running else '✅ ĐÃ HOÀN TẤT / DỪNG'}")
  print(f"● Tiến độ    : Đã xong {len(accs)} nick | Nổ 2x (DT / TNK / Na Tra): {len(wins_2x)} nick")
  print(f"● Luồng hiện : {step_msg}")
  print("=" * 88)

  if wins_2x:
    print("\n🔥🔥 DANH SÁCH NICK NỔ CẶP 2x DƯƠNG TIỄN / 2x TÔN NGỘ KHÔNG / 2x NA TRA (JACKPOT):")
    for idx, a in enumerate(wins_2x, 1):
      c = Counter(a.get("heroes5Star") or [])
      combos = " + ".join([f"{k} x{v}" if v > 1 else k for k, v in c.items()])
      print(f"  {idx}. TK: {a['account']} | MK: {a.get('password', 'tphtd123')} | ID Nạp: {a.get('funtapId', '')} | {a['serverName']} => {', '.join(a.get('targetHeroes', []))}")
      print(f"     . {combos}")
    print("=" * 88)


def main():
  os.chdir(DIRECTORY)
  newest_srv = fetch_latest_server_live()
  if "--cmd" in sys.argv:
    print_cmd_reroll_dashboard()
    return
  fetch_fresh_authkey()
  ips = get_ip_addresses()
  primary_ip = ips[0] if ips else "localhost"

  server_address = ("0.0.0.0", PORT)
  httpd = ThreadedHTTPServer(server_address, DAutoAIRequestHandler)

  bot_status_str = f"ĐÃ BẬT ({APP_CONFIG['sales_bot']['webhook_url']})" if APP_CONFIG.get("sales_bot", {}).get("webhook_url") else "Chờ cấu hình webhook (Sẵn sàng đấu nối)"
  print("=" * 88)
  print(f"📱 D-AUTO PRO MAX v7.9 — [MÁY: {MACHINE_ID.upper()}] | TIỀN TỐ NICK: '{ACCOUNT_PREFIX}'")
  print("=" * 88)
  print(f"🎮 Giao diện Web (nếu cần): http://localhost:{PORT}/")
  print(f"🔥 Server Mới Nhất tự động : {newest_srv['name']} (SID: {newest_srv['sid']})")
  print(f"⚡ Số luồng xử lý          : {PARALLEL_REROLL_WORKERS} luồng")
  print(f"🤖 Đấu nối Bot Bán Hàng    : {bot_status_str}")
  print(f"📂 File lưu kết quả 2x     : DAN_NICK_TRUNG_TUONG.txt & DANH_SACH_NICK_D_AUTO.txt")
  print("=" * 88)

  print_cmd_reroll_dashboard()

  if "--no-auto-reroll" not in sys.argv:
    print(f"\n🚀 ĐANG TỰ ĐỘNG CHẠY XUYÊN SUỐT {PARALLEL_REROLL_WORKERS} LUỒNG SIÊU TỐC (TIỀN TỐ: '{ACCOUNT_PREFIX}') TẠI {newest_srv['name']}...")
    print("👉 Khi nổ 2x sẽ hiện bảng lớn, chụp ảnh Thần Tướng & lưu vào DAN_NICK_TRUNG_TUONG.txt rồi TIẾP TỤC CHẠY LUÔN KHÔNG DỪNG:\n", flush=True)
    start_reroll_background(count=10000, sid_str="latest", stop_on_win=False, prefix=ACCOUNT_PREFIX, min_copies=2)

  def _cmd_console_listener():
    while True:
      try:
        line = sys.stdin.readline()
        if not line:
          break
        cmd_txt = line.strip()
        with REROLL_LOCK:
          is_run = REROLL_STATE["running"]
        if is_run:
          print("⚡ Hệ thống vẫn đang chạy xuyên suốt! Nếu muốn dừng, gõ 'stop' rồi bấm Enter.", flush=True)
          if cmd_txt.lower() == "stop":
            with REROLL_LOCK:
              REROLL_STATE["stopRequested"] = True
          continue
        next_cnt = int(cmd_txt) if cmd_txt.isdigit() and int(cmd_txt) > 0 else 10000
        latest_now = fetch_latest_server_live()
        print(f"\n🚀 TIẾP TỤC CHẠY XUYÊN SUỐT {next_cnt} NICK ({PARALLEL_REROLL_WORKERS} LUỒNG TẠI {latest_now['name']} - KHÔNG DỪNG KHI TRÚNG)...\n", flush=True)
        start_reroll_background(count=next_cnt, sid_str="latest", stop_on_win=False, prefix=ACCOUNT_PREFIX, min_copies=2)
      except Exception:
        time.sleep(1)

  threading.Thread(target=_cmd_console_listener, daemon=True).start()

  try:
    httpd.serve_forever()
  except KeyboardInterrupt:
    httpd.server_close()


if __name__ == "__main__":
  main()
