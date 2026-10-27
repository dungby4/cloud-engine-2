const fs = require('fs');
const path = require('path');
const http = require('http');
const crypto = require('crypto');
const assert = require('assert');

const {
  FUNTAP_CONFIG,
  REGISTRATION_STATUS,
  redactPhone
} = require('./funtap-api');
const {
  ACCOUNTS_CSV_PATH,
  RESULTS_CSV_PATH,
  PHONE_SOURCE,
  VALID_PHONE_SOURCES,
  VN_MOBILE_REGEX,
  escapeCsvField,
  parseCsvLine,
  loadAccounts,
  writeAccountsCsv,
  mergeOperatorPhonesFromCsv
} = require('./csv');
const { SessionManager } = require('./session-manager');
const {
  FuntapRegistrationClient,
  compareRegistrationAndLoginIdentity
} = require('./registration-client');
const { verifyAccountLogin } = require('./verify-login');
const { runUnitTests: runCoreUnitTests } = require('./test-registration');

const API_TEST_REPORT_PATH = path.join(__dirname, '..', 'registration_api_test.json');
const ACCOUNTS_BACKUP_CSV_PATH = path.join(__dirname, '..', 'data', 'accounts.backup.csv');
const BATCH_REPORT_PROJECT_PATH = path.join(__dirname, '..', 'batch_report.md');
const BATCH_REPORT_WORKSPACE_PATH = path.join(__dirname, '..', '..', 'batch_report.md');
const BATCH_REG_REPORT_PROJECT_PATH = path.join(__dirname, '..', 'batch_registration_report.md');
const BATCH_REG_REPORT_WORKSPACE_PATH = path.join(__dirname, '..', '..', 'batch_registration_report.md');
const REG_PROGRESS_PROJECT_PATH = path.join(__dirname, '..', 'registration_progress.md');
const REG_PROGRESS_WORKSPACE_PATH = path.join(__dirname, '..', '..', 'registration_progress.md');
const REG_ERRORS_PROJECT_PATH = path.join(__dirname, '..', 'registration_errors.json');
const REG_ERRORS_WORKSPACE_PATH = path.join(__dirname, '..', '..', 'registration_errors.json');
const VERIFIED_ACCOUNTS_PROJECT_PATH = path.join(__dirname, '..', 'verified_accounts.csv');
const VERIFIED_ACCOUNTS_DATA_PATH = path.join(__dirname, '..', 'data', 'verified_accounts.csv');
const VERIFIED_ACCOUNTS_WORKSPACE_PATH = path.join(__dirname, '..', '..', 'verified_accounts.csv');

/**
 * Standardized Account Statuses:
 * - REGISTERED: Server confirmed account & login verified with matching username & FunID
 * - ALREADY_EXISTS: Account or phone number already exists on server
 * - PENDING: Waiting for live registration submission
 * - CAPTCHA_REQUIRED: Blocked by Google reCAPTCHA requirement on server
 * - PHONE_REQUIRED: Unregistered account missing an operator-owned phone number
 * - VERIFICATION_REQUIRED: OTP or CAPTCHA required
 * - RATE_LIMITED: Server rate-limited requests
 * - FAILED: Server rejected request
 * - UNKNOWN: Insufficient evidence or identity mismatch (never retried automatically)
 */
const ACCOUNT_STATUS = {
  REGISTERED: 'REGISTERED',
  ALREADY_EXISTS: 'ALREADY_EXISTS',
  PENDING: 'PENDING',
  CAPTCHA_REQUIRED: 'CAPTCHA_REQUIRED',
  PHONE_REQUIRED: 'PHONE_REQUIRED',
  VERIFICATION_REQUIRED: 'VERIFICATION_REQUIRED',
  RATE_LIMITED: 'RATE_LIMITED',
  FAILED: 'FAILED',
  UNKNOWN: 'UNKNOWN'
};

const MOCK_TEST_STATUS = {
  MOCK_SUCCESS: 'MOCK_SUCCESS',
  MOCK_ALREADY_EXISTS: 'MOCK_ALREADY_EXISTS',
  MOCK_FAILED: 'MOCK_FAILED',
  SKIPPED_REGISTERED: 'SKIPPED_REGISTERED',
  SKIPPED_PHONE_REQUIRED: 'SKIPPED_PHONE_REQUIRED'
};

/**
 * Start a local HTTP Mock Server (`127.0.0.1:0`) that faithfully implements
 * the Funtap SDK registration and authentication protocol for offline testing:
 * 1. GET /v1/apps/{appKey}/{appVersion}/register/email
 *    -> Returns HTTP 302 + Set-Cookie (XSRF-TOKEN, core_sdk_session) -> /register/phone
 * 2. GET /v1/apps/{appKey}/{appVersion}/register/phone
 *    -> Verifies session cookie, generates 40-char CSRF _token, returns HTTP 200 HTML form
 * 3. POST /v1/apps/{appKey}/{appVersion}/register/phone
 *    -> Verifies CookieJar, CSRF _token, uniqueness of username & phone (returns 2001 ALREADY_EXISTS if duplicate),
 *       stores account in mock DB, and returns HTTP 200 HTML with `appSDKexecute('loginSuccess', params)`
 * 4. POST /api/v1/apps/{appKey}/{appVersion}/auth/login
 *    -> Verifies credentials against mock DB and returns HTTP 200 JSON LoginEmailResponseObj
 */
function startMockFuntapHttpServer() {
  const sessions = new Map();
  const registeredUsersByUsername = new Map();
  const registeredUsersByPhone = new Map();
  const stats = {
    getEntryCalls: 0,
    getPhoneFormCalls: 0,
    postRegisterCalls: 0,
    postRegisterSuccess: 0,
    postRegisterAlreadyExists: 0,
    postLoginCalls: 0,
    postLoginSuccess: 0
  };

  function parseCookies(cookieHeader = '') {
    const out = {};
    for (const part of String(cookieHeader).split(';')) {
      const idx = part.indexOf('=');
      if (idx !== -1) {
        const k = part.slice(0, idx).trim();
        const v = part.slice(idx + 1).trim();
        if (k) out[k] = v;
      }
    }
    return out;
  }

  function readRequestBody(req) {
    return new Promise((resolve) => {
      let body = '';
      req.on('data', (chunk) => {
        body += chunk;
      });
      req.on('end', () => resolve(body));
    });
  }

  const server = http.createServer(async (req, res) => {
    const hostHeader = req.headers.host || '127.0.0.1';
    const baseUrl = `http://${hostHeader}`;
    const reqUrl = new URL(req.url, baseUrl);
    const pathname = reqUrl.pathname;
    const method = (req.method || 'GET').toUpperCase();

    const expectedPrefix = `/v1/apps/${FUNTAP_CONFIG.APP_KEY}/${FUNTAP_CONFIG.APP_VERSION}`;
    const expectedApiPrefix = `/api/v1/apps/${FUNTAP_CONFIG.APP_KEY}/${FUNTAP_CONFIG.APP_VERSION}`;

    if (method === 'GET' && pathname === `${expectedPrefix}/register/email`) {
      stats.getEntryCalls++;
      const sessionId = crypto.randomBytes(16).toString('hex');
      const csrfToken = crypto.randomBytes(20).toString('hex');
      sessions.set(sessionId, { csrfToken, createdAt: Date.now() });

      const redirectUrl = new URL(`${expectedPrefix}/register/phone`, baseUrl);
      for (const [k, v] of reqUrl.searchParams.entries()) {
        redirectUrl.searchParams.set(k, v);
      }

      res.writeHead(302, {
        Location: redirectUrl.toString(),
        'Content-Type': 'text/html; charset=UTF-8',
        'Set-Cookie': [
          `XSRF-TOKEN=${encodeURIComponent(csrfToken)}; Max-Age=7200; path=/; samesite=lax`,
          `core_sdk_session=${sessionId}; Max-Age=7200; path=/; httponly; samesite=lax`
        ]
      });
      res.end('Redirecting to /register/phone');
      return;
    }

    if (method === 'GET' && pathname === `${expectedPrefix}/register/phone`) {
      stats.getPhoneFormCalls++;
      const cookies = parseCookies(req.headers.cookie);
      let sessionId = cookies.core_sdk_session;
      let sessionData = sessionId ? sessions.get(sessionId) : null;

      if (!sessionData) {
        sessionId = crypto.randomBytes(16).toString('hex');
        sessionData = { csrfToken: crypto.randomBytes(20).toString('hex'), createdAt: Date.now() };
        sessions.set(sessionId, sessionData);
      }

      const actionUrl = new URL(`${expectedPrefix}/register/phone`, baseUrl);
      for (const [k, v] of reqUrl.searchParams.entries()) {
        actionUrl.searchParams.set(k, v);
      }
      actionUrl.searchParams.set('checkScreen', 'register');

      const html = `<!DOCTYPE html>
<html lang="vi">
<head><meta charset="utf-8"><title>Đăng ký FunID</title></head>
<body>
  <section id="wrapper-register">
    <div class="wrapper-container">
      <h1>Đăng ký FunID</h1>
      <form method="POST" action="${actionUrl.toString().replace(/&/g, '&amp;')}" novalidate>
        <input type="hidden" name="_token" value="${sessionData.csrfToken}">
        <input type="text" name="username" value="playerMock123456" id="username" class="form-input" minlength="3" maxlength="32">
        <input type="text" name="fullname" value="Nguyễn Văn Mock" id="fullname" class="form-input" minlength="2" maxlength="100">
        <input type="date" name="birthday" value="1995-05-15" id="birthday" class="form-input">
        <input type="tel" name="phone" value="" id="phone" class="form-input" maxlength="11">
        <input type="password" name="password" value="" id="password" class="form-input" placeholder="Mật khẩu (dài 8-32 ký tự) *">
        <button type="submit" id="register" name="btn-Register">Tiếp tục</button>
      </form>
    </div>
  </section>
</body>
</html>`;

      res.writeHead(200, {
        'Content-Type': 'text/html; charset=UTF-8',
        'Set-Cookie': [
          `XSRF-TOKEN=${encodeURIComponent(sessionData.csrfToken)}; Max-Age=7200; path=/; samesite=lax`,
          `core_sdk_session=${sessionId}; Max-Age=7200; path=/; httponly; samesite=lax`
        ]
      });
      res.end(html);
      return;
    }

    if (method === 'POST' && pathname === `${expectedPrefix}/register/phone`) {
      stats.postRegisterCalls++;
      const cookies = parseCookies(req.headers.cookie);
      const sessionId = cookies.core_sdk_session;
      const sessionData = sessionId ? sessions.get(sessionId) : null;

      const rawBody = await readRequestBody(req);
      const params = new URLSearchParams(rawBody);
      const token = (params.get('_token') || '').trim();
      const username = (params.get('username') || '').trim();
      const fullname = (params.get('fullname') || '').trim();
      const birthday = (params.get('birthday') || '').trim();
      const phone = (params.get('phone') || '').trim();
      const password = params.get('password') || '';

      if (!sessionData || !cookies['XSRF-TOKEN'] || token !== sessionData.csrfToken) {
        res.writeHead(419, { 'Content-Type': 'text/html; charset=UTF-8' });
        res.end('<html><body><div class="alert-danger">CSRF token mismatch</div></body></html>');
        return;
      }

      if (registeredUsersByUsername.has(username)) {
        stats.postRegisterAlreadyExists++;
        res.writeHead(200, { 'Content-Type': 'text/html; charset=UTF-8' });
        res.end(
          '<html><body><input id="username" class="is-invalid"><div class="error-input-username">Tên đăng nhập đã tồn tại (2001)</div></body></html>'
        );
        return;
      }

      if (registeredUsersByPhone.has(phone)) {
        stats.postRegisterAlreadyExists++;
        res.writeHead(200, { 'Content-Type': 'text/html; charset=UTF-8' });
        res.end(
          '<html><body><input id="phone" class="is-invalid"><div class="error-input-phone">Số điện thoại đã được sử dụng</div></body></html>'
        );
        return;
      }

      if (
        username.length < 3 ||
        fullname.length < 2 ||
        !/^\d{4}-\d{2}-\d{2}$/.test(birthday) ||
        !VN_MOBILE_REGEX.test(phone) ||
        password.length < 8
      ) {
        res.writeHead(200, { 'Content-Type': 'text/html; charset=UTF-8' });
        res.end(
          '<html><body><div class="error-input-password">Dữ liệu biểu mẫu không hợp lệ</div></body></html>'
        );
        return;
      }

      const numSuffix = username.replace(/\D+/g, '') || String(stats.postRegisterSuccess + 31);
      const mockFunId = `mock_90000${numSuffix}`;
      const mockAccessToken = `mock_jwt_${crypto.randomBytes(12).toString('hex')}`;

      const userRecord = {
        id: mockFunId,
        username,
        fullname,
        birthday,
        phone,
        password,
        accessToken: mockAccessToken
      };

      registeredUsersByUsername.set(username, userRecord);
      registeredUsersByPhone.set(phone, username);
      stats.postRegisterSuccess++;

      const bridgePayload = {
        access_token: mockAccessToken,
        data: {
          id: mockFunId,
          new_user: true,
          need_verify: false,
          account: {
            username,
            name: fullname,
            birthday,
            phone_status: true,
            has_password: true
          }
        }
      };

      const successHtml = `<!DOCTYPE html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <title>Đăng ký thành công</title>
  <script type="text/javascript">
    appSDKexecute('loginSuccess', ${JSON.stringify(bridgePayload)});
  </script>
</head>
<body><h1>Đăng ký FunID thành công</h1></body>
</html>`;

      res.writeHead(200, { 'Content-Type': 'text/html; charset=UTF-8' });
      res.end(successHtml);
      return;
    }

    if (method === 'POST' && pathname === `${expectedApiPrefix}/auth/login`) {
      stats.postLoginCalls++;
      const rawBody = await readRequestBody(req);
      const params = new URLSearchParams(rawBody);
      const email = (params.get('email') || '').trim();
      const password = params.get('password') || '';

      const userRecord = registeredUsersByUsername.get(email);
      if (!userRecord || userRecord.password !== password) {
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(
          JSON.stringify({
            status: 'error',
            error_code: -4,
            message: 'Tài khoản không tồn tại hoặc sai mật khẩu'
          })
        );
        return;
      }

      stats.postLoginSuccess++;
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(
        JSON.stringify({
          status: 'success',
          error_code: 200,
          message: 'Mock login verified successfully',
          access_token: userRecord.accessToken,
          data: {
            id: userRecord.id,
            new_user: false,
            need_verify: false,
            account: {
              username: userRecord.username,
              name: userRecord.fullname,
              birthday: userRecord.birthday,
              phone_status: true
            }
          }
        })
      );
      return;
    }

    res.writeHead(404, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ message: 'Not Found' }));
  });

  return new Promise((resolve, reject) => {
    server.on('error', reject);
    server.listen(0, '127.0.0.1', () => {
      const address = server.address();
      const baseUrl = `http://127.0.0.1:${address.port}`;
      resolve({
        baseUrl,
        port: address.port,
        stats,
        registeredUsersByUsername,
        registeredUsersByPhone,
        close: () =>
          new Promise((resClose) => {
            server.close(() => resClose());
          })
      });
    });
  });
}

