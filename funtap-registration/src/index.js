const readline = require('readline');
const {
  ensureAccountsCsvExists,
  ensureResultsCsvExists,
  loadAccounts,
  loadCompletedUsernames,
  appendResult,
  maskPhone,
  ACCOUNTS_CSV_PATH,
  RESULTS_CSV_PATH
} = require('./csv');
const { launchBrowser } = require('./browser');
const {
  openRegistrationPage,
  fillRegistrationForm,
  captureSafeScreenshot
} = require('./form');
const {
  validateAccountInputLocally,
  inspectPageValidation
} = require('./validation');

// Default test password specified in requirements (NEVER logged or printed in plain text)
const DEFAULT_TEST_PASSWORD = process.env.FUNTAP_PASSWORD || 'ntdung12';

function parseCliArgs(argv) {
  const args = {
    initCsvOnly: false,
    regenerateMockCsv: false,
    dryRun: true, // Default mode: safe --dry-run using mock data without submitting
    liveManual: false,
    headless: false,
    limit: null
  };

  for (let i = 2; i < argv.length; i++) {
    const arg = argv[i];
    if (arg === '--init-csv-only') {
      args.initCsvOnly = true;
    } else if (arg === '--regenerate-mock-csv') {
      args.regenerateMockCsv = true;
    } else if (arg === '--dry-run') {
      args.dryRun = true;
      args.liveManual = false;
    } else if (arg === '--live-manual') {
      args.liveManual = true;
      args.dryRun = false;
    } else if (arg === '--headless') {
      args.headless = true;
    } else if (arg === '--limit' && argv[i + 1]) {
      args.limit = parseInt(argv[i + 1], 10);
      i++;
    }
  }
  return args;
}

function askOperatorQuestion(query) {
  if (!process.stdin.isTTY) {
    return Promise.resolve('q');
  }
  const rl = readline.createInterface({
    input: process.stdin,
    output: process.stdout
  });
  return new Promise((resolve) => {
    rl.question(query, (ans) => {
      rl.close();
      resolve(ans.trim().toLowerCase());
    });
  });
}

