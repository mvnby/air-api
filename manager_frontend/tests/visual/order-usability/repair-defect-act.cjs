// Exercise the real Manager UI against an isolated synthetic order.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require(process.env.KITLANE_PLAYWRIGHT_MODULE || 'playwright');
const { createFixtureServer } = require('../proposal-mail/server.cjs');

const port = Number(process.env.KITLANE_FIXTURE_PORT || 5231);
const origin = `http://127.0.0.1:${port}`;
const output = process.env.KITLANE_SCREENSHOTS || '/tmp/repair-defect-act-screens';
const documentType = 'repair_defect_act';
const readiness = { checked: true, can_issue: true, missing_fields: [], template_id: null, template_version_id: null };
const fixture = createFixtureServer(port, async (req, res, { url, state, json, body }) => {
  const endpoint = url.pathname;
  if (endpoint === '/api/manager/orders/591') {
    json(res, { ...state.order, id: 591, title: 'Следующий ремонт', customer: { id: 542, name: 'Другой клиент', type: 'individual' },
      repair_meta: { equipment_model: 'Блок B-12' }, proposals: [], service_lines: [] });
  } else if (endpoint.endsWith('/request-context')) {
    json(res, { sources: [], files: [], warnings: [] });
  } else if (endpoint.endsWith('/document-system/templates') && url.searchParams.get('doc_type') === documentType) {
    json(res, { items: [] });
  } else if (endpoint.endsWith('/documents/readiness') || endpoint.endsWith('/documents/863/readiness')) {
    json(res, readiness);
  } else if (endpoint.endsWith('/documents/863/draft/parameters')) {
    if (req.method === 'PATCH') {
      const payload = await body(req);
      state.documents[0].repair_defect = payload.repair_defect;
      json(res, state.documents[0]);
    } else {
      json(res, { issue_date: '2026-11-05', issue_city: 'Витебск', revision: '1'.repeat(64), template_version_id: 101,
        has_editable_copy: false, repair_defect: state.documents[0].repair_defect });
    }
  } else if (endpoint.endsWith('/orders/590/documents/drafts')) {
    const payload = await body(req);
    state.creates.push(payload);
    state.documents = [{ id: 863, order_id: 590, legal_entity_id: 5, doc_type: documentType, status: 'draft', provider: 'native',
      date: '2026-11-05', created_at: '2026-11-05', artifacts: [], repair_defect: payload.repair_defect }];
    json(res, state.documents[0]);
  } else return false;
  return true;
});

