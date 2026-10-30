// Real production build, synthetic localhost data; no production/customer writes.
const { chromium } = require(process.env.KITLANE_PLAYWRIGHT_MODULE || 'playwright');
const { createFixtureServer } = require('../order-request/server.cjs');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const output = path.resolve(process.env.KITLANE_SCREENSHOTS || '/tmp/order-usability-acceptance');
fs.mkdirSync(output, { recursive: true });
const fixture = createFixtureServer(Number(process.env.KITLANE_FIXTURE_PORT || 5203));
const base = `http://127.0.0.1:${fixture.port}`;
const orderUrl = `${base}/manager/orders/590?company=999&site=minsk&proposalId=586`;
const sizes = [{ width: 973, height: 684 }, { width: 390, height: 844 }, { width: 320, height: 684 }, { width: 1440, height: 900 }];
const tariffs = Array.from({ length: 8 }, (_, index) => ({ tariff_id: 91 + index, service_kind: 'installation', short_name: `Монтаж ${index + 1}`, title: `Монтаж оборудования — вариант ${index + 1}`, full_description: 'Трасса 3 м, отверстие, подключение и проверка оборудования', price: '600' }));
const checks = [];
let browser;
const near = (actual, expected, label, tolerance = 2) => assert(Math.abs(actual - expected) <= tolerance, `${label}: ${actual} vs ${expected}`);
const box = async locator => { const result = await locator.boundingBox(); assert(result, 'Visible element has geometry'); return result; };
async function targetSize(locator, label) {
  const rect = await box(locator);
  assert(rect.width >= 43 && rect.height >= 43, `${label}: touch target ${JSON.stringify(rect)}`);
}
async function noOverflow(page, width) {
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth), false, 'No document horizontal scrolling');
  const nav = await box(page.getByRole('navigation', { name: 'Рабочая область заказа' }));
  assert(nav.x >= 0 && nav.x + nav.width <= width + 1, 'All tabs fit the screen');
  for (const tab of await page.getByRole('navigation', { name: 'Рабочая область заказа' }).getByRole('button').all()) {
    assert(await tab.evaluate(el => el.scrollWidth <= el.clientWidth + 1), 'Full tab labels fit their controls');
  }
}
async function run(viewport, name, scenario) {
  if (process.env.KITLANE_CASE && process.env.KITLANE_CASE !== name) return;
  await fetch(`${base}/__request/reset?scenario=manual`);
  const state = fixture.getState();
  const context = await browser.newContext({ viewport, isMobile: viewport.width < 768, hasTouch: viewport.width < 768, serviceWorkers: 'block' });
  await context.addInitScript(() => sessionStorage.setItem('manager_order_drawer_sections_590', JSON.stringify({ documents: false, payments: false, proposals: false })));
  await context.route('**/*', route => {
    const url = new URL(route.request().url());
    if (url.origin === base && url.pathname === '/api/manager/tariffs/quick-add') return route.fulfill({ json: { items: tariffs } });
    if (url.origin === base || ['fonts.googleapis.com', 'fonts.gstatic.com'].includes(url.hostname)) return route.continue();
    return route.abort();
  });
  const page = await context.newPage();
  page.setDefaultTimeout(12000);
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  const workspace = page.getByRole('region', { name: 'Рабочая область заказа', exact: true });
  const nav = page.getByRole('navigation', { name: 'Рабочая область заказа', exact: true });
  const shot = async suffix => page.screenshot({ path: path.join(output, `${viewport.width}-${name}-${suffix}.png`), animations: 'disabled' });
  try {
    const result = await scenario({ page, state, workspace, nav, shot, viewport });
    await noOverflow(page, viewport.width);
    assert.deepEqual(errors, [], 'No browser exceptions');
    checks.push({ ...viewport, name, passed: true, ...result });
    console.log(viewport.width, name, 'passed');
  } catch (error) {
    await shot('FAILURE').catch(() => {});
    throw error;
  } finally { await context.close(); }
}
async function load(page, workspace) {
  await page.goto(orderUrl);
  await workspace.getByTestId('add-service-line').waitFor();
  await page.evaluate(() => document.fonts.ready);
}
async function confirmation(page, proceed) {
  const dialog = page.getByRole('dialog').filter({ hasText: 'Применить введённые позиции?' });
  await dialog.waitFor();
  await dialog.getByRole('button', { name: proceed ? 'Применить и сохранить' : 'Продолжить ввод', exact: true }).click();
  await dialog.waitFor({ state: 'hidden' });
}
(async () => {
  await new Promise(resolve => fixture.server.listen(fixture.port, '127.0.0.1', resolve));
  browser = await chromium.launch({ headless: true, ...(process.env.KITLANE_CHROMIUM_PATH ? { executablePath: process.env.KITLANE_CHROMIUM_PATH } : {}) });
  try {
    for (const viewport of sizes) {
      await run(viewport, 'layout', async ({ page, state, workspace, nav, shot }) => {
        const services = Array.from({ length: 12 }, (_, index) => ({ ...state.order.service_lines[0], id: index + 1, service_title: `Комплексное обслуживание кондиционера на объекте ${index + 1}: очистка узлов и проверка работы`, price: 210 }));
        const product = { id: 50, proposal_id: 586, product_id: null, product_title: 'Расходные материалы для обслуживания', quantity: 1, price: 125, cost: 0 };
        state.order.service_lines = state.order.proposals[0].service_lines = services;
        state.order.product_lines = state.order.proposals[0].product_lines = [product];
        await load(page, workspace);
        const scroller = workspace.locator('[data-order-scroll]');
        const content = await box(scroller), header = await box(workspace.locator(':scope > header')), tabs = await box(nav), footer = await box(workspace.locator('footer'));
        assert(content.height >= (viewport.width === 320 ? 300 : 350), `Useful initial workspace height: ${content.height}`);
        assert(footer.height <= 80, `Footer should stay in one row: ${footer.height}`);
        await noOverflow(page, viewport.width);
        for (const selector of ['order_product_edit', 'order_product_remove', 'order_service_edit', 'order_service_remove']) await targetSize(workspace.locator(`[data-order-usage="${selector}"]`).first(), selector);
        await targetSize(workspace.getByTestId('add-product-line'), 'Add product');
        await targetSize(workspace.getByTestId('add-service-line'), 'Add service');
        const controls = workspace.getByTestId('order-context-controls');
        await controls.waitFor({ state: 'visible' });
        await shot('overview');
        await scroller.evaluate(el => { el.scrollTop = 400; });
        await controls.waitFor({ state: 'hidden' });
        await page.waitForTimeout(450); // Existing sticky-header layout compensation interval.
        near((await box(nav)).y, 0, 'Section navigation stays discoverable after shell and identity collapse');
        const compactContent = await box(scroller);
        assert(compactContent.height >= content.height + header.height - 1, 'Downward scroll reclaims the combined order header');
        await shot('scrolled');
        await scroller.evaluate(el => { el.scrollTop = Math.max(0, el.scrollTop - 150); });
        await controls.waitFor({ state: 'visible' });
        await scroller.evaluate(el => { el.scrollTop = 0; });
        await workspace.getByTestId('order-request-trigger').click();
        const request = page.getByRole('region', { name: 'Заявка и файлы', exact: true });
        await request.waitFor();
        const requestBox = await box(request);
        if (viewport.width < 1280) assert(requestBox.width > content.width * .9, 'Request uses full workspace width on constrained screens');
        await shot('request');
        await request.getByRole('button', { name: 'Закрыть заявку и файлы', exact: true }).click();
        await nav.getByRole('button', { name: 'Документы', exact: true }).click();
        await page.getByTestId('native-documents-workspace').waitFor();
        assert.equal(await workspace.locator('#order-workspace-documents > button').count(), 0, 'Dedicated documents tab has no outer collapse control');
        await shot('documents');
        await nav.getByRole('button', { name: 'Оплаты', exact: true }).click();
        await page.getByTestId('payment-amount').waitFor();
        assert.equal(await workspace.locator('#order-workspace-payments > button').count(), 0, 'Dedicated payment tab has no outer collapse control');
        await shot('payments');
        return { geometry: { content, header, tabs, footer, compactContent } };
      });
      await run(viewport, 'drafts', async ({ page, state, workspace, nav, shot }) => {
        await load(page, workspace);
        await workspace.getByTestId('add-product-line').click();
        const productTitle = workspace.getByPlaceholder('Найти в каталоге или ввести название');
        await productTitle.fill('Синтетический товар вручную');
        const productRow = workspace.getByTestId('product-line-row').first();
        await productRow.getByRole('spinbutton', { name: /Цена/ }).fill('350');
        const quantity = productRow.getByRole('spinbutton', { name: /Кол-во/ });
        await quantity.fill('0');
        await nav.getByRole('button', { name: 'Документы', exact: true }).click();
        await confirmation(page, true);
        assert.equal(await nav.getByRole('button', { name: 'Предложение', exact: true }).getAttribute('aria-current'), 'page');
        assert.equal(await quantity.evaluate(el => el === document.activeElement), true, 'Invalid quantity receives keyboard focus');
        assert.equal(state.patches.length, 0, 'Invalid draft is never sent to the API');
        await shot('invalid');
        await quantity.fill('2');
        await nav.getByRole('button', { name: 'Документы', exact: true }).click();
        await confirmation(page, false);
        assert.equal(await productTitle.inputValue(), 'Синтетический товар вручную');
        assert.equal(state.patches.length, 0, 'Cancelling navigation preserves the draft without saving');
        await nav.getByRole('button', { name: 'Документы', exact: true }).click();
        await confirmation(page, true);
        await page.getByTestId('native-documents-workspace').waitFor();
        assert(state.patches.some(patch => JSON.stringify(patch.products || []).includes('Синтетический товар вручную')), 'Applying saves the new product before opening documents');
        await nav.getByRole('button', { name: 'Предложение', exact: true }).click();
        await workspace.getByTestId('add-service-line').click();
        const title = workspace.getByTestId('service-title-input');
        await title.click();
        const suggestions = workspace.getByTestId('service-context-menu');
        await suggestions.getByTestId('select-service-91').waitFor();
        const formWidth = await title.evaluate(el => el.closest('.order-line-form').getBoundingClientRect().width);
        assert((await box(suggestions)).width >= formWidth - 2, 'Service suggestions use the full form width');
        await shot('suggestions');
        await suggestions.getByTestId('select-service-91').click();
        await title.fill('Синтетическая новая услуга');
        await workspace.getByTestId('service-client-description').fill('Проверка сохранения введённого состава работ');
        const actions = workspace.locator('[data-line-editor-actions]').filter({ has: page.getByRole('button', { name: 'Добавить услугу', exact: true }) });
        const commit = actions.getByRole('button', { name: 'Добавить услугу', exact: true }), cancel = actions.getByRole('button', { name: 'Отмена', exact: true });
        const commitBox = await box(commit), scrollBox = await box(workspace.locator('[data-order-scroll]'));
        near(commitBox.y, (await box(cancel)).y, 'Apply and Cancel share one action row');
        assert(commitBox.y >= scrollBox.y - 1 && commitBox.y + commitBox.height <= scrollBox.y + scrollBox.height + 1, 'The active form action remains inside the visible workspace');
        await targetSize(commit, 'Apply service');
        await targetSize(cancel, 'Cancel service');
        await nav.getByRole('button', { name: 'Документы', exact: true }).click();
        await confirmation(page, false);
        assert.equal(await title.inputValue(), 'Синтетическая новая услуга');
        await nav.getByRole('button', { name: 'Документы', exact: true }).click();
        await confirmation(page, true);
        await page.getByTestId('native-documents-workspace').waitFor();
        assert(state.patches.some(patch => JSON.stringify(patch.services || []).includes('Синтетическая новая услуга')), 'Applying saves the new service before opening documents');
        await shot('saved');
        return { savedRequests: state.patches.length };
      });
    }
    await run({ width: 320, height: 684 }, 'invalid-fields', async ({ page, state, workspace, nav, shot }) => {
      await load(page, workspace);
      const fieldChecks = [];
      const assertCorrectable = async (input, suffix) => {
        await page.waitForTimeout(100);
        const field = await box(input), scroll = await box(workspace.locator('[data-order-scroll]'));
        const actionBar = await box(workspace.locator('[data-line-editor-actions]').last());
        const focused = await input.evaluate(el => el === document.activeElement);
        await shot(suffix);
        const visible = field.y >= scroll.y - 1 && field.y + field.height <= Math.min(scroll.y + scroll.height, actionBar.y) + 1;
        fieldChecks.push({ suffix, field, scroll, actionBar, focused, visible });
      };
      await workspace.getByTestId('add-product-line').click();
      const productTitle = workspace.getByPlaceholder('Найти в каталоге или ввести название');
      await productTitle.fill('Синтетический товар с подробными техническими характеристиками и комплектацией. '.repeat(8));
      const productRow = workspace.getByTestId('product-line-row').first();
      await productRow.getByRole('spinbutton', { name: /Цена/ }).fill('350');
      const quantity = productRow.getByRole('spinbutton', { name: /Кол-во/ });
      await quantity.fill('0');
      await productRow.getByRole('button', { name: /^Добавить товар #/ }).click();
      await assertCorrectable(quantity, 'product-direct');
      await nav.getByRole('button', { name: 'Документы', exact: true }).click();
      await confirmation(page, true);
      await assertCorrectable(quantity, 'product-navigation');
      await productRow.getByRole('button', { name: /^Отмена: товар #/ }).click();
      await workspace.getByTestId('add-service-line').click();
      const serviceTitle = workspace.getByTestId('service-title-input');
      await serviceTitle.fill('Подробное техническое обслуживание наружного и внутреннего блоков кондиционера. '.repeat(8));
      const service = workspace.getByRole('region', { name: 'Услуги', exact: true });
      const serviceQuantity = service.getByRole('spinbutton', { name: /Кол-во/ });
      await serviceQuantity.fill('0');
      await service.getByRole('button', { name: 'Добавить услугу', exact: true }).click();
      await assertCorrectable(serviceQuantity, 'service-direct');
      await nav.getByRole('button', { name: 'Документы', exact: true }).click();
      await confirmation(page, true);
      await assertCorrectable(serviceQuantity, 'service-navigation');
      assert.equal(state.patches.length, 0, 'Neither invalid editor submits a request');
      assert(fieldChecks.every(check => check.focused && check.visible), `Each invalid field is focused and visible above the action bar: ${JSON.stringify(fieldChecks)}`);
      return { fieldChecks };
    });
    fs.writeFileSync(path.join(output, 'results.json'), JSON.stringify({ checks }, null, 2));
    console.log(JSON.stringify({ checks: checks.length, output }));
  } finally { await browser?.close(); await new Promise(resolve => fixture.server.close(resolve)); }
})().catch(error => { console.error(error); fixture.server.close(); process.exitCode = 1; });