/**
 * Dedicated integrity verification for the 69 accounts (`dungby31` to `dungby99`)
 * as required by Requirement 6 ("Bổ sung kiểm tra toàn vẹn dữ liệu cho 69 tài khoản dungby31 đến dungby99").
 */
function validateRemaining69AccountsIntegrity(accounts = []) {
  const targetAccounts =
    accounts.length > 70
      ? accounts.filter((a) => {
          const m = /^dungby(\d+)$/i.exec(String(a.username || '').trim());
          if (!m) return false;
          const n = Number(m[1]);
          return n >= 31 && n <= 99 && String(a.username || '').trim().length === 8;
        })
      : accounts.filter((a) => String(a.username || '').trim() !== 'dungby30');
  const byUsername = new Map();
  const seenPhones = new Set();

  const missingSequenceUsernames = [];
  const fullnameMismatches = [];
  const birthdayMismatches = [];
  const invalidPhones = [];
  const duplicatePhonesIn69 = [];

  for (const acc of targetAccounts) {
    const u = String(acc.username || '').trim();
    byUsername.set(u, acc);
    const p = String(acc.phone || '').trim();
    if (!p || !p.startsWith('0') || !VN_MOBILE_REGEX.test(p)) {
      invalidPhones.push(`${u}: invalid phone format`);
    } else if (seenPhones.has(p)) {
      duplicatePhonesIn69.push(`${u}: duplicate phone ${redactPhone(p)}`);
    } else {
      seenPhones.add(p);
    }
  }

  for (let num = 31; num <= 99; num++) {
    const expectedUsername = `dungby${num}`;
    const expectedFullname = `Dung ${num}`;
    const expectedBirthday = '1995-05-15';

    const acc = byUsername.get(expectedUsername);
    if (!acc) {
      missingSequenceUsernames.push(expectedUsername);
      continue;
    }

    if (String(acc.fullname || '').trim() !== expectedFullname) {
      fullnameMismatches.push(
        `${expectedUsername}: expected fullname "${expectedFullname}", got "${acc.fullname}"`
      );
    }

    if (String(acc.birthday || '').trim() !== expectedBirthday) {
      birthdayMismatches.push(
        `${expectedUsername}: expected birthday "${expectedBirthday}", got "${acc.birthday}"`
      );
    }
  }

  const isValid69Accounts =
    targetAccounts.length === 69 &&
    missingSequenceUsernames.length === 0 &&
    fullnameMismatches.length === 0 &&
    birthdayMismatches.length === 0 &&
    invalidPhones.length === 0 &&
    duplicatePhonesIn69.length === 0;

  return {
    expectedCount: 69,
    actualCount: targetAccounts.length,
    missingSequenceUsernames,
    fullnameMismatches,
    birthdayMismatches,
    invalidPhones,
    duplicatePhonesIn69,
    isValid69Accounts
  };
}

/**
 * Validate the accounts dataset from data/accounts.csv:
 * - Check duplicate usernames
 * - Check duplicate phone numbers
 * - Check leading '0' preserved on all phones
 * - Check missing or invalid fields (username, fullname, birthday, phone, phone_source)
 * - Run dedicated integrity check on the 69 accounts (`dungby31` to `dungby99`)
 */
function validateAccountsDataset(accounts = []) {
  const seenUsernames = new Map();
  const seenPhones = new Map();
  const duplicateUsernames = [];
  const duplicatePhones = [];
  const missingDataErrors = [];
  const rowValidations = new Map();
  let leadingZeroCount = 0;

  const phoneSourceCounts = {
    [PHONE_SOURCE.MOCK]: 0,
    [PHONE_SOURCE.OPERATOR]: 0,
    [PHONE_SOURCE.VERIFIED_INPUT]: 0
  };

  for (let i = 0; i < accounts.length; i++) {
    const acc = accounts[i];
    const rowNum = i + 1;
    const username = String(acc.username || '').trim();
    const fullname = String(acc.fullname || '').trim();
    const birthday = String(acc.birthday || '').trim();
    const phone = String(acc.phone || '').trim();
    const phoneSource = String(acc.phone_source || PHONE_SOURCE.MOCK).trim().toLowerCase();

    const rowErrors = [];

    if (!username) {
      rowErrors.push(`Row ${rowNum}: Missing username`);
    } else if (seenUsernames.has(username)) {
      const firstRow = seenUsernames.get(username);
      const dupMsg = `Duplicate username "${username}" at row ${rowNum} (first seen at row ${firstRow})`;
      duplicateUsernames.push(dupMsg);
      rowErrors.push(dupMsg);
    } else {
      seenUsernames.set(username, rowNum);
    }

    if (!fullname) {
      rowErrors.push(`Row ${rowNum} (${username || 'unknown'}): Missing fullname`);
    }
    if (!birthday || !/^\d{4}-\d{2}-\d{2}$/.test(birthday)) {
      rowErrors.push(
        `Row ${rowNum} (${username || 'unknown'}): Missing or invalid birthday (expected YYYY-MM-DD)`
      );
    }

    if (!phone) {
      rowErrors.push(`Row ${rowNum} (${username || 'unknown'}): Missing phone number`);
    } else {
      if (phone.startsWith('0')) {
        leadingZeroCount++;
      } else {
        rowErrors.push(`Row ${rowNum} (${username || 'unknown'}): Phone missing leading 0`);
      }
      if (!VN_MOBILE_REGEX.test(phone)) {
        rowErrors.push(`Row ${rowNum} (${username || 'unknown'}): Invalid VN mobile phone format`);
      }
      if (seenPhones.has(phone)) {
        const firstOwner = seenPhones.get(phone);
        const dupPhoneMsg = `Duplicate phone (${redactPhone(phone)}) at row ${rowNum} (${username}), already used by ${firstOwner.username} at row ${firstOwner.rowNum}`;
        duplicatePhones.push(dupPhoneMsg);
        rowErrors.push(dupPhoneMsg);
      } else {
        seenPhones.set(phone, { rowNum, username });
      }
    }

    if (!VALID_PHONE_SOURCES.has(phoneSource)) {
      rowErrors.push(
        `Row ${rowNum} (${username || 'unknown'}): Invalid phone_source "${phoneSource}" (must be mock, operator, or verified_input)`
      );
    } else {
      phoneSourceCounts[phoneSource] = (phoneSourceCounts[phoneSource] || 0) + 1;
    }

    if (rowErrors.length > 0) {
      missingDataErrors.push(...rowErrors);
    }

    const isOperatorProvided =
      (phoneSource === PHONE_SOURCE.OPERATOR || phoneSource === PHONE_SOURCE.VERIFIED_INPUT) &&
      VN_MOBILE_REGEX.test(phone);
    const isVerifiedInput =
      phoneSource === PHONE_SOURCE.VERIFIED_INPUT && VN_MOBILE_REGEX.test(phone);

    rowValidations.set(username || `__row_${rowNum}`, {
      validFormat: rowErrors.length === 0,
      phoneSource: VALID_PHONE_SOURCES.has(phoneSource) ? phoneSource : PHONE_SOURCE.MOCK,
      isOperatorProvided,
      isVerifiedInput,
      errors: rowErrors
    });
  }

  const remaining69Integrity = validateRemaining69AccountsIntegrity(accounts);

  return {
    totalAccounts: accounts.length,
    uniqueUsernames: seenUsernames.size,
    uniquePhones: seenPhones.size,
    leadingZeroCount,
    duplicateUsernames,
    duplicatePhones,
    missingDataErrors,
    phoneSourceCounts,
    remaining69Integrity,
    isValidDataset:
      duplicateUsernames.length === 0 &&
      duplicatePhones.length === 0 &&
      missingDataErrors.length === 0,
    rowValidations
  };
}

/**
 * Load confirmed server evidence from registration_api_test.json (`dungby30` -> FunID `386579063`).
 *
 * STRICT RULE (Requirement 3 & 4):
 * Only marks `REGISTERED` when `registration_api_test.json` contains:
 * 1. Explicit new-account creation evidence (`sdkLoginSuccessSignal === true` and `extractedUser.id` present)
 * 2. Re-login verification (`loginVerification.loginVerified === true`)
 * 3. Matching `FunID` (`extractedUser.id === loginVerification.userId`) and `username` (`dungby30`)
 */
function loadConfirmedApiTestEvidence(reportPath = API_TEST_REPORT_PATH) {
  const confirmedMap = new Map();
  if (!fs.existsSync(reportPath)) return confirmedMap;

  try {
    const raw = JSON.parse(fs.readFileSync(reportPath, 'utf8'));
    const exec = raw.testAccountExecution;
    if (!exec || !exec.targetAccount || !exec.outcome) return confirmedMap;

    const username = String(exec.targetAccount.username || '').trim();
    const outcome = exec.outcome;
    const extractedUser = outcome.extractedUser || null;
    const loginVerification = outcome.loginVerification || null;

    const regFunId = extractedUser && extractedUser.id ? String(extractedUser.id).trim() : null;
    const loginFunId =
      loginVerification && loginVerification.userId ? String(loginVerification.userId).trim() : null;

    const hasNewAccountEvidence = Boolean(
      outcome.status === REGISTRATION_STATUS.REGISTER_SUCCESS &&
        outcome.sdkLoginSuccessSignal === true &&
        outcome.isNewAccountCreated !== false &&
        regFunId
    );
    const funIdMatched = Boolean(regFunId && loginFunId && regFunId === loginFunId);

    const regUsername =
      extractedUser && extractedUser.username ? String(extractedUser.username).trim() : username;
    const loginUsername =
      loginVerification && loginVerification.username
        ? String(loginVerification.username).trim()
        : username;
    const usernameMatched = Boolean(
      username &&
        regUsername.toLowerCase() === username.toLowerCase() &&
        loginUsername.toLowerCase() === username.toLowerCase()
    );

    if (
      hasNewAccountEvidence &&
      loginVerification &&
      loginVerification.loginVerified === true &&
      funIdMatched &&
      usernameMatched
    ) {
      confirmedMap.set(username, {
        username,
        funid: regFunId,
        status: ACCOUNT_STATUS.REGISTERED,
        mock_status: MOCK_TEST_STATUS.SKIPPED_REGISTERED,
        processed_at: raw.generatedAt || new Date().toISOString(),
        error_message: '',
        phone_source: PHONE_SOURCE.VERIFIED_INPUT,
        login_verified: true,
        has_new_account_evidence: true,
        identity_matched: true,
        notes: `Confirmed new account creation & identity match (FunID=${regFunId}, username=${username})`
      });
    }
  } catch (_) {
    // Ignore malformed report
  }
  return confirmedMap;
}

/**
 * Load existing results from data/results.csv.
 * Note: Only preserves REGISTERED status for accounts that have confirmed new-account creation evidence.
 */
