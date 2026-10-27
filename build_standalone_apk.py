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
APP_NAME = "Hắc Tây Du Mod v10.0.1"
VERSION_CODE = "1001"
VERSION_NAME = "10.0.1"

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
import android.content.Context;
import android.content.SharedPreferences;
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
import java.io.BufferedReader;
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.util.HashMap;
import java.util.Map;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import org.json.JSONObject;

public class MainActivity extends Activity {
    private static final String TAG = "DAUTO_PRO";
    private WebView webView;

    private byte[] libJsBytes;
    private byte[] gameJsBytes;
    private byte[] pluginJsBytes;
    private String indexHtml;

    public static JSONObject doFuntapLogin(String username, String password) {
        JSONObject res = new JSONObject();
        try {
            username = username != null ? username.trim() : "";
            password = password != null ? password.trim() : "";
            if (username.isEmpty() || password.isEmpty()) {
                res.put("ok", false);
                res.put("error", "Vui lòng nhập đầy đủ Tài khoản/Email và Mật khẩu!");
                return res;
            }

            String[] endpoints = new String[]{
                "https://core.sdkmain.com/api/v1/apps/f0d9c5e4b5d0de9bd966ed884c72e5ad/vi/auth/login",
                "https://core.sdkmain.com/api/v1/apps/f0d9c5e4b5d0de9bd966ed884c72e5ad/com.loinguyen.nguoigiuuuuu.ftg/auth/login"
            };

            String postBody = "email=" + URLEncoder.encode(username, "UTF-8")
                    + "&password=" + URLEncoder.encode(password, "UTF-8")
                    + "&device_os=18.0&device_name=iPhone&device_resolution=1170x2532&device_network=1&sdk_version=7.0.0";
            byte[] postBytes = postBody.getBytes(StandardCharsets.UTF_8);

            JSONObject respJson = null;
            String lastErr = "Thông tin đăng nhập không chính xác.";

            for (String ep : endpoints) {
                HttpURLConnection conn = null;
                try {
                    URL url = new URL(ep);
                    conn = (HttpURLConnection) url.openConnection();
                    conn.setRequestMethod("POST");
                    conn.setConnectTimeout(8000);
                    conn.setReadTimeout(8000);
                    conn.setDoOutput(true);
                    conn.setRequestProperty("Content-Type", "application/x-www-form-urlencoded");
                    conn.setRequestProperty("Accept", "application/json");
                    conn.setRequestProperty("User-Agent", "HacTayDu/1.0.1 (iPhone; iOS 18.0; Scale/3.00)");
                    conn.setRequestProperty("Origin", "https://funtap-xy.ridvqqxa.com");

                    OutputStream os = conn.getOutputStream();
                    os.write(postBytes);
                    os.flush();
                    os.close();

                    int code = conn.getResponseCode();
                    InputStream is = (code >= 200 && code < 400) ? conn.getInputStream() : conn.getErrorStream();
                    String raw = "";
                    if (is != null) {
                        BufferedReader reader = new BufferedReader(new InputStreamReader(is, StandardCharsets.UTF_8));
                        StringBuilder sb = new StringBuilder();
                        String line;
                        while ((line = reader.readLine()) != null) {
                            sb.append(line);
                        }
                        reader.close();
                        raw = sb.toString();
                    }

                    if (!raw.isEmpty()) {
                        JSONObject data = new JSONObject(raw);
                        if (data.has("data") && (data.has("access_token") || data.optJSONObject("data") != null)) {
                            respJson = data;
                            break;
                        }
                        if (data.has("message")) {
                            lastErr = data.optString("message");
                        }
                    }
                } catch (Exception e) {
                    lastErr = e.getMessage() != null ? e.getMessage() : e.toString();
                } finally {
                    if (conn != null) conn.disconnect();
                }
            }

            if (respJson == null) {
                res.put("ok", false);
                res.put("error", lastErr);
                return res;
            }

            JSONObject d = respJson.optJSONObject("data");
            if (d == null) d = new JSONObject();
            JSONObject accObj = d.optJSONObject("account");
            String accountId = (accObj != null && accObj.has("account_id")) ? accObj.optString("account_id")
                    : (d.has("id") ? d.optString("id") : username);
            String funId = d.has("id") ? d.optString("id") : accountId;
            String funName = d.has("name") ? d.optString("name") : username;
            String accessToken = respJson.optString("access_token", "r");

            // Query igame.php for authKey and timestamp
            JSONObject akInfo = doFetchAuthKey(accountId, accessToken);
            if (akInfo.optBoolean("ok")) {
                if (akInfo.has("accountId") && !akInfo.optString("accountId").isEmpty()) {
                    accountId = akInfo.optString("accountId");
                }
            }

            res.put("ok", true);
            res.put("accountId", accountId);
            res.put("accessToken", accessToken);
            res.put("funId", funId);
            res.put("username", funName);
            res.put("timestamp", akInfo.optString("timestamp", "" + (System.currentTimeMillis() / 1000)));
            res.put("authKey", akInfo.optString("authKey", "b72abd2d0909a2eda5f65dc7e8f25acb"));
            res.put("userIp", akInfo.optString("userIp", "14.231.169.242"));
            return res;

        } catch (Exception e) {
            try {
                res.put("ok", false);
                res.put("error", "Lỗi: " + (e.getMessage() != null ? e.getMessage() : e.toString()));
            } catch (Exception ignored) {}
            return res;
        }
    }

