/**
 * Client-side and DOM validation analyzer for https://id.funtap.vn/register
 *
 * Security & Compliance Rules:
 * - Never log or expose the raw password in error messages or reports.
 * - Do not auto-modify the password if it fails policy; report the error/warning clearly.
 * - In `--dry-run` mode: allow mock Vietnamese mobile numbers (`phone_source="mock"`) to test form filling & UI validation without submitting.
 * - In `--live-manual` mode: strictly require operator-provided phone numbers (`phone_source="operator"`) and block mock phone numbers from live submission.
 */

const VIETNAMESE_PHONE_REGEX = /^(0[35789][0-9]{8}|\+?84[35789][0-9]{8})$/;
const USERNAME_REGEX = /^[a-zA-Z0-9_.-]{6,30}$/;

/**
 * Validate input data locally before interacting with the form.
 * Never mutates password; returns errors & warnings.
 *
 * @param {Object} account - Account row from data/accounts.csv
 * @param {string} password - Test password (`ntdung12`)
 * @param {Object} options - `{ mode: 'dry-run' | 'live-manual' }`
 */
function validateAccountInputLocally(account, password, options = { mode: 'dry-run' }) {
  const mode = options.mode || 'dry-run';
  const errors = [];
  const warnings = [];

  // 1. Username validation
  if (!account.username || !USERNAME_REGEX.test(account.username)) {
    errors.push(
      `Username "${account.username}" không hợp lệ (cần 6-30 ký tự chữ/số).`
    );
  }

  // 2. Fullname validation
  if (!account.fullname || account.fullname.trim().length < 2) {
    errors.push('Họ và tên không được để trống.');
  }

  // 3. Phone validation (distinguishing `--dry-run` mock phone vs `--live-manual` operator phone)
  const phone = (account.phone || '').trim();
  const phoneSource = (account.phone_source || 'mock').trim().toLowerCase();

  if (!phone) {
    errors.push('Thiếu số điện thoại trong data/accounts.csv.');
  } else if (!VIETNAMESE_PHONE_REGEX.test(phone)) {
    errors.push(
      `Định dạng số điện thoại không đúng chuẩn di động Việt Nam (10 số bắt đầu bằng 03, 05, 07, 08, 09).`
    );
  } else if (mode === 'live-manual' && phoneSource === 'mock') {
    errors.push(
      'Chế độ --live-manual yêu cầu số điện thoại thật do người vận hành cung cấp (phone_source="operator"). Không được dùng số điện thoại mock để đăng ký thật.'
    );
  } else if (mode === 'dry-run' && phoneSource === 'mock') {
    warnings.push(
      'Đang sử dụng số điện thoại MOCK ngẫu nhiên cho chế độ --dry-run (Chỉ kiểm thử biểu mẫu, tuyệt đối không gửi request đăng ký).'
    );
  }

  // 4. Birthday / Age >= 18 check
  if (!account.birthday) {
    errors.push('Thiếu ngày sinh (birthday).');
  } else {
    const parts = account.birthday.split('-');
    if (parts.length !== 3) {
      errors.push(`Định dạng ngày sinh "${account.birthday}" cần theo chuẩn YYYY-MM-DD.`);
    } else {
      const birthDate = new Date(
        parseInt(parts[0], 10),
        parseInt(parts[1], 10) - 1,
        parseInt(parts[2], 10)
      );
      const min18Date = new Date(
        birthDate.getFullYear() + 18,
        birthDate.getMonth(),
        birthDate.getDate()
      );
      if (new Date() < min18Date) {
        errors.push('Ngày sinh chưa đủ 18 tuổi theo yêu cầu của Funtap.');
      }
    }
  }

  // 5. Password policy check against Funtap's strong password guidelines
  // Do NOT log the password value itself!
  if (!password || typeof password !== 'string') {
    errors.push('Mật khẩu thử nghiệm đang để trống.');
  } else {
    if (password.length < 6) {
      errors.push('Mật khẩu quá ngắn (dưới 6 ký tự).');
    }
    const hasLength8To15 = password.length >= 8 && password.length <= 15;
    const hasUpper = /[A-Z]/.test(password);
    const hasLower = /[a-z]/.test(password);
    const hasNumber = /[0-9]/.test(password);
    const hasSpecial = /[^A-Za-z0-9]/.test(password);

    if (!hasLength8To15 || !hasUpper || !hasLower || !hasNumber || !hasSpecial) {
      warnings.push(
        'Mật khẩu thử nghiệm không đáp ứng đầy đủ gợi ý mật khẩu mạnh của Funtap (8-15 ký tự, gồm chữ hoa, chữ thường, số và ký tự đặc biệt). Hệ thống giữ nguyên mật khẩu theo đúng yêu cầu, không tự ý sửa đổi.'
      );
    }
  }

  return {
    valid: errors.length === 0,
    errors,
    warnings
  };
}

