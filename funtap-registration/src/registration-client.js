const {
  FUNTAP_CONFIG,
  REGISTRATION_STATUS,
  buildRegisterEntryUrl,
  buildRegisterPhoneActionUrl,
  buildAuthConfigUrl,
  buildWebViewHeaders,
  buildRestHeaders,
  sanitizeForLog
} = require('./funtap-api');
const { SessionManager } = require('./session-manager');
const {detectVerification} = require('../../src/verification');
const { parseCsrfAndFormHtml } = require('./csrf-parser');
const { parseRegistrationResponse } = require('./response-parser');
const { verifyAccountLogin } = require('./verify-login');

// Confirmed Vietnamese mobile number pattern (10 digits, starting with 0)
const VN_MOBILE_REGEX = /^(03|05|07|08|09)[0-9]{8}$/;

/**
 * Validate registration fields locally before sending any network POST request
 * Confirmed rules from /register/phone HTML attributes & StringUtils.java:
 * - username: 3..32 chars, alphanumeric/underscore/dot
 * - fullname: 2..100 chars
 * - birthday: YYYY-MM-DD
 * - phone: 10-digit VN mobile number (maxlength=11 on form)
 * - password: 8..32 chars (confirmed on /register/phone placeholder "Mật khẩu (dài 8-32 ký tự) *")
 */
function validateRegistrationInput(input = {}) {
  const errors = [];
  const username = String(input.username || '').trim();
  const fullname = String(input.fullname || '').trim();
  const birthday = String(input.birthday || '').trim();
  const phone = String(input.phone || '').trim();
  const password = String(input.password || '');

  if (username.length < 3 || username.length > 32) {
    errors.push('username must be between 3 and 32 characters');
  } else if (!/^[a-zA-Z0-9._]+$/.test(username)) {
    errors.push('username may only contain letters, digits, dots, or underscores');
  }

  if (fullname.length < 2 || fullname.length > 100) {
    errors.push('fullname must be between 2 and 100 characters');
  }

  if (!/^\d{4}-\d{2}-\d{2}$/.test(birthday)) {
    errors.push('birthday must match YYYY-MM-DD format');
  }

  if (!VN_MOBILE_REGEX.test(phone)) {
    errors.push('phone must be a valid 10-digit Vietnamese mobile number (03/05/07/08/09xxxxxxxx)');
  }

  if (password.length < 8 || password.length > 32) {
    errors.push('password must be between 8 and 32 characters for in-game /register/phone');
  }

  return {
    valid: errors.length === 0,
    errors
  };
}

/**
 * Cross-check (`đối chiếu`) username and FunID between:
 * 1. The requested account (`account.username`)
 * 2. The registration response (`parsed.extractedUser` from `/register/phone`)
 * 3. The re-login verification response (`loginCheck` from `/api/v1/apps/.../auth/login`)
 */
