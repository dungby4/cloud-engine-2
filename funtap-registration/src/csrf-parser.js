const { redactSecret } = require('./funtap-api');

/**
 * Extract an attribute value from an HTML tag string
 */
function extractAttribute(tagHtml, attrName) {
  if (!tagHtml) return null;
  const regex = new RegExp(`\\b${attrName}\\s*=\\s*(?:"([^"]*)"|'([^']*)'|([^\\s>"']+))`, 'i');
  const match = tagHtml.match(regex);
  if (!match) return null;
  const raw = match[1] ?? match[2] ?? match[3] ?? '';
  return raw.replace(/&amp;/g, '&');
}

/**
 * Find an <input> tag by name or id in HTML and return its attributes
 */
function findInputTagByNameOrId(html, fieldKey) {
  if (typeof html !== 'string') return null;
  const inputTags = html.match(/<input\b[^>]*>/gi) || [];
  for (const tag of inputTags) {
    const name = extractAttribute(tag, 'name');
    const id = extractAttribute(tag, 'id');
    if (name === fieldKey || id === fieldKey) {
      return {
        rawTag: tag,
        name,
        id,
        type: extractAttribute(tag, 'type'),
        value: extractAttribute(tag, 'value'),
        minlength: extractAttribute(tag, 'minlength'),
        maxlength: extractAttribute(tag, 'maxlength'),
        placeholder: extractAttribute(tag, 'placeholder')
      };
    }
  }
  return null;
}

/**
 * Parse CSRF token (_token), form action, method, and server-prefilled inputs
 * from Funtap SDK's /register/phone HTML response.
 */
function parseCsrfAndFormHtml(html) {
  if (typeof html !== 'string' || !html.trim()) {
    return {
      valid: false,
      error: 'Empty or non-string HTML body',
      csrfToken: null,
      redactedCsrfToken: null,
      formAction: null,
      formMethod: null,
      prefilled: {},
      fieldsPresent: {}
    };
  }

  // 1. Extract <form ...> tag
  const formMatch = html.match(/<form\b[^>]*>/i);
  const formTag = formMatch ? formMatch[0] : null;
  const formAction = extractAttribute(formTag, 'action');
  const formMethod = (extractAttribute(formTag, 'method') || 'POST').toUpperCase();

  // 2. Extract <input type="hidden" name="_token" value="..."> or meta csrf-token
  const tokenInput = findInputTagByNameOrId(html, '_token');
  let csrfToken = tokenInput && tokenInput.value ? tokenInput.value.trim() : null;

  if (!csrfToken) {
    const metaMatch = html.match(/<meta\b[^>]*name=["']csrf-token["'][^>]*>/i);
    if (metaMatch) {
      csrfToken = extractAttribute(metaMatch[0], 'content');
    }
  }

  // 3. Extract confirmed form inputs (username, fullname, birthday, phone, password)
  const usernameInput = findInputTagByNameOrId(html, 'username');
  const fullnameInput = findInputTagByNameOrId(html, 'fullname');
  const birthdayInput = findInputTagByNameOrId(html, 'birthday');
  const phoneInput = findInputTagByNameOrId(html, 'phone');
  const passwordInput = findInputTagByNameOrId(html, 'password');

  // 4. Extract page title and heading
  const titleMatch = html.match(/<title[^>]*>([\s\S]*?)<\/title>/i);
  const h1Match = html.match(/<h1[^>]*>([\s\S]*?)<\/h1>/i);

  const fieldsPresent = {
    _token: Boolean(csrfToken),
    username: Boolean(usernameInput),
    fullname: Boolean(fullnameInput),
    birthday: Boolean(birthdayInput),
    phone: Boolean(phoneInput),
    password: Boolean(passwordInput)
  };

  const allRequiredFieldsPresent = Object.values(fieldsPresent).every(Boolean);

  return {
    valid: Boolean(csrfToken) && allRequiredFieldsPresent,
    error: !csrfToken
      ? 'CSRF _token not found in HTML'
      : !allRequiredFieldsPresent
      ? 'One or more expected registration form inputs are missing'
      : null,
    pageTitle: titleMatch ? titleMatch[1].trim() : null,
    heading: h1Match ? h1Match[1].replace(/<[^>]+>/g, '').trim() : null,
    csrfToken,
    csrfTokenLength: csrfToken ? csrfToken.length : 0,
    redactedCsrfToken: csrfToken ? redactSecret(csrfToken, true) : null,
    formAction,
    formMethod,
    prefilled: {
      username: usernameInput ? usernameInput.value || '' : '',
      fullname: fullnameInput ? fullnameInput.value || '' : '',
      birthday: birthdayInput ? birthdayInput.value || '' : ''
    },
    constraints: {
      username: usernameInput
        ? { minlength: usernameInput.minlength, maxlength: usernameInput.maxlength }
        : null,
      fullname: fullnameInput
        ? { minlength: fullnameInput.minlength, maxlength: fullnameInput.maxlength }
        : null,
      phone: phoneInput ? { maxlength: phoneInput.maxlength } : null,
      password: passwordInput ? { placeholder: passwordInput.placeholder } : null
    },
    fieldsPresent
  };
}

module.exports = {
  parseCsrfAndFormHtml,
  findInputTagByNameOrId,
  extractAttribute
};
