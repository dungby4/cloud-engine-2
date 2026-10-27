const { REGISTRATION_STATUS, redactSecret } = require('./funtap-api');

/**
 * Strip HTML tags and normalize whitespace
 */
function stripHtmlTags(str) {
  if (!str) return '';
  return String(str)
    .replace(/<script[\s\S]*?<\/script>/gi, ' ')
    .replace(/<style[\s\S]*?<\/style>/gi, ' ')
    .replace(/<[^>]+>/g, ' ')
    .replace(/&nbsp;/gi, ' ')
    .replace(/&amp;/gi, '&')
    .replace(/&quot;/gi, '"')
    .replace(/&#039;/gi, "'")
    .replace(/\s+/g, ' ')
    .trim();
}

/**
 * Extract inline validation error messages from Funtap HTML response
 * Matches:
 * - elements with class "error-input-<field>" (confirmed in register-base.js:32)
 * - elements with class "invalid-feedback", "text-danger", "alert-danger", "error-message"
 * - inputs with class "is-invalid" (confirmed in register-base.js:2)
 */
function extractHtmlErrors(html) {
  if (typeof html !== 'string') {
    return { errorMessages: [], invalidFields: [], hasRecaptchaError: false };
  }

  const errorMessages = [];
  const invalidFields = [];

  // Check inputs marked with .is-invalid
  const inputTags = html.match(/<input\b[^>]*class=["'][^"']*is-invalid[^"']*["'][^>]*>/gi) || [];
  for (const tag of inputTags) {
    const nameMatch = tag.match(/\b(?:name|id)\s*=\s*["']([^"']+)["']/i);
    if (nameMatch && nameMatch[1]) {
      invalidFields.push(nameMatch[1]);
    }
  }

  // Check error-input-* blocks and alert/danger blocks
  const errorBlockRegex =
    /<([a-z0-9]+)\b[^>]*class=["'][^"']*(?:error-input-[a-z0-9_-]+|invalid-feedback|alert-danger|text-danger|txt-error|error-message)[^"']*["'][^>]*>([\s\S]*?)<\/\1>/gi;
  let match;
  let hasRecaptchaError = false;

  while ((match = errorBlockRegex.exec(html)) !== null) {
    const fullTag = match[0];
    const innerText = stripHtmlTags(match[2]);
    if (/error-input-g-recaptcha-response/i.test(fullTag)) {
      hasRecaptchaError = true;
    }
    const fieldMatch = fullTag.match(/error-input-([a-z0-9_-]+)/i);
    if (fieldMatch && fieldMatch[1] && !invalidFields.includes(fieldMatch[1])) {
      invalidFields.push(fieldMatch[1]);
    }
    if (innerText && !errorMessages.includes(innerText)) {
      errorMessages.push(innerText);
    }
  }

  return {
    errorMessages,
    invalidFields,
    hasRecaptchaError
  };
}

/**
 * Extract JsRegister bridge call from HTML if registration succeeded on the WebView:
 * e.g. appSDKexecute('loginSuccess', {...}) or window.JsHandler.mobAppSDKexecute('loginSuccess', ...)
 */
function extractJsBridgeLoginSuccess(html) {
  if (typeof html !== 'string') return null;

  const callRegex =
    /(?:appSDKexecute|mobAppSDKexecute)\s*\(\s*['"]loginSuccess['"]\s*,\s*([\s\S]*?)\)\s*(?:;|\s*<\/script>|\s*$|\r|\n)/i;
  const match = html.match(callRegex);
  if (!match || !match[1]) return null;

  let rawArg = match[1].trim();
  const stringifyMatch = rawArg.match(/^JSON\.stringify\(([\s\S]*)\)$/i);
  if (stringifyMatch) {
    rawArg = stringifyMatch[1].trim();
  }
  if (
    (rawArg.startsWith("'") && rawArg.endsWith("'")) ||
    (rawArg.startsWith('"') && rawArg.endsWith('"'))
  ) {
    try {
      rawArg = JSON.parse(rawArg);
    } catch (_) {
      rawArg = rawArg.slice(1, -1).replace(/\\"/g, '"').replace(/\\'/g, "'");
    }
  }

  if (typeof rawArg === 'object' && rawArg !== null) {
    return rawArg;
  }

  try {
    return JSON.parse(rawArg);
  } catch (_) {
    return { rawUnparsed: rawArg.slice(0, 200) };
  }
}

/**
 * Check if an error message or error code indicates the account/username/phone already exists
 */
function isAlreadyExistsError(messages = [], errorCode = null) {
  if (Number(errorCode) === 2001) return true;
  const duplicateRegex =
    /đã tồn tại|2001|already exists|đã được sử dụng|đã đăng ký|tài khoản đã có|số điện thoại đã được đăng ký/i;
  return messages.some((m) => duplicateRegex.test(String(m || '')));
}

/**
 * Parse and classify HTTP response from Funtap Registration endpoint.
 *
 * STRICT RULES:
 * 1. HTTP 200 or 302 redirect alone is NEVER classified as REGISTER_SUCCESS.
 * 2. Login success alone is NEVER evaluated here; this parser strictly inspects the registration POST response.
 * 3. Only flags `sdkLoginSuccessSignal: true` and `isNewAccountCreated: true` when the registration response
 *    contains an explicit new-account creation payload (`loginSuccess` JS bridge or JSON UserObj with `new_user !== false`).
 * 4. If the server reports that the username or phone already exists (e.g., Error 2001 / "đã tồn tại" / "đã được sử dụng"
 *    or `new_user === false`), classifies as `ALREADY_EXISTS` (never `REGISTER_SUCCESS`).
 * 5. Never stores raw access tokens in `extractedUser` (only `redactedAccessToken`).
 */
function parseRegistrationResponse({ httpStatus, headers = {}, body, redirectChain = [] }) {
  const contentType = String(headers['content-type'] || headers['Content-Type'] || '').toLowerCase();
  const responseType =
    contentType.includes('application/json') || (typeof body === 'object' && body !== null)
      ? 'json'
      : 'html';

  // 1. Check HTTP-level rate limit
  if (httpStatus === 429) {
    return {
      status: REGISTRATION_STATUS.RATE_LIMITED,
      httpStatus,
      responseType,
      sdkLoginSuccessSignal: false,
      isNewAccountCreated: false,
      requiresOtp: false,
      requiresCaptcha: false,
      errorCode: 429,
      messages: ['HTTP 429 Too Many Requests (Rate Limited)'],
      invalidFields: [],
      extractedUser: null
    };
  }

  // 2. Handle JSON response
  if (responseType === 'json') {
    const jsonObj =
      typeof body === 'string'
        ? (() => {
            try {
              return JSON.parse(body);
            } catch (_) {
              return {};
            }
          })()
        : body || {};

    const errorCode =
      jsonObj.error_code !== undefined
        ? Number(jsonObj.error_code)
        : jsonObj.status !== undefined && typeof jsonObj.status === 'number'
        ? Number(jsonObj.status)
        : null;
    const msg = jsonObj.message || jsonObj.msg || null;

    if (errorCode === 1006 || /limit|quá số lần|giới hạn/i.test(String(msg))) {
      return {
        status: REGISTRATION_STATUS.RATE_LIMITED,
        httpStatus,
        responseType,
        sdkLoginSuccessSignal: false,
        isNewAccountCreated: false,
        requiresOtp: false,
        requiresCaptcha: false,
        errorCode: errorCode || 1006,
        messages: [msg || 'ErrorCode 1006: LIMIT_CREATE_USER'],
        invalidFields: [],
        extractedUser: null
      };
    }

    if (jsonObj.need_verify === true || (jsonObj.data && jsonObj.data.need_verify === true)) {
      return {
        status: REGISTRATION_STATUS.VERIFICATION_REQUIRED,
        httpStatus,
        responseType,
        sdkLoginSuccessSignal: false,
        isNewAccountCreated: false,
        requiresOtp: true,
        requiresCaptcha: false,
        errorCode,
        messages: [msg || 'Server requires additional user verification (need_verify=true)'],
        invalidFields: [],
        extractedUser: null
      };
    }

    if (isAlreadyExistsError([msg], errorCode)) {
      return {
        status: REGISTRATION_STATUS.ALREADY_EXISTS,
        httpStatus,
        responseType,
        sdkLoginSuccessSignal: false,
        isNewAccountCreated: false,
        requiresOtp: false,
        requiresCaptcha: false,
        errorCode: errorCode || 2001,
        messages: [msg || 'Account or phone number already exists (2001)'],
        invalidFields: jsonObj.errors ? Object.keys(jsonObj.errors) : [],
        extractedUser: null
      };
    }

    if (jsonObj.access_token && jsonObj.data && jsonObj.data.id) {
      // Check if payload explicitly indicates an existing account rather than a newly created one
      if (jsonObj.data.new_user === false || jsonObj.is_register === 0) {
        return {
          status: REGISTRATION_STATUS.ALREADY_EXISTS,
          httpStatus,
          responseType,
          sdkLoginSuccessSignal: false,
          isNewAccountCreated: false,
          requiresOtp: false,
          requiresCaptcha: false,
          errorCode: 2001,
          messages: ['Server returned existing account (new_user=false); classified as ALREADY_EXISTS'],
          invalidFields: [],
          extractedUser: {
            id: String(jsonObj.data.id),
            username:
              jsonObj.data.account && jsonObj.data.account.username
                ? String(jsonObj.data.account.username).trim()
                : jsonObj.data.username
                ? String(jsonObj.data.username).trim()
                : jsonObj.data.name
                ? String(jsonObj.data.name).trim()
                : null,
            newUser: false,
            loginType: 'Email',
            loginOrRegister: 0,
            redactedAccessToken: redactSecret(jsonObj.access_token, true)
          }
        };
      }

      return {
        status: REGISTRATION_STATUS.REGISTER_SUCCESS,
        httpStatus,
        responseType,
        sdkLoginSuccessSignal: true,
        isNewAccountCreated: true,
        requiresOtp: false,
        requiresCaptcha: false,
        errorCode: errorCode ?? 200,
        messages: [msg || 'Server confirmed new account creation (access_token and UserObj)'],
        invalidFields: [],
        extractedUser: {
          id: String(jsonObj.data.id),
          username:
            jsonObj.data.account && jsonObj.data.account.username
              ? String(jsonObj.data.account.username).trim()
              : jsonObj.data.username
              ? String(jsonObj.data.username).trim()
              : jsonObj.data.name
              ? String(jsonObj.data.name).trim()
              : null,
          newUser: true,
          loginType: 'Email',
          loginOrRegister: 1,
          redactedAccessToken: redactSecret(jsonObj.access_token, true)
        }
      };
    }

    if (
      httpStatus >= 400 ||
      (errorCode !== null && errorCode !== 200 && errorCode !== 0) ||
      jsonObj.status === 'error' ||
      jsonObj.errors
    ) {
      const errList = [];
      if (msg) errList.push(msg);
      if (jsonObj.errors && typeof jsonObj.errors === 'object') {
        for (const [field, fieldErrs] of Object.entries(jsonObj.errors)) {
          errList.push(`${field}: ${Array.isArray(fieldErrs) ? fieldErrs.join(', ') : fieldErrs}`);
        }
      }

      if (isAlreadyExistsError(errList, errorCode)) {
        return {
          status: REGISTRATION_STATUS.ALREADY_EXISTS,
          httpStatus,
          responseType,
          sdkLoginSuccessSignal: false,
          isNewAccountCreated: false,
          requiresOtp: false,
          requiresCaptcha: false,
          errorCode: errorCode || 2001,
          messages: errList,
          invalidFields: jsonObj.errors ? Object.keys(jsonObj.errors) : [],
          extractedUser: null
        };
      }

      return {
        status: REGISTRATION_STATUS.REGISTER_FAILED,
        httpStatus,
        responseType,
        sdkLoginSuccessSignal: false,
        isNewAccountCreated: false,
        requiresOtp: false,
        requiresCaptcha: false,
        errorCode,
        messages: errList.length > 0 ? errList : [`HTTP ${httpStatus} JSON Error`],
        invalidFields: jsonObj.errors ? Object.keys(jsonObj.errors) : [],
        extractedUser: null
      };
    }

    return {
      status: REGISTRATION_STATUS.UNKNOWN,
      httpStatus,
      responseType,
      sdkLoginSuccessSignal: false,
      isNewAccountCreated: false,
      requiresOtp: false,
      requiresCaptcha: false,
      errorCode,
      messages: [msg || 'Unrecognized JSON response structure'],
      invalidFields: [],
      extractedUser: null
    };
  }

  // 3. Handle HTML response
  const html = typeof body === 'string' ? body : String(body || '');

  // 3a. Check for JsRegister loginSuccess bridge call in HTML script
  const bridgePayload = extractJsBridgeLoginSuccess(html);
  if (bridgePayload && bridgePayload.access_token && bridgePayload.data && bridgePayload.data.id) {
    if (bridgePayload.data.new_user === false || bridgePayload.is_register === 0) {
      return {
        status: REGISTRATION_STATUS.ALREADY_EXISTS,
        httpStatus,
        responseType,
        sdkLoginSuccessSignal: false,
        isNewAccountCreated: false,
        requiresOtp: false,
        requiresCaptcha: false,
        errorCode: 2001,
        messages: ['JS Bridge returned existing user (new_user=false); classified as ALREADY_EXISTS'],
        invalidFields: [],
        extractedUser: {
          id: String(bridgePayload.data.id),
          username:
            bridgePayload.data.account && bridgePayload.data.account.username
              ? String(bridgePayload.data.account.username).trim()
              : bridgePayload.data.username
              ? String(bridgePayload.data.username).trim()
              : bridgePayload.data.name
              ? String(bridgePayload.data.name).trim()
              : null,
          newUser: false,
          loginType: 'Email',
          loginOrRegister: 0,
          redactedAccessToken: redactSecret(bridgePayload.access_token, true)
        }
      };
    }

    return {
      status: REGISTRATION_STATUS.REGISTER_SUCCESS,
      httpStatus,
      responseType,
      sdkLoginSuccessSignal: true,
      isNewAccountCreated: true,
      requiresOtp: false,
      requiresCaptcha: false,
      errorCode: 200,
      messages: ['Confirmed window.JsHandler.mobAppSDKexecute("loginSuccess", params) in response'],
      invalidFields: [],
      extractedUser: {
        id: String(bridgePayload.data.id),
        username:
          bridgePayload.data.account && bridgePayload.data.account.username
            ? String(bridgePayload.data.account.username).trim()
            : bridgePayload.data.username
            ? String(bridgePayload.data.username).trim()
            : bridgePayload.data.name
            ? String(bridgePayload.data.name).trim()
            : null,
        newUser: true,
        phoneStatus: bridgePayload.data.account ? bridgePayload.data.account.phone_status : null,
        needVerify: Boolean(bridgePayload.data.need_verify),
        loginType: 'Email',
        loginOrRegister: 1,
        redactedAccessToken: redactSecret(bridgePayload.access_token, true)
      }
    };
  }

  // 3b. Extract HTML errors, OTP inputs, and CAPTCHA widgets
  const { errorMessages, invalidFields, hasRecaptchaError } = extractHtmlErrors(html);

  const hasOtpInput =
    /<input\b[^>]*(?:id|name)\s*=\s*["']otp["'][^>]*>/i.test(html) ||
    /nhập mã xác thực|nhập mã otp|mã xác minh đã được gửi/i.test(html);

  const hasCaptchaWidget =
    hasRecaptchaError ||
    /class=["'][^"']*g-recaptcha[^"']*["']/i.test(html) ||
    /google\.com\/recaptcha/i.test(html);

  const isRateLimitedText =
    /1006|limit_create_user|vượt quá giới hạn|quá nhiều lần|tạm thời chặn|too many attempts/i.test(
      html
    );

  if (isRateLimitedText) {
    return {
      status: REGISTRATION_STATUS.RATE_LIMITED,
      httpStatus,
      responseType,
      sdkLoginSuccessSignal: false,
      isNewAccountCreated: false,
      requiresOtp: false,
      requiresCaptcha: hasCaptchaWidget,
      errorCode: 1006,
      messages:
        errorMessages.length > 0
          ? errorMessages
          : ['Server rate-limited account creation (ErrorCode 1006 / LIMIT_CREATE_USER)'],
      invalidFields,
      extractedUser: null
    };
  }

  if (hasOtpInput || hasCaptchaWidget) {
    const reasons = [];
    if (hasOtpInput) reasons.push('SMS OTP verification required (input#otp detected)');
    if (hasCaptchaWidget) reasons.push('CAPTCHA verification required (reCAPTCHA detected)');
    reasons.push(...errorMessages);

    return {
      status: REGISTRATION_STATUS.VERIFICATION_REQUIRED,
      httpStatus,
      responseType,
      sdkLoginSuccessSignal: false,
      isNewAccountCreated: false,
      requiresOtp: hasOtpInput,
      requiresCaptcha: hasCaptchaWidget,
      errorCode: null,
      messages: reasons,
      invalidFields,
      extractedUser: null
    };
  }

  // 3c. Check if HTML validation error indicates account/username/phone already exists
  if (isAlreadyExistsError(errorMessages)) {
    return {
      status: REGISTRATION_STATUS.ALREADY_EXISTS,
      httpStatus,
      responseType,
      sdkLoginSuccessSignal: false,
      isNewAccountCreated: false,
      requiresOtp: false,
      requiresCaptcha: false,
      errorCode: 2001,
      messages: errorMessages,
      invalidFields,
      extractedUser: null
    };
  }

  if (errorMessages.length > 0 || invalidFields.length > 0 || httpStatus >= 400) {
    return {
      status: REGISTRATION_STATUS.REGISTER_FAILED,
      httpStatus,
      responseType,
      sdkLoginSuccessSignal: false,
      isNewAccountCreated: false,
      requiresOtp: false,
      requiresCaptcha: false,
      errorCode: httpStatus >= 400 ? httpStatus : null,
      messages:
        errorMessages.length > 0
          ? errorMessages
          : [`Form validation failed on fields: ${invalidFields.join(', ') || `HTTP ${httpStatus}`}`],
      invalidFields,
      extractedUser: null
    };
  }

  // 3d. HTTP 200 or 302 returning the registration form itself without loginSuccess or error
  return {
    status: REGISTRATION_STATUS.UNKNOWN,
    httpStatus,
    responseType,
    sdkLoginSuccessSignal: false,
    isNewAccountCreated: false,
    requiresOtp: false,
    requiresCaptcha: false,
    errorCode: null,
    messages: [
      'HTTP 200/302 returned HTML without loginSuccess signal, OTP prompt, or error message (never treated as REGISTER_SUCCESS)'
    ],
    invalidFields: [],
    extractedUser: null,
    redirectCount: redirectChain.length
  };
}

module.exports = {
  parseRegistrationResponse,
  extractHtmlErrors,
  extractJsBridgeLoginSuccess,
  isAlreadyExistsError,
  stripHtmlTags
};