function compareRegistrationAndLoginIdentity({
  requestedUsername,
  parsedRegistration,
  loginVerification
}) {
  const reqUser = String(requestedUsername || '').trim();
  const extractedUser = parsedRegistration && parsedRegistration.extractedUser ? parsedRegistration.extractedUser : null;

  const regFunId = extractedUser && extractedUser.id ? String(extractedUser.id).trim() : null;
  const regUsername = extractedUser && extractedUser.username ? String(extractedUser.username).trim() : null;

  const loginFunId =
    loginVerification && loginVerification.userId ? String(loginVerification.userId).trim() : null;
  const loginUsername =
    loginVerification && loginVerification.username ? String(loginVerification.username).trim() : null;

  const hasNewAccountEvidence = Boolean(
    parsedRegistration &&
      parsedRegistration.status === REGISTRATION_STATUS.REGISTER_SUCCESS &&
      parsedRegistration.sdkLoginSuccessSignal === true &&
      parsedRegistration.isNewAccountCreated === true &&
      regFunId
  );

  const funIdMatched = Boolean(regFunId && loginFunId && regFunId === loginFunId);

  const regUsernameMatchesRequest = Boolean(
    reqUser && regUsername && regUsername.toLowerCase() === reqUser.toLowerCase()
  );
  const loginUsernameMatchesRequest = Boolean(
    reqUser && loginUsername && loginUsername.toLowerCase() === reqUser.toLowerCase()
  );
  const regAndLoginUsernameMatch = Boolean(
    regUsername && loginUsername && regUsername.toLowerCase() === loginUsername.toLowerCase()
  );

  const usernameMatched = Boolean(
    regUsernameMatchesRequest && loginUsernameMatchesRequest && regAndLoginUsernameMatch
  );

  const mismatchReasons = [];
  if (!hasNewAccountEvidence) {
    mismatchReasons.push('Missing new-account creation evidence from registration response');
  }
  if (!loginVerification || loginVerification.loginVerified !== true) {
    mismatchReasons.push('Re-login verification did not succeed');
  }
  if (!funIdMatched) {
    mismatchReasons.push(
      `FunID mismatch between registration (${regFunId || 'null'}) and login (${loginFunId || 'null'})`
    );
  }
  if (!usernameMatched) {
    mismatchReasons.push(
      `Username mismatch between request (${reqUser || 'null'}), registration (${regUsername || 'null'}), and login (${loginUsername || 'null'})`
    );
  }

  return {
    hasNewAccountEvidence,
    funIdMatched,
    usernameMatched,
    registeredFunId: regFunId,
    loginFunId,
    requestedUsername: reqUser,
    registeredUsername: regUsername,
    loginUsername,
    identityVerified:
      hasNewAccountEvidence &&
      Boolean(loginVerification && loginVerification.loginVerified === true) &&
      funIdMatched &&
      usernameMatched,
    mismatchReasons
  };
}

class FuntapRegistrationClient {
  constructor(options = {}) {
    this.baseUrl = options.baseUrl || FUNTAP_CONFIG.BASE_URL;
    this.device = { ...FUNTAP_CONFIG.DEFAULT_DEVICE, ...(options.device || {}) };
    this.sessionManager = options.sessionManager || new SessionManager(options);
    this.lastFormMeta = null;
    this.lastRedirectChain = [];
  }

  isProductionTarget() {
    return /sdkmain\.com|funtap\.vn/i.test(this.baseUrl);
  }

  /**
   * Fetch SDK authentication config (GET /api/v1/apps/{appKey}/{appVersion}/configs/auth)
   */
  async fetchAuthConfig() {
    const url = buildAuthConfigUrl(this.baseUrl);
    const res = await this.sessionManager.request({
      method: 'GET',
      url,
      headers: buildRestHeaders()
    });
    return {
      httpStatus: res.status,
      url,
      data: res.data
    };
  }

  /**
   * Step 1-4 of Funtap SDK Registration Flow:
   * 1. GET /v1/apps/{appKey}/{appVersion}/register/email
   * 2. Receive HTTP 302 and session cookies (XSRF-TOKEN, core_sdk_session)
   * 3. Follow redirect to /v1/apps/{appKey}/{appVersion}/register/phone (HTTP 200)
   * 4. Extract CSRF _token and form action from HTML
   */
  async initializeSessionAndFetchForm() {
    const entryUrl = buildRegisterEntryUrl(this.device, this.baseUrl);
    const headers = buildWebViewHeaders(this.device);

    const { finalResponse, finalUrl, redirectChain } =
      await this.sessionManager.requestWithRedirects({
        method: 'GET',
        url: entryUrl,
        headers
      });

    this.lastRedirectChain = redirectChain;
    const html = typeof finalResponse.data === 'string' ? finalResponse.data : '';
    const formMeta = parseCsrfAndFormHtml(html);
    this.lastFormMeta = formMeta;

    return {
      entryUrl,
      finalUrl,
      httpStatus: finalResponse.status,
      retryAfter: finalResponse.headers?.['retry-after'],
      ...detectVerification(html),
      redirectChain,
      cookies: this.sessionManager.getRedactedCookieSummary(),
      hasValidSessionCookies: this.sessionManager.hasValidSessionCookies(),
      formMeta: {
        valid: formMeta.valid,
        error: formMeta.error,
        pageTitle: formMeta.pageTitle,
        heading: formMeta.heading,
        csrfTokenLength: formMeta.csrfTokenLength,
        redactedCsrfToken: formMeta.redactedCsrfToken,
        formAction: formMeta.formAction,
        formMethod: formMeta.formMethod,
        prefilled: formMeta.prefilled,
        constraints: formMeta.constraints,
        fieldsPresent: formMeta.fieldsPresent
      }
    };
  }

