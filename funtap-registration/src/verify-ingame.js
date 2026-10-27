const { chromium } = require('playwright');
const https = require('https');

const APP_KEY = '2a456b78cf5122cd9278ef24b4d7bfb9';
const APP_VERSION = '9.9.9.5';
const SDK_VERSION = '6.1.2';
const PACKAGE_NAME = 'vn.ftg.hactaydu';

const REGISTER_ENTRY_URL =
  `https://core.sdkmain.com/v1/apps/${APP_KEY}/${APP_VERSION}/register/email` +
  `?sdk_version=${SDK_VERSION}` +
  `&device_network=wifi` +
  `&appsflyer_id=1729500000000-1234567890123456789` +
  `&adjust_id=` +
  `&advertising_id=00000000-0000-0000-0000-000000000000` +
  `&device_os=Android%2012` +
  `&device_name=Pixel%206`;

const LOGIN_API_URL = `https://core.sdkmain.com/api/v1/apps/${APP_KEY}/${APP_VERSION}/auth/login`;

function maskSecret(str) {
  if (!str || str.length < 6) return '[REDACTED]';
  return `${str.slice(0, 3)}***${str.slice(-3)}`;
}

function testReloginApi({ username, password, deviceId }) {
  return new Promise((resolve) => {
    const bodyParams = new URLSearchParams({
      email: username,
      password: password,
      device_id: deviceId || 'a94a8fe5ccb19ba61c4c0873d391e987982fbbd3',
      fcm_token: '',
      package_name: PACKAGE_NAME,
      appsflyer_id: '1729500000000-1234567890123456789',
      advertising_id: '00000000-0000-0000-0000-000000000000'
    }).toString();

    const urlObj = new URL(LOGIN_API_URL);
    const req = https.request(
      {
        hostname: urlObj.hostname,
        path: urlObj.pathname,
        method: 'POST',
        headers: {
          Accept: 'application/json',
          'Content-Type': 'application/x-www-form-urlencoded',
          'Content-Length': Buffer.byteLength(bodyParams),
          'X-Request': APP_KEY,
          'app-Version': APP_VERSION,
          'sdk-Version': SDK_VERSION,
          Language: 'vi-VN',
          'X-Android-Notch': 'false'
        }
      },
      (res) => {
        let raw = '';
        res.on('data', (chunk) => {
          raw += chunk;
        });
        res.on('end', () => {
          let parsed = null;
          try {
            parsed = JSON.parse(raw);
          } catch (_) {
            // ignore parse error
          }
          resolve({
            httpStatus: res.statusCode,
            body: parsed,
            rawPreview: parsed ? undefined : raw.slice(0, 200)
          });
        });
      }
    );

    req.on('error', (err) => {
      resolve({
        httpStatus: 0,
        error: err.message
      });
    });

    req.write(bodyParams);
    req.end();
  });
}

async function inspectCurrentDomState(page) {
  try {
    return await page.evaluate(() => {
      const invalidEls = Array.from(
        document.querySelectorAll(
          '.is-invalid, [class*="error-input-"], .text-danger, .alert-danger, .invalid-feedback, .error-message, .txt-error'
        )
      )
        .map((el) => {
          if (el.tagName === 'INPUT') {
            return `Input #${el.id || el.name} has class .is-invalid`;
          }
          return el.innerText.trim();
        })
        .filter(Boolean);

      const otpInput =
        document.getElementById('otp') ||
        document.querySelector('input[name="otp"], input[placeholder*="OTP"], input[placeholder*="mã xác"]');
      const recaptcha = document.querySelector(
        '.g-recaptcha, iframe[src*="recaptcha"], .error-input-g-recaptcha-response'
      );
      const form = document.querySelector('form');

      return {
        currentUrl: window.location.href,
        title: document.title,
        h1: document.querySelector('h1') ? document.querySelector('h1').innerText.trim() : null,
        formAction: form ? form.action : null,
        hasOtpInput: Boolean(otpInput),
        hasCaptcha: Boolean(recaptcha),
        errorMessages: invalidEls,
        bodyTextPreview: document.body
          ? document.body.innerText.replace(/\s+/g, ' ').trim().slice(0, 400)
          : ''
      };
    });
  } catch (err) {
    return { error: err.message };
  }
}