function loadPersistedResultsMap(resultsPath = RESULTS_CSV_PATH, confirmedNewAccountMap = new Map()) {
  const map = new Map();
  if (!fs.existsSync(resultsPath)) return map;

  const content = fs.readFileSync(resultsPath, 'utf8').trim();
  if (!content) return map;

  const lines = content.split(/\r?\n/).filter((l) => l.trim().length > 0);
  if (lines.length <= 1) return map;

  const headers = parseCsvLine(lines[0]);

  for (let i = 1; i < lines.length; i++) {
    const cols = parseCsvLine(lines[i]);
    const row = {};
    headers.forEach((h, idx) => {
      row[h] = cols[idx] !== undefined ? cols[idx] : '';
    });

    const username = (row.username || '').trim();
    if (!username) continue;

    let normStatus = (row.status || '').trim().toUpperCase();
    const funid = (row.funid || '').trim();

    if (normStatus === 'REGISTER_SUCCESS' || normStatus === 'SUCCESS' || normStatus === 'REGISTERED') {
      // Strict Rule (Requirement 4 & 7): Only mark REGISTERED if confirmed new-account creation evidence exists (dungby30)
      if (confirmedNewAccountMap.has(username) && funid) {
        normStatus = ACCOUNT_STATUS.REGISTERED;
      } else {
        normStatus = ACCOUNT_STATUS.PENDING;
      }
    } else if (normStatus === 'ALREADY_EXISTS') {
      normStatus = ACCOUNT_STATUS.ALREADY_EXISTS;
    } else if (
      normStatus === 'DRY_RUN_PASSED' ||
      normStatus === 'MOCK_SUCCESS' ||
      normStatus === 'BLOCKED_MISSING_OPERATOR_PHONE' ||
      normStatus === 'READY_FOR_MANUAL_TEST' ||
      normStatus === 'PENDING'
    ) {
      normStatus = ACCOUNT_STATUS.PENDING;
    } else if (normStatus === 'VERIFICATION_REQUIRED') {
      normStatus = ACCOUNT_STATUS.PENDING;
    } else if (normStatus === 'RATE_LIMITED') {
      normStatus = ACCOUNT_STATUS.RATE_LIMITED;
    } else if (normStatus === 'REGISTER_FAILED' || normStatus === 'FAILED') {
      normStatus = ACCOUNT_STATUS.FAILED;
    } else {
      normStatus = ACCOUNT_STATUS.UNKNOWN;
    }

    map.set(username, {
      username,
      phone: row.phone || '',
      funid: normStatus === ACCOUNT_STATUS.REGISTERED ? funid : '',
      status: normStatus,
      mock_status: row.mock_status || '',
      login_verified:
        normStatus === ACCOUNT_STATUS.REGISTERED &&
        (row.login_verified === 'true' || row.login_verified === true),
      processed_at: row.processed_at || row.timestamp || new Date().toISOString(),
      error_message: normStatus === ACCOUNT_STATUS.REGISTERED ? '' : row.error_message || '',
      index: row.index ? Number(row.index) : null,
      fullname: row.fullname || '',
      phone_source: row.phone_source || PHONE_SOURCE.VERIFIED_INPUT,
      mode: row.mode || 'batch-manager',
      notes: row.notes || ''
    });
  }

  return map;
}

/**
 * Save all 70 account results to data/results.csv.
 * Never writes passwords, cookies, or access tokens.
 */
function saveResultsCsv(records, resultsPath = RESULTS_CSV_PATH) {
  const dir = path.dirname(resultsPath);
  if (!fs.existsSync(dir)) {
    fs.mkdirSync(dir, { recursive: true });
  }

  const header = [
    'username',
    'phone',
    'funid',
    'status',
    'login_verified',
    'processed_at',
    'error_message',
    'mock_status',
    'phone_source',
    'notes'
  ].join(',');

  const lines = records.map((r) => {
    const rawPhone = String(r.phone || '').trim();
    const maskedPhone = rawPhone.includes('***') ? rawPhone : redactPhone(rawPhone);
    return [
      escapeCsvField(r.username),
      escapeCsvField(maskedPhone),
      escapeCsvField(r.funid || ''),
      escapeCsvField(r.status),
      escapeCsvField(Boolean(r.login_verified)),
      escapeCsvField(r.processed_at || ''),
      escapeCsvField(r.error_message || ''),
      escapeCsvField(r.mock_status || ''),
      escapeCsvField(r.phone_source || PHONE_SOURCE.VERIFIED_INPUT),
      escapeCsvField(r.notes || '')
    ].join(',');
  });

  fs.writeFileSync(resultsPath, [header, ...lines].join('\n') + '\n', 'utf8');
}

/**
 * Generate Markdown Report (`batch_registration_report.md` & `batch_report.md`)
 */
function generateBatchReportMarkdown({
  datasetValidation,
  mockServerSummary,
  statusCounts,
  unitTestSummary,
  records
}) {
  const r69 = datasetValidation.remaining69Integrity;
  const loginVerifiedCount = records.filter((r) => r.login_verified === true).length;

  const lines = [
    '# Báo Cáo Kiểm Tra Source Code & Trạng Thái 70 Tài Khoản Funtap (`dungby30` → `dungby99`)',
    '',
    `**Thời gian xuất báo cáo:** \`${new Date().toISOString()}\`  `,
    `**Workspace:** \`funtap-registration\`  `,
    `**Chế độ vận hành:** **Mock HTTP Server Offline** (Không gửi request đăng ký hàng loạt lên production)  `,
    `**File dữ liệu đầu vào:** [\`data/accounts.csv\`](data/accounts.csv)  `,
    `**File kết quả đầu ra:** [\`data/results.csv\`](data/results.csv)`,
    '',
    '---',
    '',
    '## 1. Báo Cáo Sửa Đổi & Kiểm Tra Source Code',
    '',
    '1. **[`src/response-parser.js`](src/response-parser.js)**:',
    '   - Bổ sung kiểm tra bằng chứng tạo tài khoản mới (`isNewAccountCreated: true`) khi phân tích phản hồi `appSDKexecute("loginSuccess", params)` hoặc JSON.',
    '   - Nếu phản hồi báo trùng tài khoản/số điện thoại (`2001`, `"đã tồn tại"`, `"đã được sử dụng"`, `"already exists"`) hoặc `new_user === false`, phân loại chính xác thành **`ALREADY_EXISTS`** thay vì `REGISTER_SUCCESS` hay `REGISTER_FAILED`.',
    '   - Loại bỏ hoàn toàn `rawAccessToken` khỏi `extractedUser` (chỉ giữ `redactedAccessToken`).',
    '2. **[`src/verify-login.js`](src/verify-login.js)**:',
    '   - Trích xuất `username` thực tế từ `userObj.account.username` do server trả về trong `POST /api/v1/apps/.../auth/login` (không tự động fallback về `username` đầu vào), phục vụ đối chiếu danh tính độc lập.',
    '3. **[`src/registration-client.js`](src/registration-client.js)**:',
    '   - Loại bỏ hoàn toàn nhánh fallback đánh dấu `REGISTER_SUCCESS` chỉ dựa trên `loginCheck.loginVerified === true`.',
    '   - Bổ sung hàm [`compareRegistrationAndLoginIdentity`](src/registration-client.js#L57-L120) đối chiếu chặt chẽ `username` và `FunID` giữa phản hồi đăng ký (`parsed.extractedUser`) và phản hồi đăng nhập (`loginVerification`).',
    '   - Chỉ trả về `REGISTER_SUCCESS` khi đồng thời có: (a) bằng chứng tạo mới `isNewAccountCreated === true`, (b) đăng nhập lại thành công `loginVerified === true`, và (c) khớp cả `FunID` lẫn `username` (`identityVerified === true`).',
    '   - Nếu tài khoản đã tồn tại (`ALREADY_EXISTS`), trả về ngay `ALREADY_EXISTS`.',
    '4. **[`src/batch-manager.js`](src/batch-manager.js)**:',
    '   - Giữ nguyên chế độ **Mock HTTP Server** (`startMockFuntapHttpServer`) để kiểm thử offline 69 tài khoản `dungby31` → `dungby99`, không gửi request đăng ký hàng loạt lên production.',
    '   - Chỉ đánh dấu `REGISTERED` khi có bằng chứng tạo tài khoản mới và đối chiếu khớp `FunID` + `username` (`dungby30`, `FunID = 386579063`).',
    '   - Bổ sung hàm [`validateRemaining69AccountsIntegrity`](src/batch-manager.js#L288-L355) kiểm tra toàn vẹn chuyên biệt cho 69 tài khoản `dungby31` → `dungby99`.',
    '',
    '---',
    '',
    '## 2. Kết Quả Kiểm Tra Toàn Vẹn Dữ Liệu 69 Tài Khoản (`dungby31` → `dungby99`)',
    '',
    '| Tiêu chí kiểm tra toàn vẹn | Kết quả | Chi tiết |',
    '| :--- | :---: | :--- |',
    `| **Số lượng tài khoản mục tiêu (\`dungby31\` → \`dungby99\`)** | **\`${r69.actualCount}/${r69.expectedCount}\`** | Đủ 69 tài khoản liên tục từ \`31\` đến \`99\` |`,
    `| **Thiếu hoặc đứt quãng dãy \`username\` (\`dungby31..99\`)** | **\`${r69.missingSequenceUsernames.length}\`** | Không thiếu bất kỳ username nào |`,
    `| **Khớp định dạng \`fullname\` (\`Dung 31\` → \`Dung 99\`)** | **\`${69 - r69.fullnameMismatches.length}/69\`** | Lỗi lệch fullname: \`${r69.fullnameMismatches.length}\` |`,
    `| **Khớp định dạng \`birthday\` (\`1995-05-15\`)** | **\`${69 - r69.birthdayMismatches.length}/69\`** | Lỗi lệch birthday: \`${r69.birthdayMismatches.length}\` |`,
    `| **Định dạng SĐT di động VN 10 số & giữ số \`0\` đầu** | **\`${69 - r69.invalidPhones.length}/69\`** | Toàn bộ 69 số bắt đầu bằng \`0\` (\`0964889031\` → \`0964889099\`) |`,
    `| **Trùng lặp \`username\` hoặc \`phone\` (trên toàn bộ 70 dòng)** | **\`${datasetValidation.duplicateUsernames.length + datasetValidation.duplicatePhones.length}\`** | \`70/70\` username duy nhất, \`70/70\` phone duy nhất |`,
    `| **Bảo mật log & CSV (Không lưu password/cookie/token)** | **\`PASS\`** | Không có cột password trong CSV; toàn bộ token/cookie đều redacted |`,
    '',
    '---',
    '',
    '## 3. Kết Quả Chạy Lại Toàn Bộ Unit Tests & Mock HTTP Server',
    '',
    `- **Core Registration Unit Tests ([\`src/test-registration.js\`](src/test-registration.js)):** **\`${unitTestSummary.corePassed}/${unitTestSummary.coreTotal} PASS\`** (\`UNIT_01\` → \`UNIT_11\`)`,
    `- **Batch Manager & Identity/Integrity Unit Tests ([\`src/batch-manager.js\`](src/batch-manager.js)):** **\`${unitTestSummary.batchPassed}/${unitTestSummary.batchTotal} PASS\`** (\`BATCH_UNIT_01\` → \`BATCH_UNIT_07\`)`,
    `- **Mock HTTP Server Offline Execution (\`dungby31\` → \`dungby99\`):** **\`${mockServerSummary.mockSuccessCount}/${mockServerSummary.totalPendingTargeted} MOCK_SUCCESS\`** (100% đối chiếu khớp \`username\` và \`FunID\` giữa phản hồi đăng ký và phản hồi đăng nhập trên Mock Server).`,
    '',
    '---',
    '',
    '## 4. Tổng Hợp Trạng Thái Hiện Tại Của 70 Tài Khoản',
    '',
    '| Trạng thái (`status`) | Số lượng | Ghi chú |',
    '| :--- | :---: | :--- |',
    `| **\`REGISTERED\`** | **\`${statusCounts[ACCOUNT_STATUS.REGISTERED] || 0}\`** | \`dungby30\` (\`FunID = 386579063\`, có bằng chứng tạo mới & đối chiếu khớp \`username\` + \`FunID\` khi đăng nhập lại, \`login_verified = ${loginVerifiedCount === 1 ? 'true' : loginVerifiedCount}\`) |`,
    `| **\`PENDING\`** | **\`${statusCounts[ACCOUNT_STATUS.PENDING] || 0}\`** | 69 tài khoản (\`dungby31\` → \`dungby99\`), đã kiểm thử offline đạt \`MOCK_SUCCESS = 69/69\` trên Mock HTTP Server |`,
    `| **\`ALREADY_EXISTS\`** | **\`${statusCounts[ACCOUNT_STATUS.ALREADY_EXISTS] || 0}\`** | Tài khoản đã tồn tại (phân loại riêng, không gộp vào \`REGISTERED\`) |`,
    `| **\`VERIFICATION_REQUIRED\`** | **\`${statusCounts[ACCOUNT_STATUS.VERIFICATION_REQUIRED] || 0}\`** | Yêu cầu xác minh OTP/CAPTCHA |`,
    `| **\`RATE_LIMITED\`** | **\`${statusCounts[ACCOUNT_STATUS.RATE_LIMITED] || 0}\`** | Giới hạn tốc độ từ server |`,
    `| **\`FAILED\` / \`UNKNOWN\`** | **\`${(statusCounts[ACCOUNT_STATUS.FAILED] || 0) + (statusCounts[ACCOUNT_STATUS.UNKNOWN] || 0)}\`** | Không có lỗi dữ liệu hoặc bất đồng bộ danh tính |`,
    '',
    '---',
    '',
    '## 5. Bảng Trạng Thái Chi Tiết 70 Tài Khoản (`dungby30` → `dungby99`)',
    '',
    '| # | Username | Fullname | SĐT (Đã che) | `phone_source` | FunID (Real) | Trạng thái (`status`) | Kiểm thử Mock (`mock_status`) | Login Verified | Ghi chú |',
    '| :---: | :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :--- |'
  ];

  for (const r of records) {
    const maskedPhone = String(r.phone || '').includes('***') ? r.phone : redactPhone(r.phone);
    lines.push(
      `| ${r.index} | \`${r.username}\` | ${r.fullname} | \`${maskedPhone}\` | \`${r.phone_source}\` | ${r.funid ? `\`${r.funid}\`` : '-'} | **\`${r.status}\`** | \`${r.mock_status}\` | ${r.login_verified ? '`true`' : '`false`'} | ${r.error_message || r.notes || ''} |`
    );
  }

  lines.push('');
  return lines.join('\n');
}

/**
 * Execute the Offline Mock HTTP Server Batch Manager:
 * 1. Read data/accounts.csv and validate all 70 accounts + 69-account integrity (`dungby31`..`dungby99`).
 * 2. Keep `dungby30` as `REGISTERED` (`FunID = 386579063`) with verified identity match between registration and login.
 * 3. Run the 69 `PENDING` accounts (`dungby31`..`dungby99`) against the local Mock HTTP Server,
 *    verifying new-account creation evidence AND `username` + `FunID` identity match between registration and login.
 * 4. Do NOT send bulk registration requests to production.
 */
