// Exercise both native sale forms against the built Manager and a local fixture API.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require(process.env.KITLANE_PLAYWRIGHT_MODULE || 'playwright');
const { createFixtureServer } = require('../proposal-mail/server.cjs');

const port = Number(process.env.KITLANE_FIXTURE_PORT || 5241);
const origin = `http://127.0.0.1:${port}`;
const output = process.env.KITLANE_SCREENSHOTS || '/tmp/mvn-sale-document-screens';
const fixture = createFixtureServer(port, async (_req, res, { url, json }) => {
  const p = url.pathname;
  if (p.endsWith('/equipment-links')) json(res, { items: [{ role: 'sale', equipment: {
    id: 18, customer_id: 541, catalog_product_id: 10, display_name: 'Сплит-система с удлинённым названием настенного внутреннего блока',
    serial: 'ST-2026-ABC-456', created_at: '2026-06-01' } }] });
  else if (p.endsWith('/documents/readiness')) json(res, { checked: true, can_issue: true, missing_fields: [], template_id: null, template_version_id: null });
  else if (p.endsWith('/request-context')) json(res, { sources: [], files: [], warnings: [] });
  else if (p.endsWith('/document-system/legal-entities')) json(res, { items: [{ id: 5, tenant_id: 999,
    display_name: 'Продавец', is_default: true, status: 'active', requisites: { city: 'Витебск', offer_url: 'https://offer.example.test',
      offer_version: '1', offer_published_on: '01.01.2026' } }] });
  else if (p.endsWith('/document-system/templates')) json(res, { items: [] });
  else return false;
  return true;
});

async function checkWidth(browser, width) {
  await fetch(`${origin}/__fixture/reset?kind=mixed&documents=false`);
  const state = fixture.getState();
  Object.assign(state.order.customer, { type: 'individual', name: 'Покупатель', full_legal_name: '', inn: null });
  const context = await browser.newContext({ viewport: { width, height: 860 }, serviceWorkers: 'block' });
  try {
    await context.route('**/*', route => new URL(route.request().url()).origin === origin ? route.continue() : route.abort());
    const page = await context.newPage();
    page.setDefaultTimeout(10000);
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(`${origin}/manager/orders/590?company=999&site=minsk&proposalId=586`);
    await page.getByRole('navigation', { name: 'Рабочая область заказа' }).getByRole('button', { name: 'Документы', exact: true }).click();
    for (const type of ['retail_receipt', 'warranty_certificate']) {
      await page.getByTestId(`native-document-type-${type}`).click();
      if (type === 'retail_receipt') await page.getByTestId('receipt-note').fill('Пуск после отделки');
      else await page.getByTestId('warranty-equipment').selectOption('18');
      const create = page.getByTestId('create-native-draft');
      await create.scrollIntoViewIfNeeded();
      assert.equal(await create.isEnabled(), true);
      const controls = page.locator('[data-testid="native-document-type"] button,[data-testid="receipt-note"],[data-testid="warranty-equipment"],[data-testid="create-native-draft"]');
      for (const control of await controls.all()) {
        const box = await control.boundingBox();
        assert(box && box.x >= 0 && box.x + box.width <= width + 1, `control width ${width}`);
      }
      await page.getByTestId('native-document-type').scrollIntoViewIfNeeded();
      await page.getByText('Черновик создан', { exact: true }).waitFor({ state: 'hidden' });
      await page.screenshot({ path: path.join(output, `${width}-${type}.png`), animations: 'disabled' });
      await Promise.all([
        page.waitForResponse(response => response.url().endsWith('/documents/drafts') && response.request().method() === 'POST'),
        create.click(),
      ]);
      const payload = state.creates.at(-1);
      assert.equal(payload?.document_type, type);
      assert.equal(payload?.proposal_id, 586);
      if (type === 'warranty_certificate') assert.equal(payload.warranty_equipment_id, 18);
      else assert.equal(payload.receipt_note, 'Пуск после отделки');
    }
    assert.deepEqual(errors, []);
  } finally { await context.close(); }
}

(async () => {
  fs.mkdirSync(output, { recursive: true });
  await new Promise(resolve => fixture.server.listen(port, '127.0.0.1', resolve));
  let browser;
  try {
    browser = await chromium.launch({ headless: true, executablePath: process.env.KITLANE_CHROMIUM_PATH });
    for (const width of [320, 390, 1024, 1440]) await checkWidth(browser, width);
  } finally { await browser?.close(); fixture.server.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
