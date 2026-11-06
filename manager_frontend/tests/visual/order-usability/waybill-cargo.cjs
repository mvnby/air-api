// Exercise the standard Manager draft workflow using a private synthetic shipment.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require(process.env.KITLANE_PLAYWRIGHT_MODULE || 'playwright');
const { createFixtureServer } = require('../proposal-mail/server.cjs');

const port = Number(process.env.KITLANE_FIXTURE_PORT || 5238);
const origin = 'http://127.0.0.1:' + port;
const output = process.env.KITLANE_SCREENSHOTS || '/tmp/waybill-cargo-screens';
const draft = { id: 863, order_id: 590, proposal_id: 586, legal_entity_id: 5, doc_type: 'ttn1', status: 'draft',
  provider: 'native', date: '2026-11-06', created_at: '2026-11-06', artifacts: [], template_version_id: 101 };
const fixture = createFixtureServer(port, async (req, res, { state, url, body, json }) => {
  const endpoint = url.pathname;
  if (endpoint.endsWith('/orders/590/request-context')) json(res, { sources: [], files: [], warnings: [] });
  else if (endpoint.endsWith('/orders/590/documents/drafts')) {
    state.creates.push(await body(req));
    state.documents.unshift(draft);
    json(res, draft);
  } else if (endpoint.endsWith('/documents/863/draft/parameters')) {
    const rows = [
      { line_number: 1, title: 'Внутренний блок системы кондиционирования с расширенным названием модели', quantity: '4', unit: 'шт.' },
      { line_number: 2, title: 'Наружный блок', quantity: '2', unit: 'шт.' },
    ];
    if (req.method === 'PATCH') {
      const payload = await body(req);
      state.cargo = payload.waybill_cargo;
      json(res, draft);
    } else json(res, { issue_date: '2026-11-06', revision: 'a'.repeat(64), template_version_id: 101, has_editable_copy: false,
      total_amount: '3000.00', waybill_cargo: rows.map((r, i) => ({ seats: null, mass_kg: null, ...r, ...state.cargo?.[i] })) });
  } else return false;
  return true;
});

async function inspect(browser, width) {
  await fetch(origin + '/__fixture/reset?kind=mixed&documents=false');
  const state = fixture.getState();
  state.documents.push({ ...draft, id: 862, doc_type: 'contract', status: 'issued', official_full_number: 'Д-026' });
  const context = await browser.newContext({ viewport: { width, height: 860 }, serviceWorkers: 'block' });
  const page = await context.newPage();
  page.setDefaultTimeout(10000);
  await context.route('**/*', route => new URL(route.request().url()).origin === origin ? route.continue() : route.abort());
  try {
    await page.goto(origin + '/manager/orders/590?company=999&site=minsk&proposalId=586');
    await page.getByRole('navigation', { name: 'Рабочая область заказа' }).getByRole('button', { name: 'Документы', exact: true }).click();
    await page.getByTestId('native-document-type-ttn1').click();
    await page.getByTestId('native-document-basis').selectOption('document:862');
    await page.getByTestId('create-native-draft').click();
    const card = page.getByTestId('current-document-863');
    const cargo = card.getByTestId('waybill-cargo');
    await cargo.waitFor();
    assert.equal(state.creates[0].document_type, 'ttn1');
    assert.equal(await cargo.getByLabel('Масса, кг').first().inputValue(), '');
    await cargo.getByLabel('Грузовые места', { exact: true }).first().fill('1');
    await cargo.getByLabel('Масса, кг').first().fill('34.5');
    await cargo.getByLabel('Грузовые места', { exact: true }).last().fill('2');
    await cargo.getByLabel('Масса, кг').last().fill('54.5');
    for (const input of await cargo.getByRole('spinbutton').all()) {
      const box = await input.boundingBox();
      assert(box && box.x >= 0 && box.x + box.width <= width + 1);
    }
    await cargo.screenshot({ path: path.join(output, width + '-cargo.png') });
    await card.getByTestId('save-draft-parameters').click();
    await cargo.waitFor({ state: 'hidden' });
    assert.deepEqual(state.cargo, [{ line_number: 1, seats: 1, mass_kg: '34.5' }, { line_number: 2, seats: 2, mass_kg: '54.5' }]);
    await card.getByRole('button', { name: 'Груз и параметры' }).click();
    assert.equal(await cargo.getByLabel('Масса, кг').last().inputValue(), '54.5');
    console.log(width + 'px: frozen lines, measurement inputs and draft update OK');
  } catch (error) {
    console.error((await page.locator('body').innerText()).slice(-700));
    throw error;
  } finally { await context.close(); }
}
(async () => {
  fs.mkdirSync(output, { recursive: true });
  await new Promise(resolve => fixture.server.listen(port, '127.0.0.1', resolve));
  let browser;
  try {
    browser = await chromium.launch({ headless: true, executablePath: process.env.KITLANE_CHROMIUM_PATH });
    for (const width of [320, 390, 1440]) await inspect(browser, width);
  } finally { await browser?.close(); fixture.server.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