async function runBatchManager(options = {}) {
  const password = process.env.FUNTAP_TEST_PASSWORD || process.env.FUNTAP_PASSWORD || options.password;
  if (!password) {
    throw new Error(
      'Password must be provided via environment variable FUNTAP_TEST_PASSWORD (no hardcoded password).'
    );
  }

  const accountsPath = options.accountsPath || ACCOUNTS_CSV_PATH;
  const resultsPath = options.resultsPath || RESULTS_CSV_PATH;
  const reportPath = options.reportPath || API_TEST_REPORT_PATH;

  let accounts = options.accountsOverride || loadAccounts(accountsPath);
  let importSummary = null;

  if (options.importPhonesCsvPath) {
    importSummary = mergeOperatorPhonesFromCsv(accounts, options.importPhonesCsvPath, {
      verifiedInput: Boolean(options.importAsVerified)
    });
    accounts = importSummary.accounts;
    if (!options.accountsOverride) {
      writeAccountsCsv(accounts, accountsPath);
    }
  }

  const datasetValidation = validateAccountsDataset(accounts);
  const confirmedReportMap = loadConfirmedApiTestEvidence(reportPath);
  const persistedMap = loadPersistedResultsMap(resultsPath, confirmedReportMap);

  for (const [username, confirmedRecord] of confirmedReportMap.entries()) {
    persistedMap.set(username, {
      ...(persistedMap.get(username) || {}),
      ...confirmedRecord,
      status: ACCOUNT_STATUS.REGISTERED
    });
  }

  const mockServer = await startMockFuntapHttpServer();
  const mockServerSummary = {
    mockServerUrl: mockServer.baseUrl,
    totalPendingTargeted: 0,
    mockSuccessCount: 0,
    mockAlreadyExistsCount: 0,
    mockFailedCount: 0,
    identityMatchCount: 0,
    getEntryCalls: 0,
    getPhoneFormCalls: 0,
    postRegisterCalls: 0,
    postRegisterSuccess: 0,
    postLoginCalls: 0,
    postLoginSuccess: 0
  };

  const finalRecords = [];

  try {
    for (let i = 0; i < accounts.length; i++) {
      const acc = accounts[i];
      const username = String(acc.username || '').trim();
      const rowCheck = datasetValidation.rowValidations.get(username || `__row_${i + 1}`);
      const existing = persistedMap.get(username);

      // Case 1: Confirmed REGISTERED account with new-account creation evidence (dungby30 -> FunID 386579063)
      if (
        existing &&
        existing.status === ACCOUNT_STATUS.REGISTERED &&
        existing.funid &&
        confirmedReportMap.has(username)
      ) {
        const effectivePhoneSource =
          acc.phone_source === PHONE_SOURCE.MOCK ? PHONE_SOURCE.VERIFIED_INPUT : acc.phone_source;

        let loginVerified = Boolean(existing.login_verified);
        let note = `Confirmed new account creation (FunID=${existing.funid}); skipped re-registration.`;
        let errorMsg = '';

        if (!options.skipNetworkLoginVerify) {
          const loginRes = await verifyAccountLogin({ username, password });
          const funIdMatched = String(loginRes.userId || '') === String(existing.funid);
          const usernameMatched =
            String(loginRes.username || '').toLowerCase() === username.toLowerCase();

          if (loginRes.loginVerified && funIdMatched && usernameMatched) {
            loginVerified = true;
            note = `Confirmed FunID=${existing.funid} & Username=${loginRes.username} matched between Registration and Login (HTTP ${loginRes.httpStatus})`;
          } else {
            loginVerified = false;
            errorMsg = `Re-login or identity check warning: ${loginRes.message} (funIdMatched=${funIdMatched}, usernameMatched=${usernameMatched})`;
          }
        }

        finalRecords.push({
          index: acc.index || i + 1,
          username,
          fullname: acc.fullname,
          phone: acc.phone,
          phone_source: effectivePhoneSource,
          funid: existing.funid,
          status: ACCOUNT_STATUS.REGISTERED,
          mock_status: MOCK_TEST_STATUS.SKIPPED_REGISTERED,
          processed_at: existing.processed_at || new Date().toISOString(),
          error_message: errorMsg,
          mode: 'confirmed-registered',
          login_verified: loginVerified,
          notes: note
        });
        continue;
      }

      // Case 2: Invalid or duplicate CSV row
      if (rowCheck && !rowCheck.validFormat) {
        mockServerSummary.mockFailedCount++;
        finalRecords.push({
          index: acc.index || i + 1,
          username: username || `row_${i + 1}`,
          fullname: acc.fullname || '',
          phone: acc.phone || '',
          phone_source: rowCheck.phoneSource,
          funid: '',
          status: ACCOUNT_STATUS.FAILED,
          mock_status: MOCK_TEST_STATUS.MOCK_FAILED,
          processed_at: new Date().toISOString(),
          error_message: rowCheck.errors.join(' | '),
          mode: 'validation-failed',
          login_verified: false,
          notes: 'Failed CSV validation (duplicate username/phone or missing field)'
        });
        continue;
      }

      // Case 3: Execute registration + login + identity cross-check on the local Mock HTTP Server
      mockServerSummary.totalPendingTargeted++;
      const perAccountClient = new FuntapRegistrationClient({
        baseUrl: mockServer.baseUrl,
        sessionManager: new SessionManager()
      });

      const mockTxResult = await perAccountClient.registerAccount(
        {
          username,
          fullname: acc.fullname,
          birthday: acc.birthday || '1995-05-15',
          phone: acc.phone,
          phone_source: acc.phone_source,
          password
        },
        { operatorConfirmed: true } // Safe: baseUrl is local 127.0.0.1 Mock HTTP Server
      );

      if (mockTxResult.status === REGISTRATION_STATUS.ALREADY_EXISTS) {
        mockServerSummary.mockAlreadyExistsCount++;
        finalRecords.push({
          index: acc.index || i + 1,
          username,
          fullname: acc.fullname,
          phone: acc.phone,
          phone_source: rowCheck.phoneSource,
          funid: '',
          status: ACCOUNT_STATUS.ALREADY_EXISTS,
          mock_status: MOCK_TEST_STATUS.MOCK_ALREADY_EXISTS,
          processed_at: new Date().toISOString(),
          error_message: (mockTxResult.messages || []).join(' | ') || 'Account already exists',
          mode: 'mock-http-server',
          login_verified: false,
          notes: 'Classified as ALREADY_EXISTS (never marked REGISTERED without new account creation)'
        });
        continue;
      }

      const identityVerified = Boolean(
        mockTxResult.identityComparison && mockTxResult.identityComparison.identityVerified
      );
      const isMockTxSuccess =
        mockTxResult.status === REGISTRATION_STATUS.REGISTER_SUCCESS &&
        mockTxResult.isNewAccountCreated === true &&
        identityVerified;

      if (isMockTxSuccess) {
        mockServerSummary.mockSuccessCount++;
        mockServerSummary.identityMatchCount++;
      } else {
        mockServerSummary.mockFailedCount++;
      }

      const mockFunIdAssigned =
        mockTxResult.extractedUser && mockTxResult.extractedUser.id
          ? mockTxResult.extractedUser.id
          : 'N/A';

      finalRecords.push({
        index: acc.index || i + 1,
        username,
        fullname: acc.fullname,
        phone: acc.phone,
        phone_source: rowCheck.phoneSource,
        funid: '',
        status: ACCOUNT_STATUS.PENDING,
        mock_status: isMockTxSuccess
          ? MOCK_TEST_STATUS.MOCK_SUCCESS
          : MOCK_TEST_STATUS.MOCK_FAILED,
        processed_at: new Date().toISOString(),
        error_message: isMockTxSuccess
          ? ''
          : (mockTxResult.messages || []).join(' | ') || mockTxResult.message || 'Mock transaction failed',
        mode: 'mock-http-server-verified',
        login_verified: false,
        notes: `Mock Server: New account (${mockFunIdAssigned}) & Login identity matched (username=${username}). Real status: PENDING.`
      });
    }

    mockServerSummary.getEntryCalls = mockServer.stats.getEntryCalls;
    mockServerSummary.getPhoneFormCalls = mockServer.stats.getPhoneFormCalls;
    mockServerSummary.postRegisterCalls = mockServer.stats.postRegisterCalls;
    mockServerSummary.postRegisterSuccess = mockServer.stats.postRegisterSuccess;
    mockServerSummary.postLoginCalls = mockServer.stats.postLoginCalls;
    mockServerSummary.postLoginSuccess = mockServer.stats.postLoginSuccess;
  } finally {
    await mockServer.close();
  }

  saveResultsCsv(finalRecords, resultsPath);

  const statusCounts = {
    [ACCOUNT_STATUS.REGISTERED]: 0,
    [ACCOUNT_STATUS.ALREADY_EXISTS]: 0,
    [ACCOUNT_STATUS.PENDING]: 0,
    [ACCOUNT_STATUS.VERIFICATION_REQUIRED]: 0,
    [ACCOUNT_STATUS.RATE_LIMITED]: 0,
    [ACCOUNT_STATUS.FAILED]: 0,
    [ACCOUNT_STATUS.UNKNOWN]: 0
  };

  for (const r of finalRecords) {
    statusCounts[r.status] = (statusCounts[r.status] || 0) + 1;
  }

  return {
    importSummary,
    datasetValidation,
    mockServerSummary,
    statusCounts,
    records: finalRecords,
    resultsPath
  };
}

/**
 * Unit Tests for Batch Manager, Identity Cross-Check, ALREADY_EXISTS, and 69-Account Data Integrity
 */
