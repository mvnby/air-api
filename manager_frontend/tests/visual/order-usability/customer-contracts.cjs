// Verify the real customer document tab using synthetic local records.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require(process.env.KITLANE_PLAYWRIGHT_MODULE || 'playwright');
const { createFixtureServer } = require('../proposal-mail/server.cjs');

const port = Number(process.env.KITLANE_FIXTURE_PORT || 5232);
const origin = `http://127.0.0.1:${port}`;
const output = process.env.KITLANE_SCREENSHOTS || '/tmp/registry-contract-screens';
const base = { customer_id: 541, number: 'ОД-2026-001', valid_from: '2026-04-25', valid_until: '2099-04-25',
  status: 'active', can_delete: false, document_role_type: null, legal_entity_id: null };
let selected, payload;
const fixture = createFixtureServer(port, async (req, res, { url, state, json, body }) => {
  if (url.pathname === '/api/manager/customers/541') {
    json(res, { ...state.order.customer, branches: [], order_count: 3 });
  } else if (url.pathname === '/api/manager/customers/541/contracts') {
    json(res, { items: [
      { ...base, ...selected, id: 21, edit_url: 'https://docs.google.com/document/d/example/edit' },
      { ...base, id: 22, number: 'РД-2026-001', source_document_id: 855, source_order_id: 590, legal_entity_id: 5, document_role_type: 'executor_customer' },
      { ...base, id: 23, number: 'ОД-2024-005', valid_until: '2025-04-25', status: 'archived' },
    ] });
  } else if (url.pathname === '/api/manager/customers/541/contracts/21' && req.method === 'PATCH') {
    payload = await body(req);
    selected = { ...payload };
    json(res, { ...base, ...selected, id: 21 });
  } else {
    return false;
  }
  return true;
});

async function exercise(browser, width) {
  selected = null;
  payload = null;
  const context = await browser.newContext({ viewport: { width, height: 860 }, serviceWorkers: 'block' });
  await context.route('**/*', route => new URL(route.request().url()).origin === origin ? route.continue() : route.abort());
  const page = await context.newPage();
  page.setDefaultTimeout(12000);
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  try {
    await page.goto(`${origin}/manager/customers/profile?customerId=541&company=999&site=minsk`);
    await page.getByRole('navigation', { name: 'Разделы клиента' }).getByRole('button', { name: 'Документы' }).click();
    const register = page.getByTestId('customer-contract-register');
    const legacy = register.getByTestId('contract-row-21');
    const native = register.getByTestId('contract-row-22');
    const target = new URL(await native.getByRole('link').getAttribute('href'), origin);
    assert.equal(target.pathname, '/manager/orders/590');
    assert.equal(target.searchParams.get('section'), 'documents');
    assert.equal(await native.getByRole('button', { name: 'Изменить стороны' }).count(), 0);
    assert.equal(await register.getByRole('button', { name: 'Удалить договор' }).count(), 0);
    await register.scrollIntoViewIfNeeded();
    await page.screenshot({ path: path.join(output, `${width}-register.png`) });
    await legacy.getByRole('button', { name: 'Изменить стороны' }).click();
    await legacy.getByLabel('Наше юрлицо или ИП').selectOption('5');
    await legacy.getByLabel('Названия сторон').selectOption('executor_customer');
    const save = legacy.getByRole('button', { name: 'Сохранить стороны' });
    await save.scrollIntoViewIfNeeded();
    await page.screenshot({ path: path.join(output, `${width}-parties.png`) });
    assert(await register.evaluate(el => el.scrollWidth <= el.clientWidth + 1));
    for (const field of await legacy.locator('select, button:visible, a:visible').all()) {
      const box = await field.boundingBox();
      assert(box && box.x >= 0 && box.x + box.width <= width + 1, 'Control fits the viewport');
      if (width <= 390) assert(box.height >= 43, 'Touch target remains accessible');
    }
    await save.click();
    await legacy.getByText('Мастер Воздуха · Исполнитель / Заказчик').waitFor();
    assert.deepEqual(payload, { legal_entity_id: 5, document_role_type: 'executor_customer' });
    assert.deepEqual(errors, []);
    console.log(`${width}px: sources, links, edit parties and protected delete verified`);
  } catch (error) {
    console.error({ width, page: (await page.locator('body').innerText()).slice(-1200), errors });
    await page.screenshot({ path: path.join(output, `${width}-failure.png`) });
    throw error;
  } finally {
    await context.close();
  }
}

(async () => {
  fs.mkdirSync(output, { recursive: true });
  await new Promise(resolve => fixture.server.listen(port, '127.0.0.1', resolve));
  let browser;
  try {
    browser = await chromium.launch({ headless: true, executablePath: process.env.KITLANE_CHROMIUM_PATH });
    for (const width of [320, 390, 1440]) await exercise(browser, width);
  } finally {
    await browser?.close();
    fixture.server.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