  /**
   * Step 5: Prepare the application/x-www-form-urlencoded registration request
   * using the extracted CSRF _token and session cookies.
   */
  prepareRegistrationRequest(account) {
    if (!this.lastFormMeta || !this.lastFormMeta.csrfToken) {
      throw new Error(
        'Cannot prepare registration request before initializeSessionAndFetchForm() extracts a valid CSRF _token'
      );
    }

    const validation = validateRegistrationInput(account);
    const targetUrl =
      this.lastFormMeta.formAction || buildRegisterPhoneActionUrl(this.device, this.baseUrl);

    const formFields = {
      _token: this.lastFormMeta.csrfToken,
      username: String(account.username || '').trim(),
      fullname: String(account.fullname || '').trim(),
      birthday: String(account.birthday || '').trim(),
      phone: String(account.phone || '').trim(),
      password: String(account.password || '')
    };

    const urlEncodedBody = new URLSearchParams(formFields).toString();

    const headers = {
      ...buildWebViewHeaders(this.device),
      'Content-Type': 'application/x-www-form-urlencoded',
      Origin: this.baseUrl,
      Referer: targetUrl
    };

    return {
      validation,
      method: 'POST',
      url: targetUrl,
      headers,
      urlEncodedBody,
      redactedPayload: sanitizeForLog(formFields),
      redactedHeaders: sanitizeForLog(headers)
    };
  }