    public static JSONObject doFetchAuthKey(String accountId, String token) {
        JSONObject res = new JSONObject();
        HttpURLConnection conn = null;
        try {
            if (accountId == null || accountId.isEmpty()) accountId = "230519465";
            if (token == null || token.isEmpty()) token = "r";

            String authUrl = "https://funtap-xy.xinliugame.net/funtap/igame.php?accountID="
                    + URLEncoder.encode(accountId, "UTF-8")
                    + "&token=" + URLEncoder.encode(token, "UTF-8")
                    + "&v=1&appVersion=1.0.1";

            URL url = new URL(authUrl);
            conn = (HttpURLConnection) url.openConnection();
            conn.setRequestMethod("GET");
            conn.setConnectTimeout(8000);
            conn.setReadTimeout(8000);
            conn.setRequestProperty("User-Agent", "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X)");

            int code = conn.getResponseCode();
            InputStream is = (code >= 200 && code < 400) ? conn.getInputStream() : conn.getErrorStream();
            StringBuilder sb = new StringBuilder();
            if (is != null) {
                BufferedReader reader = new BufferedReader(new InputStreamReader(is, StandardCharsets.UTF_8));
                String line;
                while ((line = reader.readLine()) != null) {
                    sb.append(line);
                }
                reader.close();
            }
            String txt = sb.toString();

            Pattern pTs = Pattern.compile("GLOBAL_TIMESTAMP\\s*=\\s*\"([^\"]+)\"");
            Pattern pAk = Pattern.compile("GLOBAL_AUTHKEY\\s*=\\s*\"([^\"]+)\"");
            Pattern pAcc = Pattern.compile("GLOBAL_ACCOUNT\\s*=\\s*\"([^\"]+)\"");
            Pattern pIp = Pattern.compile("GLOBAL_USER_IP\\s*=\\s*\"([^\"]*)\"");

            Matcher mTs = pTs.matcher(txt);
            Matcher mAk = pAk.matcher(txt);
            Matcher mAcc = pAcc.matcher(txt);
            Matcher mIp = pIp.matcher(txt);

            String ts = mTs.find() ? mTs.group(1) : ("" + (System.currentTimeMillis() / 1000));
            String ak = mAk.find() ? mAk.group(1) : "b72abd2d0909a2eda5f65dc7e8f25acb";
            String resolvedAcc = mAcc.find() ? mAcc.group(1) : accountId;
            String userIp = (mIp.find() && !mIp.group(1).trim().isEmpty()) ? mIp.group(1).trim() : "14.231.169.242";

            res.put("ok", true);
            res.put("timestamp", ts);
            res.put("authKey", ak);
            res.put("accountId", resolvedAcc);
            res.put("userIp", userIp);
            return res;

        } catch (Exception e) {
            try {
                res.put("ok", false);
                res.put("timestamp", "" + (System.currentTimeMillis() / 1000));
                res.put("authKey", "b72abd2d0909a2eda5f65dc7e8f25acb");
                res.put("accountId", accountId);
                res.put("userIp", "14.231.169.242");
            } catch (Exception ignored) {}
            return res;
        } finally {
            if (conn != null) conn.disconnect();
        }
    }

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

        @JavascriptInterface
        public String funtapLogin(String username, String password) {
            Log.d(TAG, "[PlatformScript] funtapLogin called for: " + username);
            JSONObject res = doFuntapLogin(username, password);
            return res.toString();
        }

        @JavascriptInterface
        public String fetchAuthKey(String accountId, String token) {
            Log.d(TAG, "[PlatformScript] fetchAuthKey called for: " + accountId);
            JSONObject res = doFetchAuthKey(accountId, token);
            return res.toString();
        }

        @JavascriptInterface
        public void saveCredentials(String username, String password, String accountId) {
            try {
                SharedPreferences sp = getSharedPreferences("dauto_creds", Context.MODE_PRIVATE);
                sp.edit()
                    .putString("username", username)
                    .putString("password", password)
                    .putString("accountId", accountId)
                    .apply();
            } catch (Exception e) {
                Log.e(TAG, "saveCredentials error", e);
            }
        }

