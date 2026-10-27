const {
  FUNTAP_CONFIG,
  buildLoginEmailUrl,
  buildRestHeaders,
  redactSecret
} = require('./funtap-api');
const { SessionManager } = require('./session-manager');

/**
 * Verify whether a FunID account can log in via the native Funtap SDK REST endpoint:
 * POST https://core.sdkmain.com/api/v1/apps/2a456b78cf5122cd9278ef24b4d7bfb9/9.9.9.5/auth/login
 *
 * Confirmed parameters from LoginRequest.loginEmail (classes2.dex):
 * - email (FunID username, email, or phone)
 * - password
 * - device_id
 * - fcm_token
 * - package_name
 * - appsflyer_id
 * - advertising_id
 */
async function verifyAccountLogin({
  username,
  password,
  device = FUNTAP_CONFIG.DEFAULT_DEVICE,
  sessionManager = null,
  baseUrl = FUNTAP_CONFIG.BASE_URL
}) {
  if (!username || !password) {
    return {
      loginVerified: false,
      httpStatus: 0,
      errorCode: null,
      status: 'INVALID_INPUT',
      message: 'Missing username or password for login verification',
      userId: null,
      redactedAccessToken: null
    };
  }

  const client = sessionManager || new SessionManager();
  const loginUrl = buildLoginEmailUrl(baseUrl);

  const formBody = new URLSearchParams({
    email: String(username).trim(),
    password: String(password),
    device_id: device.device_id,
    fcm_token: '',
    package_name: FUNTAP_CONFIG.PACKAGE_NAME,
    appsflyer_id: device.appsflyer_id,
    advertising_id: device.advertising_id
  }).toString();

  const headers = {
    ...buildRestHeaders(),
    'Content-Type': 'application/x-www-form-urlencoded'
  };

  try {
    const response = await client.request({
      method: 'POST',
      url: loginUrl,
      headers,
      data: formBody
    });

    const body =
      typeof response.data === 'string'
        ? (() => {
            try {
              return JSON.parse(response.data);
            } catch (_) {
              return null;
            }
          })()
        : response.data;

    if (!body || typeof body !== 'object') {
      return {
        loginVerified: false,
        httpStatus: response.status,
        errorCode: null,
        status: 'NON_JSON_RESPONSE',
        message: `HTTP ${response.status} non-JSON response from auth/login`,
        userId: null,
        redactedAccessToken: null
      };
    }

    const errorCode =
      body.error_code !== undefined
        ? Number(body.error_code)
        : typeof body.status === 'number'
        ? Number(body.status)
        : null;

    const accessToken = body.access_token || (body.data && body.data.accessToken) || null;
    const userObj = body.data || null;
    const userId = userObj && userObj.id ? String(userObj.id) : null;

    const serverUsername =
      userObj && userObj.account && userObj.account.username
        ? String(userObj.account.username).trim()
        : userObj && userObj.username
        ? String(userObj.username).trim()
        : userObj && userObj.name
        ? String(userObj.name).trim()
        : null;

    // LoginInteractorImpl checks response.code() == 200 && error_code >= 0 && access_token present
    const isSuccess =
      response.status === 200 &&
      (errorCode === null || errorCode >= 0) &&
      Boolean(accessToken) &&
      Boolean(userId);

    return {
      loginVerified: isSuccess,
      httpStatus: response.status,
      errorCode,
      status: isSuccess ? 'LOGIN_SUCCESS' : 'LOGIN_FAILED',
      message: body.message || (isSuccess ? 'Login verified successfully' : 'Login failed'),
      userId,
      username: serverUsername,
      loginType: 'Email',
      redactedAccessToken: accessToken ? redactSecret(accessToken, true) : null
    };
  } catch (err) {
    return {
      loginVerified: false,
      httpStatus: 0,
      errorCode: -100,
      status: 'NETWORK_ERROR',
      message: err.message,
      userId: null,
      redactedAccessToken: null
    };
  }
}

module.exports = {
  verifyAccountLogin
};
