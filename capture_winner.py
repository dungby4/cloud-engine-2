"""Standalone screenshot capture and tutorial runner for Hac Tay Du winners.
Runs in an isolated process so Playwright/Chrome never blocks the main reroll engine.
"""

import argparse
import asyncio
import os
import re
import sys
import time

DIRECTORY = os.path.dirname(os.path.abspath(__file__))


async def capture_winner_screenshot(acc_name, fid, sid, port=8088):
  srv_num = sid - 610000 if sid > 610000 else sid
  rel_path = f"anh_nick_trung/{acc_name}_S{srv_num}.png"
  out_path = os.path.join(DIRECTORY, "anh_nick_trung", f"{acc_name}_S{srv_num}.png")
  os.makedirs(os.path.dirname(out_path), exist_ok=True)

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

        # 2. Chờ thanh điều hướng chính
        for _ in range(50):
          await asyncio.sleep(0.5)
          ready = await page.evaluate("() => typeof bt !== 'undefined' && bt.getInstance && bt.getInstance().inStage && bt.getInstance().inStage()")
          if ready:
            break

        # 3. Sort ưu tiên tướng đỏ & mở tab Thần Tướng
        await page.evaluate("""() => {
          if (typeof at !== 'undefined') at.data = null;
          if (typeof De !== 'undefined') De.isInCombat = false;
          if (window.tt) {
            var priorityWeight = function(h) {
              if (!h) return 0;
              var reds = [
                "Dương Tiễn", "Ngộ Không", "Na Tra", "Lý Tịnh", "Đường Tam Tạng", "Đường Tăng",
                "Trấn Nguyên", "Ngưu Ma", "Hồng Hài Nhi", "Hàng Long", "Trư Bát Giới",
                "Hằng Nga", "Thiết Phiến", "Hoàng My", "Ngọc Diện"
              ];
              var hName = h.name || "";
              for (var i = 0; i < reds.length; i++) {
                if (hName.indexOf(reds[i]) >= 0) return 100000 - i * 500;
              }
              if (h.id === 1014) return 100000;
              if (h.id === 2014) return 95000;
              if (h.id === 3014) return 90000;
              if (h.id === 3010) return 80000;
              return (h.star || 0) * 1000 + (h.lv || 1);
            };
            window.tt.combatheroSort = function(a, b) {
              return priorityWeight(b) - priorityWeight(a);
            };
          }
          if (typeof bt !== 'undefined' && bt.getInstance) {
            try { bt.getInstance().onTab(1); } catch(e) {}
          }
        }""")

        for _ in range(30):
          await asyncio.sleep(0.5)
          inst_ready = await page.evaluate("() => typeof si !== 'undefined' && si.getInstance && si.getInstance().inStage && si.getInstance().inStage()")
          if inst_ready:
            break

        await asyncio.sleep(2.5)
        await page.evaluate("""() => {
          try {
            if (typeof si !== 'undefined' && si.getInstance && si.getInstance().setList) {
              si.getInstance().setList(0, 0);
            }
          } catch(e) {}
          if (window.HacTayDuAuto) {
            if (window.HacTayDuAuto.layaMenu) window.HacTayDuAuto.layaMenu.visible = false;
            if (window.HacTayDuAuto.layaBtn) window.HacTayDuAuto.layaBtn.visible = false;
          }
        }""")
        await asyncio.sleep(0.8)
        await page.screenshot(path=out_path)

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
            print(f"📸 [{acc_name}] Đã lưu ảnh: JPG={os.path.getsize(jpg_path)//1024} KB | PNG={os.path.getsize(out_path)//1024} KB", flush=True)
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
  args = parser.parse_args()

  try:
    asyncio.run(asyncio.wait_for(
        capture_winner_screenshot(args.acc, args.fid, args.sid, args.port),
        timeout=120.0
    ))
  except Exception as e:
    print(f"⚠️ [capture_winner] Timeout hoặc lỗi: {e}", flush=True)


if __name__ == "__main__":
  main()