/**
 * Inspect live DOM validation states on https://id.funtap.vn/register
 */
async function inspectPageValidation(page) {
  return await page.evaluate(() => {
    const getVisibleText = (id) => {
      const el = document.getElementById(id);
      if (!el) return null;
      const style = window.getComputedStyle(el);
      if (style.display === 'none' || style.visibility === 'hidden') return null;
      return el.innerText.trim();
    };

    const phoneError = getVisibleText('phone-error');
    const birthdayAgeError = getVisibleText('birthday-age-error');
    const passwordStrengthContainer = document.getElementById('password-strength');
    let passwordStrengthText = null;
    let passwordStrengthClass = null;

    if (passwordStrengthContainer) {
      const style = window.getComputedStyle(passwordStrengthContainer);
      if (style.display !== 'none' && style.visibility !== 'hidden') {
        const textEl = document.getElementById('password-strength-text');
        passwordStrengthText = textEl ? textEl.innerText.trim() : passwordStrengthContainer.innerText.trim();
        passwordStrengthClass = passwordStrengthContainer.className;
      }
    }

    // Also check any server/Laravel returned `.txt-err` or `.help-block` elements
    const allTxtErrors = Array.from(document.querySelectorAll('.txt-err, .text-danger'))
      .filter((el) => {
        const style = window.getComputedStyle(el);
        return style.display !== 'none' && style.visibility !== 'hidden' && el.innerText.trim().length > 0;
      })
      .map((el) => el.innerText.trim());

    const submitBtn = document.getElementById('submitButton');
    const submitReady = submitBtn
      ? window.getComputedStyle(submitBtn).pointerEvents !== 'none' &&
        parseFloat(window.getComputedStyle(submitBtn).opacity) >= 0.9
      : false;

    const serviceConsentChecked = document.getElementById('serviceRegistrationCheckbox')
      ? document.getElementById('serviceRegistrationCheckbox').checked
      : false;
    const dataSharingConsentChecked = document.getElementById('dataSharingCheckbox')
      ? document.getElementById('dataSharingCheckbox').checked
      : false;

    const recaptchaScriptPresent = !!document.querySelector('script[src*="recaptcha/enterprise.js"]');
    const recaptchaBadgePresent = !!document.querySelector('.grecaptcha-badge');

    return {
      phoneError,
      birthdayAgeError,
      passwordStrengthText,
      passwordStrengthClass,
      allTxtErrors,
      submitReady,
      serviceConsentChecked,
      dataSharingConsentChecked,
      recaptchaScriptPresent,
      recaptchaBadgePresent,
      hiddenBirthdayValue: document.getElementById('birthday')
        ? document.getElementById('birthday').value
        : null
    };
  });
}

module.exports = {
  VIETNAMESE_PHONE_REGEX,
  USERNAME_REGEX,
  validateAccountInputLocally,
  inspectPageValidation
};