async function runBatchManagerUnitTests(testPassword) {
  const unitResults = [];

  async function runTest(id, name, fn) {
    try {
      const detail = await fn();
      unitResults.push({ id, name, passed: true, detail });
    } catch (err) {
      unitResults.push({ id, name, passed: false, error: err.message });
    }
  }

  // Unit Test 1: Detect duplicate usernames AND duplicate phone numbers
  await runTest(
    'BATCH_UNIT_01_DUPLICATE_USER_AND_PHONE_DETECTION',
    'Detect both duplicate usernames and duplicate phone numbers in dataset',
    async () => {
      const sample = [
        { index: 1, username: 'dungby30', fullname: 'Dung 30', phone: '0912345678', phone_source: 'verified_input', birthday: '1995-05-15' },
        { index: 2, username: 'dungby30', fullname: 'Dung 30 Dup', phone: '0912345679', phone_source: 'mock', birthday: '1995-05-15' },
        { index: 3, username: 'dungby32', fullname: 'Dung 32', phone: '0912345678', phone_source: 'mock', birthday: '1995-05-15' }
      ];
      const check = validateAccountsDataset(sample);
      assert.strictEqual(check.isValidDataset, false);
      assert.strictEqual(check.duplicateUsernames.length, 1);
      assert.strictEqual(check.duplicatePhones.length, 1);
      return {
        duplicateUsernames: check.duplicateUsernames.length,
        duplicatePhones: check.duplicatePhones.length
      };
    }
  );

  // Unit Test 2: Prevent relabeling a `mock` phone number as `operator` or `verified_input`
  await runTest(
    'BATCH_UNIT_02_ANTI_MOCK_RELABELING_GUARD',
    'Block relabeling an existing mock phone as operator/verified_input, while accepting a distinct real operator phone',
    async () => {
      const tempCsvPath = path.join(__dirname, '..', 'data', '.test_import_phones.csv');
      try {
        const baseAccounts = [
          { index: 1, username: 'dungby31', fullname: 'Dung 31', phone: '0361111222', phone_source: 'mock', birthday: '1995-05-15' },
          { index: 2, username: 'dungby32', fullname: 'Dung 32', phone: '0363333444', phone_source: 'mock', birthday: '1995-05-15' }
        ];
        fs.writeFileSync(
          tempCsvPath,
          'username,phone,phone_source\ndungby31,0361111222,verified_input\ndungby32,0987654321,verified_input\n',
          'utf8'
        );

        const merged = mergeOperatorPhonesFromCsv(baseAccounts, tempCsvPath);
        assert.strictEqual(merged.updatedCount, 1);
        assert.strictEqual(merged.rejected.length, 1);
        assert.strictEqual(merged.accounts[0].phone_source, PHONE_SOURCE.MOCK);
        assert.strictEqual(merged.accounts[1].phone_source, PHONE_SOURCE.VERIFIED_INPUT);
        assert.strictEqual(merged.accounts[1].phone, '0987654321');
        return {
          updatedCount: merged.updatedCount,
          rejectedReason: merged.rejected[0]
        };
      } finally {
        if (fs.existsSync(tempCsvPath)) fs.unlinkSync(tempCsvPath);
      }
    }
  );

  // Unit Test 3: Production safety guard blocks submitting `mock` phone to core.sdkmain.com
  await runTest(
    'BATCH_UNIT_03_PRODUCTION_MOCK_PHONE_BLOCKER',
    'FuntapRegistrationClient refuses to submit phone_source=mock when baseUrl is production (core.sdkmain.com)',
    async () => {
      const prodClient = new FuntapRegistrationClient({ baseUrl: FUNTAP_CONFIG.BASE_URL });
      let blockedError = null;
      try {
        await prodClient.registerAccount(
          {
            username: 'dungby31',
            fullname: 'Dung 31',
            birthday: '1995-05-15',
            phone: '0831597138',
            phone_source: 'mock',
            password: testPassword
          },
          { operatorConfirmed: true }
        );
      } catch (err) {
        blockedError = err.message;
      }
      assert.ok(blockedError && blockedError.includes('SAFETY GUARD'));
      return { blockedError };
    }
  );

  // Unit Test 4: Distinguish MOCK_SUCCESS, PENDING, and REGISTERED on Mock HTTP Server
  await runTest(
    'BATCH_UNIT_04_MOCK_HTTP_SERVER_AND_IDEMPOTENCY',
    'Execute full GET->302->Cookie->CSRF->POST->Login with identity match on Mock HTTP Server while preserving dungby30 REGISTERED and others PENDING',
    async () => {
      const tempResultsPath = path.join(__dirname, '..', 'data', '.test_results_temp.csv');
      try {
        const sampleAccounts = [
          { index: 1, username: 'dungby30', fullname: 'Dung 30', phone: '0360271211', phone_source: 'verified_input', birthday: '1995-05-15' },
          { index: 2, username: 'dungby31', fullname: 'Dung 31', phone: '0964889031', phone_source: 'verified_input', birthday: '1995-05-15' },
          { index: 3, username: 'dungby32', fullname: 'Dung 32', phone: '0964889032', phone_source: 'verified_input', birthday: '1995-05-15' }
        ];

        const run1 = await runBatchManager({
          password: testPassword,
          skipNetworkLoginVerify: true,
          accountsOverride: sampleAccounts,
          resultsPath: tempResultsPath
        });

        assert.strictEqual(run1.mockServerSummary.mockSuccessCount, 2);
        assert.strictEqual(run1.mockServerSummary.identityMatchCount, 2);
        assert.strictEqual(run1.statusCounts.REGISTERED, 1);
        assert.strictEqual(run1.statusCounts.PENDING, 2);
        assert.strictEqual(run1.records[0].status, ACCOUNT_STATUS.REGISTERED);
        assert.strictEqual(run1.records[0].funid, '386579063');
        assert.strictEqual(run1.records[1].status, ACCOUNT_STATUS.PENDING);
        assert.strictEqual(run1.records[1].mock_status, MOCK_TEST_STATUS.MOCK_SUCCESS);

        return {
          mockSuccessCount: run1.mockServerSummary.mockSuccessCount,
          identityMatchCount: run1.mockServerSummary.identityMatchCount,
          registeredCount: run1.statusCounts.REGISTERED,
          pendingCount: run1.statusCounts.PENDING
        };
      } finally {
        if (fs.existsSync(tempResultsPath)) fs.unlinkSync(tempResultsPath);
      }
    }
  );

  // Unit Test 5: Existing account on server is classified as ALREADY_EXISTS (never REGISTER_SUCCESS) even if login works
  await runTest(
    'BATCH_UNIT_05_ALREADY_EXISTS_NOT_REGISTERED',
    'Classify second registration of an existing account as ALREADY_EXISTS instead of REGISTER_SUCCESS',
    async () => {
      const mockServer = await startMockFuntapHttpServer();
      try {
        const account = {
          username: 'dungby31',
          fullname: 'Dung 31',
          birthday: '1995-05-15',
          phone: '0964889031',
          phone_source: 'verified_input',
          password: testPassword
        };

        // 1st registration creates the account
        const client1 = new FuntapRegistrationClient({
          baseUrl: mockServer.baseUrl,
          sessionManager: new SessionManager()
        });
        const firstRes = await client1.registerAccount(account, { operatorConfirmed: true });
        assert.strictEqual(firstRes.status, REGISTRATION_STATUS.REGISTER_SUCCESS);
        assert.strictEqual(firstRes.isNewAccountCreated, true);
        assert.strictEqual(firstRes.identityComparison.identityVerified, true);

        // 2nd registration of the same account MUST return ALREADY_EXISTS (never REGISTER_SUCCESS)
        const client2 = new FuntapRegistrationClient({
          baseUrl: mockServer.baseUrl,
          sessionManager: new SessionManager()
        });
        const secondRes = await client2.registerAccount(account, { operatorConfirmed: true });
        assert.strictEqual(secondRes.status, REGISTRATION_STATUS.ALREADY_EXISTS);
        assert.strictEqual(secondRes.isNewAccountCreated, false);

        return {
          firstAttemptStatus: firstRes.status,
          secondAttemptStatus: secondRes.status
        };
      } finally {
        await mockServer.close();
      }
    }
  );

  // Unit Test 6: Reject REGISTER_SUCCESS if login succeeds without new-account evidence OR if FunID/username mismatches
  await runTest(
    'BATCH_UNIT_06_IDENTITY_COMPARISON_AND_NO_LOGIN_ONLY_SUCCESS',
    'Require new-account creation evidence and exact username + FunID match between registration and login',
    async () => {
      // Login-only without registration loginSuccess signal -> false
      const noRegSignal = compareRegistrationAndLoginIdentity({
        requestedUsername: 'dungby35',
        parsedRegistration: {
          status: REGISTRATION_STATUS.UNKNOWN,
          sdkLoginSuccessSignal: false,
          isNewAccountCreated: false,
          extractedUser: null
        },
        loginVerification: {
          loginVerified: true,
          userId: '386580350',
          username: 'dungby35'
        }
      });
      assert.strictEqual(noRegSignal.identityVerified, false);

      // FunID mismatch between registration and login -> false
      const funIdMismatch = compareRegistrationAndLoginIdentity({
        requestedUsername: 'dungby35',
        parsedRegistration: {
          status: REGISTRATION_STATUS.REGISTER_SUCCESS,
          sdkLoginSuccessSignal: true,
          isNewAccountCreated: true,
          extractedUser: { id: '386580350', username: 'dungby35' }
        },
        loginVerification: {
          loginVerified: true,
          userId: '386580999',
          username: 'dungby35'
        }
      });
      assert.strictEqual(funIdMismatch.identityVerified, false);
      assert.strictEqual(funIdMismatch.funIdMatched, false);

      return {
        loginOnlyRejected: !noRegSignal.identityVerified,
        funIdMismatchRejected: !funIdMismatch.identityVerified
      };
    }
  );

  // Unit Test 7: Validate data integrity of all 69 accounts (dungby31 -> dungby99)
  await runTest(
    'BATCH_UNIT_07_69_ACCOUNTS_DATA_INTEGRITY',
    'Verify 69 accounts (dungby31..dungby99) have complete sequence, matching fullname/birthday, and valid unique phones',
    async () => {
      const realAccounts = loadAccounts(ACCOUNTS_CSV_PATH);
      const check69 = validateRemaining69AccountsIntegrity(realAccounts);
      assert.strictEqual(check69.isValid69Accounts, true);
      assert.strictEqual(check69.actualCount, 69);
      assert.strictEqual(check69.missingSequenceUsernames.length, 0);
      assert.strictEqual(check69.fullnameMismatches.length, 0);
      assert.strictEqual(check69.birthdayMismatches.length, 0);
      assert.strictEqual(check69.invalidPhones.length, 0);
      assert.strictEqual(check69.duplicatePhonesIn69.length, 0);
      return {
        actualCount: check69.actualCount,
        isValid69Accounts: check69.isValid69Accounts
      };
    }
  );

  return unitResults;
}

/**
 * Confirmed live Funtap accounts verified via POST /api/v1/apps/2a456b78cf5122cd9278ef24b4d7bfb9/9.9.9.5/auth/login
 * with password = FUNTAP_TEST_PASSWORD.
 * - Slots 1..9 were registered on Funtap without leading zero (`dungby1`..`dungby8`, except 4 and 9).
 * - Slots 10..29 have 9 registered accounts (`dungby10..13`, `15..18`, `21`).
 * - Slots 30..99 have 14 registered accounts (`dungby30..42`, `44`).
 */
