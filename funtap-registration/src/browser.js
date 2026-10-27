const { chromium } = require('playwright');

/**
 * Launch Chromium browser in headed mode (or headless ONLY if explicitly overridden by CI/test flag).
 * By default, opens a visible Chromium window (`headless: false`) as required.
 */
async function launchBrowser(options = {}) {
  const headless = options.headless === true ? true : false;
  const slowMo = options.slowMo !== undefined ? options.slowMo : 80;

  const browser = await chromium.launch({
    headless,
    slowMo,
    args: [
      '--disable-blink-features=AutomationControlled',
      '--window-size=1280,900'
    ]
  });

  const context = await browser.newContext({
    viewport: { width: 1280, height: 860 },
    locale: 'vi-VN',
    timezoneId: 'Asia/Ho_Chi_Minh'
  });

  const page = await context.newPage();
  return { browser, context, page };
}

module.exports = {
  launchBrowser
};
