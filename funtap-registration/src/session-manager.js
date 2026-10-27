const axios = require('axios');
const { redactSecret } = require('./funtap-api');

/**
 * SessionManager manages RFC-6265 cookies (XSRF-TOKEN, core_sdk_session, etc.)
 * and executes HTTP requests with manual redirect tracking so every 302 hop
 * and cookie update is captured and verified.
 */
class SessionManager {
  constructor(options = {}) {
    this.cookies = new Map();
    this.timeoutMs = options.timeoutMs || 15000;
    this.httpClient = axios.create({
      timeout: this.timeoutMs,
      maxRedirects: 0, // Handle redirects manually to preserve and log Set-Cookie on every hop
      validateStatus: () => true // Never throw on 3xx/4xx/5xx so caller can inspect all status codes
    });
  }

  /**
   * Parse Set-Cookie header array or string and store cookies in the jar
   */
  storeCookiesFromHeaders(headers = {}) {
    const setCookieHeader = headers['set-cookie'] || headers['Set-Cookie'];
    if (!setCookieHeader) return [];

    const rawList = Array.isArray(setCookieHeader) ? setCookieHeader : [setCookieHeader];
    const updatedNames = [];

    for (const rawCookie of rawList) {
      if (typeof rawCookie !== 'string') continue;
      const firstSegment = rawCookie.split(';')[0];
      const eqIdx = firstSegment.indexOf('=');
      if (eqIdx === -1) continue;

      const name = firstSegment.slice(0, eqIdx).trim();
      const value = firstSegment.slice(eqIdx + 1).trim();
      if (!name) continue;

      this.cookies.set(name, {
        name,
        value,
        updatedAt: new Date().toISOString()
      });
      updatedNames.push(name);
    }

    return updatedNames;
  }

  /**
   * Build the Cookie request header string from stored cookies
   */
  getCookieHeaderString() {
    const parts = [];
    for (const [name, entry] of this.cookies.entries()) {
      parts.push(`${name}=${entry.value}`);
    }
    return parts.join('; ');
  }

  /**
   * Get decoded XSRF-TOKEN value if present
   */
  getXsrfToken() {
    const entry = this.cookies.get('XSRF-TOKEN');
    if (!entry || !entry.value) return null;
    try {
      return decodeURIComponent(entry.value);
    } catch (_) {
      return entry.value;
    }
  }

  /**
   * Return a redacted summary of stored cookies safe for logging and reports
   */
  getRedactedCookieSummary() {
    const summary = {};
    for (const [name, entry] of this.cookies.entries()) {
      summary[name] = {
        present: Boolean(entry.value),
        length: entry.value ? entry.value.length : 0,
        redactedValue: redactSecret(entry.value, true),
        updatedAt: entry.updatedAt
      };
    }
    return summary;
  }

  hasValidSessionCookies() {
    return (
      this.cookies.has('XSRF-TOKEN') &&
      (this.cookies.has('core_sdk_session') || this.cookies.has('funtap_session'))
    );
  }

  /**
   * Execute a single HTTP request with current Cookie jar attached
   */
  async request(config) {
    const headers = { ...(config.headers || {}) };
    const cookieHeader = this.getCookieHeaderString();
    if (cookieHeader) {
      headers.Cookie = cookieHeader;
    }

    const response = await this.httpClient.request({
      ...config,
      headers
    });

    const updatedCookies = this.storeCookiesFromHeaders(response.headers);

    return {
      status: response.status,
      statusText: response.statusText,
      headers: response.headers,
      data: response.data,
      updatedCookies,
      requestUrl: config.url,
      requestMethod: (config.method || 'GET').toUpperCase()
    };
  }

  /**
   * Execute an HTTP request and manually follow 301/302/303/307/308 redirects,
   * recording each hop and updating the Cookie jar at every step.
   */
  async requestWithRedirects(initialConfig, maxRedirects = 5) {
    const redirectChain = [];
    let currentConfig = { ...initialConfig };

    for (let hop = 0; hop <= maxRedirects; hop++) {
      const res = await this.request(currentConfig);
      const location = res.headers ? res.headers.location || res.headers.Location : null;

      redirectChain.push({
        hop,
        method: res.requestMethod,
        url: res.requestUrl,
        status: res.status,
        location: location || null,
        cookiesUpdated: res.updatedCookies
      });

      const isRedirect = [301, 302, 303, 307, 308].includes(res.status) && Boolean(location);
      if (!isRedirect) {
        return {
          finalResponse: res,
          finalUrl: res.requestUrl,
          redirectChain
        };
      }

      const nextUrl = new URL(location, res.requestUrl).toString();
      const nextMethod =
        res.status === 303 || ((res.status === 301 || res.status === 302) && res.requestMethod === 'POST')
          ? 'GET'
          : res.requestMethod;

      const nextHeaders = { ...(currentConfig.headers || {}) };
      if (nextMethod === 'GET') {
        delete nextHeaders['Content-Type'];
        delete nextHeaders['content-type'];
        delete nextHeaders['Content-Length'];
        delete nextHeaders['content-length'];
      }
      nextHeaders.Referer = res.requestUrl;

      currentConfig = {
        method: nextMethod,
        url: nextUrl,
        headers: nextHeaders,
        data: nextMethod === 'GET' ? undefined : currentConfig.data
      };
    }

    throw new Error(`Exceeded maximum redirects (${maxRedirects})`);
  }
}

module.exports = {
  SessionManager
};
