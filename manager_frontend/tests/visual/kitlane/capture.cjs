// Verification tooling only. Playwright comes from the caller's tooling environment;
// it is not a Manager dependency. All HTTP API responses are synthetic fixtures.
const { chromium } = require(process.env.KITLANE_PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { auth, stores, overview } = require('./fixtures.json');
const base = process.env.KITLANE_PREVIEW_URL || 'http://127.0.0.1:5173';
const out = path.resolve(process.env.KITLANE_SCREENSHOTS || '.codex-tmp/kitlane');
const prefix = process.argv[2] || 'after';
assert(['localhost', '127.0.0.1'].includes(new URL(base).hostname), 'Only local preview is allowed');
fs.mkdirSync(out, { recursive: true });

async function run() {
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1080 } });
    const errors = [];
    const dimensions = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.route('**/*', async route => {
      const url = new URL(route.request().url());
      if (url.origin !== new URL(base).origin) return route.abort();
      if (!url.pathname.startsWith('/api') && !url.pathname.startsWith('/login')) return route.continue();
      let data = {};
      if (url.pathname.endsWith('/me')) data = auth;
      else if (url.pathname.endsWith('/storefronts')) {
        const selected = route.request().headers()['x-mvn-manager-storefront'] || 'minsk';
        data = { items: stores.map(item => ({ ...item, is_current: item.slug === selected })) };
      } else if (url.pathname.endsWith('/dashboard/overview')) data = overview;
      else if (url.pathname.endsWith('/dashboard/stats')) {
        data = { bank_receipts_review_count: 2, bank_receipts_review: [], expiring_contracts: [], upcoming_touchpoints: [] };
      } else if (url.pathname.includes('counter')) data = { count: 3 };
      else if (url.pathname.includes('rebuild')) data = { needs_rebuild: false, state: 'idle' };
      await route.fulfill({ json: data });
    });
    const button = name => page.getByRole('button', { name, exact: true });
    const ready = () => page.getByText('Оплаты за месяц', { exact: true }).waitFor();
    const capture = name => page.screenshot({ path: path.join(out, `${prefix}-${name}.png`), animations: 'disabled' });
    const checkWidth = async () => {
      const size = await page.evaluate(() => ({ width: innerWidth, scroll: document.documentElement.scrollWidth }));
      dimensions.push(size);
      assert(size.scroll <= size.width, `Horizontal overflow: ${JSON.stringify(size)}`);
    };
    await page.goto(`${base}/manager/`);
    await ready();
    await capture('desktop-light');
    if (prefix === 'before') return;

    await button('Тёмная тема').click();
    await capture('desktop-dark');
    await page.reload();
    await ready();
    assert(await page.locator('html').evaluate(element => element.classList.contains('dark')));
    await button('Светлая тема').click();
    await button('Свернуть меню').click();
    await capture('collapsed');
    await button('Развернуть меню').click();

    for (const width of [1440, 1280, 768, 390, 320]) {
      await page.setViewportSize({ width, height: 1080 });
      await checkWidth();
      await capture(String(width));
    }
    await page.setViewportSize({ width: 390, height: 844 });
    await button('Открыть меню').click();
    await capture('mobile-menu');
    await page.keyboard.press('Escape');
    assert(await button('Открыть меню').evaluate(element => element === document.activeElement));
    await page.getByRole('button', { name: /Аккаунт:/ }).click();
    await capture('mobile-account');
    await page.keyboard.press('Escape');

    // 640 CSS px is the viewport equivalent of a 1280 px window at 200% zoom.
    // Also check enlarged root text independently of the browser zoom control.
    await page.setViewportSize({ width: 640, height: 540 });
    await page.evaluate(() => { document.documentElement.style.fontSize = '20px'; });
    await checkWidth();
    await capture('zoom');
    await page.evaluate(() => { document.documentElement.style.fontSize = ''; });
    await page.setViewportSize({ width: 1440, height: 1080 });
    await button('Переключиться: Демо филиал, Брест').click();
    await page.waitForFunction(() => document.title === 'Демо филиал · KitLane');
    await ready();
    await capture('context-switch');
    stores[1].display_name = 'Демонстрационная компания с очень длинным названием';
    await page.reload();
    await ready();
    await checkWidth();
    await capture('long-name');

    for (const [name, file] of [['Сайт и SEO', 'site-seo'], ['Реклама', 'advertising']]) {
      await page.getByRole('tab', { name, exact: true }).click();
      await capture(file);
    }
    await page.getByRole('button', { name: /Аккаунт:/ }).click();
    await page.getByRole('menuitem', { name: 'Выйти', exact: true }).click();
    await page.getByRole('heading', { name: 'Вход в менеджер', exact: true }).waitFor();
    assert.equal(await page.title(), 'KitLane');
    await capture('login');
    await page.evaluate(() => document.documentElement.classList.add('dark'));
    await capture('login-dark');
    await page.goto(`${base}/manager/tests/visual/kitlane/brands.html`);
    await page.getByText('Проверка брендов · только синтетические данные').waitFor();
    await capture('logo-fixtures');
    assert.deepEqual(errors, []);
    fs.writeFileSync(path.join(out, 'results.json'), JSON.stringify({ errors, dimensions }, null, 2));
    console.log({ errors, dimensions });
  } finally {
    await browser.close();
  }
}
run().catch(error => { console.error(error); process.exitCode = 1; });