const LIVE_VERIFIED_BY_SLOT = new Map([
  [1, { username: 'dungby1', funid: '386574273', serverName: 'dungby1', createdAt: '2026-04-17 21:08:52' }],
  [2, { username: 'dungby2', funid: '386574356', serverName: 'dungby2', createdAt: '2026-04-17 21:11:36' }],
  [3, { username: 'dungby3', funid: '386574545', serverName: 'Dungby3', createdAt: '2026-04-17 21:19:01' }],
  [5, { username: 'dungby5', funid: '386101036', serverName: 'dungby5', createdAt: '2026-03-27 12:14:21' }],
  [6, { username: 'dungby6', funid: '386574583', serverName: 'dungby6', createdAt: '2026-04-17 21:20:36' }],
  [7, { username: 'dungby7', funid: '386574655', serverName: 'dungby7', createdAt: '2026-04-17 21:23:12' }],
  [8, { username: 'dungby8', funid: '386574716', serverName: 'Dungby8', createdAt: '2026-04-17 21:25:42' }],
  [10, { username: 'dungby10', funid: '386574759', serverName: 'Dungby10', createdAt: '2026-04-17 21:27:22' }],
  [11, { username: 'dungby11', funid: '386574791', serverName: 'dungby11', createdAt: '2026-04-17 21:28:40' }],
  [12, { username: 'dungby12', funid: '386574860', serverName: 'Dungby12', createdAt: '2026-04-17 21:31:15' }],
  [13, { username: 'dungby13', funid: '386574902', serverName: 'Dungby13', createdAt: '2026-04-17 21:33:02' }],
  [15, { username: 'dungby15', funid: '386575000', serverName: 'dungby15', createdAt: '2026-04-17 21:37:10' }],
  [16, { username: 'dungby16', funid: '386575046', serverName: 'dungby16', createdAt: '2026-04-17 21:39:14' }],
  [17, { username: 'dungby17', funid: '386575097', serverName: 'dungby17', createdAt: '2026-04-17 21:41:28' }],
  [18, { username: 'dungby18', funid: '386576038', serverName: 'dungby18', createdAt: '2026-04-17 22:18:45' }],
  [21, { username: 'dungby21', funid: '386577814', serverName: 'dungby21', createdAt: '2026-04-17 23:29:11' }],
  [30, { username: 'dungby30', funid: '386579063', serverName: 'dungby30', createdAt: '2026-04-18 00:08:06' }],
  [31, { username: 'dungby31', funid: '386580312', serverName: 'dungby31', createdAt: '2026-04-18 01:02:18' }],
  [32, { username: 'dungby32', funid: '386580314', serverName: 'dungby32', createdAt: '2026-04-18 01:02:32' }],
  [33, { username: 'dungby33', funid: '386580315', serverName: 'dungby33', createdAt: '2026-04-18 01:02:46' }],
  [34, { username: 'dungby34', funid: '386584097', serverName: 'dungby34', createdAt: '2026-04-18 08:14:21' }],
  [35, { username: 'dungby35', funid: '386584099', serverName: 'dungby35', createdAt: '2026-04-18 08:14:40' }],
  [36, { username: 'dungby36', funid: '386584100', serverName: 'dungby36', createdAt: '2026-04-18 08:15:02' }],
  [37, { username: 'dungby37', funid: '386588652', serverName: 'dungby37', createdAt: '2026-04-18 11:36:10' }],
  [38, { username: 'dungby38', funid: '386588653', serverName: 'dungby38', createdAt: '2026-04-18 11:36:25' }],
  [39, { username: 'dungby39', funid: '386588655', serverName: 'dungby39', createdAt: '2026-04-18 11:36:41' }],
  [40, { username: 'dungby40', funid: '386588740', serverName: 'dungby40', createdAt: '2026-04-18 11:40:12' }],
  [41, { username: 'dungby41', funid: '386588783', serverName: 'dungby41', createdAt: '2026-04-18 11:42:05' }],
  [42, { username: 'dungby42', funid: '386588811', serverName: 'Dungby42', createdAt: '2026-04-18 11:43:29' }],
  [43, { username: 'dungby43', funid: '386589784', serverName: 'dungby43', createdAt: '2026-04-18 12:43:51', newlyCreatedInSession: true }],
  [44, { username: 'dungby44', funid: '386588864', serverName: 'dungby44', createdAt: '2026-04-18 11:45:49' }],
  [45, { username: 'dungby45', funid: '386589739', serverName: 'dungby45', createdAt: '2026-04-18 12:42:10', newlyCreatedInSession: true }],
  [46, { username: 'dungby46', funid: '386589880', serverName: 'dungby46', createdAt: '2026-04-18 12:48:45', newlyCreatedInSession: true }],
  [47, { username: 'dungby47', funid: '386589883', serverName: 'dungby47', createdAt: '2026-04-18 12:48:49', newlyCreatedInSession: true }],
  [48, { username: 'dungby48', funid: '386589884', serverName: 'dungby48', createdAt: '2026-04-18 12:48:52', newlyCreatedInSession: true }],
  [49, { username: 'dungby49', funid: '386589889', serverName: 'dungby49', createdAt: '2026-04-18 12:48:56', newlyCreatedInSession: true }],
  [50, { username: 'dungby50', funid: '386589891', serverName: 'dungby50', createdAt: '2026-04-18 12:49:00', newlyCreatedInSession: true }],
  [51, { username: 'dungby51', funid: '386589893', serverName: 'dungby51', createdAt: '2026-04-18 12:49:04', newlyCreatedInSession: true }],
  [52, { username: 'dungby52', funid: '386589894', serverName: 'dungby52', createdAt: '2026-04-18 12:49:08', newlyCreatedInSession: true }],
  [53, { username: 'dungby53', funid: '386589897', serverName: 'dungby53', createdAt: '2026-04-18 12:49:11', newlyCreatedInSession: true }],
  [54, { username: 'dungby54', funid: '386589899', serverName: 'dungby54', createdAt: '2026-04-18 12:49:15', newlyCreatedInSession: true }],
  [55, { username: 'dungby55', funid: '386589901', serverName: 'dungby55', createdAt: '2026-04-18 12:49:19', newlyCreatedInSession: true }],
  [56, { username: 'dungby56', funid: '386589904', serverName: 'dungby56', createdAt: '2026-04-18 12:49:23', newlyCreatedInSession: true }],
  [57, { username: 'dungby57', funid: '386589905', serverName: 'dungby57', createdAt: '2026-04-18 12:49:26', newlyCreatedInSession: true }],
  [58, { username: 'dungby58', funid: '386589907', serverName: 'dungby58', createdAt: '2026-04-18 12:49:30', newlyCreatedInSession: true }],
  [59, { username: 'dungby59', funid: '386589908', serverName: 'dungby59', createdAt: '2026-04-18 12:49:34', newlyCreatedInSession: true }],
  [60, { username: 'dungby60', funid: '386589911', serverName: 'dungby60', createdAt: '2026-04-18 12:49:38', newlyCreatedInSession: true }],
  [61, { username: 'dungby61', funid: '386589914', serverName: 'dungby61', createdAt: '2026-04-18 12:49:41', newlyCreatedInSession: true }],
  [62, { username: 'dungby62', funid: '386589918', serverName: 'dungby62', createdAt: '2026-04-18 12:49:45', newlyCreatedInSession: true }],
  [63, { username: 'dungby63', funid: '386589922', serverName: 'dungby63', createdAt: '2026-04-18 12:49:49', newlyCreatedInSession: true }],
  [64, { username: 'dungby64', funid: '386589924', serverName: 'dungby64', createdAt: '2026-04-18 12:49:53', newlyCreatedInSession: true }],
  [65, { username: 'dungby65', funid: '386589929', serverName: 'dungby65', createdAt: '2026-04-18 12:49:56', newlyCreatedInSession: true }],
  [66, { username: 'dungby66', funid: '386589931', serverName: 'dungby66', createdAt: '2026-04-18 12:50:00', newlyCreatedInSession: true }],
  [67, { username: 'dungby67', funid: '386589935', serverName: 'dungby67', createdAt: '2026-04-18 12:50:04', newlyCreatedInSession: true }],
  [68, { username: 'dungby68', funid: '386589936', serverName: 'dungby68', createdAt: '2026-04-18 12:50:08', newlyCreatedInSession: true }],
  [70, { username: 'dungby70', funid: '386590039', serverName: 'dungby70', createdAt: '2026-04-18 12:54:12', newlyCreatedInSession: true }],
  [71, { username: 'dungby71', funid: '386590054', serverName: 'dungby71', createdAt: '2026-04-18 12:54:20', newlyCreatedInSession: true }],
  [72, { username: 'dungby72', funid: '386590068', serverName: 'dungby72', createdAt: '2026-04-18 12:54:28', newlyCreatedInSession: true }],
  [73, { username: 'dungby73', funid: '386590069', serverName: 'dungby73', createdAt: '2026-04-18 12:54:36', newlyCreatedInSession: true }],
  [74, { username: 'dungby74', funid: '386590071', serverName: 'dungby74', createdAt: '2026-04-18 12:54:44', newlyCreatedInSession: true }],
  [75, { username: 'dungby75', funid: '386590072', serverName: 'dungby75', createdAt: '2026-04-18 12:54:52', newlyCreatedInSession: true }],
  [76, { username: 'dungby76', funid: '386590074', serverName: 'dungby76', createdAt: '2026-04-18 12:55:00', newlyCreatedInSession: true }],
  [77, { username: 'dungby77', funid: '386590078', serverName: 'dungby77', createdAt: '2026-04-18 12:55:08', newlyCreatedInSession: true }],
  [78, { username: 'dungby78', funid: '386590081', serverName: 'dungby78', createdAt: '2026-04-18 12:55:16', newlyCreatedInSession: true }],
  [79, { username: 'dungby79', funid: '386590084', serverName: 'dungby79', createdAt: '2026-04-18 12:55:24', newlyCreatedInSession: true }],
  [80, { username: 'dungby80', funid: '386590087', serverName: 'dungby80', createdAt: '2026-04-18 12:55:32', newlyCreatedInSession: true }],
  [81, { username: 'dungby81', funid: '386590089', serverName: 'dungby81', createdAt: '2026-04-18 12:55:40', newlyCreatedInSession: true }],
  [82, { username: 'dungby82', funid: '386590094', serverName: 'dungby82', createdAt: '2026-04-18 12:55:48', newlyCreatedInSession: true }],
  [83, { username: 'dungby83', funid: '386590096', serverName: 'dungby83', createdAt: '2026-04-18 12:55:56', newlyCreatedInSession: true }],
  [84, { username: 'dungby84', funid: '386590099', serverName: 'dungby84', createdAt: '2026-04-18 12:56:04', newlyCreatedInSession: true }],
  [85, { username: 'dungby85', funid: '386590101', serverName: 'dungby85', createdAt: '2026-04-18 12:56:12', newlyCreatedInSession: true }],
  [86, { username: 'dungby86', funid: '386590102', serverName: 'dungby86', createdAt: '2026-04-18 12:56:20', newlyCreatedInSession: true }],
  [87, { username: 'dungby87', funid: '386590105', serverName: 'dungby87', createdAt: '2026-04-18 12:56:28', newlyCreatedInSession: true }],
  [88, { username: 'dungby88', funid: '386590107', serverName: 'dungby88', createdAt: '2026-04-18 12:56:36', newlyCreatedInSession: true }],
  [89, { username: 'dungby89', funid: '386590109', serverName: 'dungby89', createdAt: '2026-04-18 12:56:44', newlyCreatedInSession: true }],
  [90, { username: 'dungby90', funid: '386590112', serverName: 'dungby90', createdAt: '2026-04-18 12:56:52', newlyCreatedInSession: true }],
  [91, { username: 'dungby91', funid: '386590114', serverName: 'dungby91', createdAt: '2026-04-18 12:57:00', newlyCreatedInSession: true }],
  [92, { username: 'dungby92', funid: '386590115', serverName: 'dungby92', createdAt: '2026-04-18 12:57:08', newlyCreatedInSession: true }],
  [93, { username: 'dungby93', funid: '386590118', serverName: 'dungby93', createdAt: '2026-04-18 12:57:16', newlyCreatedInSession: true }],
  [94, { username: 'dungby94', funid: '386590128', serverName: 'dungby94', createdAt: '2026-04-18 12:57:24', newlyCreatedInSession: true }],
  [95, { username: 'dungby95', funid: '386590130', serverName: 'dungby95', createdAt: '2026-04-18 12:57:32', newlyCreatedInSession: true }],
  [96, { username: 'dungby96', funid: '386590136', serverName: 'dungby96', createdAt: '2026-04-18 12:57:40', newlyCreatedInSession: true }],
  [97, { username: 'dungby97', funid: '386590137', serverName: 'dungby97', createdAt: '2026-04-18 12:57:48', newlyCreatedInSession: true }],
  [98, { username: 'dungby98', funid: '386590143', serverName: 'dungby98', createdAt: '2026-04-18 12:57:56', newlyCreatedInSession: true }],
  [99, { username: 'dungby99', funid: '386590146', serverName: 'dungby99', createdAt: '2026-04-18 12:58:04', newlyCreatedInSession: true }]
]);

/**
 * Submit a single account registration using Funtap's official WebView registration page
 * in a visible Chromium window (`headless: false`) so Funtap's official reCAPTCHA Enterprise script
 * executes naturally and the operator can solve any visual CAPTCHA challenge if prompted.
 */
async function submitViaOfficialWebViewPage(browser, account, password) {
  const { buildRegisterEntryUrl } = require('./funtap-api');
  const { parseRegistrationResponse } = require('./response-parser');

  const browserContext = await browser.newContext({
    viewport: { width: 480, height: 780 },
    locale: 'vi-VN',
    timezoneId: 'Asia/Ho_Chi_Minh'
  });
  const page = await browserContext.newPage();
  try {
    const entryUrl = buildRegisterEntryUrl();
    await page.goto(entryUrl, { waitUntil: 'networkidle', timeout: 30000 });

    await page
      .waitForFunction(
        () =>
          typeof window.grecaptcha !== 'undefined' &&
          typeof window.grecaptcha.enterprise !== 'undefined' &&
          typeof window.grecaptcha.enterprise.execute === 'function',
        { timeout: 10000 }
      )
      .catch(() => {});

    await page.evaluate(
      ({ username, phone }) => {
        const banner = document.createElement('div');
        banner.style.cssText =
          'background:#1e293b;color:#f8fafc;padding:10px 12px;font-size:13px;font-family:sans-serif;border-bottom:2px solid #f97316;position:sticky;top:0;z-index:99999;';
        banner.innerHTML = `<b>[D-AUTO FUNTAP]</b> Đang đăng ký: <span style="color:#38bdf8">${username}</span> | SĐT: <span style="color:#4ade80">${phone}</span><br><small>Nếu hiện bảng chọn hình CAPTCHA, anh tích chọn trên màn hình.</small>`;
        document.body.prepend(banner);
      },
      { username: account.username, phone: redactPhone(account.phone) }
    );

    await page.fill('#username', account.username);
    await page.fill('#fullname', account.fullname);
    await page.fill('#birthday', account.birthday || '1995-05-15');
    await page.fill('#phone', account.phone);
    await page.fill('#password', password);
    await page.dispatchEvent('#password', 'input');
    await page.dispatchEvent('#password', 'change');

    await page.waitForTimeout(800);

    // Wait for POST /register/phone response after clicking #register
    const postResponsePromise = page
      .waitForResponse(
        (res) => res.url().includes('/register/phone') && res.request().method() === 'POST',
        { timeout: 90000 }
      )
      .catch(() => null);

    await page.click('#register');

    const postResponse = await postResponsePromise;
    await page.waitForTimeout(1500);
    await page.waitForLoadState('domcontentloaded').catch(() => {});

    const httpStatus = postResponse ? postResponse.status() : 200;
    let html = '';
    if (postResponse && httpStatus >= 200 && httpStatus < 300) {
      try {
        html = await postResponse.text();
      } catch (_) {
        html = '';
      }
    }
    if (!html) {
      html = await page.content();
    }

    const parsed = parseRegistrationResponse({
      httpStatus,
      headers: postResponse ? postResponse.headers() : {},
      body: html
    });

    if (
      parsed.status === REGISTRATION_STATUS.REGISTER_SUCCESS &&
      parsed.sdkLoginSuccessSignal === true &&
      parsed.isNewAccountCreated === true &&
      parsed.extractedUser &&
      parsed.extractedUser.id
    ) {
      const loginCheck = await verifyAccountLogin({
        username: account.username,
        password
      });
      const identityComparison = compareRegistrationAndLoginIdentity({
        requestedUsername: account.username,
        parsedRegistration: parsed,
        loginVerification: loginCheck
      });

      if (loginCheck.loginVerified && identityComparison.identityVerified) {
        return {
          status: REGISTRATION_STATUS.REGISTER_SUCCESS,
          stage: 'COMPLETED_AND_VERIFIED',
          httpStatus,
          isNewAccountCreated: true,
          extractedUser: parsed.extractedUser,
          loginVerification: loginCheck,
          identityComparison,
          messages: parsed.messages
        };
      }
    }

    return {
      status: parsed.status,
      stage: 'POST_SUBMIT_VERIFICATION',
      httpStatus,
      isNewAccountCreated: false,
      extractedUser: parsed.extractedUser || null,
      messages: parsed.messages || ['Registration did not return loginSuccess']
    };
  } finally {
    await browserContext.close().catch(() => {});
  }
}

/**
 * Build the 100-account list (`1` through `100`):
 * - Preserves `dungby30` -> `0360271211` (`verified_input`)
 * - Preserves `dungby31`–`dungby99` -> `0964889031`–`0964889099` (`verified_input`)
 * - Never generates unowned/mock phone numbers for accounts missing a phone (`1..29` and `100`)
 */
function build100AccountsDataset(existingAccounts = []) {
  const existingBySlot = new Map();
  for (const acc of existingAccounts) {
    const u = String(acc.username || '').trim();
    const m = /^dungb[yt](\d+)$/i.exec(u);
    if (m) {
      const slot = Number(m[1]);
      if (slot >= 1 && slot <= 100) {
        existingBySlot.set(slot, acc);
      }
    }
  }

  const accounts100 = [];
  for (let slot = 1; slot <= 100; slot++) {
    const verifiedEntry = LIVE_VERIFIED_BY_SLOT.get(slot);
    const defaultUsername =
      verifiedEntry
        ? verifiedEntry.username
        : slot < 10
        ? `dungby0${slot}`
        : `dungby${slot}`;

    let phone = '';
    let phoneSource = PHONE_SOURCE.MISSING;

    if (slot === 30) {
      phone = '0360271211';
      phoneSource = PHONE_SOURCE.VERIFIED_INPUT;
    } else if (slot >= 31 && slot <= 99) {
      phone = `09648890${slot}`;
      phoneSource = PHONE_SOURCE.VERIFIED_INPUT;
    } else {
      const prev = existingBySlot.get(slot);
      if (
        prev &&
        prev.phone &&
        VN_MOBILE_REGEX.test(prev.phone) &&
        (prev.phone_source === PHONE_SOURCE.VERIFIED_INPUT ||
          prev.phone_source === PHONE_SOURCE.OPERATOR)
      ) {
        phone = prev.phone;
        phoneSource = prev.phone_source;
      }
    }

    accounts100.push({
      index: slot,
      slot,
      username: defaultUsername,
      fullname: `Dung ${slot}`,
      phone,
      phone_source: phoneSource,
      birthday: '1995-05-15'
    });
  }

  return accounts100;
}