  /**
   * Execute or stage the registration workflow for a single account.
   *
   * Strict Verification & Safety Rules:
   * 1. Never submit `phone_source === "mock"` to production (`core.sdkmain.com`).
   * 2. If `operatorConfirmed !== true`, does NOT send the POST request and returns `READY_FOR_MANUAL_TEST`.
   * 3. Never classifies HTTP 200/302 or login success alone as `REGISTER_SUCCESS`.
   * 4. If the account already exists (`ALREADY_EXISTS`), returns `ALREADY_EXISTS` immediately without marking `REGISTER_SUCCESS`.
   * 5. Only marks `REGISTER_SUCCESS` when:
   *    (a) The registration response confirms new account creation (`sdkLoginSuccessSignal === true && isNewAccountCreated === true`),
   *    (b) Re-login (`verifyAccountLogin`) succeeds (`loginVerified === true`), AND
   *    (c) Both `FunID` and `username` match between the registration response and the login response (`identityComparison.identityVerified === true`).
   */
  async registerAccount(account, options = {}) {
    const operatorConfirmed = Boolean(options.operatorConfirmed);

    if (
      operatorConfirmed &&
      this.isProductionTarget() &&
      String(account.phone_source || '').toLowerCase() === 'mock'
    ) {
      throw new Error(
        `SAFETY GUARD: Refusing to submit mock phone number for ${account.username} to production server (${this.baseUrl})`
      );
    }

    // 1. Initialize session, follow 302 redirect, and extract CSRF _token
    const sessionInit = await this.initializeSessionAndFetchForm();
    if (sessionInit.requiresCaptcha || sessionInit.requiresOtp) {
      return {status:REGISTRATION_STATUS.VERIFICATION_REQUIRED,stage:'FORM_VERIFICATION_REQUIRED',httpStatus:sessionInit.httpStatus,isNewAccountCreated:false,requiresCaptcha:sessionInit.requiresCaptcha,requiresOtp:sessionInit.requiresOtp};
    }
    if (!sessionInit.formMeta.valid || !sessionInit.hasValidSessionCookies) {
      return {
        status: REGISTRATION_STATUS.REGISTER_FAILED,
        stage: 'SESSION_INIT',
        httpStatus: sessionInit.httpStatus,
        retryAfter:sessionInit.retryAfter,
        isNewAccountCreated: false,
        sessionInit,
        message:
          sessionInit.formMeta.error || 'Failed to obtain valid session cookies or CSRF _token'
      };
    }

    // 2. Prepare and validate request payload
    const prepared = this.prepareRegistrationRequest(account);
    if (!prepared.validation.valid) {
      return {
        status: REGISTRATION_STATUS.REGISTER_FAILED,
        stage: 'LOCAL_VALIDATION',
        httpStatus: null,
        isNewAccountCreated: false,
        sessionInit,
        preparedRequest: {
          method: prepared.method,
          url: prepared.url,
          payload: prepared.redactedPayload,
          validationErrors: prepared.validation.errors
        },
        message: `Local validation failed: ${prepared.validation.errors.join('; ')}`
      };
    }

    // 3. Stop safely if operator has not explicitly confirmed submission
    if (!operatorConfirmed) {
      return {
        status: REGISTRATION_STATUS.READY_FOR_MANUAL_TEST,
        stage: 'AWAITING_OPERATOR_CONFIRMATION',
        httpStatus: sessionInit.httpStatus,
        isNewAccountCreated: false,
        sessionInit,
        preparedRequest: {
          method: prepared.method,
          url: prepared.url,
          contentType: 'application/x-www-form-urlencoded',
          payload: prepared.redactedPayload,
          headers: prepared.redactedHeaders
        },
        loginVerification: null,
        identityComparison: null,
        message:
          'Session cookies and CSRF _token verified. Prepared POST request is ready and awaiting operator confirmation.'
      };
    }

    // 4. Send single POST registration request (and follow any 302 redirect)
    const postResult = await this.sessionManager.requestWithRedirects({
      method: prepared.method,
      url: prepared.url,
      headers: prepared.headers,
      data: prepared.urlEncodedBody
    });

    const parsed = parseRegistrationResponse({
      httpStatus: postResult.finalResponse.status,
      headers: postResult.finalResponse.headers,
      body: postResult.finalResponse.data,
      redirectChain: postResult.redirectChain
    });

    // 5. If verification (OTP / CAPTCHA) is required, stop immediately
    if (parsed.status === REGISTRATION_STATUS.VERIFICATION_REQUIRED) {
      return {
        status: REGISTRATION_STATUS.VERIFICATION_REQUIRED,
        stage: 'POST_SUBMIT_VERIFICATION',
        httpStatus: parsed.httpStatus,
        responseType: parsed.responseType,
        isNewAccountCreated: false,
        requiresOtp: parsed.requiresOtp,
        requiresCaptcha: parsed.requiresCaptcha,
        messages: parsed.messages,
        sessionInit,
        postRedirectChain: postResult.redirectChain,
        loginVerification: null,
        identityComparison: null
      };
    }

    // 6. If account already exists, return ALREADY_EXISTS (never REGISTER_SUCCESS)
    if (parsed.status === REGISTRATION_STATUS.ALREADY_EXISTS) {
      return {
        status: REGISTRATION_STATUS.ALREADY_EXISTS,
        stage: 'POST_SUBMIT_RESPONSE',
        httpStatus: parsed.httpStatus,
        responseType: parsed.responseType,
        isNewAccountCreated: false,
        errorCode: parsed.errorCode,
        messages: parsed.messages,
        invalidFields: parsed.invalidFields,
        extractedUser: parsed.extractedUser || null,
        sessionInit,
        postRedirectChain: postResult.redirectChain,
        loginVerification: null,
        identityComparison: null
      };
    }

    // 7. If rate-limited or failed, return immediately
    if (
      parsed.status === REGISTRATION_STATUS.RATE_LIMITED ||
      parsed.status === REGISTRATION_STATUS.REGISTER_FAILED
    ) {
      return {
        status: parsed.status,
        stage: 'POST_SUBMIT_RESPONSE',
        httpStatus: parsed.httpStatus,
        retryAfter: postResult.finalResponse.headers?.['retry-after'],
        responseType: parsed.responseType,
        isNewAccountCreated: false,
        errorCode: parsed.errorCode,
        messages: parsed.messages,
        invalidFields: parsed.invalidFields,
        sessionInit,
        postRedirectChain: postResult.redirectChain,
        loginVerification: null,
        identityComparison: null
      };
    }

    // 8. If the registration response does NOT contain explicit evidence of new account creation,
    // NEVER fall back to login verification to claim REGISTER_SUCCESS!
    if (
      parsed.status !== REGISTRATION_STATUS.REGISTER_SUCCESS ||
      parsed.sdkLoginSuccessSignal !== true ||
      parsed.isNewAccountCreated !== true ||
      !parsed.extractedUser ||
      !parsed.extractedUser.id
    ) {
      return {
        status: REGISTRATION_STATUS.UNKNOWN,
        stage: 'POST_SUBMIT_MISSING_NEW_ACCOUNT_EVIDENCE',
        httpStatus: parsed.httpStatus,
        responseType: parsed.responseType,
        sdkLoginSuccessSignal: Boolean(parsed.sdkLoginSuccessSignal),
        isNewAccountCreated: false,
        extractedUser: null,
        messages:
          parsed.messages && parsed.messages.length > 0
            ? parsed.messages
            : ['Registration response lacked new-account creation evidence (never marked REGISTER_SUCCESS from login alone)'],
        sessionInit,
        postRedirectChain: postResult.redirectChain,
        loginVerification: null,
        identityComparison: null
      };
    }

    // 9. Verify re-login via POST /api/v1/apps/.../auth/login and cross-check username & FunID
    const loginCheck = await verifyAccountLogin({
      username: account.username,
      password: account.password,
      device: this.device,
      baseUrl: this.baseUrl
    });

    const identityComparison = compareRegistrationAndLoginIdentity({
      requestedUsername: account.username,
      parsedRegistration: parsed,
      loginVerification: loginCheck
    });

    const finalMessages = [...(parsed.messages || [])];
    if (!identityComparison.identityVerified) {
      finalMessages.push(...identityComparison.mismatchReasons);
    }

    return {
      status: identityComparison.identityVerified
        ? REGISTRATION_STATUS.REGISTER_SUCCESS
        : REGISTRATION_STATUS.UNKNOWN,
      stage: 'COMPLETED_WITH_LOGIN_AND_IDENTITY_CHECK',
      httpStatus: parsed.httpStatus,
      responseType: parsed.responseType,
      sdkLoginSuccessSignal: parsed.sdkLoginSuccessSignal,
      isNewAccountCreated: identityComparison.identityVerified,
      extractedUser: {
        id: String(parsed.extractedUser.id),
        username: parsed.extractedUser.username,
        newUser: Boolean(parsed.extractedUser.newUser),
        loginType: parsed.extractedUser.loginType,
        loginOrRegister: parsed.extractedUser.loginOrRegister,
        redactedAccessToken: parsed.extractedUser.redactedAccessToken
      },
      messages: finalMessages,
      sessionInit,
      postRedirectChain: postResult.redirectChain,
      loginVerification: loginCheck,
      identityComparison
    };
  }
}

module.exports = {
  FuntapRegistrationClient,
  validateRegistrationInput,
  compareRegistrationAndLoginIdentity,
  VN_MOBILE_REGEX
};