async function main() {
  const argv = process.argv.slice(2);
  const isDryRun = argv.includes('--dry-run');
  const username = 'dungby30';
  const fullname = 'Dung 30';
  const birthday = '1995-05-15';
  const password = process.env.FUNTAP_PASSWORD || 'ntdung12';

  console.log('====================================================================');
  console.log(' FUNTAP IN-GAME SDK REGISTRATION VERIFIER (RegistryFragmentV2 FLOW)');
  console.log('====================================================================');
  console.log(`[INFO] Entry URL : ${REGISTER_ENTRY_URL}`);
  console.log(
    `[INFO] Mode      : ${
      isDryRun
        ? 'DRY-RUN (Inspect & Fill only, NO POST submit)'
        : 'INTERACTIVE-BROWSER (Điền sẵn dungby30, chờ người vận hành nhập SĐT & bấm Tiếp tục)'
    }`
  );
  console.log(`[INFO] Username  : ${username}`);
  console.log(`[INFO] Fullname  : ${fullname}`);
  console.log(`[INFO] Birthday  : ${birthday}`);
  console.log(`[INFO] Password  : [REDACTED - length ${password.length}]`);

  let browser;
  try {
    browser = await chromium.launch({ headless: isDryRun });
    const context = await browser.newContext({
      viewport: { width: 430, height: 860 },
      userAgent:
        'Mozilla/5.0 (Linux; Android 12; Pixel 6 Build/SP1A.210812.015; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/114.0.5735.196 Mobile Safari/537.36',
      extraHTTPHeaders: {
        device_name: 'Pixel 6',
        device_os: 'Android 12',
        device_resolution: '1080x2400',
        sdk_version: SDK_VERSION,
        device_network: 'wifi',
        appsflyer_id: '1729500000000-1234567890123456789',
        advertising_id: '00000000-0000-0000-0000-000000000000',
        Language: 'vi-VN',
        'X-Android-Notch': 'false'
      }
    });

    const page = await context.newPage();

    let registerSuccessPayload = null;
    let submittedUsername = username;
    const postResponses = [];

    // Emulate Android WebView window.JsHandler (com.game.sdk.javascript.JsRegister)
    await page.exposeFunction('__onSdkBridgeCall', (command, paramsStr) => {
      let parsed = null;
      try {
        parsed = JSON.parse(paramsStr);
      } catch (_) {
        parsed = paramsStr;
      }
      if (String(command).toLowerCase() === 'loginsuccess') {
        registerSuccessPayload = parsed;
        console.log(
          '\n[JS-BRIDGE] >>> Nhận tín hiệu window.JsHandler.mobAppSDKexecute("loginSuccess", params)!'
        );
      } else if (String(command).toLowerCase() === 'track') {
        const label = parsed && parsed.label ? parsed.label : 'unknown';
        const uName = parsed && parsed.value && parsed.value.user_name ? parsed.value.user_name : '';
        if (uName) submittedUsername = uName;
        console.log(`[JS-BRIDGE] track label="${label}" user_name="${uName}"`);
      } else {
        console.log(`[JS-BRIDGE] command="${command}"`);
      }
    });

    await page.addInitScript(() => {
      window.JsHandler = {
        mobAppSDKexecute: function (command, params) {
          window.__onSdkBridgeCall(command, params);
        }
      };
    });

    if (isDryRun) {
      await page.route('**/*', async (route) => {
        if (route.request().method() === 'POST') {
          console.log(`[DRY-RUN GUARD] Chặn POST tới ${route.request().url()}`);
          await route.abort();
          return;
        }
        await route.continue();
      });
    }

    page.on('request', (req) => {
      if (req.method() === 'POST' && req.url().includes('sdkmain.com')) {
        const postData = req.postData() || '';
        const params = new URLSearchParams(postData);
        const safeKeys = Array.from(params.keys());
        if (params.get('username')) {
          submittedUsername = params.get('username');
        }
        console.log(
          `\n[HTTP POST REQUEST] ${req.url()}\n  -> Content-Type: ${
            req.headers()['content-type'] || 'N/A'
          }\n  -> Form Keys   : ${safeKeys.join(', ')}\n  -> username    : ${
            params.get('username') || '(n/a)'
          }\n  -> phone       : ${
            params.get('phone') ? maskSecret(params.get('phone')) : '(n/a)'
          }\n  -> otp         : ${params.get('otp') ? '[PROVIDED]' : '(n/a)'}`
        );
      }
    });

    page.on('response', async (res) => {
      const url = res.url();
      const method = res.request().method();
      if (url.includes('sdkmain.com/v1/apps') || url.includes('sdkmain.com/api/')) {
        const status = res.status();
        const location = res.headers()['location'] || null;
        console.log(
          `[HTTP RESPONSE] ${method} ${url} -> HTTP ${status}${
            location ? ` (Redirect -> ${location})` : ''
          }`
        );
        if (method === 'POST') {
          postResponses.push({ method, url, status, location, timestamp: new Date().toISOString() });
        }
      }
    });

    console.log('\n[STEP 1] Đang mở URL đăng ký In-Game SDK...');
    await page.goto(REGISTER_ENTRY_URL, { waitUntil: 'domcontentloaded', timeout: 30000 });

    // If the collapsible section #collapseInfo exists or fields are visible, fill username, fullname, birthday, password
    await page.evaluate(() => {
      const collapseEl = document.getElementById('collapseInfo');
      if (collapseEl && !collapseEl.classList.contains('show')) {
        collapseEl.classList.add('show');
        collapseEl.style.display = 'block';
      }
    });

    await page.fill('#username', username);
    await page.fill('#fullname', fullname);
    await page.fill('#birthday', birthday);
    await page.fill('#password', password);

    if (isDryRun) {
      await page.fill('#phone', '0912345678');
      const state = await inspectCurrentDomState(page);
      console.log('\n[DRY-RUN STATE]', JSON.stringify(state, null, 2));
      await browser.close();
      return;
    }

    // Focus the #phone input so the operator can type their phone number immediately
    await page.focus('#phone');

    console.log('\n====================================================================');
    console.log(' CỬA SỔ CHROMIUM ĐÃ SẴN SÀNG CHO NGƯỜI VẬN HÀNH');
    console.log('====================================================================');
    console.log('Đã điền sẵn trên biểu mẫu In-Game FunID:');
    console.log(`  - Tên đăng nhập (#username) : ${username}`);
    console.log(`  - Họ và tên (#fullname)     : ${fullname}`);
    console.log(`  - Ngày sinh (#birthday)     : ${birthday}`);
    console.log(`  - Mật khẩu (#password)      : [REDACTED - 8 ký tự]`);
    console.log('\n>>> HƯỚNG DẪN:');
    console.log('  1. Trên cửa sổ Chromium vừa mở, hãy nhập Số điện thoại hợp lệ của anh vào ô "Số điện thoại *".');
    console.log('  2. Bấm nút "Tiếp tục" (#register) để gửi xác nhận thủ công.');
    console.log('  3. Nếu server yêu cầu nhập mã OTP SMS hoặc CAPTCHA, anh có thể nhập trực tiếp hoặc đóng cửa sổ trình duyệt để kết thúc.');
    console.log('====================================================================\n');

    let lastInspectedPostCount = 0;
    let lastDomState = null;

    // Wait loop until loginSuccess is received, or browser window is closed by operator, or timeout (5 minutes)
    const startTime = Date.now();
    const maxWaitMs = 5 * 60 * 1000;

    while (Date.now() - startTime < maxWaitMs) {
      if (page.isClosed()) {
        console.log('\n[INFO] Người vận hành đã đóng cửa sổ trình duyệt.');
        break;
      }

      if (registerSuccessPayload) {
        break;
      }

      if (postResponses.length > lastInspectedPostCount) {
        lastInspectedPostCount = postResponses.length;
        await page.waitForTimeout(1500);
        if (!page.isClosed()) {
          lastDomState = await inspectCurrentDomState(page);
          console.log('\n[DOM STATE AFTER POST]', JSON.stringify(lastDomState, null, 2));
        }
      }

      await new Promise((r) => setTimeout(r, 1000));
    }

    if (!page.isClosed() && !lastDomState && postResponses.length > 0) {
      lastDomState = await inspectCurrentDomState(page);
    }

    // Final Evaluation
    console.log('\n====================================================================');
    console.log(' TỔNG HỢP KẾT QUẢ XÁC MINH');
    console.log('====================================================================');
    console.log(`- Tổng số POST đã gửi : ${postResponses.length}`);
    for (const p of postResponses) {
      console.log(`  * ${p.method} ${p.url} -> HTTP ${p.status}${p.location ? ` (Redirect -> ${p.location})` : ''}`);
    }

    let finalStatus = 'UNKNOWN';

    if (registerSuccessPayload && registerSuccessPayload.access_token) {
      finalStatus = 'REGISTER_SUCCESS';
      const userObj = registerSuccessPayload.data || {};
      console.log(`- Tín hiệu JS Bridge  : loginSuccess RECEIVED`);
      console.log(`- FunID User ID       : ${userObj.id}`);
      console.log(
        `- FunID Username      : ${userObj.account ? userObj.account.username : submittedUsername}`
      );
      console.log(`- Access Token        : ${maskSecret(registerSuccessPayload.access_token)}`);
      console.log(
        `- Phone Status        : ${userObj.account ? userObj.account.phone_status : 'N/A'}`
      );
      console.log(`- Need Verify         : ${userObj.need_verify}`);
    } else if (lastDomState) {
      if (lastDomState.hasOtpInput || lastDomState.hasCaptcha) {
        finalStatus = 'VERIFICATION_REQUIRED';
        console.log(
          `- Trạng thái bước tiếp: Server yêu cầu xác minh (hasOtpInput=${lastDomState.hasOtpInput}, hasCaptcha=${lastDomState.hasCaptcha})`
        );
      } else if (lastDomState.errorMessages && lastDomState.errorMessages.length > 0) {
        finalStatus = 'REGISTER_FAILED';
        console.log(`- Thông báo lỗi Server: ${lastDomState.errorMessages.join(' | ')}`);
      }
    }

    // Also test login API if at least 1 POST was sent (to verify whether account was created even before/after OTP)
    if (postResponses.length > 0) {
      console.log(
        `\n[STEP 7] Kiểm tra đăng nhập lại qua REST API (POST /api/v1/apps/.../auth/login) cho username="${submittedUsername}"...`
      );
      const reloginResult = await testReloginApi({ username: submittedUsername, password });
      console.log(`- Relogin HTTP Status : ${reloginResult.httpStatus}`);
      if (reloginResult.body) {
        console.log(
          `- Relogin Error Code  : ${reloginResult.body.error_code} (status="${reloginResult.body.status}")`
        );
        console.log(`- Relogin Message     : ${reloginResult.body.message || '(none)'}`);
        console.log(
          `- Relogin AccessToken : ${
            reloginResult.body.access_token ? maskSecret(reloginResult.body.access_token) : 'NONE'
          }`
        );
        if (reloginResult.body.access_token && finalStatus !== 'REGISTER_SUCCESS') {
          console.log(
            '  [!] Lưu ý: Đăng nhập REST API trả về access_token hợp lệ (Tài khoản đã được tạo và có thể đăng nhập).'
          );
          finalStatus = 'REGISTER_SUCCESS';
        }
      }
    }

    console.log(`\n>>> KẾT LUẬN CUỐI CÙNG: ${finalStatus}`);
  } finally {
    if (browser) {
      await browser.close();
    }
  }
}

main().catch((err) => {
  console.error('[FATAL]', err.message);
  process.exit(1);
});