async function inspect(browser, width) {
  const context = await browser.newContext({ viewport: { width, height: width < 500 ? 844 : 960 }, serviceWorkers: 'block' });
  await context.route('**/*', route => new URL(route.request().url()).origin === origin ? route.continue() : route.abort());
  const page = await context.newPage();
  page.setDefaultTimeout(12000);
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  try {
    await fetch(`${origin}/__fixture/reset?kind=repair&documents=false`);
    const state = fixture.getState();
    Object.assign(state.order, {
      workflow_type: 'repair', linked_equipment_count: 0,
      repair_meta: {
        equipment_name: 'Кондиционер', equipment_model: 'Модель A-09', equipment_serial_number: 'T001',
        confirmed_facts: ['Обнаружена утечка в соединении'], repair_recommendation: 'Устранить утечку и проверить герметичность',
        diagnostic_notes: 'Внутренний журнал измерений', promised_date: '2026-12-01', repair_status: 'new',
      },
    });
    await page.goto(`${origin}/manager/orders/590?company=999&site=minsk&proposalId=586`);
    const nav = page.getByRole('navigation', { name: 'Рабочая область заказа' });
    await nav.getByRole('button', { name: 'Ремонт', exact: true }).click();
    const section = page.getByRole('button', { name: /Ремонт \/ диагностика/ });
    if (await section.getAttribute('aria-expanded') === 'false') await section.click();
    await page.getByTestId('open-repair-client-act').click();
    const form = page.getByTestId('repair-defect-fields');
    const field = name => form.getByTestId(`repair-${name}`);
    await form.waitFor();
    assert.equal(await field('verdict').inputValue(), '');
    assert.equal(await field('finding').inputValue(), '');
    assert(await page.getByText('Начальная редактируемая форма', { exact: false }).first().isVisible());
    await form.getByRole('button', { name: 'Подставить результат диагностики из заказа' }).click();
    assert.equal(await field('finding').inputValue(), 'Обнаружена утечка в соединении');
    await field('verdict').selectOption('repairable');
    await form.getByRole('button', { name: 'Подставить рекомендацию из заказа' }).click();
    assert.equal(await field('cost').inputValue(), '');
    assert.equal(await field('term').inputValue(), '');
    if (width === 390) {
      await field('cost').fill('240 BYN');
      await field('term').fill('3 рабочих дня');
    }
    await field('finding').scrollIntoViewIfNeeded();
    for (const control of await form.locator('select,input:visible,textarea').all()) {
      const box = await control.boundingBox();
      assert(box && box.x >= 0 && box.x + box.width <= width + 1, `Control exceeds ${width}px`);
    }
    await form.screenshot({ path: path.join(output, `${width}-form.png`), animations: 'disabled' });
    const create = page.getByTestId('create-native-draft');
    await create.scrollIntoViewIfNeeded();
    await page.screenshot({ path: path.join(output, `${width}-actions.png`), animations: 'disabled' });
    await create.click();
    const card = page.getByTestId('current-document-863');
    await card.getByRole('button', { name: 'Выпустить', exact: true }).waitFor();
    assert.deepEqual(state.creates[0].repair_defect, {
      verdict: 'repairable', equipment: 'Кондиционер Модель A-09 S/N T001', finding: 'Обнаружена утечка в соединении',
      recommendation: 'Устранить утечку и проверить герметичность', restriction: null,
      cost: width === 390 ? '240 BYN' : null, term: width === 390 ? '3 рабочих дня' : null,
    });
    await card.getByRole('button', { name: 'Изменить параметры' }).click();
    const editor = card.getByTestId('repair-defect-fields');
    await editor.getByTestId('repair-verdict').selectOption('uneconomical');
    assert.equal(await editor.getByTestId('repair-cost').inputValue(), '');
    await editor.getByTestId('repair-recommendation').fill('Заменить блок');
    await card.getByTestId('save-draft-parameters').click();
    await editor.waitFor({ state: 'detached' });
    assert.equal(state.documents[0].repair_defect.recommendation, 'Заменить блок');
    await field('verdict').selectOption('repairable');
    await field('cost').fill('100 BYN');
    await field('finding').fill('Первый заказ');
    // Switch orders in the active Manager tab, preserving the SPA instance.
    await page.evaluate(() => {
      history.pushState({}, '', '/manager/orders/591?company=999&site=minsk');
      window.dispatchEvent(new PopStateEvent('popstate'));
    });
    await page.getByRole('button', { name: 'Изменить название: Следующий ремонт', exact: true }).waitFor();
    await nav.getByRole('button', { name: 'Документы', exact: true }).click();
    await form.waitFor();
    assert.equal(await field('equipment').inputValue(), 'Блок B-12');
    for (const id of ['verdict', 'finding', 'recommendation', 'cost', 'term']) assert.equal(await field(id).inputValue(), '');
    assert.equal(await page.getByTestId('current-document-863').count(), 0);
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth));
    assert.deepEqual(errors, []);
    console.log(`${width}px: repair shortcut, fields, draft, edit, and order isolation OK`);
  } catch (error) {
    console.error({ width, url: page.url(), errors, text: (await page.locator('body').innerText()).slice(-900) });
    await page.screenshot({ path: path.join(output, `${width}-failure.png`), animations: 'disabled' });
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
  } finally {
    await browser?.close();
    fixture.server.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
