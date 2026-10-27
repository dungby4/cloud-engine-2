"""Standalone screenshot capture and tutorial runner for Hac Tay Du winners.
Runs in an isolated process so Playwright/Chrome never blocks the main reroll engine.
"""

import argparse
import asyncio
import os
import re
import sys
import time

import json
import shutil

DIRECTORY = os.path.dirname(os.path.abspath(__file__))


def _compress_image(out_path):
  try:
    from PIL import Image
    with Image.open(out_path) as im:
      im_rgb = im.convert("RGB") if im.mode in ("RGBA", "LA", "P") else im
      orig_w, orig_h = im_rgb.size
      max_w = 540
      if orig_w > max_w:
        new_h = int(orig_h * (max_w / orig_w))
        im_resized = im_rgb.resize((max_w, new_h), Image.Resampling.LANCZOS)
      else:
        im_resized = im_rgb
      jpg_path = os.path.splitext(out_path)[0] + ".jpg"
      im_resized.save(jpg_path, format="JPEG", quality=72, optimize=True, progressive=True)
      p_im = im_resized.convert("P", palette=Image.ADAPTIVE, colors=256)
      p_im.save(out_path, format="PNG", optimize=True)
      print(f"📸 Đã lưu ảnh nén: JPG={os.path.getsize(jpg_path)//1024} KB | PNG={os.path.getsize(out_path)//1024} KB", flush=True)
  except Exception as e_comp:
    print(f"⚠️ Không thể nén ảnh: {e_comp}", flush=True)


