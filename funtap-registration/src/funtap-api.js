const crypto = require('crypto');

/**
 * Confirmed Funtap SDK constants & endpoints reconstructed from
 * Hắc Tây Du (vn.ftg.hactaydu v9.9.9.5 - classes2.dex & classes4.dex)
 */
const FUNTAP_CONFIG = {
  BASE_URL: 'https://core.sdkmain.com',
  APP_KEY: '2a456b78cf5122cd9278ef24b4d7bfb9',
  APP_VERSION: '9.9.9.5',
  SDK_VERSION: '6.1.2',
  PACKAGE_NAME: 'vn.ftg.hactaydu',
  PROJECT_ID: 1633,
  PACKAGE_CODE: 'ft105',
  DEFAULT_DEVICE: {
    device_name: 'Pixel 6',
    device_os: 'Android 12',
    device_resolution: '1080x2400',
    device_network: 'wifi',
    appsflyer_id: '1729500000000-1234567890123456789',
    adjust_id: '',
    advertising_id: '00000000-0000-0000-0000-000000000000',
    device_id: crypto.createHash('sha1').update('vn.ftg.hactaydu.pixel6.device').digest('hex')
  }
};

/**
 * Classification statuses required by verification specification
 */
const REGISTRATION_STATUS = {
  REGISTER_SUCCESS: 'REGISTER_SUCCESS',
  ALREADY_EXISTS: 'ALREADY_EXISTS',
  REGISTER_FAILED: 'REGISTER_FAILED',
  VERIFICATION_REQUIRED: 'VERIFICATION_REQUIRED',
  RATE_LIMITED: 'RATE_LIMITED',
  UNKNOWN: 'UNKNOWN',
  READY_FOR_MANUAL_TEST: 'READY_FOR_MANUAL_TEST'
};

/**
 * Build WebView Registration Entry URL (ApiUtils.getUrlWvRegister - ApiUtils.java:67-78)
 * Note: This endpoint is a WebView GET entry that returns HTTP 302 -> /register/phone
 */
function buildRegisterEntryUrl(
  device = FUNTAP_CONFIG.DEFAULT_DEVICE,
  baseUrl = FUNTAP_CONFIG.BASE_URL
) {
  const url = new URL(
    `/v1/apps/${FUNTAP_CONFIG.APP_KEY}/${FUNTAP_CONFIG.APP_VERSION}/register/email`,
    baseUrl
  );
  url.searchParams.set('sdk_version', FUNTAP_CONFIG.SDK_VERSION);
  url.searchParams.set('device_network', device.device_network);
  url.searchParams.set('appsflyer_id', device.appsflyer_id);
  url.searchParams.set('adjust_id', device.adjust_id || '');
  url.searchParams.set('advertising_id', device.advertising_id);
  url.searchParams.set('device_os', device.device_os);
  url.searchParams.set('device_name', device.device_name);
  return url.toString();
}

/**
 * Build Fallback Phone Registration Form Action URL
 * (/v1/apps/{appKey}/{appVersion}/register/phone?...&checkScreen=register)
 */
function buildRegisterPhoneActionUrl(
  device = FUNTAP_CONFIG.DEFAULT_DEVICE,
  baseUrl = FUNTAP_CONFIG.BASE_URL
) {
  const url = new URL(
    `/v1/apps/${FUNTAP_CONFIG.APP_KEY}/${FUNTAP_CONFIG.APP_VERSION}/register/phone`,
    baseUrl
  );
  url.searchParams.set('device_os', device.device_os);
  url.searchParams.set('device_name', device.device_name);
  url.searchParams.set('device_resolution', device.device_resolution);
  url.searchParams.set('device_network', device.device_network);
  url.searchParams.set('sdk_version', FUNTAP_CONFIG.SDK_VERSION);
  url.searchParams.set('appsflyer_id', device.appsflyer_id);
  url.searchParams.set('advertising_id', device.advertising_id);
  url.searchParams.set('checkScreen', 'register');
  return url.toString();
}

/**
 * Build REST API URLs (ConstantApi.java)
 * Distinct from WebView registration endpoints:
 * - auth/login: Native FunID username/email/phone + password login
 * - auth/playNow: Native Guest account creation/login (disabled on prod: play_now=0)
 * - configs/auth: Auth configuration endpoint
 */
function buildAuthConfigUrl(baseUrl = FUNTAP_CONFIG.BASE_URL) {
  return `${baseUrl.replace(/\/$/, '')}/api/v1/apps/${FUNTAP_CONFIG.APP_KEY}/${FUNTAP_CONFIG.APP_VERSION}/configs/auth`;
}

