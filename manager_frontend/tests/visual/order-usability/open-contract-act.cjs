// Real Manager bundle, isolated fixture API, no production writes.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require(process.env.KITLANE_PLAYWRIGHT_MODULE || 'playwright');
const { createFixtureServer } = require('../proposal-mail/server.cjs');

const port = Number(process.env.KITLANE_FIXTURE_PORT || 5228);
const origin = `http://127.0.0.1:${port}`;
const output = process.env.KITLANE_SCREENSHOTS || '/tmp/open-contract-act-screens';
const previous = { id: 901, order_id: 550, number: 'А-2026-086', url: null };
const readiness = { checked: true, can_issue: true, missing_fields: [], template_id: 100, template_version_id: 101 };
const fixture = createFixtureServer(port, async (req, res, { url, state, json, body }) => {
  const endpoint = url.pathname;
  if (endpoint === '/api/manager/orders/590/request-context') {
    json(res, { sources: [], files: [], warnings: [] });
  } else if (endpoint === '/api/manager/customers/541/contracts') {
    json(res, { items: [{ id: 71, customer_id: 541, number: 'ОД-2026-001', status: 'active',
      valid_from: '2020-04-25', valid_until: '2099-04-25', document_role_type: null }] });
  } else if (endpoint === '/api/manager/customers/541/branches') {
    json(res, { items: [{ id: 81, customer_id: 541, name: 'Магазин', delivery_address: 'Витебск, ул. Кирова, 2' }] });
  } else if (endpoint.endsWith('/documents/readiness') || endpoint.endsWith('/documents/863/readiness')) {
    json(res, readiness);
  } else if (endpoint.endsWith('/orders/590/documents/drafts')) {
    const payload = await body(req);
    state.creates.push(payload);
    state.documents = [{ id: 863, order_id: 590, doc_type: 'act', status: 'draft', provider: 'native', display_number: '',
      base_customer_contract_id: payload.base_customer_contract_id, date: '2026-11-05', created_at: '2026-11-05', artifacts: [] }];
    json(res, state.documents[0]);
  } else if (endpoint.endsWith('/documents/863/issue')) {
    if (url.searchParams.get('confirmed_previous_act_number') !== '21') {
      json(res, { detail: { error_code: 'contract_act_number_confirmation_required', previous_act: previous } }, 409);
    } else {
      assert.equal(url.searchParams.get('expected_previous_act_id'), '901');
      Object.assign(state.documents[0], { status: 'issued', official_full_number: 'А-2026-087', contract_act_number: 22 });
      json(res, state.documents[0]);
    }
  } else {
    return false;
  }
  return true;
});

async function checkViewport(browser, width) {
  const context = await browser.newContext({ viewport: { width, height: width < 500 ? 844 : 960 }, serviceWorkers: 'block' });
  await context.route('**/*', route => new URL(route.request().url()).origin === origin ? route.continue() : route.abort());
  const page = await context.newPage();
  page.setDefaultTimeout(12000);
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  try {
    await fetch(`${origin}/__fixture/reset?kind=maintenance&documents=false`);
    const state = fixture.getState();
    const lines = state.order.proposals[0].service_lines;
    lines.push({ ...lines[0], id: 30, service_title: 'Дополнительная диагностика на другом объекте' });
    await page.goto(`${origin}/manager/orders/590?company=999&site=minsk&proposalId=586`);
    await page.getByRole('navigation', { name: 'Рабочая область заказа' }).getByRole('button', { name: 'Документы', exact: true }).click();
    await page.getByTestId('native-document-type-act').click();
    const basis = page.getByTestId('native-document-basis');
    await basis.locator('option[value="customer-contract:71"]').waitFor({ state: 'attached' });
    assert.equal(await basis.inputValue(), 'customer-contract:71');
    const create = page.getByTestId('create-native-draft');
    assert.equal(await create.isEnabled(), false);
    await page.getByTestId('native-document-party-roles').selectOption('executor_customer');
    const composition = page.getByTestId('native-act-composition');
    await composition.getByTestId('act-site').selectOption('81');
    await composition.getByRole('checkbox', { name: 'Дополнительная диагностика на другом объекте' }).uncheck();
    await composition.getByRole('spinbutton', { name: 'Количество: Техническое обслуживание' }).fill('1');
    await composition.scrollIntoViewIfNeeded();
    for (const control of await composition.locator('select,input').all()) {
      const box = await control.boundingBox();
      assert(box && box.x >= 0 && box.x + box.width <= width + 1, `Act control exceeds ${width}px`);
    }
    await page.screenshot({ path: path.join(output, `${width}-composition.png`), animations: 'disabled' });
    await create.click();
    const draft = page.getByTestId('current-document-863');
    await draft.getByRole('button', { name: 'Выпустить', exact: true }).click();
    assert.deepEqual(state.creates[0].scope_service_line_quantities, { 1: 1 });
    assert.equal(state.creates[0].scope_customer_branch_id, 81);
    assert.equal(state.creates[0].scope_address, 'Витебск, ул. Кирова, 2');
    assert.equal(state.creates[0].base_customer_contract_id, 71);
    const panel = page.getByTestId('contract-act-number-confirmation');
    await panel.getByTestId('previous-act-number').fill('21');
    await panel.getByRole('button', { name: 'Выпустить акт №22' }).scrollIntoViewIfNeeded();
    await page.screenshot({ path: path.join(output, `${width}-number.png`), animations: 'disabled' });
    assert(await panel.evaluate(el => el.scrollWidth <= el.clientWidth + 1));
    await panel.getByRole('button', { name: 'Выпустить акт №22' }).click();
    await draft.getByRole('heading', { name: /Акт №22.*А-2026-087/ }).waitFor();
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth));
    assert.deepEqual(errors, []);
    console.log(`${width}px: contract, partial works, issue confirmation and both numbers verified`);
  } catch (error) {
    console.error({ width, url: page.url(), errors, pageText: (await page.locator('body').innerText()).slice(-750) });
    await page.screenshot({ path: path.join(output, `${width}-failure.png`), animations: 'disabled' });
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
    for (const width of [320, 390, 1440]) await checkViewport(browser, width);
  } finally {
    await browser?.close();
    fixture.server.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
