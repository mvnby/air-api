// Built Manager UI with synthetic order, customer equipment and supplied parts.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require(process.env.KITLANE_PLAYWRIGHT_MODULE || 'playwright');
const { createFixtureServer } = require('../proposal-mail/server.cjs');
const port = Number(process.env.KITLANE_FIXTURE_PORT || 5248);
const origin = `http://127.0.0.1:${port}`;
const output = process.env.KITLANE_SCREENSHOTS || '/tmp/mvn-consumer-work-composition';
const fixture = createFixtureServer(port, async (_req, res, { url, json }) => {
  if (url.pathname.endsWith('/document-system/legal-entities')) {
    json(res, { items: [{ id: 5, tenant_id: 999, display_name: 'Исполнитель', is_default: true, status: 'active',
      requisites: { city: 'Витебск', offer_url: 'https://offer.example.test', offer_version: '1', offer_published_on: '01.01.2026' } }] });
  } else if (url.pathname.endsWith('/request-context')) json(res, { sources: [], files: [], warnings: [] });
  else return false;
  return true;
});

async function checkWidth(browser, width) {
  await fetch(`${origin}/__fixture/reset?kind=mixed&documents=false`);
  const state = fixture.getState();
  state.order.customer.type = 'individual';
  const proposal = state.order.proposals.find(item => item.id === 586);
  const equipment = { ...proposal.product_lines[0], product_title: 'Кондиционер заказчика', line_total: 1000, price: 1000, id: 10 };
  const material = { ...equipment, id: 11, product_title: 'Комплект материалов для подключения внутреннего и наружного блока', quantity: 3, line_total: 75, price: 25 };
  Object.assign(proposal, { product_lines: [equipment, material], service_lines: [{
    ...proposal.service_lines[0], service_title: 'Монтаж оборудования заказчика', quantity: 1, price: 500, line_total: 500 }] });
  const context = await browser.newContext({ viewport: { width, height: 850 }, serviceWorkers: 'block' });
  try {
    await context.route('**/*', route => new URL(route.request().url()).origin === origin ? route.continue() : route.abort());
    const page = await context.newPage();
    page.setDefaultTimeout(12000);
    const errors = [];
    page.on('pageerror', err => errors.push(err.message));
    await page.goto(`${origin}/manager/orders/590?company=999&site=minsk&proposalId=586`);
    await page.getByRole('navigation', { name: 'Рабочая область заказа' }).getByRole('button', { name: 'Документы', exact: true }).click();
    for (const type of ['b2c_customer_equipment_installation_act', 'b2c_maintenance_repair_act']) {
      await page.getByTestId(`native-document-type-${type}`).click();
      const create = page.getByTestId('create-native-draft');
      const composition = page.getByTestId('consumer-work-composition');
      await composition.waitFor();
      assert.equal(await create.isEnabled(), false);
      await page.getByTestId('consumer-work-only').check();
      assert.match(await page.getByTestId('consumer-act-total').innerText(), /500,00/);
      await page.getByTestId('consumer-material-11').check();
      assert.match(await page.getByTestId('consumer-act-total').innerText(), /575,00/);
      assert.equal(await page.getByTestId('consumer-material-10').isChecked(), false);
      if (type === 'b2c_customer_equipment_installation_act') {
        await page.getByTestId('installation-two-stages-toggle').click();
        assert.equal(await page.getByTestId('installation-first-stage-amount').inputValue(), '475.00');
        assert.equal(await page.getByTestId('installation-second-stage-amount').inputValue(), '100.00');
      }
      await composition.scrollIntoViewIfNeeded();
      for (const control of await composition.locator('label,input,li,p').all()) {
        const box = await control.boundingBox();
        assert(box && box.x >= 0 && box.x + box.width <= width + 1, `Overflow at ${width}px`);
      }
      if (type === 'b2c_customer_equipment_installation_act') {
        await composition.screenshot({ path: path.join(output, `${width}-composition.png`), animations: 'disabled' });
        await page.screenshot({ path: path.join(output, `${width}-page.png`), animations: 'disabled' });
      }
      await Promise.all([page.waitForResponse(r => r.url().endsWith('/documents/drafts') && r.request().method() === 'POST'), create.click()]);
      assert.deepEqual(state.creates.at(-1).scope_product_line_ids, [11]);
      assert.equal(state.creates.at(-1).document_type, type);
    }
    assert.deepEqual(errors, []);
    console.log(`${width}px: work act and service act, confirmed materials, stage totals and draft payload OK`);
  } finally { await context.close(); }
}
(async () => {
  fs.mkdirSync(output, { recursive: true });
  await new Promise(resolve => fixture.server.listen(port, '127.0.0.1', resolve));
  let browser;
  try {
    browser = await chromium.launch({ headless: true, executablePath: process.env.KITLANE_CHROMIUM_PATH });
    for (const width of [320,390,1440]) await checkWidth(browser,width);
  } finally { await browser?.close(); fixture.server.close(); }
})().catch(err => { console.error(err); process.exitCode = 1; });