async function main() {
  const args = parseCliArgs(process.argv);
  const modeName = args.liveManual ? 'live-manual' : 'dry-run';

  ensureAccountsCsvExists(args.regenerateMockCsv);
  ensureResultsCsvExists();

  const accounts = loadAccounts();
  const mockCount = accounts.filter((a) => (a.phone_source || 'mock') === 'mock').length;
  const operatorCount = accounts.length - mockCount;

  console.log('==============================================================');
  console.log(' FUNTAP ACCOUNT REGISTRATION AUTOMATION (HUMAN-IN-THE-LOOP)');
  console.log('==============================================================');
  console.log(
    `[INFO] Danh sách tài khoản: ${ACCOUNTS_CSV_PATH} (${accounts.length} tài khoản: ${mockCount} SĐT mock, ${operatorCount} SĐT operator)`
  );
  console.log(`[INFO] File kết quả       : ${RESULTS_CSV_PATH}`);
  console.log(`[INFO] Mật khẩu cấu hình  : [REDACTED - độ dài ${DEFAULT_TEST_PASSWORD.length} ký tự]`);
  console.log(
    `[INFO] Chế độ chạy        : ${
      args.liveManual
        ? '--live-manual (Chỉ nhận SĐT thật do người vận hành cung cấp, điền sẵn form và dừng chờ người thật xác minh & bấm Đăng ký)'
        : '--dry-run (Chạy thử quy trình bằng dữ liệu mock, kiểm tra DOM/validation, chụp screenshot, KHÔNG gửi bất kỳ request đăng ký nào)'
    }`
  );
  console.log('--------------------------------------------------------------');

  if (args.initCsvOnly || args.regenerateMockCsv) {
    console.log(
      `[SUCCESS] Đã chuẩn bị đầy đủ ${accounts.length} tài khoản (dungby30 -> dungby99) tại ${ACCOUNTS_CSV_PATH}.`
    );
    return;
  }

  // Check resume state from data/results.csv
  const completedMap = loadCompletedUsernames();
  const pendingAccounts = accounts.filter((acc) => {
    const prev = completedMap.get(acc.username);
    return !prev || (prev.status !== 'SUCCESS' && prev.status !== 'REGISTERED');
  });

  if (pendingAccounts.length === 0) {
    console.log('[INFO] Tất cả 70 tài khoản trong danh sách đều đã có trạng thái SUCCESS.');
    return;
  }

  console.log(
    `[INFO] Tiếp tục công việc: còn ${pendingAccounts.length}/${accounts.length} tài khoản cần xử lý.`
  );

  const maxToProcess = args.limit
    ? Math.min(args.limit, pendingAccounts.length)
    : pendingAccounts.length;

  let browserContext;
  try {
    browserContext = await launchBrowser({ headless: args.headless });
    const { page } = browserContext;

    // In --dry-run mode, attach a safety route blocker so POST https://id.funtap.vn/register can NEVER be sent accidentally
    if (args.dryRun) {
      await page.route('https://id.funtap.vn/register', async (route) => {
        if (route.request().method() === 'POST') {
          console.warn(
            '[DRY-RUN SAFETY GUARD] Đã chặn request POST /register để đảm bảo không gửi yêu cầu đăng ký trong chế độ --dry-run.'
          );
          await route.abort();
        } else {
          await route.continue();
        }
      });
    }

    for (let i = 0; i < maxToProcess; i++) {
      const account = pendingAccounts[i];
      const phoneSource = (account.phone_source || 'mock').toLowerCase();
      console.log(
        `\n>>> [${i + 1}/${maxToProcess}] Xử lý tài khoản #${account.index}: username="${
          account.username
        }", fullname="${account.fullname}", phone="${
          account.phone ? maskPhone(account.phone) : '(trống)'
        }" (source=${phoneSource})`
      );

      // Step 1: Local pre-validation (distinguishes --dry-run vs --live-manual)
      const localValidation = validateAccountInputLocally(account, DEFAULT_TEST_PASSWORD, {
        mode: modeName
      });

      if (localValidation.warnings.length > 0) {
        for (const w of localValidation.warnings) {
          console.warn(`[WARN] ${w}`);
        }
      }
      if (!localValidation.valid) {
        for (const err of localValidation.errors) {
          console.warn(`[ERROR - VALIDATION] ${err}`);
        }
      }

      // In --live-manual mode, if phone is mock or invalid, do not proceed with live registration
      if (args.liveManual && !localValidation.valid) {
        appendResult({
          index: account.index,
          username: account.username,
          fullname: account.fullname,
          phone: account.phone,
          phoneSource,
          mode: modeName,
          status: 'BLOCKED_MISSING_OPERATOR_PHONE',
          validationSummary: [...localValidation.errors, ...localValidation.warnings].join(' | '),
          screenshotPath: '',
          notes:
            'Chặn ở chế độ --live-manual: Cần cập nhật số điện thoại thật của người vận hành (phone_source="operator") trong data/accounts.csv.'
        });
        console.log(
          `[STOP] Tài khoản ${account.username} đang dùng SĐT mock hoặc thiếu SĐT hợp lệ của người vận hành. Bỏ qua gửi thật.`
        );
        if (process.stdin.isTTY && i < maxToProcess - 1) {
          const ans = await askOperatorQuestion(
            '\n[OPERATOR] Nhấn Enter để kiểm tra tài khoản tiếp theo, hoặc "q" để dừng: '
          );
          if (ans === 'q') break;
          continue;
        } else {
          break;
        }
      }

      // Step 2: Open https://id.funtap.vn/register and verify selectors
      await openRegistrationPage(page);
      console.log('[INFO] Đã tải trang https://id.funtap.vn/register và xác minh đầy đủ DOM selectors.');

      // Step 3: Fill form fields (auto-checks both checkboxes, stops before clicking Submit)
      await fillRegistrationForm(page, account, DEFAULT_TEST_PASSWORD);
      console.log('[INFO] Đã điền biểu mẫu và tự động tích 2 ô Điều khoản (Mật khẩu được che kín).');

      // Step 4: Inspect live client-side & AJAX validation on the page
      const pageState = await inspectPageValidation(page);
      console.log('[INFO] Kết quả kiểm tra trạng thái trên trang:');
      console.log(`       - Hidden Birthday (#birthday)     : ${pageState.hiddenBirthdayValue}`);
      console.log(
        `       - Phản hồi độ mạnh mật khẩu       : ${
          pageState.passwordStrengthText || 'Không có cảnh báo'
        } (${pageState.passwordStrengthClass || 'N/A'})`
      );
      console.log(
        `       - Lỗi số điện thoại (#phone-error): ${pageState.phoneError || 'Không hiển thị'}`
      );
      console.log(
        `       - Lỗi độ tuổi (#birthday-age-error): ${pageState.birthdayAgeError || 'Không hiển thị'}`
      );
      console.log(
        `       - Checkbox Điều khoản dịch vụ     : ${
          pageState.serviceConsentChecked ? 'Đã tự động tích' : 'Chưa chọn'
        }`
      );
      console.log(
        `       - Checkbox Bảo vệ dữ liệu cá nhân : ${
          pageState.dataSharingConsentChecked ? 'Đã tự động tích' : 'Chưa chọn'
        }`
      );
      console.log(
        `       - Nút ĐĂNG KÝ (#submitButton)     : ${
          pageState.submitReady
            ? 'Sẵn sàng bấm (opacity: 1, pointer-events: auto)'
            : 'Đang khóa (opacity 0.6, pointer-events: none)'
        }`
      );
      console.log(
        `       - Google reCAPTCHA Enterprise     : ${
          pageState.recaptchaScriptPresent ? 'Có tích hợp' : 'Không phát hiện'
        }`
      );

      // Step 5: Take safe screenshot (passwords guaranteed masked)
      const screenshotRelPath = await captureSafeScreenshot(
        page,
        `account_${account.username}_${modeName}`
      );
      console.log(`[INFO] Đã lưu screenshot kiểm tra tại: ${screenshotRelPath}`);

      const validationNotes = [
        ...localValidation.errors,
        ...localValidation.warnings,
        pageState.passwordStrengthText ? `WebPasswordCheck: ${pageState.passwordStrengthText}` : null,
        pageState.phoneError ? `WebPhoneError: ${pageState.phoneError}` : null,
        pageState.birthdayAgeError ? `WebAgeError: ${pageState.birthdayAgeError}` : null,
        `SubmitButtonReady: ${pageState.submitReady}`
      ]
        .filter(Boolean)
        .join(' | ');

      // Step 6: Handle Dry-Run vs Live Manual Confirmation
      if (args.dryRun) {
        const status =
          localValidation.valid && pageState.submitReady ? 'DRY_RUN_PASSED' : 'DRY_RUN_FAILED';
        appendResult({
          index: account.index,
          username: account.username,
          fullname: account.fullname,
          phone: account.phone,
          phoneSource,
          mode: 'dry-run',
          status,
          validationSummary: validationNotes,
          screenshotPath: screenshotRelPath,
          notes:
            'Chế độ --dry-run với SĐT mock: Biểu mẫu đã điền đầy đủ, nút ĐĂNG KÝ đã bật sáng, dừng an toàn và KHÔNG gửi request đăng ký.'
        });
        console.log(
          `[RESULT] Đã ghi trạng thái "${status}" cho ${account.username} vào data/results.csv.`
        );
      } else {
        // --live-manual mode with verified operator phone
        console.log('\n==============================================================');
        console.log(' TẠM DỪNG CHỜ NGƯỜI VẬN HÀNH XÁC MINH & GỬI ĐĂNG KÝ THỦ CÔNG');
        console.log('==============================================================');
        console.log('Hướng dẫn thao tác trên cửa sổ Chromium đang mở:');
        console.log('  1. Kiểm tra lại thông tin Họ tên, Số điện thoại thật, Ngày sinh, Username.');
        console.log('  2. Hai ô Điều khoản đã được tích sẵn và nút "ĐĂNG KÝ" màu cam đã mở khóa.');
        console.log('  3. Người vận hành trực tiếp bấm nút "ĐĂNG KÝ" và xử lý CAPTCHA / OTP (nếu có).');
        console.log('  4. Sau khi hoàn tất trên trình duyệt, quay lại terminal này để ghi nhận kết quả.');

        const operatorChoice = await askOperatorQuestion(
          '\n[OPERATOR] Nhập kết quả cho tài khoản này:\n' +
            '  [y] Đăng ký THÀNH CÔNG (SUCCESS)\n' +
            '  [v] Cần xác minh thêm OTP/CAPTCHA (NEEDS_VERIFICATION)\n' +
            '  [f] Đăng ký THẤT BẠI (FAILED)\n' +
            '  [s] Bỏ qua tài khoản này (SKIPPED)\n' +
            '  [q] Thoát chương trình (lần sau chạy lại sẽ tiếp tục)\n' +
            'Lựa chọn của bạn (y/v/f/s/q): '
        );

        const postScreenshot = await captureSafeScreenshot(
          page,
          `account_${account.username}_post_manual`
        );

        if (operatorChoice === 'y') {
          appendResult({
            index: account.index,
            username: account.username,
            fullname: account.fullname,
            phone: account.phone,
            phoneSource,
            mode: 'live-manual',
            status: 'SUCCESS',
            validationSummary: validationNotes,
            screenshotPath: postScreenshot,
            notes: 'Người vận hành xác nhận đã hoàn tất đăng ký hợp lệ trên trình duyệt.'
          });
          console.log(`[SUCCESS] Đã lưu trạng thái SUCCESS cho ${account.username}.`);
        } else if (operatorChoice === 'v') {
          appendResult({
            index: account.index,
            username: account.username,
            fullname: account.fullname,
            phone: account.phone,
            phoneSource,
            mode: 'live-manual',
            status: 'NEEDS_VERIFICATION',
            validationSummary: validationNotes,
            screenshotPath: postScreenshot,
            notes: 'Cần xác minh bổ sung OTP/CAPTCHA bởi người vận hành.'
          });
          console.log(`[INFO] Đã lưu trạng thái NEEDS_VERIFICATION cho ${account.username}.`);
        } else if (operatorChoice === 'f') {
          const postState = await inspectPageValidation(page);
          const serverErrors = (postState.allTxtErrors || []).join('; ');
          appendResult({
            index: account.index,
            username: account.username,
            fullname: account.fullname,
            phone: account.phone,
            phoneSource,
            mode: 'live-manual',
            status: 'FAILED',
            validationSummary: [validationNotes, serverErrors].filter(Boolean).join(' | '),
            screenshotPath: postScreenshot,
            notes: 'Người vận hành xác nhận đăng ký thất bại.'
          });
          console.log(`[INFO] Đã lưu trạng thái FAILED cho ${account.username}.`);
        } else if (operatorChoice === 'q') {
          console.log('[INFO] Đang đóng trình duyệt và lưu tiến độ. Hẹn gặp lại!');
          break;
        } else {
          appendResult({
            index: account.index,
            username: account.username,
            fullname: account.fullname,
            phone: account.phone,
            phoneSource,
            mode: 'live-manual',
            status: 'SKIPPED',
            validationSummary: validationNotes,
            screenshotPath: postScreenshot,
            notes: 'Người vận hành chọn bỏ qua tạm thời.'
          });
          console.log(`[INFO] Đã lưu trạng thái SKIPPED cho ${account.username}.`);
        }
      }
    }
  } catch (err) {
    console.error(`[FATAL ERROR] Đã xảy ra lỗi trong quá trình thực thi: ${err.message}`);
    process.exitCode = 1;
  } finally {
    if (browserContext && browserContext.browser) {
      await browserContext.browser.close();
      console.log('[INFO] Đã đóng trình duyệt Chromium.');
    }
  }
}

main();