async def capture_winner_screenshot(acc_name, fid, sid, port=8088, pwd="", srv_name="", ws_url="", hero_id=0, hero_name=""):
  srv_num = sid - 610000 if sid > 610000 else sid
  rel_path = f"anh_nick_trung/{acc_name}_S{srv_num}.png"
  out_path = os.path.join(DIRECTORY, "anh_nick_trung", f"{acc_name}_S{srv_num}.png")
  os.makedirs(os.path.dirname(out_path), exist_ok=True)
  json_meta_path = os.path.join(DIRECTORY, "anh_nick_trung", f"{acc_name}_S{srv_num}.json")

  # 1. Ưu tiên chạy qua prepare_jackpot_account.js (Node.js engine) để hoàn thành tân thủ Lv.8+, xếp 2 tướng nổ cạnh nhau ở Slot 1 & 2
  prep_script = os.path.join(DIRECTORY, "prepare_jackpot_account.js")
  if os.path.exists(prep_script):
    try:
      import subprocess
      node_bin = shutil.which("node")
      if node_bin:
        cmd = [
            node_bin,
            prep_script,
            "--acc", acc_name,
            "--pwd", pwd,
            "--fid", str(fid),
            "--sid", str(sid),
            "--server-name", srv_name,
            "--ws-url", ws_url,
            "--hero", str(hero_id),
            "--hero-name", hero_name
        ]
        print(f"🎮 [{acc_name}] Đang gọi prepare_jackpot_account.js (Node.js) chạy tân thủ Lv.8+, xếp túi tướng & chụp ảnh...", flush=True)
        cp = await asyncio.to_thread(subprocess.run, cmd, capture_output=True, text=True, timeout=180.0, cwd=DIRECTORY)
        if cp.stdout:
          for l in cp.stdout.splitlines():
            if "RESULT_JSON_START:" in l and ":RESULT_JSON_END" in l:
              raw_j = l.split("RESULT_JSON_START:")[1].split(":RESULT_JSON_END")[0]
              res_data = json.loads(raw_j)
              shot_src = res_data.get("heroShotPath") or res_data.get("mainShotPath")
              if shot_src and os.path.exists(shot_src):
                shutil.copyfile(shot_src, out_path)
                with open(json_meta_path, "w", encoding="utf-8") as jf:
                  json.dump(res_data, jf, indent=2, ensure_ascii=False)
                _compress_image(out_path)
                print(f"✅ [{acc_name}] Hoàn tất chạy tân thủ (Lv.{res_data.get('roleLv', 8)}) & xếp túi tướng chụp ảnh thành công!", flush=True)
                return rel_path
            elif l.strip():
              print(f"   [NodePrep] {l.strip()}", flush=True)
    except Exception as e_node:
      print(f"⚠️ [{acc_name}] prepare_jackpot_account.js gặp lỗi: {e_node}, chuyển sang Playwright nội bộ...", flush=True)

  try:
    from playwright.async_api import async_playwright
  except ImportError:
    print(f"⚠️ [capture_winner] Thiếu Playwright, bỏ qua chụp ảnh cho {acc_name}", flush=True)
    return ""

  exe_path = os.environ.get("PLAYWRIGHT_CHROME_PATH")
  if not exe_path and sys.platform == "win32":
    chrome_paths = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ]
    exe_path = next((p for p in chrome_paths if os.path.exists(p)), None)

  launch_kwargs = {
      "headless": True,
      "args": [
          "--no-sandbox",
          "--disable-setuid-sandbox",
          "--disable-dev-shm-usage",
          "--mute-audio",
          "--enable-webgl",
          "--ignore-gpu-blocklist",
          "--disable-gpu-vsync",
          "--renderer-process-limit=1",
          "--num-raster-threads=2",
      ] + (["--use-gl=angle", "--use-angle=swiftshader"] if sys.platform.startswith("linux") else []),
  }
  if exe_path:
    launch_kwargs["executable_path"] = exe_path

  try:
    async with async_playwright() as p:
      browser = await p.chromium.launch(**launch_kwargs)
      try:
        page = await browser.new_page(viewport={"width": 720, "height": 1280})
        url = f"http://localhost:{port}/play_frame?acc={fid}&sid={sid}&direct=1"
        await page.goto(url, wait_until="domcontentloaded", timeout=25000)

        for _ in range(45):
          await asyncio.sleep(0.5)
          cnt = await page.evaluate("() => (window.tt && window.tt.heros) ? window.tt.heros.length : 0")
          if cnt > 0:
            break
        await asyncio.sleep(1.0)

        # 1. Chạy nhiệm vụ tân thủ nếu level < 5
        try:
          cur_lv = await page.evaluate("() => window.H && window.H.data ? (window.H.data.lv || window.H.data.level || 1) : 1")
          if cur_lv < 5:
            print(f"🎮 [{acc_name}] Đang tự động chạy nhiệm vụ tân thủ (Lv.{cur_lv} -> Lv.5+)...", flush=True)
            await page.evaluate("""() => {
              if (window.HacTayDuAuto) {
                window.HacTayDuAuto.autoCampaign = true;
                if (window.HacTayDuAuto.cleanSkipTutorialNow) window.HacTayDuAuto.cleanSkipTutorialNow();
              }
              try {
                if (typeof Ri !== 'undefined' && Ri.getInstance && Ri.getInstance().inStage()) {
                  Ri.getInstance().onFight();
                } else if (typeof Et !== 'undefined' && Et.show) {
                  Et.show(1, '');
                } else if (typeof n !== 'undefined' && n.CG_COMBAT_READY) {
                  n.CG_COMBAT_READY(1, '', 0, 0);
                }
              } catch(e) {}
            }""")

            for sec in range(1, 45):
              await asyncio.sleep(1.0)
              cur_lv = await page.evaluate("() => window.H && window.H.data ? (window.H.data.lv || window.H.data.level || 1) : 1")
              in_combat = await page.evaluate("() => !!(typeof De !== 'undefined' && De && De.isInCombat)")
              if cur_lv >= 5 and not in_combat:
                print(f"✅ [{acc_name}] Đã hoàn thành nhiệm vụ tân thủ! Đạt Lv.{cur_lv}", flush=True)
                break

              await page.evaluate("""() => {
                try {
                  if (typeof De !== 'undefined' && De && De.isInCombat) {
                    De._pendingSkip = true;
                    if (De.finishData) {
                      De.endFlag = false;
                      try { De.onEnd(); } catch(e) {}
                    }
                  }
                } catch(e) {}
                try {
                  if (typeof qe !== 'undefined' && qe.getInstance && qe.getInstance().inStage()) {
                    try { qe.getInstance().onNextCopy(); } catch(e) {
                      try { qe.getInstance().close(); } catch(e2) {}
                    }
                  }
                } catch(e) {}
                try {
                  if (window.HacTayDuAuto && window.HacTayDuAuto.cleanSkipTutorialNow) {
                    window.HacTayDuAuto.cleanSkipTutorialNow();
                  }
                } catch(e) {}
              }""")

              if sec % 2 == 0 and not in_combat and cur_lv < 5:
                await page.evaluate("""() => {
                  try {
                    if (typeof Ri !== 'undefined' && Ri.getInstance && Ri.getInstance().inStage()) {
                      Ri.getInstance().onFight();
                    } else if (typeof Et !== 'undefined' && Et.show) {
                      Et.show(1, '');
                    } else if (typeof n !== 'undefined' && n.CG_COMBAT_READY) {
                      n.CG_COMBAT_READY(1, '', 0, 0);
                    }
                  } catch(e) {}
                }""")
                try:
                  await page.mouse.click(360, 640)
                except Exception:
                  pass

            await page.evaluate("""() => {
              if (window.HacTayDuAuto) {
                window.HacTayDuAuto.autoCampaign = false;
                try { window.HacTayDuAuto.cleanSkipTutorialNow(); } catch(e) {}
              }
              if (window.Laya && window.Laya.Dialog) {
                try { window.Laya.Dialog.closeAll(); } catch(e) {}
              }
              if (typeof qe !== 'undefined' && qe.getInstance && qe.getInstance().inStage()) {
                try { qe.getInstance().close(); } catch(e) {}
              }
            }""")
            await asyncio.sleep(1.0)
        except Exception as err_tan_thu:
          print(f"⚠️ [{acc_name}] Lỗi khi chạy tân thủ: {err_tan_thu}", flush=True)

        # 2. Chờ game tải xong tài nguyên CDN và hiển thị thanh điều hướng chính
        ready = False
        print(f"⏳ [{acc_name}] Đang chờ game nạp xong CDN vào giao diện chính...", flush=True)
        for _ in range(120):
          await asyncio.sleep(1.0)
          ready = await page.evaluate("() => typeof bt !== 'undefined' && bt.getInstance && bt.getInstance().inStage && bt.getInstance().inStage()")
          if ready:
            break

        if not ready:
          print(f"⚠️ [{acc_name}] Game chưa load xong CDN sau 120s (vẫn ở màn hình tải), hủy chụp ảnh để tránh ảnh lỗi!", flush=True)
          return ""

        # 3. Mở tab Thần Tướng và đảm bảo thẻ tướng đã load
        print(f"📦 [{acc_name}] Đang mở Túi Thần Tướng và sắp xếp tướng nổ cạnh nhau...", flush=True)
        bag_ready = False
        for attempt in range(1, 35):
          await page.evaluate("""() => {
            if (typeof at !== 'undefined') at.data = null;
            if (typeof De !== 'undefined') De.isInCombat = false;
            try {
              if (window.bt && bt.getInstance) {
                var mb = bt.getInstance();
                if (window.ye && !mb.index2Panel[0]) mb.register(0, ye.getInstance());
                if (window.si) mb.register(1, si.getInstance());
                mb.onTab(1);
              }
            } catch(e) {}
            try {
              if (window.si && si.getInstance) {
                var s = si.getInstance();
                s.open(0);
                if (typeof s.reflushHero === 'function') s.reflushHero();
              }
            } catch(e) {}
          }""")
          await asyncio.sleep(1.0)

          bag_ready = await page.evaluate("""() => {
            try {
              if (window.si && si.getInstance) {
                var s = si.getInstance();
                if (s && ((typeof s.inStage === 'function' && s.inStage()) || (s.ui && (s.ui.inStage ? s.ui.inStage() : !!s.ui.parent)))) {
                  var list = s.ui && s.ui.cardList && s.ui.cardList.list;
                  if (list) {
                    var arr = list.array || list.dataSource;
                    return !!(arr && arr.length > 0);
                  }
                }
              }
            } catch(e) {}
            return false;
          }""")
          if bag_ready:
            break

        if not bag_ready:
          print(f"⚠️ [{acc_name}] Túi Thần Tướng chưa mở được thẻ tướng sau 35s, hủy chụp ảnh để tránh ảnh lỗi!", flush=True)
          return ""

        # 4. Sắp xếp 2 tướng jackpot đứng kề nhau ở Slot 1 & 2 hàng đầu
        await page.evaluate("""(targetId) => {
          try {
            var comp = window.si && window.si.getInstance && window.si.getInstance().ui && window.si.getInstance().ui.cardList && window.si.getInstance().ui.cardList.list;
            if (comp) {
              var rows = comp.dataSource || comp.array;
              if (Array.isArray(rows) && rows.length > 0) {
                var reds = [
                  "Dương Tiễn", "Ngộ Không", "Na Tra", "Lý Tịnh", "Đường Tam Tạng", "Đường Tăng",
                  "Trấn Nguyên", "Ngưu Ma", "Hồng Hài Nhi", "Hàng Long", "Trư Bát Giới",
                  "Hằng Nga", "Thiết Phiến", "Hoàng My", "Ngọc Diện"
                ];
                var priorityWeight = function(h) {
                  if (!h) return 0;
                  var hId = h.id || (h.heroSimple && h.heroSimple.id) || 0;
                  if (targetId && hId === targetId) return 2000000;
                  var hName = h.name || (h.heroSimple && h.heroSimple.name) || "";
                  for (var i = 0; i < reds.length; i++) {
                    if (hName.indexOf(reds[i]) >= 0) return 1000000 - i * 1000;
                  }
                  if (hId === 1014) return 990000;
                  if (hId === 2014) return 980000;
                  if (hId === 3014) return 970000;
                  if (hId === 3010) return 960000;
                  return (h.star || 0) * 1000 + (h.lv || 1);
                };
                rows.sort(function(a, b) {
                  return priorityWeight(b) - priorityWeight(a);
                });
                comp.array = rows;
                comp.dataSource = rows;
                if (comp.cells && comp.renderHandler) {
                  for (var i = 0; i < Math.min(6, rows.length); i++) {
                    if (comp.cells[i]) comp.renderHandler.runWith([comp.cells[i], i]);
                  }
                }
                if (comp.refresh) comp.refresh();
                if (comp.scrollTo) comp.scrollTo(0);
              }
            }
          } catch(e) {}
          if (window.HacTayDuAuto) {
            if (window.HacTayDuAuto.layaMenu) window.HacTayDuAuto.layaMenu.visible = false;
            if (window.HacTayDuAuto.layaBtn) window.HacTayDuAuto.layaBtn.visible = false;
          }
        }""", hero_id)

        # Chờ 3.5s để ảnh render đầy đủ avatar
        await asyncio.sleep(3.5)
        await page.screenshot(path=out_path)

        if not os.path.exists(out_path) or os.path.getsize(out_path) < 15000:
          print(f"⚠️ [{acc_name}] Ảnh chụp không hợp lệ (< 15 KB), hủy ảnh!", flush=True)
          return ""

        # Nén ảnh JPG siêu gọn
        try:
          from PIL import Image
          with Image.open(out_path) as im:
            im_rgb = im.convert("RGB") if im.mode in ("RGBA", "LA", "P") else im
            orig_w, orig_h = im_rgb.size
            max_w = 540
            if orig_w > max_w:
              new_h = int(orig_h * (max_w / orig_w))
              im_resized = im_rgb.resize((max_w, new_h), Image.Resampling.LANCZOS)
            else:
              im_resized = im_rgb
            jpg_path = os.path.splitext(out_path)[0] + ".jpg"
            im_resized.save(jpg_path, format="JPEG", quality=72, optimize=True, progressive=True)
            p_im = im_resized.convert("P", palette=Image.ADAPTIVE, colors=256)
            p_im.save(out_path, format="PNG", optimize=True)
            print(f"📸 [{acc_name}] Đã lưu ảnh Túi Thần Tướng: JPG={os.path.getsize(jpg_path)//1024} KB | PNG={os.path.getsize(out_path)//1024} KB", flush=True)
        except Exception as e_compress:
          print(f"⚠️ [{acc_name}] Không thể nén ảnh: {e_compress}", flush=True)

        return rel_path
      finally:
        try:
          await asyncio.wait_for(browser.close(), timeout=3.0)
        except Exception:
          pass
  except Exception as e:
    print(f"⚠️ [capture_winner Error] {acc_name}: {e}", flush=True)
    return ""


def main():
  try:
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
      sys.stdout.reconfigure(encoding="utf-8", write_through=True)
  except Exception:
    pass

  parser = argparse.ArgumentParser()
  parser.add_argument("--acc", required=True)
  parser.add_argument("--fid", required=True)
  parser.add_argument("--sid", type=int, required=True)
  parser.add_argument("--port", type=int, default=8088)
  parser.add_argument("--pwd", default="")
  parser.add_argument("--server-name", default="")
  parser.add_argument("--ws-url", default="")
  parser.add_argument("--hero", type=int, default=0)
  parser.add_argument("--hero-name", default="")
  args = parser.parse_args()

  try:
    asyncio.run(asyncio.wait_for(
        capture_winner_screenshot(
            args.acc,
            args.fid,
            args.sid,
            args.port,
            pwd=args.pwd,
            srv_name=args.server_name,
            ws_url=args.ws_url,
            hero_id=args.hero,
            hero_name=args.hero_name,
        ),
        timeout=240.0,
    ))
  except Exception as e:
    print(f"⚠️ [capture_winner] Timeout hoặc lỗi: {e}", flush=True)


if __name__ == "__main__":
  main()
