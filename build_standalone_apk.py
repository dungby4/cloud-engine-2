#!/usr/bin/env python3
"""build_standalone_apk.py - Biên dịch Standalone Mod APK Hắc Tây Du cho Android.
Bản V9.9.9.9 (Bản Hoàn Thiện Tối Ưu Cho Mobile):
- Tắt hoàn toàn tự động nhảy vào game (p.GLOBAL_DIRECT_ENTER = 0).
- Hiển thị đầy đủ giao diện chọn Server Funtap (S84, S83... S1) và nút "Vào Game".
- Hộp thoại Nhập UID / Đổi Tài Khoản tiện lợi, không bị ép vào S2.
- Giữ nguyên trọn vẹn Mod: x5 Tốc độ, Skip 0s, Auto Phù Đồ Tháp không cần nạp 1280 ngọc.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

try:
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if sys.stderr and hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

ANDROID_SDK = Path(r"C:\Users\truon\AppData\Local\Android\Sdk")
BUILD_TOOLS = ANDROID_SDK / "build-tools" / "35.0.0"
PLATFORM = ANDROID_SDK / "platforms" / "android-30"

AAPT2 = BUILD_TOOLS / "aapt2.exe"
D8 = BUILD_TOOLS / "d8.bat"
ZIPALIGN = BUILD_TOOLS / "zipalign.exe"
APKSIGNER = BUILD_TOOLS / "apksigner.bat"
ANDROID_JAR = PLATFORM / "android.jar"
JAVAC = Path(r"C:\Program Files\Microsoft\jdk-21.0.11.10-hotspot\bin\javac.exe")

PACKAGE_NAME = "vn.ftg.hactaydu.dauto"
APP_NAME = "Hắc Tây Du Mod D-AUTO"
VERSION_CODE = "11"
VERSION_NAME = "11.0.0.0"

SRC_DIR = Path("standalone_android_project")
OUT_DIR = SRC_DIR / "build"

def create_project_structure():
    print("📁 [1/6] Chuẩn bị mã nguồn dự án Android độc lập...")
    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)
    
    (SRC_DIR / "src" / "vn" / "ftg" / "hactaydu" / "dauto").mkdir(parents=True, exist_ok=True)
    (SRC_DIR / "res" / "values").mkdir(parents=True, exist_ok=True)
    (SRC_DIR / "res" / "drawable").mkdir(parents=True, exist_ok=True)
    (SRC_DIR / "res" / "mipmap-hdpi").mkdir(parents=True, exist_ok=True)
    (SRC_DIR / "assets").mkdir(parents=True, exist_ok=True)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Strings & Styles
    with open(SRC_DIR / "res" / "values" / "strings.xml", "w", encoding="utf-8") as f:
        f.write(f'''<?xml version="1.0" encoding="utf-8"?>
<resources>
    <string name="app_name">{APP_NAME}</string>
</resources>''')

    with open(SRC_DIR / "res" / "values" / "styles.xml", "w", encoding="utf-8") as f:
        f.write('''<?xml version="1.0" encoding="utf-8"?>
<resources>
    <style name="AppTheme" parent="android:Theme.NoTitleBar.Fullscreen">
        <item name="android:windowBackground">@android:color/black</item>
    </style>
</resources>''')

    # Copy icon
    icon_source = Path("icon.png")
    if not icon_source.exists():
        with zipfile.ZipFile("HacTayDu_latest.xapk", "r") as z:
            if "icon.png" in z.namelist():
                z.extract("icon.png", ".")
    if icon_source.exists():
        shutil.copy(icon_source, SRC_DIR / "res" / "mipmap-hdpi" / "ic_launcher.png")
        shutil.copy(icon_source, SRC_DIR / "res" / "drawable" / "ic_launcher.png")

    # 2. AndroidManifest.xml
    with open(SRC_DIR / "AndroidManifest.xml", "w", encoding="utf-8") as f:
        f.write(f'''<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android"
    package="{PACKAGE_NAME}"
    android:versionCode="{VERSION_CODE}"
    android:versionName="{VERSION_NAME}">

    <uses-sdk android:minSdkVersion="24" android:targetSdkVersion="34" />

    <uses-permission android:name="android.permission.INTERNET" />
    <uses-permission android:name="android.permission.ACCESS_NETWORK_STATE" />
    <uses-permission android:name="android.permission.ACCESS_WIFI_STATE" />
    <uses-permission android:name="android.permission.WAKE_LOCK" />

    <application
        android:label="@string/app_name"
        android:icon="@drawable/ic_launcher"
        android:theme="@style/AppTheme"
        android:hardwareAccelerated="true"
        android:usesCleartextTraffic="true">

        <activity
            android:name=".MainActivity"
            android:screenOrientation="portrait"
            android:configChanges="orientation|screenSize|keyboardHidden"
            android:exported="true">
            <intent-filter>
                <action android:name="android.intent.action.MAIN" />
                <category android:name="android.intent.category.LAUNCHER" />
            </intent-filter>
        </activity>
    </application>
</manifest>''')

    # 3. MainActivity.java (Bổ sung JavascriptInterface PlatformScript đầy đủ API)
    java_code = '''package vn.ftg.hactaydu.dauto;

import android.app.Activity;
import android.os.Bundle;
import android.util.Log;
import android.view.Window;
import android.view.WindowManager;
import android.webkit.ConsoleMessage;
import android.webkit.JavascriptInterface;
import android.webkit.JsResult;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.util.HashMap;
import java.util.Map;

public class MainActivity extends Activity {
    private static final String TAG = "DAUTO_PRO";
    private WebView webView;

    private byte[] libJsBytes;
    private byte[] gameJsBytes;
    private byte[] pluginJsBytes;
    private String indexHtml;

    public class PlatformScriptBridge {
        @JavascriptInterface
        public void jsReady() {
            Log.d(TAG, "[PlatformScript] jsReady called by LayaAir Engine");
        }
        @JavascriptInterface
        public void login() {
            Log.d(TAG, "[PlatformScript] login requested");
        }
        @JavascriptInterface
        public void relogin() {
            Log.d(TAG, "[PlatformScript] relogin requested");
        }
        @JavascriptInterface
        public void logout() {
            Log.d(TAG, "[PlatformScript] logout requested");
        }
        @JavascriptInterface
        public void reloadWindow() {
            runOnUiThread(new Runnable() {
                @Override
                public void run() {
                    if (webView != null) webView.reload();
                }
            });
        }
        @JavascriptInterface
        public void openWindow(String url) {
            Log.d(TAG, "[PlatformScript] openWindow: " + url);
        }
        @JavascriptInterface
        public void openGoogleScore() {}
        @JavascriptInterface
        public String getPriceList(String json) {
            return "[]";
        }
        @JavascriptInterface
        public void setPriceList(String p1, String p2) {}
        @JavascriptInterface
        public void onCreateRole(String info) {
            Log.d(TAG, "[PlatformScript] onCreateRole: " + info);
        }
        @JavascriptInterface
        public void onEnterGame(String info) {
            Log.d(TAG, "[PlatformScript] onEnterGame: " + info);
        }
        @JavascriptInterface
        public void onLevelUp(String info) {
            Log.d(TAG, "[PlatformScript] onLevelUp: " + info);
        }
        @JavascriptInterface
        public void pay(String info) {
            Log.d(TAG, "[PlatformScript] pay: " + info);
        }
        @JavascriptInterface
        public void openUserCenter() {}
        @JavascriptInterface
        public void onReport(String info) {}
        @JavascriptInterface
        public void fbShare(String t, String e) {}
        @JavascriptInterface
        public void setLanguage(String lang) {}
        @JavascriptInterface
        public void onBuyVoucher() {}
        @JavascriptInterface
        public void onDashboard() {}
        @JavascriptInterface
        public void onVipLevelUp(String lv) {}
    }

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        requestWindowFeature(Window.FEATURE_NO_TITLE);
        getWindow().setFlags(WindowManager.LayoutParams.FLAG_FULLSCREEN, WindowManager.LayoutParams.FLAG_FULLSCREEN);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);

        preloadAssets();

        webView = new WebView(this);
        setContentView(webView);

        WebSettings s = webView.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setDatabaseEnabled(true);
        s.setAllowFileAccess(true);
        s.setAllowContentAccess(true);
        s.setAllowFileAccessFromFileURLs(true);
        s.setAllowUniversalAccessFromFileURLs(true);
        s.setUseWideViewPort(true);
        s.setLoadWithOverviewMode(true);
        s.setMediaPlaybackRequiresUserGesture(false);
        s.setMixedContentMode(WebSettings.MIXED_CONTENT_ALWAYS_ALLOW);
        s.setUserAgentString(s.getUserAgentString() + " Mobile LayaAir/2.0 FuntapApp");

        // Cầu nối giao tiếp Native MontarSDK / PlatformScript giả lập
        webView.addJavascriptInterface(new PlatformScriptBridge(), "PlatformScript");

        webView.setWebChromeClient(new WebChromeClient() {
            @Override
            public boolean onConsoleMessage(ConsoleMessage consoleMessage) {
                Log.d(TAG, "[JS " + consoleMessage.messageLevel() + "] "
                        + consoleMessage.message() + " ("
                        + consoleMessage.sourceId() + ":"
                        + consoleMessage.lineNumber() + ")");
                return true;
            }

            @Override
            public boolean onJsAlert(WebView view, String url, String message, JsResult result) {
                Log.d(TAG, "[Alert] " + message);
                result.confirm();
                return true;
            }

            @Override
            public boolean onJsConfirm(WebView view, String url, String message, JsResult result) {
                Log.d(TAG, "[Confirm] " + message);
                result.confirm();
                return true;
            }
        });

        webView.setWebViewClient(new WebViewClient() {
            @Override
            public WebResourceResponse shouldInterceptRequest(WebView view, WebResourceRequest request) {
                return handleIntercept(request.getUrl().toString());
            }

            @Override
            public WebResourceResponse shouldInterceptRequest(WebView view, String url) {
                return handleIntercept(url);
            }

            private WebResourceResponse handleIntercept(String url) {
                if (url.contains("lib.js")) {
                    return serveBytes(libJsBytes, "application/javascript");
                }
                if (url.contains("game.js")) {
                    return serveBytes(gameJsBytes, "application/javascript");
                }
                if (url.contains("live_ai_plugin.js")) {
                    return serveBytes(pluginJsBytes, "application/javascript");
                }
                return null;
            }

            private WebResourceResponse serveBytes(byte[] data, String mimeType) {
                if (data == null) return null;
                Map<String, String> headers = new HashMap<>();
                headers.put("Access-Control-Allow-Origin", "*");
                headers.put("Access-Control-Allow-Methods", "GET, OPTIONS");
                headers.put("Cache-Control", "no-cache");
                return new WebResourceResponse(mimeType, "UTF-8", 200, "OK", headers, new ByteArrayInputStream(data));
            }
        });

        if (indexHtml != null) {
            webView.loadDataWithBaseURL("https://funtap-xy.ridvqqxa.com/", indexHtml, "text/html", "UTF-8", null);
        } else {
            webView.loadUrl("file:///android_asset/index.html");
        }
    }

    private void preloadAssets() {
        libJsBytes = readAssetBytes("lib.js");
        gameJsBytes = readAssetBytes("game.js");
        pluginJsBytes = readAssetBytes("live_ai_plugin.js");
        byte[] htmlBytes = readAssetBytes("index.html");
        if (htmlBytes != null) {
            try {
                indexHtml = new String(htmlBytes, "UTF-8");
            } catch (Exception e) {
                Log.e(TAG, "Error decoding index.html", e);
            }
        }
        Log.d(TAG, "Preloaded assets - lib: " + (libJsBytes != null ? libJsBytes.length : 0)
                + "b, game: " + (gameJsBytes != null ? gameJsBytes.length : 0)
                + "b, plugin: " + (pluginJsBytes != null ? pluginJsBytes.length : 0) + "b");
    }

    private byte[] readAssetBytes(String filename) {
        try {
            InputStream is = getAssets().open(filename);
            ByteArrayOutputStream baos = new ByteArrayOutputStream();
            byte[] buf = new byte[16384];
            int len;
            while ((len = is.read(buf)) != -1) {
                baos.write(buf, 0, len);
            }
            is.close();
            return baos.toByteArray();
        } catch (Exception e) {
            Log.e(TAG, "Failed to read asset: " + filename, e);
            return null;
        }
    }

    @Override
    public void onBackPressed() {
        if (webView != null && webView.canGoBack()) {
            webView.goBack();
        } else {
            super.onBackPressed();
        }
    }
}
'''
    with open(SRC_DIR / "src" / "vn" / "ftg" / "hactaydu" / "dauto" / "MainActivity.java", "w", encoding="utf-8") as f:
        f.write(java_code)

    # 4. Chuẩn bị và bảo tồn game.js chuyên dụng cho Mobile (UI v10 3-TAB)
    target_game_js = SRC_DIR / "assets" / "game.js"
    if not target_game_js.exists():
        with open("js/game.js", "r", encoding="utf-8") as f:
            game_js = f.read()
        with open(target_game_js, "w", encoding="utf-8") as f:
            f.write(game_js)

    # 5. Plugin chuyên dụng cho Mobile (Tắt sạch reroll, chỉ bật Mod Speed x5, Skip 0s, Auto Tháp)
    mobile_plugin_code = '''// ============================================================================
// D-AUTO PRO v7.9 (MOBILE STANDALONE PLUGIN)
// ============================================================================
(function() {
  function initMobilePlugin() {
    var bot = window.HacTayDuAuto;
    if (!bot) {
      setTimeout(initMobilePlugin, 300);
      return;
    }
    bot.autoSkip = true;
    bot.autoTower = true;
    bot.autoCampaign = false;
    bot.autoRerollS2 = false;
    bot.rerollRunning = false;
    bot.combatSpeedVal = 5;
    if (bot.layaBtnSub) {
      try { bot.layaBtnSub.text = "PRO v7.9 • MOD"; } catch(e) {}
    }
    console.log("[D-AUTO Mobile] Đã kích hoạt Plugin Mod v7.9 Mobile an toàn!");
  }
  initMobilePlugin();
})();
'''
    with open(SRC_DIR / "assets" / "live_ai_plugin.js", "w", encoding="utf-8") as f:
        f.write(mobile_plugin_code)

    # 6. Download lib.js if needed
    lib_path = SRC_DIR / "assets" / "lib.js"
    if not lib_path.exists():
        import urllib.request, ssl
        ctx = ssl._create_unverified_context()
        url = "https://rescdnft105vn.ridvqqxa.com/13528/libs/min/lib.js"
        with urllib.request.urlopen(url, context=ctx) as r:
            with open(lib_path, "wb") as f:
                f.write(r.read())

    # 7. Create index.html (Nạp tuần tự với Promise + Proxy Shim PlatformScript cho cả JS và Java)
    html_code = '''<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="utf-8" />
    <title>Hắc Tây Du - D-AUTO Mobile Pro v7.9</title>
    <meta name="viewport" content="width=device-width,initial-scale=1.0,minimum-scale=1.0,maximum-scale=1.0,user-scalable=no" />
    <meta name="renderer" content="webkit" />
    <meta name="apple-mobile-web-app-capable" content="yes" />
    <meta name="full-screen" content="true" />
    <meta name="x5-fullscreen" content="true" />
    <meta name="360-fullscreen" content="true" />
    <meta name="laya" screenorientation="portrait" />
    <style>
        html, body {
            width: 100%; height: 100%; margin: 0; padding: 0;
            overflow: hidden; background-color: #000000;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            user-select: none; -webkit-user-select: none;
        }
        @font-face {
            font-family: "Microsoft YaHei";
            src: url("https://rescdnft105vn.ridvqqxa.com/13528/res/font/msyh_vn.woff");
        }
        @font-face {
            font-family: "MyFont";
            src: url("https://rescdnft105vn.ridvqqxa.com/13528/res/font/msyh2_vn.woff");
        }
        #bootLoader {
            position: fixed; top: 0; left: 0; width: 100%; height: 100%;
            display: flex; flex-direction: column; align-items: center; justify-content: center;
            background: #080c14; z-index: 99999; color: #10b981;
            transition: opacity 0.4s ease;
        }
        .boot-icon {
            width: 70px; height: 70px; border-radius: 18px;
            background: linear-gradient(135deg, #f59e0b, #d97706);
            display: flex; align-items: center; justify-content: center;
            font-size: 36px; box-shadow: 0 10px 25px rgba(245, 158, 11, 0.4);
            margin-bottom: 24px;
        }
        .boot-title {
            font-size: 22px; font-weight: 800; color: #f8fafc;
            letter-spacing: 0.5px; margin-bottom: 6px;
        }
        .boot-sub {
            font-size: 13px; font-weight: 600; color: #10b981;
            text-transform: uppercase; letter-spacing: 2px; margin-bottom: 28px;
        }
        .spinner {
            width: 44px; height: 44px; border: 3px solid rgba(16, 185, 129, 0.15);
            border-top: 3px solid #10b981; border-radius: 50%;
            animation: spin 0.8s linear infinite; margin-bottom: 16px;
        }
        @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
        .boot-status {
            font-size: 13px; color: #94a3b8; max-width: 85%; text-align: center;
            line-height: 1.4; min-height: 40px;
        }
    </style>
</head>
<body>
    <div id="bootLoader">
        <div class="boot-icon">⚡</div>
        <div class="boot-title">HẮC TÂY DU</div>
        <div class="boot-sub">D-AUTO PRO v7.9 • ANDROID MOD</div>
        <div class="spinner"></div>
        <div id="bootMsg" class="boot-status">Đang chuẩn bị nạp dữ liệu...</div>
    </div>

    <script>
    // Định nghĩa Proxy Shim cho PlatformScript để bảo đảm KHÔNG BAO GIỜ bị undefined
    if (typeof window.PlatformScript === "undefined") {
        window.PlatformScript = {
            jsReady: function() { console.log("[JS Shim PlatformScript] jsReady called"); },
            login: function() { console.log("[JS Shim PlatformScript] login called"); },
            relogin: function() { console.log("[JS Shim PlatformScript] relogin called"); },
            logout: function() { console.log("[JS Shim PlatformScript] logout called"); },
            reloadWindow: function() { window.location.reload(); },
            openWindow: function(u) { window.open(u); },
            openGoogleScore: function() {},
            getPriceList: function() { return "[]"; },
            setPriceList: function() {},
            onCreateRole: function() {},
            onEnterGame: function() {},
            onLevelUp: function() {},
            pay: function() {},
            openUserCenter: function() {},
            onReport: function() {},
            fbShare: function() {},
            setLanguage: function() {},
            onBuyVoucher: function() {},
            onDashboard: function() {},
            onVipLevelUp: function() {}
        };
    }

    window.onerror = function(msg, url, line) {
        var errText = "Lỗi JS: " + msg + " (" + line + ")";
        console.error(errText);
        var el = document.getElementById("bootMsg");
        if (el) {
            el.style.color = "#ef4444";
            el.innerText = errText;
        }
    };

    (async function() {
        var msgEl = document.getElementById("bootMsg");
        function setStatus(text, color) {
            if (msgEl) {
                msgEl.innerText = text;
                if (color) msgEl.style.color = color;
            }
            console.log("[D-AUTO BOOT]", text);
        }

        function loadScript(src) {
            return new Promise(function(resolve, reject) {
                var s = document.createElement("script");
                s.src = src + "?v=" + Date.now();
                s.onload = function() { resolve(); };
                s.onerror = function(e) { reject(new Error("Không thể nạp tệp " + src)); };
                document.body.appendChild(s);
            });
        }

        try {
            var acc = localStorage.getItem("DAUTO_ACCOUNT_ID");
            if (!acc) {
                acc = "7" + Math.floor(10000000 + Math.random() * 90000000);
                localStorage.setItem("DAUTO_ACCOUNT_ID", acc);
            }

            setStatus("Đang nạp thư viện LayaAir 2.0 (lib.js)...");
            await loadScript("lib.js");

            setStatus("Đang nạp mã nguồn Mod (game.js)...");
            await loadScript("game.js");

            setStatus("Đang kích hoạt tiện ích Mod...");
            await loadScript("live_ai_plugin.js");

            setStatus("Xác thực bảo mật phiên Funtap [" + acc + "]...");
            var ts = "" + Math.floor(Date.now() / 1000);
            var authKey = "b72abd2d0909a2eda5f65dc7e8f25acb";

            try {
                var authUrl = "https://funtap-xy.xinliugame.net/funtap/igame.php?accountID=" + encodeURIComponent(acc) + "&token=r&v=1&appVersion=1.0.1";
                var resp = await fetch(authUrl);
                var txt = await resp.text();
                var mTs = txt.match(/GLOBAL_TIMESTAMP\\s*=\\s*"([^"]+)"/);
                var mAk = txt.match(/GLOBAL_AUTHKEY\\s*=\\s*"([^"]+)"/);
                if (mTs && mTs[1]) ts = mTs[1];
                if (mAk && mAk[1]) authKey = mAk[1];
            } catch(e) {
                console.warn("Auth token fallback:", e);
            }

            setStatus("Khởi tạo cấu hình trò chơi...");
            window.DAUTO_FORCE_PORTRAIT = true;
            window.DAUTO_CLIENT_TYPE = "Mobile-Standalone-v7.9";

            var G = window.Global || (typeof Global !== "undefined" ? Global : null);
            if (!G) {
                throw new Error("Không tìm thấy đối tượng Global trong game.js");
            }

            G.GLOBAL_PLATEFORM = true;
            G.GLOBAL_HIDE_IP = "1";
            G.GLOBAL_SHOW_IP = false;
            G.SHOW_DEBUG_LOGIN = false;
            G.GLOBAL_ACCOUNT = acc;
            G.ACCOUNT = acc;
            G.GLOBAL_OPENID = acc;
            G.GLOBAL_USER_IP = "14.231.169.242";
            G.GLOBAL_REGION = "VN";
            G.GLOBAL_PF = "android_funtap";
            G.GAME_PLATFORM = "funtap";
            G.GLOBAL_ENTRY_DOMAIN = "https://funtap-xy.ridvqqxa.com/";
            G.GLOBAL_ACCOUNT_PREFIX = "1";
            G.GLOBAL_LANG = "vn";
            G.GLOBAL_INVITER = "";
            G.RESHOST = "https://rescdnft105vn.ridvqqxa.com/13528/";
            G.GLOBAL_APPID = "android";
            G.GLOBAL_VERSION = "13528";
            G.GLOBAL_LOG_LOGIN = "https://funtap-xy.ridvqqxa.com/game/login.php";
            G.GLOBAL_ALL_SERVER_LIST = "https://funtap-xy.ridvqqxa.com/game/getServerList2.php";
            G.GLOBAL_LAST_SERVER_LIST = "https://funtap-xy.ridvqqxa.com/game/getServerList2.php";
            G.GLOBAL_NOTICE_QUERY = "https://center1-funtap-xy.xinliugame.net/api/get_notice2.php";
            G.GLOBAL_AGE_QUERY = "https://center1-funtap-xy.xinliugame.net/api/cadpa.php";
            G.GLOBAL_PRIVATE_QUERY = "https://center1-funtap-xy.xinliugame.net/api/user_agreement.php";
            G.GLOBAL_TIMESTAMP = ts;
            G.GLOBAL_AUTHKEY = authKey;
            G.font1 = "Microsoft YaHei";
            G.font2 = "MyFont";
            G.GLOBAL_SDK_LOGIN = 0;
            G.debugKey = false;
            G.GLOBAL_LOGO = 0;
            G.IS_TISHEN = 0;
            G.censor = null;
            G.GLOBAL_LOGIN_AUDIO = 1;
            G.GLOBAL_LOGIN_MUSIC = 1;
            G.FIRST_OPEN_TIME = 1749693600;
            G.debugGuide = false;
            G.GLOBAL_VN_AGE_TIP = 0;
            
            // Khóa chặt không bao giờ tự động nhảy vào game:
            G.GLOBAL_DIRECT_ENTER = 0;

            if (typeof window.start !== "function") {
                throw new Error("Không tìm thấy hàm window.start");
            }

            setStatus("Đang tải dữ liệu đồ họa & vào máy chủ...");
            window.start(1, 1, 1, 1);

            setTimeout(function() {
                var loader = document.getElementById("bootLoader");
                if (loader) {
                    loader.style.opacity = "0";
                    setTimeout(function() { loader.style.display = "none"; }, 400);
                }
            }, 1200);
        } catch(err) {
            setStatus("LỖI: " + (err.message || err), "#ef4444");
            console.error("BOOT CRITICAL ERROR:", err);
        }
    })();
    </script>
</body>
</html>
'''
    if not (SRC_DIR / "assets" / "index.html").exists():
        with open(SRC_DIR / "assets" / "index.html", "w", encoding="utf-8") as f:
            f.write(html_code)

    print("   ✅ Đã chèn mã nguồn Mod game.js, lib.js, live_ai_plugin.js & index.html vào assets của App.")

def compile_apk():
    print("⚙️  [2/6] Biên dịch tài nguyên với AAPT2...")
    res_zip = OUT_DIR / "res.zip"
    subprocess.run([
        str(AAPT2), "compile",
        "--dir", str(SRC_DIR / "res"),
        "-o", str(res_zip)
    ], check=True, capture_output=True)

    print("⚙️  [3/6] Liên kết (link) tạo APK và R.java...")
    unaligned_apk = OUT_DIR / "unaligned.apk"
    gen_dir = OUT_DIR / "gen"
    gen_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run([
        str(AAPT2), "link",
        "-I", str(ANDROID_JAR),
        "-A", str(SRC_DIR / "assets"),
        "--manifest", str(SRC_DIR / "AndroidManifest.xml"),
        "--java", str(gen_dir),
        "-o", str(unaligned_apk),
        str(res_zip),
        "--auto-add-overlay"
    ], check=True, capture_output=True)

    print("☕ [4/6] Biên dịch Java sang bytecode (javac)...")
    classes_dir = OUT_DIR / "classes"
    classes_dir.mkdir(parents=True, exist_ok=True)
    java_files = list((SRC_DIR / "src").rglob("*.java")) + list(gen_dir.rglob("*.java"))
    cmd_javac = [
        str(JAVAC),
        "-encoding", "UTF-8",
        "-cp", str(ANDROID_JAR),
        "-d", str(classes_dir)
    ] + [str(f) for f in java_files]
    subprocess.run(cmd_javac, check=True, capture_output=True)

    print("🤖 [5/6] Chuyển đổi bytecode sang Dalvik DEX (d8)...")
    dex_dir = OUT_DIR / "dex"
    dex_dir.mkdir(parents=True, exist_ok=True)
    class_files = list(classes_dir.rglob("*.class"))
    cmd_d8 = [
        "cmd.exe", "/c", str(D8),
        "--lib", str(ANDROID_JAR),
        "--output", str(dex_dir)
    ] + [str(f) for f in class_files]
    subprocess.run(cmd_d8, check=True, capture_output=True)

    # Thêm classes.dex vào unaligned.apk
    with zipfile.ZipFile(unaligned_apk, "a") as z:
        z.write(dex_dir / "classes.dex", arcname="classes.dex")

    print("✍️  [6/6] Zipalign và Ký số APK bằng apksigner...")
    aligned_apk = OUT_DIR / "aligned.apk"
    if aligned_apk.exists():
        aligned_apk.unlink()
    subprocess.run([
        str(ZIPALIGN), "-p", "-f", "4",
        str(unaligned_apk), str(aligned_apk)
    ], check=True, capture_output=True)

    output_apk = Path("HacTayDu_Auto_Mod_V9.apk")
    output_apk_v11 = Path("HacTayDu_Auto_Mod_V11.apk")
    if output_apk.exists():
        output_apk.unlink()
    shutil.copy(aligned_apk, output_apk)

    # Đảm bảo keystore
    keystore = Path("debug.keystore")
    if not keystore.exists():
        subprocess.run([
            "keytool", "-genkeypair", "-v",
            "-keystore", str(keystore),
            "-alias", "androiddebugkey",
            "-keyalg", "RSA", "-keysize", "2048",
            "-validity", "10000",
            "-storepass", "android", "-keypass", "android",
            "-dname", "CN=Android Debug,O=Android,C=US"
        ], check=True, capture_output=True)

    # Sign with apksigner (v1 + v2 + v3)
    cmd_sign = [
        "cmd.exe", "/c", str(APKSIGNER), "sign",
        "--ks", str(keystore),
        "--ks-key-alias", "androiddebugkey",
        "--ks-pass", "pass:android",
        "--key-pass", "pass:android",
        str(output_apk)
    ]
    subprocess.run(cmd_sign, check=True, capture_output=True)

    shutil.copy(output_apk, output_apk_v11)

    print(f"\n🎉 HOÀN THÀNH BIÊN DỊCH BẢN MOD APK STANDALONE V10.0.0.0 (3-TAB UI)!")
    print(f"📁 Tên file: {output_apk.resolve()}")
    print(f"📁 File V11: {output_apk_v11.resolve()}")
    print(f"📊 Dung lượng: {output_apk.stat().st_size / 1024 / 1024:.2f} MB")
    print(f"🏷️  Package Name: {PACKAGE_NAME} (Chạy song song, không cần gỡ app gốc!)")

def main():
    create_project_structure()
    compile_apk()

if __name__ == "__main__":
    main()