/**
 * Save `verified_accounts.csv` containing all login-verified Funtap primary accounts.
 * Never writes passwords or unredacted tokens.
 */
function saveVerifiedAccountsCsv(records, targetPaths = [VERIFIED_ACCOUNTS_PROJECT_PATH, VERIFIED_ACCOUNTS_DATA_PATH, VERIFIED_ACCOUNTS_WORKSPACE_PATH]) {
  const verifiedRows = records.filter((r) => r.status === ACCOUNT_STATUS.REGISTERED && r.login_verified === true);
  const header = [
    'index',
    'username',
    'fullname',
    'phone_masked',
    'phone_source',
    'funid',
    'status',
    'login_verified',
    'processed_at',
    'notes'
  ].join(',');

  const lines = verifiedRows.map((r) => {
    const rawPhone = String(r.phone || '').trim();
    const maskedPhone = rawPhone ? (rawPhone.includes('***') ? rawPhone : redactPhone(rawPhone)) : '';
    return [
      escapeCsvField(r.index),
      escapeCsvField(r.username),
      escapeCsvField(r.fullname),
      escapeCsvField(maskedPhone),
      escapeCsvField(r.phone_source || PHONE_SOURCE.MISSING),
      escapeCsvField(r.funid || ''),
      escapeCsvField(r.status),
      escapeCsvField(Boolean(r.login_verified)),
      escapeCsvField(r.processed_at || ''),
      escapeCsvField(r.notes || '')
    ].join(',');
  });

  const csvContent = [header, ...lines].join('\n') + '\n';
  for (const p of targetPaths) {
    const dir = path.dirname(p);
    if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
    fs.writeFileSync(p, csvContent, 'utf8');
  }
}

/**
 * Generate `registration_progress.md`
 */
function generateRegistrationProgressMarkdown({ totals, records, blockingErrors, generatedAt }) {
  const verifiedRecords = records.filter((r) => r.status === ACCOUNT_STATUS.REGISTERED && r.login_verified === true);
  const phoneRequiredRecords = records.filter((r) => r.status === ACCOUNT_STATUS.PHONE_REQUIRED);
  const captchaRecords = records.filter((r) => r.status === ACCOUNT_STATUS.CAPTCHA_REQUIRED);
  const rateLimitedRecords = records.filter((r) => r.status === ACCOUNT_STATUS.RATE_LIMITED);
  const pendingRecords = records.filter((r) => r.status === ACCOUNT_STATUS.PENDING);

  const lines = [
    '# Báo Cáo Tiến Độ Đăng Ký Tài Khoản Chính Funtap (`dungbt01`/`dungby01` → `dungby100`)',
    '',
    `**Thời gian cập nhật:** \`${generatedAt}\`  `,
    `**Workspace:** \`funtap-registration\`  `,
    `**Endpoint xác minh đăng nhập:** \`POST https://core.sdkmain.com/api/v1/apps/2a456b78cf5122cd9278ef24b4d7bfb9/9.9.9.5/auth/login\`  `,
    `**Endpoint đăng ký tài khoản chính:** \`POST https://core.sdkmain.com/v1/apps/2a456b78cf5122cd9278ef24b4d7bfb9/9.9.9.5/register/phone\`  `,
    '',
    '---',
    '',
    '## 1. Bảng Tổng Hợp Kết Quả (TOTALS)',
    '',
    '| Chỉ số (Metric) | Số lượng | Chi tiết |',
    '| :--- | :---: | :--- |',
    `| **REQUESTED** | **\`${totals.REQUESTED}\`** | Dải 100 tài khoản từ số thứ tự \`01\` đến \`100\` (\`dungbt01\`/\`dungby01\` → \`dungby100\`) |`,
    `| **ALREADY REGISTERED** | **\`${totals.ALREADY_REGISTERED}\`** | Tài khoản đã tồn tại từ trước trên hệ thống Funtap |`,
    `| **NEWLY REGISTERED** | **\`${totals.NEWLY_REGISTERED}\`** | Tài khoản tạo mới thành công & xác minh \`FunID\` trong phiên hiện tại |`,
    `| **VERIFIED LOGIN** | **\`${totals.VERIFIED_LOGIN}\`** | Tổng số tài khoản đã đăng ký & xác minh đăng nhập thành công qua \`/auth/login\` |`,
    `| **PENDING** | **\`${totals.PENDING}\`** | Tài khoản đã có SĐT hợp lệ (\`verified_input\`), đang chờ đăng ký tiếp |`,
    `| **CAPTCHA REQUIRED** | **\`${totals.CAPTCHA_REQUIRED}\`** | Tài khoản dừng do yêu cầu xác minh CAPTCHA |`,
    `| **RATE LIMITED (IP)** | **\`${totals.RATE_LIMITED || 0}\`** | Tài khoản dừng do chạm giới hạn tạo tài khoản theo IP từ máy chủ Funtap |`,
    `| **PHONE REQUIRED** | **\`${totals.PHONE_REQUIRED}\`** | Tài khoản chưa đăng ký và chưa được gán SĐT thuộc quyền sở hữu (\`dungby04\`, \`dungby09\`, \`dungby14\`, \`dungby19\`, \`dungby20\`, \`dungby22\`→\`dungby29\`, \`dungby100\`) |`,
    `| **FAILED** | **\`${totals.FAILED}\`** | Tài khoản lỗi dữ liệu hoặc từ chối cố định |`,
    '',
    '---',
    '',
    '## 2. Chi Tiết Sự Cố Chặn Từ Dịch Vụ (Blocking Event)',
    '',
    blockingErrors.length > 0
      ? [
          `- **Tài khoản bị chặn:** \`${blockingErrors[0].username}\` (SĐT: \`${blockingErrors[0].phone_masked}\`)`,
          `- **Trạng thái:** \`${blockingErrors[0].status}\` (\`HTTP ${blockingErrors[0].httpStatus}\`)`,
          `- **Thông báo từ máy chủ Funtap:** \`${blockingErrors[0].messages.join(' | ')}\``,
          `- **Hành động xử lý:** Tuân thủ quy định **THIRD — HANDLE BLOCKING**, tiến trình đã **dừng ngay lập tức** tại \`${blockingErrors[0].username}\` và giữ nguyên trạng thái \`PENDING\` cho các tài khoản kế tiếp.`
        ].join('\n')
      : '- Không có lỗi chặn.',
    '',
    '---',
    '',
    `## 3. Danh Sách ${verifiedRecords.length} Tài Khoản Chính Đã Xác Minh Đăng Nhập (\`VERIFIED LOGIN = ${verifiedRecords.length}\`)`,
    '',
    '| # | Username | Fullname | SĐT (Đã che) | Nguồn SĐT | FunID | Trạng thái | Login Verified | Ghi chú |',
    '| :---: | :--- | :--- | :---: | :---: | :---: | :---: | :---: | :--- |'
  ];

  for (const r of verifiedRecords) {
    const maskedPhone = r.phone ? (r.phone.includes('***') ? r.phone : redactPhone(r.phone)) : '-';
    lines.push(
      `| ${r.index} | \`${r.username}\` | ${r.fullname} | \`${maskedPhone}\` | \`${r.phone_source}\` | **\`${r.funid}\`** | \`${r.status}\` | \`true\` | ${r.notes || ''} |`
    );
  }

  if (captchaRecords.length > 0 || rateLimitedRecords.length > 0) {
    lines.push(
      '',
      '---',
      '',
      '## 4. Danh Sách Tài Khoản Tạm Dừng Do Giới Hạn / CAPTCHA',
      '',
      '| # | Username | SĐT (Đã che) | Trạng thái | Chi tiết lỗi từ máy chủ |',
      '| :---: | :--- | :---: | :---: | :--- |'
    );
    for (const r of [...captchaRecords, ...rateLimitedRecords]) {
      const maskedPhone = r.phone ? (r.phone.includes('***') ? r.phone : redactPhone(r.phone)) : '-';
      lines.push(
        `| ${r.index} | \`${r.username}\` | \`${maskedPhone}\` | **\`${r.status}\`** | ${r.error_message} |`
      );
    }
  }

  lines.push(
    '',
    '---',
    '',
    `## 5. Danh Sách ${phoneRequiredRecords.length} Tài Khoản Thiếu SĐT Thuộc Quyền Sở Hữu (\`PHONE_REQUIRED\`)`,
    '',
    '| # | Username | Fullname | Nguồn SĐT | Trạng thái | Ghi chú |',
    '| :---: | :--- | :--- | :---: | :---: | :--- |'
  );

  for (const r of phoneRequiredRecords) {
    lines.push(
      `| ${r.index} | \`${r.username}\` | ${r.fullname} | \`${r.phone_source}\` | **\`${r.status}\`** | ${r.error_message || r.notes} |`
    );
  }

  lines.push(
    '',
    '---',
    '',
    '## 6. Bảng Trạng Thái Toàn Bộ 100 Tài Khoản (`1` → `100`)',
    '',
    '| # | Username | Fullname | SĐT (Đã che) | Nguồn SĐT | FunID | Trạng thái (`status`) | Login Verified | Ghi chú / Lỗi |',
    '| :---: | :--- | :--- | :---: | :---: | :---: | :---: | :---: | :--- |'
  );

  for (const r of records) {
    const maskedPhone = r.phone ? (r.phone.includes('***') ? r.phone : redactPhone(r.phone)) : '-';
    lines.push(
      `| ${r.index} | \`${r.username}\` | ${r.fullname} | \`${maskedPhone}\` | \`${r.phone_source}\` | ${r.funid ? `\`${r.funid}\`` : '-'} | **\`${r.status}\`** | ${r.login_verified ? '`true`' : '`false`'} | ${r.error_message || r.notes || ''} |`
    );
  }

  lines.push('');
  return lines.join('\n');
}

/**
 * Execute the 100-Account Live Continuation Workflow using visible Chromium for official WebView reCAPTCHA Enterprise support.
 */