function buildLoginEmailUrl(baseUrl = FUNTAP_CONFIG.BASE_URL) {
  return `${baseUrl.replace(/\/$/, '')}/api/v1/apps/${FUNTAP_CONFIG.APP_KEY}/${FUNTAP_CONFIG.APP_VERSION}/auth/login`;
}

function buildPlayNowUrl(baseUrl = FUNTAP_CONFIG.BASE_URL) {
  return `${baseUrl.replace(/\/$/, '')}/api/v1/apps/${FUNTAP_CONFIG.APP_KEY}/${FUNTAP_CONFIG.APP_VERSION}/auth/playNow`;
}

/**
 * Build WebView extra headers (BaseDialogWebFragment.loadUrlWithLibraryHeaders - lines 285-309)
 */
function buildWebViewHeaders(device = FUNTAP_CONFIG.DEFAULT_DEVICE, accessToken = '') {
  const headers = {
    'User-Agent':
      'Mozilla/5.0 (Linux; Android 12; Pixel 6 Build/SP1A.210812.015; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/114.0.5735.196 Mobile Safari/537.36',
    Accept:
      'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
    'Accept-Language': 'vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7',
    device_name: device.device_name,
    device_os: device.device_os,
    device_resolution: device.device_resolution,
    sdk_version: FUNTAP_CONFIG.SDK_VERSION,
    device_network: device.device_network,
    appsflyer_id: device.appsflyer_id,
    advertising_id: device.advertising_id,
    Language: 'vi-VN',
    'X-Android-Notch': 'false'
  };
  if (accessToken) {
    headers.access_token = accessToken;
    headers.Authorization = `Bearer ${accessToken}`;
  }
  return headers;
}

/**
 * Build Retrofit REST Interceptor headers (RetrofitClient.java:59-92)
 */
function buildRestHeaders(accessToken = '') {
  const headers = {
    Accept: 'application/json',
    'X-Request': FUNTAP_CONFIG.APP_KEY,
    'app-Version': FUNTAP_CONFIG.APP_VERSION,
    'sdk-Version': FUNTAP_CONFIG.SDK_VERSION,
    Language: 'vi-VN',
    'X-Android-Notch': 'false'
  };
  if (accessToken) {
    headers.Authorization = `Bearer ${accessToken}`;
  }
  return headers;
}

/**
 * Redact sensitive strings (passwords, tokens, cookies, phone numbers)
 */
function redactSecret(value, showEdges = false) {
  if (value === undefined || value === null || value === '') {
    return '';
  }
  const str = String(value);
  if (!showEdges || str.length < 8) {
    return '[REDACTED]';
  }
  return `${str.slice(0, 3)}***${str.slice(-3)}`;
}

function redactPhone(phone) {
  if (!phone) return '';
  const str = String(phone).trim();
  if (str.length < 7) return '[REDACTED_PHONE]';
  return `${str.slice(0, 3)}***${str.slice(-3)}`;
}

/**
 * Deep-clone and redact sensitive keys in headers/payloads before logging or saving to disk
 */
function sanitizeForLog(input) {
  if (input === null || input === undefined) return input;
  if (typeof input !== 'object') return input;
  if (Array.isArray(input)) return input.map(sanitizeForLog);

  const sensitiveKeyPattern = /password|_token|access_token|authorization|cookie|set-cookie|xsrf/i;
  const phoneKeyPattern = /^phone$/i;

  const out = {};
  for (const [k, v] of Object.entries(input)) {
    if (sensitiveKeyPattern.test(k)) {
      if (typeof v === 'string' && /^(_token|access_token)$/i.test(k)) {
        out[k] = redactSecret(v, true);
      } else {
        out[k] = '[REDACTED]';
      }
    } else if (phoneKeyPattern.test(k)) {
      out[k] = redactPhone(v);
    } else if (typeof v === 'object' && v !== null) {
      out[k] = sanitizeForLog(v);
    } else {
      out[k] = v;
    }
  }
  return out;
}

module.exports = {
  FUNTAP_CONFIG,
  REGISTRATION_STATUS,
  buildRegisterEntryUrl,
  buildRegisterPhoneActionUrl,
  buildAuthConfigUrl,
  buildLoginEmailUrl,
  buildPlayNowUrl,
  buildWebViewHeaders,
  buildRestHeaders,
  redactSecret,
  redactPhone,
  sanitizeForLog
};