        @JavascriptInterface
        public String getSavedCredentials() {
            try {
                SharedPreferences sp = getSharedPreferences("dauto_creds", Context.MODE_PRIVATE);
                JSONObject o = new JSONObject();
                o.put("username", sp.getString("username", ""));
                o.put("password", sp.getString("password", ""));
                o.put("accountId", sp.getString("accountId", ""));
                return o.toString();
            } catch (Exception e) {
                return "{}";
            }
        }
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
                if (url.contains("/api/authkey")) {
                    try {
                        String acc = "230519465";
                        String tok = "r";
                        int accIdx = url.indexOf("acc=");
                        if (accIdx != -1) {
                            int end = url.indexOf("&", accIdx);
                            acc = end != -1 ? url.substring(accIdx + 4, end) : url.substring(accIdx + 4);
                            acc = java.net.URLDecoder.decode(acc, "UTF-8");
                        }
                        int tokIdx = url.indexOf("token=");
                        if (tokIdx != -1) {
                            int end = url.indexOf("&", tokIdx);
                            tok = end != -1 ? url.substring(tokIdx + 6, end) : url.substring(tokIdx + 6);
                            tok = java.net.URLDecoder.decode(tok, "UTF-8");
                        }
                        JSONObject res = doFetchAuthKey(acc, tok);
                        return serveBytes(res.toString().getBytes(StandardCharsets.UTF_8), "application/json");
                    } catch (Exception e) {
                        Log.e(TAG, "handleIntercept /api/authkey error", e);
                    }
                }
                if (url.contains("/funtap/igame.php")) {
                    try {
                        int qIdx = url.indexOf("?");
                        String q = qIdx != -1 ? url.substring(qIdx) : "";
                        String acc = "230519465";
                        String tok = "r";
                        int accIdx = q.indexOf("accountID=");
                        if (accIdx != -1) {
                            int end = q.indexOf("&", accIdx);
                            acc = end != -1 ? q.substring(accIdx + 10, end) : q.substring(accIdx + 10);
                        }
                        int tokIdx = q.indexOf("token=");
                        if (tokIdx != -1) {
                            int end = q.indexOf("&", tokIdx);
                            tok = end != -1 ? q.substring(tokIdx + 6, end) : q.substring(tokIdx + 6);
                        }
                        JSONObject res = doFetchAuthKey(acc, tok);
                        String fakePhp = "GLOBAL_TIMESTAMP = \"" + res.optString("timestamp") + "\";\n"
                                + "GLOBAL_AUTHKEY = \"" + res.optString("authKey") + "\";\n"
                                + "GLOBAL_ACCOUNT = \"" + res.optString("accountId") + "\";\n"
                                + "GLOBAL_USER_IP = \"" + res.optString("userIp") + "\";\n";
                        return serveBytes(fakePhp.getBytes(StandardCharsets.UTF_8), "text/html");
                    } catch (Exception e) {
                        Log.e(TAG, "handleIntercept igame.php error", e);
                    }
                }
                return null;
            }

            private WebResourceResponse serveBytes(byte[] data, String mimeType) {
                if (data == null) return null;
                Map<String, String> headers = new HashMap<>();
                headers.put("Access-Control-Allow-Origin", "*");
                headers.put("Access-Control-Allow-Methods", "GET, POST, OPTIONS");
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
    main_java_file = SRC_DIR / "src" / "vn" / "ftg" / "hactaydu" / "dauto" / "MainActivity.java"
    if not main_java_file.exists():
        with open(main_java_file, "w", encoding="utf-8") as f:
            f.write(java_code)

    # 4. Chuẩn bị và bảo tồn game.js chuyên dụng cho Mobile (UI v10 3-TAB)
    target_game_js = SRC_DIR / "assets" / "game.js"
    with open("js/game.js", "r", encoding="utf-8") as f:
        game_js = f.read()
    with open(target_game_js, "w", encoding="utf-8") as f:
        f.write(game_js)

    # 5. Plugin chuyên dụng cho Mobile (Tắt sạch reroll, chỉ bật Mod Speed x5, Skip 0s, Auto Tháp)
    mobile_plugin_code = '''// ============================================================================
// D-AUTO PRO v10.0.1 (MOBILE STANDALONE PLUGIN)
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
      try { bot.layaBtnSub.text = "v10.0.1"; } catch(e) {}
    }
    console.log("[D-AUTO Mobile] Đã kích hoạt Plugin Mod v10.0.1 an toàn!");
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
        url = "https://rescdnft105vn.ridvqqxa.com/13542/libs/min/lib.js"
        with urllib.request.urlopen(url, context=ctx) as r:
            with open(lib_path, "wb") as f:
                f.write(r.read())

    # 7. Create index.html (Nạp tuần tự với Promise + Proxy Shim PlatformScript cho cả JS và Java)
    html_code = r'''<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="utf-8" />
    <title>Hắc Tây Du - D-AUTO Mobile Pro v10.0.1</title>
    <meta name="viewport" content="width=device-width,initial-scale=1.0,minimum-scale=1.0,maximum-scale=1.0,user-scalable=no" />
    <meta name="renderer" content="webkit" />
    <meta name="apple-mobile-web-app-capable" content="yes" />
    <meta name="full-screen" content="true" />
    <meta name="x5-fullscreen" content="true" />
    <meta name="360-fullscreen" content="true" />
    <meta name="laya" screenorientation="portrait" />
    <style>
        * { box-sizing: border-box; -webkit-tap-highlight-color: transparent; }
        html, body {
            width: 100%; height: 100%; margin: 0; padding: 0;
            overflow: hidden; background-color: #060913;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            user-select: none; -webkit-user-select: none;
            color: #f8fafc;
        }
        @font-face {
            font-family: "Microsoft YaHei";
            src: url("https://rescdnft105vn.ridvqqxa.com/13542/res/font/msyh_vn.woff");
        }
        @font-face {
            font-family: "MyFont";
            src: url("https://rescdnft105vn.ridvqqxa.com/13542/res/font/msyh2_vn.woff");
        }
        #bootLoader {
            position: fixed; top: 0; left: 0; width: 100%; height: 100%;
            display: flex; flex-direction: column; align-items: center; justify-content: center;
            background: radial-gradient(circle at 50% 25%, #131d33 0%, #060913 100%);
            z-index: 99999; color: #10b981;
            padding: 20px;
            transition: opacity 0.4s ease;
            overflow-y: auto;
        }
        .boot-card {
            width: 100%; max-width: 440px;
            background: rgba(15, 23, 42, 0.88);
            border: 1px solid rgba(51, 65, 85, 0.7);
            border-radius: 20px;
            padding: 24px 20px;
            box-shadow: 0 20px 40px rgba(0, 0, 0, 0.6), 0 0 30px rgba(16, 185, 129, 0.1);
            backdrop-filter: blur(12px);
            display: flex; flex-direction: column; align-items: center;
        }
        .boot-icon {
            width: 64px; height: 64px; border-radius: 16px;
            background: linear-gradient(135deg, #f59e0b, #d97706);
            display: flex; align-items: center; justify-content: center;
            font-size: 32px; box-shadow: 0 8px 24px rgba(245, 158, 11, 0.4);
            margin-bottom: 12px;
        }
        .boot-title {
            font-size: 22px; font-weight: 800; color: #f8fafc;
            letter-spacing: 0.5px; margin-bottom: 4px; text-align: center;
        }
        .boot-sub {
            font-size: 11.5px; font-weight: 700; color: #10b981;
            text-transform: uppercase; letter-spacing: 1.5px; margin-bottom: 18px; text-align: center;
        }
        .tab-bar {
            width: 100%; display: flex; gap: 8px; margin-bottom: 16px;
            background: #090e1a; padding: 4px; border-radius: 12px;
            border: 1px solid #1e293b;
        }
        .tab-btn {
            flex: 1; padding: 9px 4px; font-size: 13px; font-weight: 700;
            border-radius: 8px; border: none; cursor: pointer;
            background: transparent; color: #94a3b8; transition: all 0.2s ease;
        }
        .tab-btn.active {
            background: #1e293b; color: #38bdf8;
            box-shadow: 0 2px 8px rgba(0,0,0,0.4);
        }
        .form-panel {
            width: 100%; display: flex; flex-direction: column; gap: 12px;
        }
        .inp-group {
            width: 100%; display: flex; flex-direction: column; gap: 5px;
        }
        .inp-label {
            font-size: 12px; font-weight: 600; color: #cbd5e1;
        }
        .inp-wrap {
            position: relative; width: 100%;
        }
        .inp-field {
            width: 100%; height: 46px; background: #0b1120;
            border: 1.5px solid #27354f; border-radius: 10px;
            color: #f8fafc; font-size: 14.5px; padding: 0 42px 0 12px;
            outline: none; transition: border-color 0.2s;
        }
        .inp-field:focus {
            border-color: #38bdf8;
        }
        .toggle-pwd {
            position: absolute; right: 10px; top: 50%; transform: translateY(-50%);
            background: none; border: none; color: #94a3b8; font-size: 17px;
            cursor: pointer; padding: 6px;
        }
        .check-row {
            display: flex; align-items: center; gap: 8px;
            font-size: 12.5px; color: #94a3b8; cursor: pointer; margin-top: 2px;
        }
        .check-row input[type="checkbox"] {
            width: 16px; height: 16px; accent-color: #10b981; cursor: pointer;
        }
        .btn-main {
            width: 100%; height: 48px; border-radius: 10px; border: none;
            background: linear-gradient(135deg, #10b981, #059669);
            color: #ffffff; font-size: 15px; font-weight: 800;
            cursor: pointer; display: flex; align-items: center; justify-content: center;
            box-shadow: 0 4px 16px rgba(16, 185, 129, 0.35);
            transition: all 0.2s ease; margin-top: 6px;
        }
        .btn-main:active {
            transform: scale(0.98); opacity: 0.9;
        }
        .btn-sec {
            width: 100%; height: 40px; border-radius: 10px;
            background: #1e293b; border: 1px solid #334155;
            color: #cbd5e1; font-size: 13.5px; font-weight: 700;
            cursor: pointer; display: flex; align-items: center; justify-content: center;
            transition: all 0.2s ease;
        }
        .btn-sec:active { transform: scale(0.98); }
        .saved-box {
            width: 100%; background: #064e3b2e; border: 1.5px solid #10b981;
            border-radius: 12px; padding: 12px 14px; margin-bottom: 12px;
            display: flex; flex-direction: column; gap: 8px;
        }
        .saved-info {
            font-size: 13px; color: #a7f3d0; line-height: 1.4;
        }
        .saved-btns {
            display: flex; gap: 8px; margin-top: 4px;
        }
        .saved-btns button {
            flex: 1; height: 40px; border-radius: 8px; font-size: 13px; font-weight: 700;
            cursor: pointer; border: none;
        }
        .btn-enter-saved {
            background: #10b981; color: #022c22;
        }
        .btn-switch-saved {
            background: #1e293b; color: #cbd5e1; border: 1px solid #334155 !important;
        }
        .spinner {
            width: 32px; height: 32px; border: 3px solid rgba(16, 185, 129, 0.15);
            border-top: 3px solid #10b981; border-radius: 50%;
            animation: spin 0.8s linear infinite; margin: 12px auto;
            display: none;
        }
        @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
        .boot-status {
            font-size: 12.5px; color: #94a3b8; width: 100%; text-align: center;
            line-height: 1.4; min-height: 24px; margin-top: 10px;
        }
        .badge-mod {
            background: rgba(245, 158, 11, 0.15); border: 1px solid #f59e0b;
            color: #fcd34d; font-size: 11px; padding: 3px 8px; border-radius: 6px;
            margin-bottom: 14px; font-weight: 600; text-align: center;
        }
    </style>
</head>
<body>
    <div id="bootLoader">
        <div class="boot-card">
            <div class="boot-icon">⚡</div>
            <div class="boot-title">HẮC TÂY DU</div>
            <div class="boot-sub">D-AUTO PRO v10.0.1 • BUILD 13542</div>
            <div class="badge-mod">🚀 Mod v10.0.1 • x5 Tốc Độ • Skip 0s • Auto Phù Đồ Tháp 0đ</div>

            <!-- Khung Tài khoản đã lưu (nếu có) -->
            <div id="savedBox" class="saved-box" style="display: none;">
                <div id="savedInfoTxt" class="saved-info">
                    👤 Tài khoản đã lưu: <b id="savedUserTxt"></b><br />
                    🆔 UID: <b id="savedUidTxt"></b>
                </div>
                <div class="saved-btns">
                    <button id="btnEnterSaved" class="btn-enter-saved" onclick="handleEnterSaved()">🚀 VÀO GAME (<span id="countDownTxt">3s</span>)</button>
                    <button class="btn-switch-saved" onclick="handleSwitchAccount()">🔄 ĐỔI NICK</button>
                </div>
            </div>

            <!-- Tabs đăng nhập -->
            <div id="tabBar" class="tab-bar">
                <button id="tabBtnFt" class="tab-btn active" onclick="switchTab('ft')">🔑 ĐĂNG NHẬP FUNTAP</button>
                <button id="tabBtnUid" class="tab-btn" onclick="switchTab('uid')">⚡ CHƠI NHANH (UID)</button>
            </div>

            <!-- Panel 1: Đăng nhập Funtap (TK & Pass) -->
            <div id="panelFt" class="form-panel">
                <div class="inp-group">
                    <label class="inp-label" for="inpFtUser">Tài khoản / Email / SĐT Funtap:</label>
                    <div class="inp-wrap">
                        <input id="inpFtUser" class="inp-field" type="text" placeholder="Nhập tài khoản Funtap..." autocomplete="username" />
                    </div>
                </div>
                <div class="inp-group">
                    <label class="inp-label" for="inpFtPass">Mật khẩu Funtap:</label>
                    <div class="inp-wrap">
                        <input id="inpFtPass" class="inp-field" type="password" placeholder="Nhập mật khẩu..." autocomplete="current-password" />
                        <button type="button" class="toggle-pwd" onclick="togglePasswordVisibility()">👁️</button>
                    </div>
                </div>
                <label class="check-row">
                    <input id="chkRemember" type="checkbox" checked /> Ghi nhớ tài khoản & mật khẩu
                </label>
                <button id="btnFtLogin" class="btn-main" onclick="handleFuntapLogin()">🔑 ĐĂNG NHẬP FUNTAP & VÀO GAME</button>
            </div>

            <!-- Panel 2: Chơi nhanh bằng UID -->
            <div id="panelUid" class="form-panel" style="display: none;">
                <div class="inp-group">
                    <label class="inp-label" for="inpUid">Mã UID Tài khoản (Khách/Chơi ngay):</label>
                    <div class="inp-wrap">
                        <input id="inpUid" class="inp-field" type="text" placeholder="Ví dụ: 720524013" />
                    </div>
                </div>
                <button type="button" class="btn-sec" onclick="generateRandomUid()">🎲 TẠO MÃ UID NGẪU NHIÊN MỚI</button>
                <button id="btnUidLogin" class="btn-main" onclick="handleUidLogin()">🚀 VÀO GAME BẰNG UID NÀY</button>
            </div>

            <div id="bootSpinner" class="spinner"></div>
            <div id="bootMsg" class="boot-status">Sẵn sàng khởi động phiên bản Mod v10.0.1.</div>
        </div>
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
            onVipLevelUp: function() {},
            saveCredentials: function(u, p, acc) {},
            getSavedCredentials: function() { return "{}"; }
        };
    }

    var _scriptsLoaded = false;
    var _autoCountDownTimer = null;
    var _countDownVal = 3;

    function setStatus(text, color) {
        var el = document.getElementById("bootMsg");
        if (el) {
            el.innerText = text;
            el.style.color = color || "#94a3b8";
        }
        console.log("[D-AUTO BOOT]", text);
    }

    function showSpinner(show) {
        var s = document.getElementById("bootSpinner");
        if (s) s.style.display = show ? "block" : "none";
    }

    function switchTab(tab) {
        cancelAutoCountDown();
        var isFt = (tab === "ft");
        document.getElementById("tabBtnFt").className = "tab-btn " + (isFt ? "active" : "");
        document.getElementById("tabBtnUid").className = "tab-btn " + (!isFt ? "active" : "");
        document.getElementById("panelFt").style.display = isFt ? "flex" : "none";
        document.getElementById("panelUid").style.display = !isFt ? "flex" : "none";
    }

    function togglePasswordVisibility() {
        var p = document.getElementById("inpFtPass");
        if (p) {
            p.type = (p.type === "password") ? "text" : "password";
        }
    }

    function generateRandomUid() {
        var r = "7" + Math.floor(10000000 + Math.random() * 90000000);
        document.getElementById("inpUid").value = r;
        setStatus("🎲 Đã tạo mã UID ngẫu nhiên: " + r, "#38bdf8");
    }

    function cancelAutoCountDown() {
        if (_autoCountDownTimer) {
            clearInterval(_autoCountDownTimer);
            _autoCountDownTimer = null;
        }
        var btn = document.getElementById("btnEnterSaved");
        if (btn) btn.innerText = "🚀 VÀO GAME NGAY";
    }

    function handleSwitchAccount() {
        cancelAutoCountDown();
        document.getElementById("savedBox").style.display = "none";
        document.getElementById("tabBar").style.display = "flex";
        document.getElementById("panelFt").style.display = "flex";
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

    async function ensureModScripts() {
        if (_scriptsLoaded) return;
        setStatus("Đang nạp thư viện LayaAir 2.0 (lib.js)...");
        await loadScript("lib.js");
        setStatus("Đang nạp mã nguồn Mod 13542 (game.js)...");
        await loadScript("game.js");
        setStatus("Đang kích hoạt tiện ích Mod D-AUTO...");
        await loadScript("live_ai_plugin.js");
        _scriptsLoaded = true;
    }

    // Xác thực Funtap MontarSDK qua Native Java Bridge hoặc Fetch
    async function authenticateFuntap(username, password) {
        // 1. Thử gọi Native Java Bridge
        if (window.PlatformScript && window.PlatformScript.funtapLogin) {
            try {
                var raw = window.PlatformScript.funtapLogin(username, password);
                var res = JSON.parse(raw);
                if (res && res.ok) return res;
                if (res && res.error) throw new Error(res.error);
            } catch(e) {
                console.warn("Native funtapLogin fallback:", e);
                if (e.message && e.message.indexOf("không chính xác") !== -1) {
                    throw e;
                }
            }
        }

        // 2. Fallback Fetch trực tiếp đến API MontarSDK
        var endpoints = [
            "https://core.sdkmain.com/api/v1/apps/f0d9c5e4b5d0de9bd966ed884c72e5ad/vi/auth/login",
            "https://core.sdkmain.com/api/v1/apps/f0d9c5e4b5d0de9bd966ed884c72e5ad/com.loinguyen.nguoigiuuuuu.ftg/auth/login"
        ];
        var formBody = "email=" + encodeURIComponent(username)
            + "&password=" + encodeURIComponent(password)
            + "&device_os=18.0&device_name=iPhone&device_resolution=1170x2532&device_network=1&sdk_version=7.0.0";

        var tokenData = null;
        var lastErr = "Thông tin đăng nhập không chính xác.";

        for (var i = 0; i < endpoints.length; i++) {
            try {
                var resp = await fetch(endpoints[i], {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/x-www-form-urlencoded",
                        "Accept": "application/json"
                    },
                    body: formBody
                });
                var data = await resp.json();
                if (data && (data.access_token || (data.data && data.data.id))) {
                    tokenData = data;
                    break;
                }
                if (data && data.message) lastErr = data.message;
            } catch(e) {
                lastErr = e.message || String(e);
            }
        }

        if (!tokenData) throw new Error(lastErr);

        var d = tokenData.data || {};
        var accObj = d.account || {};
        var accId = String(accObj.account_id || d.id || username);
        var funName = String(d.name || username);
        var tok = String(tokenData.access_token || "r");

        // Lấy authKey và timestamp từ igame.php
        var akRes = await fetchAccountAuthKey(accId, tok);
        return {
            ok: true,
            accountId: akRes.accountId || accId,
            accessToken: tok,
            username: funName,
            timestamp: akRes.timestamp,
            authKey: akRes.authKey,
            userIp: akRes.userIp || "14.231.169.242"
        };
    }

    async function fetchAccountAuthKey(accountId, token) {
        if (window.PlatformScript && window.PlatformScript.fetchAuthKey) {
            try {
                var raw = window.PlatformScript.fetchAuthKey(accountId, token || "r");
                var parsed = JSON.parse(raw);
                if (parsed && parsed.timestamp && parsed.authKey) return parsed;
            } catch(e) {}
        }
        var ts = "" + Math.floor(Date.now() / 1000);
        var ak = "b72abd2d0909a2eda5f65dc7e8f25acb";
        var uip = "14.231.169.242";
        try {
            var authUrl = "https://funtap-xy.xinliugame.net/funtap/igame.php?accountID="
                + encodeURIComponent(accountId) + "&token=" + encodeURIComponent(token || "r") + "&v=1&appVersion=1.0.1";
            var resp = await fetch(authUrl);
            var txt = await resp.text();
            var mTs = txt.match(/GLOBAL_TIMESTAMP\s*=\s*"([^"]+)"/);
            var mAk = txt.match(/GLOBAL_AUTHKEY\s*=\s*"([^"]+)"/);
            var mAcc = txt.match(/GLOBAL_ACCOUNT\s*=\s*"([^"]+)"/);
            var mIp = txt.match(/GLOBAL_USER_IP\s*=\s*"([^"]*)"/);
            if (mTs && mTs[1]) ts = mTs[1];
            if (mAk && mAk[1]) ak = mAk[1];
            if (mAcc && mAcc[1]) accountId = mAcc[1];
            if (mIp && mIp[1]) uip = mIp[1];
        } catch(e) {
            console.warn("fetchAccountAuthKey fallback:", e);
        }
        return { timestamp: ts, authKey: ak, accountId: accountId, userIp: uip };
    }

    function launchGameWithConfig(accId, ts, ak, uip) {
        setStatus("🚀 Đang mở giao diện chọn Máy Chủ & Vào Game...", "#10b981");
        showSpinner(true);

        window.DAUTO_FORCE_PORTRAIT = true;
        window.DAUTO_CLIENT_TYPE = "Mobile-Standalone-v10.0.1";

        var G = window.Global || (typeof Global !== "undefined" ? Global : null);
        if (!G) {
            throw new Error("Không tìm thấy đối tượng Global trong game.js");
        }

        G.GLOBAL_PLATEFORM = true;
        G.GLOBAL_HIDE_IP = "1";
        G.GLOBAL_SHOW_IP = false;
        G.SHOW_DEBUG_LOGIN = false;
        G.GLOBAL_ACCOUNT = accId;
        G.ACCOUNT = accId;
        G.GLOBAL_OPENID = accId;
        G.GLOBAL_USER_IP = uip || "14.231.169.242";
        G.GLOBAL_REGION = "VN";
        G.GLOBAL_PF = "android_funtap";
        G.GAME_PLATFORM = "funtap";
        G.GLOBAL_ENTRY_DOMAIN = "https://funtap-xy.ridvqqxa.com/";
        G.GLOBAL_ACCOUNT_PREFIX = "1";
        G.GLOBAL_LANG = "vn";
        G.GLOBAL_INVITER = "";
        G.RESHOST = "https://rescdnft105vn.ridvqqxa.com/13542/";
        G.GLOBAL_APPID = "android";
        G.GLOBAL_VERSION = "13542";
        G.GLOBAL_LOG_LOGIN = "https://funtap-xy.ridvqqxa.com/game/login.php";
        G.GLOBAL_ALL_SERVER_LIST = "https://funtap-xy.ridvqqxa.com/game/getServerList2.php";
        G.GLOBAL_LAST_SERVER_LIST = "https://funtap-xy.ridvqqxa.com/game/getServerList2.php";
        G.GLOBAL_NOTICE_QUERY = "https://center1-funtap-xy.xinliugame.net/api/get_notice2.php";
        G.GLOBAL_AGE_QUERY = "https://center1-funtap-xy.xinliugame.net/api/cadpa.php";
        G.GLOBAL_PRIVATE_QUERY = "https://center1-funtap-xy.xinliugame.net/api/user_agreement.php";
        G.GLOBAL_TIMESTAMP = ts;
        G.GLOBAL_AUTHKEY = ak;
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

        // Cho phép hiển thị bảng chọn máy chủ (S95...S1)
        G.GLOBAL_DIRECT_ENTER = 0;

        if (typeof window.start !== "function") {
            throw new Error("Không tìm thấy hàm window.start");
        }

        window.start(1, 1, 1, 1);

        setTimeout(function() {
            var loader = document.getElementById("bootLoader");
            if (loader) {
                loader.style.opacity = "0";
                setTimeout(function() { loader.style.display = "none"; }, 400);
            }
        }, 1200);
    }

    async function handleFuntapLogin() {
        cancelAutoCountDown();
        var u = (document.getElementById("inpFtUser").value || "").trim();
        var p = (document.getElementById("inpFtPass").value || "").trim();
        var rem = document.getElementById("chkRemember").checked;

        if (!u || !p) {
            setStatus("⚠️ Vui lòng nhập Tài khoản/Email và Mật khẩu Funtap!", "#ef4444");
            return;
        }

        showSpinner(true);
        setStatus("⏳ Đang xác thực tài khoản Funtap [" + u + "]...", "#38bdf8");

        try {
            await ensureModScripts();
            var auth = await authenticateFuntap(u, p);
            setStatus("🎉 Đăng nhập Funtap thành công! UID: " + auth.accountId, "#10b981");

            if (rem) {
                try {
                    localStorage.setItem("DAUTO_FT_USER", u);
                    localStorage.setItem("DAUTO_FT_PASS", p);
                    localStorage.setItem("DAUTO_ACCOUNT_ID", auth.accountId);
                    if (auth.accessToken) localStorage.setItem("DAUTO_WEB_TOKEN", auth.accessToken);
                    if (window.PlatformScript && window.PlatformScript.saveCredentials) {
                        window.PlatformScript.saveCredentials(u, p, auth.accountId);
                    }
                } catch(e) {}
            }

            launchGameWithConfig(auth.accountId, auth.timestamp, auth.authKey, auth.userIp);
        } catch(err) {
            showSpinner(false);
            setStatus("❌ " + (err.message || err), "#ef4444");
        }
    }

    async function handleUidLogin() {
        cancelAutoCountDown();
        var uid = (document.getElementById("inpUid").value || "").trim();
        if (!uid) {
            generateRandomUid();
            uid = document.getElementById("inpUid").value;
        }

        showSpinner(true);
        setStatus("⏳ Đang kết nối bằng UID [" + uid + "]...", "#38bdf8");

        try {
            await ensureModScripts();
            var tok = "r";
            try { tok = localStorage.getItem("DAUTO_WEB_TOKEN") || "r"; } catch(e) {}
            var akRes = await fetchAccountAuthKey(uid, tok);
            localStorage.setItem("DAUTO_ACCOUNT_ID", uid);
            launchGameWithConfig(akRes.accountId || uid, akRes.timestamp, akRes.authKey, akRes.userIp);
        } catch(err) {
            showSpinner(false);
            setStatus("❌ " + (err.message || err), "#ef4444");
        }
    }

    async function handleEnterSaved() {
        cancelAutoCountDown();
        var u = "";
        var p = "";
        try {
            u = localStorage.getItem("DAUTO_FT_USER") || "";
            p = localStorage.getItem("DAUTO_FT_PASS") || "";
        } catch(e) {}

        if (!u && window.PlatformScript && window.PlatformScript.getSavedCredentials) {
            try {
                var creds = JSON.parse(window.PlatformScript.getSavedCredentials());
                u = creds.username || "";
                p = creds.password || "";
            } catch(e) {}
        }

        if (u && p) {
            document.getElementById("inpFtUser").value = u;
            document.getElementById("inpFtPass").value = p;
            handleFuntapLogin();
        } else {
            handleUidLogin();
        }
    }

    // Tự động kiểm tra tài khoản đã lưu khi mở app
    (async function initApp() {
        var savedUser = "";
        var savedPass = "";
        var savedUid = "";

        try {
            savedUser = localStorage.getItem("DAUTO_FT_USER") || "";
            savedPass = localStorage.getItem("DAUTO_FT_PASS") || "";
            savedUid = localStorage.getItem("DAUTO_ACCOUNT_ID") || "";
        } catch(e) {}

        if ((!savedUser || !savedPass) && window.PlatformScript && window.PlatformScript.getSavedCredentials) {
            try {
                var sc = JSON.parse(window.PlatformScript.getSavedCredentials());
                if (sc && sc.username) {
                    savedUser = sc.username;
                    savedPass = sc.password || "";
                    savedUid = sc.accountId || savedUid;
                }
            } catch(e) {}
        }

        if (savedUser) document.getElementById("inpFtUser").value = savedUser;
        if (savedPass) document.getElementById("inpFtPass").value = savedPass;
        if (savedUid) {
            document.getElementById("inpUid").value = savedUid;
        } else {
            generateRandomUid();
        }

        // Nếu đã có thông tin đăng nhập trước đó: Hiển thị hộp Đã lưu và đếm ngược 3s tự vào
        if (savedUser && savedPass) {
            var box = document.getElementById("savedBox");
            var userTxt = document.getElementById("savedUserTxt");
            var uidTxt = document.getElementById("savedUidTxt");
            if (box && userTxt && uidTxt) {
                userTxt.innerText = savedUser;
                uidTxt.innerText = savedUid || "Đang lấy...";
                box.style.display = "flex";
                document.getElementById("tabBar").style.display = "none";
                document.getElementById("panelFt").style.display = "none";

                _countDownVal = 3;
                var cdSpan = document.getElementById("countDownTxt");
                _autoCountDownTimer = setInterval(function() {
                    _countDownVal--;
                    if (cdSpan) cdSpan.innerText = _countDownVal + "s";
                    if (_countDownVal <= 0) {
                        cancelAutoCountDown();
                        handleEnterSaved();
                    }
                }, 1000);
            }
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

    output_apk_v1001 = Path("HacTayDu_Auto_Mod_V10.0.1.apk")
    output_apk_def = Path("HacTayDu_Auto_Mod.apk")
    output_apk_v12 = Path("HacTayDu_Auto_Mod_V12.apk")
    output_apk_v11 = Path("HacTayDu_Auto_Mod_V11.apk")
    output_apk_v9 = Path("HacTayDu_Auto_Mod_V9.apk")

    if output_apk_v1001.exists():
        output_apk_v1001.unlink()
    shutil.copy(aligned_apk, output_apk_v1001)

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
        str(output_apk_v1001)
    ]
    subprocess.run(cmd_sign, check=True, capture_output=True)

    shutil.copy(output_apk_v1001, output_apk_def)
    shutil.copy(output_apk_v1001, output_apk_v12)
    shutil.copy(output_apk_v1001, output_apk_v11)
    shutil.copy(output_apk_v1001, output_apk_v9)

    print(f"\n🎉 HOÀN THÀNH BIÊN DỊCH BẢN MOD APK STANDALONE V10.0.1 (MOD 13542 + LOGIN TK & PASS)!")
    print(f"📁 Tên file V10.0.1: {output_apk_v1001.resolve()}")
    print(f"📁 Tên file Chuẩn:   {output_apk_def.resolve()}")
    print(f"📁 Tên file V12:     {output_apk_v12.resolve()}")
    print(f"📁 Tên file V11:     {output_apk_v11.resolve()}")
    print(f"📊 Dung lượng:       {output_apk_v1001.stat().st_size / 1024 / 1024:.2f} MB")
    print(f"🏷️  Package Name: {PACKAGE_NAME} (Chạy song song, không cần gỡ app gốc!)")

def main():
    create_project_structure()
    compile_apk()

if __name__ == "__main__":
    main()