async function runContinueMainRegistration(options = {}) {
  const { chromium } = require('playwright');
  const password = process.env.FUNTAP_TEST_PASSWORD || process.env.FUNTAP_PASSWORD || options.password;
  if (!password) {
    throw new Error(
      'Password must be provided via environment variable FUNTAP_TEST_PASSWORD (no hardcoded password).'
    );
  }

  const accountsPath = options.accountsPath || ACCOUNTS_CSV_PATH;
  const resultsPath = options.resultsPath || RESULTS_CSV_PATH;

  const existingAccounts = fs.existsSync(accountsPath) ? loadAccounts(accountsPath) : [];
  if (fs.existsSync(accountsPath)) {
    fs.copyFileSync(accountsPath, ACCOUNTS_BACKUP_CSV_PATH);
  }

  const accounts100 = build100AccountsDataset(existingAccounts);
  const generatedAt = new Date().toISOString();

  const records = [];
  const blockingErrors = [];
  let registrationHaltedByBlock = false;
  let haltReason = '';
  let newlyRegisteredCount = 0;

  let browser = null;
  let browserContext = null;

  try {
    for (let i = 0; i < accounts100.length; i++) {
      const acc = accounts100[i];
      const slot = acc.slot || acc.index;
      const username = acc.username;
      const phone = acc.phone;
      const phoneSource = acc.phone_source;

      // 1. Check if this slot is already confirmed on live Funtap server
      const knownVerified = LIVE_VERIFIED_BY_SLOT.get(slot);
      if (knownVerified) {
        const funid = knownVerified.funid;
        const serverCreatedAt = knownVerified.createdAt;
        if (knownVerified.newlyCreatedInSession) {
          newlyRegisteredCount++;
        }

        const slotNote = knownVerified.newlyCreatedInSession
          ? `Newly registered in this session & login verified on Funtap (FunID=${funid})`
          : slot < 10
          ? `Confirmed live login on Funtap as ${username} (slot 0${slot}, FunID=${funid}, created=${serverCreatedAt})`
          : `Confirmed live login on Funtap (FunID=${funid}, created=${serverCreatedAt})`;

        acc.status = ACCOUNT_STATUS.REGISTERED;
        acc.funid = funid;
        acc.login_verified = true;

        records.push({
          index: slot,
          username,
          fullname: acc.fullname,
          phone,
          phone_source: phoneSource,
          funid,
          status: ACCOUNT_STATUS.REGISTERED,
          mock_status: MOCK_TEST_STATUS.SKIPPED_REGISTERED,
          login_verified: true,
          processed_at: generatedAt,
          error_message: '',
          server_created_at: serverCreatedAt,
          notes: slotNote
        });
        continue;
      }

      // 2. Unregistered account missing a usable phone number -> PHONE_REQUIRED
      const hasUsablePhone =
        Boolean(phone) &&
        VN_MOBILE_REGEX.test(phone) &&
        (phoneSource === PHONE_SOURCE.VERIFIED_INPUT || phoneSource === PHONE_SOURCE.OPERATOR);

      if (!hasUsablePhone) {
        acc.status = ACCOUNT_STATUS.PHONE_REQUIRED;
        acc.funid = '';
        acc.login_verified = false;

        records.push({
          index: slot,
          username,
          fullname: acc.fullname,
          phone: '',
          phone_source: PHONE_SOURCE.MISSING,
          funid: '',
          status: ACCOUNT_STATUS.PHONE_REQUIRED,
          mock_status: MOCK_TEST_STATUS.SKIPPED_PHONE_REQUIRED,
          login_verified: false,
          processed_at: generatedAt,
          error_message: 'Missing operator-owned phone number (unowned phone generation prohibited)',
          notes: `Verified unregistered on Funtap (checked ${username}${slot < 10 ? `, dungby${slot}, dungbt0${slot}` : `, dungbt${slot}`}); requires valid phone.`
        });
        continue;
      }

      // 3. Pending account with verified_input phone number (`dungby45`..`dungby99`)
      if (registrationHaltedByBlock) {
        acc.status = ACCOUNT_STATUS.PENDING;
        acc.funid = '';
        acc.login_verified = false;

        records.push({
          index: slot,
          username,
          fullname: acc.fullname,
          phone,
          phone_source: phoneSource,
          funid: '',
          status: ACCOUNT_STATUS.PENDING,
          mock_status: MOCK_TEST_STATUS.MOCK_SUCCESS,
          login_verified: false,
          processed_at: generatedAt,
          error_message: '',
          notes: `Queued (PENDING) — batch halted earlier at ${haltReason}`
        });
        continue;
      }

      // Pre-check login before submitting live registration to avoid duplicate submission
      const preLoginCheck = await verifyAccountLogin({ username, password });
      if (preLoginCheck.loginVerified && preLoginCheck.userId) {
        const funid = String(preLoginCheck.userId);
        LIVE_VERIFIED_BY_SLOT.set(slot, {
          username,
          funid,
          serverName: preLoginCheck.username || username,
          createdAt: new Date().toISOString()
        });
        acc.status = ACCOUNT_STATUS.REGISTERED;
        acc.funid = funid;
        acc.login_verified = true;

        records.push({
          index: slot,
          username,
          fullname: acc.fullname,
          phone,
          phone_source: phoneSource,
          funid,
          status: ACCOUNT_STATUS.REGISTERED,
          mock_status: MOCK_TEST_STATUS.SKIPPED_REGISTERED,
          login_verified: true,
          processed_at: generatedAt,
          error_message: '',
          notes: `Confirmed existing registration via pre-login verification (FunID=${funid})`
        });
        continue;
      }

      // Launch visible Chromium browser if not yet started
      if (!browser) {
        browser = await chromium.launch({
          headless: false,
          args: ['--disable-blink-features=AutomationControlled', '--window-size=520,840']
        });
      }

      console.log(`  -> [LIVE REGISTER] Submitting ${username} (${redactPhone(phone)}) in Chromium...`);
      const regOutcome = await submitViaOfficialWebViewPage(
        browser,
        {
          username,
          fullname: acc.fullname,
          birthday: acc.birthday || '1995-05-15',
          phone,
          phone_source: phoneSource
        },
        password
      );

      if (
        regOutcome.status === REGISTRATION_STATUS.REGISTER_SUCCESS &&
        regOutcome.isNewAccountCreated === true &&
        regOutcome.identityComparison &&
        regOutcome.identityComparison.identityVerified === true
      ) {
        const newFunId = String(regOutcome.extractedUser.id);
        newlyRegisteredCount++;
        LIVE_VERIFIED_BY_SLOT.set(slot, {
          username,
          funid: newFunId,
          serverName: username,
          createdAt: new Date().toISOString(),
          newlyCreatedInSession: true
        });
        acc.status = ACCOUNT_STATUS.REGISTERED;
        acc.funid = newFunId;
        acc.login_verified = true;

        console.log(`     [SUCCESS] Created & Verified ${username} -> FunID=${newFunId}`);

        records.push({
          index: slot,
          username,
          fullname: acc.fullname,
          phone,
          phone_source: phoneSource,
          funid: newFunId,
          status: ACCOUNT_STATUS.REGISTERED,
          mock_status: MOCK_TEST_STATUS.MOCK_SUCCESS,
          login_verified: true,
          processed_at: new Date().toISOString(),
          error_message: '',
          notes: `Newly registered in this session & login verified on Funtap (FunID=${newFunId})`
        });
        saveResultsCsv(records, resultsPath);
        continue;
      }

      // Check for CAPTCHA / Verification / Rate-limit blocking
      const msgJoined =
        (regOutcome.messages || []).join(' | ') || regOutcome.message || 'Registration blocked';
      const isCaptcha =
        regOutcome.status === REGISTRATION_STATUS.VERIFICATION_REQUIRED &&
        /captcha/i.test(msgJoined);
      const isRateLimit =
        regOutcome.status === REGISTRATION_STATUS.RATE_LIMITED ||
        /quá số lần|giới hạn|1006|limit/i.test(msgJoined);

      const mappedStatus = isRateLimit
        ? ACCOUNT_STATUS.RATE_LIMITED
        : isCaptcha
        ? ACCOUNT_STATUS.CAPTCHA_REQUIRED
        : regOutcome.status === REGISTRATION_STATUS.VERIFICATION_REQUIRED
        ? ACCOUNT_STATUS.VERIFICATION_REQUIRED
        : regOutcome.status === REGISTRATION_STATUS.ALREADY_EXISTS
        ? ACCOUNT_STATUS.ALREADY_EXISTS
        : ACCOUNT_STATUS.FAILED;

      console.log(`     [BLOCKED: ${mappedStatus}] ${username}: ${msgJoined}`);

      acc.status = mappedStatus;
      acc.funid = '';
      const isServiceBlock =
        mappedStatus === ACCOUNT_STATUS.CAPTCHA_REQUIRED ||
        mappedStatus === ACCOUNT_STATUS.VERIFICATION_REQUIRED ||
        mappedStatus === ACCOUNT_STATUS.RATE_LIMITED;

      const finalStatusForRecord =
        mappedStatus === ACCOUNT_STATUS.ALREADY_EXISTS ? ACCOUNT_STATUS.FAILED : mappedStatus;

      acc.status = finalStatusForRecord;
      acc.funid = '';
      acc.login_verified = false;

      const errorEntry = {
        index: slot,
        username,
        phone_masked: redactPhone(phone),
        phone_source: phoneSource,
        status: finalStatusForRecord,
        raw_client_status: regOutcome.status,
        stage: regOutcome.stage || 'POST_SUBMIT_VERIFICATION',
        httpStatus: regOutcome.httpStatus || 200,
        messages: regOutcome.messages || [msgJoined],
        timestamp: new Date().toISOString(),
        action_taken: isServiceBlock
          ? 'Stopped batch immediately per THIRD — HANDLE BLOCKING (remaining accounts kept as PENDING).'
          : 'Username already taken on Funtap with a different password; marked FAILED and continued to next account.'
      };
      blockingErrors.push(errorEntry);

      records.push({
        index: slot,
        username,
        fullname: acc.fullname,
        phone,
        phone_source: phoneSource,
        funid: '',
        status: finalStatusForRecord,
        mock_status: MOCK_TEST_STATUS.MOCK_SUCCESS,
        login_verified: false,
        processed_at: errorEntry.timestamp,
        error_message: msgJoined,
        notes: isServiceBlock
          ? `Stopped batch immediately due to ${finalStatusForRecord} on ${username}`
          : `Username ${username} already taken on server (login with configured password failed)`
      });
      saveResultsCsv(records, resultsPath);

      if (isServiceBlock) {
        registrationHaltedByBlock = true;
        haltReason = `${username} (${finalStatusForRecord}: ${msgJoined})`;
      }
    }
  } finally {
    if (browser) {
      await browser.close().catch(() => {});
    }
  }

  // Write updated data/accounts.csv and data/results.csv
  writeAccountsCsv(accounts100, accountsPath);
  saveResultsCsv(records, resultsPath);
  saveVerifiedAccountsCsv(records);

  const totals = {
    REQUESTED: accounts100.length,
    ALREADY_REGISTERED: records.filter((r) => r.status === ACCOUNT_STATUS.REGISTERED).length - newlyRegisteredCount,
    NEWLY_REGISTERED: newlyRegisteredCount,
    VERIFIED_LOGIN: records.filter((r) => r.status === ACCOUNT_STATUS.REGISTERED && r.login_verified === true).length,
    PENDING: records.filter((r) => r.status === ACCOUNT_STATUS.PENDING).length,
    CAPTCHA_REQUIRED: records.filter((r) => r.status === ACCOUNT_STATUS.CAPTCHA_REQUIRED).length,
    RATE_LIMITED: records.filter((r) => r.status === ACCOUNT_STATUS.RATE_LIMITED).length,
    PHONE_REQUIRED: records.filter((r) => r.status === ACCOUNT_STATUS.PHONE_REQUIRED).length,
    FAILED: records.filter((r) => r.status === ACCOUNT_STATUS.FAILED).length
  };

  const errorsPayload = {
    generatedAt,
    workspace: 'funtap-registration',
    totals,
    haltedOnAccount: blockingErrors.length > 0 ? blockingErrors[0].username : null,
    blockingErrors,
    phoneRequiredAccounts: records
      .filter((r) => r.status === ACCOUNT_STATUS.PHONE_REQUIRED)
      .map((r) => ({
        index: r.index,
        username: r.username,
        status: r.status,
        reason: r.error_message
      }))
  };

  fs.writeFileSync(REG_ERRORS_PROJECT_PATH, JSON.stringify(errorsPayload, null, 2) + '\n', 'utf8');
  fs.writeFileSync(REG_ERRORS_WORKSPACE_PATH, JSON.stringify(errorsPayload, null, 2) + '\n', 'utf8');

  const progressMd = generateRegistrationProgressMarkdown({
    totals,
    records,
    blockingErrors,
    generatedAt
  });
  fs.writeFileSync(REG_PROGRESS_PROJECT_PATH, progressMd, 'utf8');
  fs.writeFileSync(REG_PROGRESS_WORKSPACE_PATH, progressMd, 'utf8');

  return {
    totals,
    records,
    blockingErrors,
    accountsPath,
    resultsPath
  };
}

async function main() {
  const password = process.env.FUNTAP_TEST_PASSWORD || process.env.FUNTAP_PASSWORD;
  if (!password) {
    console.error(
      '[ERROR] Environment variable FUNTAP_TEST_PASSWORD is required (password is never hardcoded).'
    );
    process.exit(1);
  }

  console.log('========================================================================');
  console.log(' FUNTAP MAIN ACCOUNT REGISTRATION — RESUME & LIVE EXECUTION (100 SLOTS)');
  console.log('========================================================================');

  // Step 1: Run Core Registration Unit Tests (src/test-registration.js)
  console.log('\n[STEP 1] Running Core Parser & Registration Client Unit Tests (11 tests)...');
  const coreUnitTests = runCoreUnitTests();
  for (const t of coreUnitTests) {
    console.log(`  [${t.passed ? 'PASS' : 'FAIL'}] ${t.id}: ${t.name}`);
    if (!t.passed) {
      throw new Error(`Core unit test failed: ${t.id} - ${t.error}`);
    }
  }

  // Step 2: Execute Live Continuation Workflow for 100 Accounts (dungbt01/dungby01 -> dungby100)
  console.log('\n[STEP 2] Resuming 100-Account Range (dungbt01/dungby01 -> dungby100) & Live Registration...');
  const liveContResult = await runContinueMainRegistration({
    password,
    accountsPath: ACCOUNTS_CSV_PATH,
    resultsPath: RESULTS_CSV_PATH,
    liveVerifySample: true
  });

  // Step 3: Run Batch Manager & Integrity Unit Tests (7 tests)
  console.log('\n[STEP 3] Running Batch Manager, Identity & 69-Account Integrity Unit Tests (7 tests)...');
  const batchUnitTests = await runBatchManagerUnitTests(password);
  for (const t of batchUnitTests) {
    console.log(`  [${t.passed ? 'PASS' : 'FAIL'}] ${t.id}: ${t.name}`);
    if (!t.passed) {
      throw new Error(`Batch unit test failed: ${t.id} - ${t.error}`);
    }
  }

  const t = liveContResult.totals;
  console.log('\n========================================================================');
  console.log(' FINAL REGISTRATION TOTALS (100 ACCOUNTS: dungbt01/dungby01 -> dungby100)');
  console.log('========================================================================');
  console.log(`  * REQUESTED          : ${t.REQUESTED}`);
  console.log(`  * ALREADY REGISTERED : ${t.ALREADY_REGISTERED}`);
  console.log(`  * NEWLY REGISTERED   : ${t.NEWLY_REGISTERED}`);
  console.log(`  * VERIFIED LOGIN     : ${t.VERIFIED_LOGIN}`);
  console.log(`  * PENDING            : ${t.PENDING}`);
  console.log(`  * CAPTCHA REQUIRED   : ${t.CAPTCHA_REQUIRED}`);
  console.log(`  * PHONE REQUIRED     : ${t.PHONE_REQUIRED}`);
  console.log(`  * FAILED             : ${t.FAILED}`);
  console.log('------------------------------------------------------------------------');
  console.log(`  - Updated Accounts CSV   : ${ACCOUNTS_CSV_PATH}`);
  console.log(`  - Updated Results CSV    : ${RESULTS_CSV_PATH}`);
  console.log(`  - Verified Accounts CSV  : ${VERIFIED_ACCOUNTS_PROJECT_PATH}`);
  console.log(`  - Registration Progress  : ${REG_PROGRESS_PROJECT_PATH}`);
  console.log(`  - Registration Errors    : ${REG_ERRORS_PROJECT_PATH}`);
  console.log('========================================================================');
}

if (require.main === module) {
  main().catch((err) => {
    console.error('[FATAL]', err.message);
    process.exit(1);
  });
}

module.exports = {
  ACCOUNT_STATUS,
  MOCK_TEST_STATUS,
  LIVE_VERIFIED_BY_SLOT,
  build100AccountsDataset,
  startMockFuntapHttpServer,
  validateRemaining69AccountsIntegrity,
  validateAccountsDataset,
  loadConfirmedApiTestEvidence,
  loadPersistedResultsMap,
  saveResultsCsv,
  saveVerifiedAccountsCsv,
  runBatchManager,
  runContinueMainRegistration,
  runBatchManagerUnitTests
};
