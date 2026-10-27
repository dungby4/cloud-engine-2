const path = require('path');
const fs = require('fs');

const REGISTER_URL = 'https://id.funtap.vn/register';
const SCREENSHOTS_DIR = path.join(__dirname, '..', 'screenshots');

/**
 * Verified DOM Selectors on https://id.funtap.vn/register
 */
const SELECTORS = {
  form: '#register-form',
  csrfToken: 'input[name="_token"]',
  fullname: '#fullname',
  phone: '#phone',
  phoneError: '#phone-error',
  birthdayPicker: '#birthday_picker',
  birthdayHidden: '#birthday',
  birthdayAgeError: '#birthday-age-error',
  username: '#username',
  password: '#password',
  passwordConfirm: '#password-confirm',
  passwordStrength: '#password-strength',
  passwordStrengthText: '#password-strength-text',
  serviceTermsCheckbox: '#serviceRegistrationCheckbox',
  dataSharingCheckbox: '#dataSharingCheckbox',
  recaptchaResponse: '#g-recaptcha-response',
  submitButton: '#submitButton',
  passwordToggleIcons: '.icon-shp'
};

/**
 * Navigate to Funtap registration page and verify all required selectors exist
 */
async function openRegistrationPage(page, timeoutMs = 30000) {
  await page.goto(REGISTER_URL, {
    waitUntil: 'domcontentloaded',
    timeout: timeoutMs
  });

  // Verify core form selectors are present and attached
  await page.waitForSelector(SELECTORS.form, { state: 'visible', timeout: 15000 });
  await page.waitForSelector(SELECTORS.fullname, { state: 'visible', timeout: 10000 });
  await page.waitForSelector(SELECTORS.phone, { state: 'visible', timeout: 10000 });
  await page.waitForSelector(SELECTORS.birthdayPicker, { state: 'visible', timeout: 10000 });
  await page.waitForSelector(SELECTORS.username, { state: 'visible', timeout: 10000 });
  await page.waitForSelector(SELECTORS.password, { state: 'visible', timeout: 10000 });
  await page.waitForSelector(SELECTORS.passwordConfirm, { state: 'visible', timeout: 10000 });
  await page.waitForSelector(SELECTORS.serviceTermsCheckbox, { state: 'attached', timeout: 10000 });
  await page.waitForSelector(SELECTORS.dataSharingCheckbox, { state: 'attached', timeout: 10000 });
  await page.waitForSelector(SELECTORS.submitButton, { state: 'visible', timeout: 10000 });
}

/**
 * Ensure password inputs remain `type="password"` (masked) before filling or taking screenshots,
 * so passwords are NEVER exposed in screenshots.
 */
async function ensurePasswordInputsMasked(page) {
  await page.evaluate(() => {
    const pwd = document.getElementById('password');
    const pwdConfirm = document.getElementById('password-confirm');
    if (pwd && pwd.type !== 'password') pwd.type = 'password';
    if (pwdConfirm && pwdConfirm.type !== 'password') pwdConfirm.type = 'password';
    document.querySelectorAll('.icon-shp.active').forEach((el) => el.classList.remove('active'));
  });
}

/**
 * Fill the registration form fields for an account.
 *
 * IMPORTANT SAFETY RULES:
 * 1. Does NOT automatically check `#serviceRegistrationCheckbox` or `#dataSharingCheckbox`.
 * 2. Does NOT click `#submitButton`.
 * 3. Keeps password masked (`type="password"`) at all times.
 */
async function fillRegistrationForm(page, account, password) {
  await ensurePasswordInputsMasked(page);

  // 1. Fill fullname (overwrite Funtap's auto-generated random Vietnamese name)
  await page.fill(SELECTORS.fullname, '');
  await page.fill(SELECTORS.fullname, account.fullname);

  // 2. Fill phone number (if provided by operator in CSV)
  await page.fill(SELECTORS.phone, '');
  if (account.phone && account.phone.trim() !== '') {
    await page.fill(SELECTORS.phone, account.phone.trim());
  }

  // 3. Fill birthday_picker (YYYY-MM-DD) and trigger change event so hidden #birthday updates to DD/MM/YYYY
  if (account.birthday) {
    await page.fill(SELECTORS.birthdayPicker, account.birthday);
    await page.dispatchEvent(SELECTORS.birthdayPicker, 'change');
  }

  // 4. Fill username
  await page.fill(SELECTORS.username, '');
  await page.fill(SELECTORS.username, account.username);

  // 5. Fill password and password_confirmation while ensuring type="password"
  await ensurePasswordInputsMasked(page);
  await page.fill(SELECTORS.password, '');
  await page.fill(SELECTORS.password, password);
  // Trigger change event on #password so Funtap's /password/check AJAX runs and displays password strength feedback
  await page.dispatchEvent(SELECTORS.password, 'change');

  await page.fill(SELECTORS.passwordConfirm, '');
  await page.fill(SELECTORS.passwordConfirm, password);
  await page.dispatchEvent(SELECTORS.passwordConfirm, 'input');

  // 6. Automatically check both Terms & Data Sharing checkboxes per user request
  await page.check(SELECTORS.serviceTermsCheckbox);
  await page.check(SELECTORS.dataSharingCheckbox);
  await page.evaluate(() => {
    if (typeof window.toggleSubmitButton === 'function') {
      window.toggleSubmitButton();
    }
  });

  // Wait briefly for `/password/check` AJAX response to render `#password-strength`
  await page.waitForTimeout(1200);
}

/**
 * Capture a safe screenshot of the form with password fields strictly masked as `type="password"`
 */
async function captureSafeScreenshot(page, filenamePrefix) {
  if (!fs.existsSync(SCREENSHOTS_DIR)) {
    fs.mkdirSync(SCREENSHOTS_DIR, { recursive: true });
  }
  await ensurePasswordInputsMasked(page);
  const safeName = `${filenamePrefix}_${Date.now()}.png`.replace(/[^a-zA-Z0-9_.-]/g, '_');
  const fullPath = path.join(SCREENSHOTS_DIR, safeName);
  await page.screenshot({ path: fullPath, fullPage: true });
  return path.relative(path.join(__dirname, '..'), fullPath);
}

module.exports = {
  REGISTER_URL,
  SELECTORS,
  openRegistrationPage,
  ensurePasswordInputsMasked,
  fillRegistrationForm,
  captureSafeScreenshot
};
