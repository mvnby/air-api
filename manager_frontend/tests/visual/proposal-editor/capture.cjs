// Production-build acceptance on synthetic data only. No request reaches a real API.
const { chromium } = require(process.env.KITLANE_PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { auth, stores } = require('../kitlane/fixtures.json');
const base = process.env.KITLANE_PREVIEW_URL || 'http://127.0.0.1:5197';
assert(['127.0.0.1', 'localhost'].includes(new URL(base).hostname));
const output = path.resolve(process.env.KITLANE_SCREENSHOTS || '/tmp/proposal-editor-acceptance');
fs.mkdirSync(output, { recursive: true });
const checks = [];
const makeOrder = () => {
  const products = Array.from({ length: 7 }, (_, i) => ({ id: 101 + i, proposal_id: 24, product_id: 501 + i, product_title: i ? `Кондиционер для помещения ${i + 1}` : 'Каталожный товар — сохранить без изменений', client_description: 'Инвертор, стандартная комплектация', quantity: 1, price: 1500, cost: 900, catalog_price: 1500, line_total: 1500 }));
  return { id: 477, title: 'Предварительная смета — тест редактора', status: 'negotiation', lead_source: 'manager', workflow_type: 'sales_installation', negotiation_status: 'awaiting_offer', execution_status: 'needs_schedule', created_at: '2026-10-23T08:00:00Z', is_paid: false, total_amount: 10500, total_cost: 6300, margin: 4200, total_payments: 0, balance_due: 10500, payments: [], documents: [], product_lines: products, service_lines: [], work_stages: [], attachment_count: 0,
    customer: { id: 12, name: 'Тестовый заказчик', type: 'company' },
    proposals: [
      { id: 24, name: 'Основное', status: 'draft', is_selected: true, is_archived: false, product_lines: products, service_lines: [], total_amount: 10500 },
      { id: 25, name: 'Альтернатива', status: 'draft', is_selected: false, is_archived: false, product_lines: [{ ...products[0], id: 201, proposal_id: 25, quantity: 3, price: 1200 }], service_lines: [], total_amount: 3600 },
    ] };
};
async function fixture(browser, width, height) {
  const context = await browser.newContext({ viewport: { width, height }, serviceWorkers: 'block', isMobile: width < 768, hasTouch: width < 768 });
  const page = await context.newPage();
  page.setDefaultTimeout(10000);
  let current = structuredClone(makeOrder()), nextId = 1000;
  const attempts = [], errors = [];
  page.on('pageerror', e => { errors.push(e.message); console.error(e.message); });
  await context.route('**/*', async route => {
    const url = new URL(route.request().url());
    if (url.origin !== base) return route.abort();
    if (!url.pathname.startsWith('/api') && !url.pathname.startsWith('/login')) return route.continue();
    let data = { items: [], total: 0, page: 1, limit: 100, meta: { pages: 1 }, enabled: false };
    if (url.pathname === '/api/manager/account/companies') data = { staff_user_id: 999, username: auth.username, is_platform_owner: true, default_tenant_id: 999, items: [{ tenant_id: 999, slug: 'test', display_name: 'Тестовая компания', role: 'owner', membership_id: 999, access_kind: 'membership', is_system: true, demo_read_only: false, default_storefront_slug: 'minsk' }], total: 1, page: 1, limit: 100 };
    else if (url.pathname.endsWith('/me')) data = { ...auth, capabilities: [...auth.capabilities, 'worker.pay.read', 'worker.pay.manage'] };
    else if (url.pathname.endsWith('/storefronts')) data = { items: stores.map(store => ({ ...store, id: store.slug === 'minsk' ? 999 : 998 })) };
    else if (url.pathname === '/api/manager/orders/477') {
      if (route.request().method() === 'PATCH') {
        const payload = route.request().postDataJSON(); attempts.push(payload);
        const target = current.proposals.find(p => p.id === payload.line_proposal_id);
        const { products, services, line_proposal_id, ...form } = payload;
        current = { ...current, ...form };
        for (const [incoming, field] of [[products, 'product_lines'], [services, 'service_lines']]) if (incoming) {
          assert(target, 'Every line write is scoped to a proposal');
          const known = new Set(target[field].map(line => line.id));
          assert(incoming.every(line => !line.link_id || known.has(line.link_id)));
          target[field] = incoming.map(line => ({ ...line, id: line.link_id ?? nextId++, proposal_id: target.id,
            product_title: line.product_id ? target.product_lines.find(old => old.product_id === line.product_id)?.product_title || 'Каталожный кондиционер' : line.title,
            service_title: line.title, line_total: line.price * line.quantity }));
        }
        const selected = current.proposals.find(p => p.is_selected);
        current.product_lines = selected.product_lines; current.service_lines = selected.service_lines;
      }
      data = current;
    }
    else if (url.pathname.endsWith('/request-context')) data = { order_id: 477, sources: [], files: [], warnings: [] };
    else if (url.pathname.endsWith('/installer-workspace')) data = { order_id: 477, assignments: [], materials: [], collection: { version: 1, assignment_id: null, amount: null, currency: null, status: 'not_assigned', updated_at: null }, balances: [], financial_fingerprint: 'synthetic' };
    else if (url.pathname.endsWith('/worker-pay')) data = { order_id: 477, agreements: [], candidates: [], can_manage: true };
    else if (url.pathname.endsWith('/tender-workflow')) data = { order_id: 477, stage: null, deadline_at: null, price_enquiry: null, publications: [], history: [] };
    else if (url.pathname === '/api/manager/calendar/events') data = [];
    else if (url.pathname === '/api/manager/customers/12') data = current.customer;
    else if (/smart-search/.test(url.pathname)) data = [];
    return route.fulfill({ status: 200, json: data });
  });
  await page.goto(`${base}/manager/orders/477?company=999&site=minsk&proposalId=24&returnTo=%2Fmanager%2Forders%3Fsegment%3Db2b`);
  const workspace = page.getByRole('region', { name: 'Рабочая область заказа', exact: true });
  await workspace.getByTestId('add-product-line').waitFor();
  return { page, context, workspace, attempts, errors, current: () => current };
}

(async () => {
  const browser = await chromium.launch({ headless: true, ...(process.env.KITLANE_CHROMIUM_PATH ? { executablePath: process.env.KITLANE_CHROMIUM_PATH } : {}) });
  try {
    for (const [width, height] of [[675, 608], [390, 844], [1440, 1000]]) {
      const { page, context, workspace, attempts, errors, current } = await fixture(browser, width, height);
      const prefix = `${width}x${height}`;
      const footer = workspace.getByTestId('proposal-totals-bar');
      const scroll = workspace.locator('[data-order-scroll]');
      const screenshot = name => page.screenshot({ path: path.join(output, `${prefix}-${name}.png`), animations: 'disabled' });
      const original = structuredClone(current().proposals);
      await screenshot('composition');
      await scroll.evaluate(el => { el.scrollTop = el.scrollHeight; });
      const bar = await footer.boundingBox(); assert(bar.y + bar.height <= height + 1, JSON.stringify({ bar, height }));
      await footer.getByTestId('add-product-line').click();
      const rows = workspace.getByTestId('product-line-row');
      const draft = rows.last();
      await draft.locator('textarea').first().waitFor();
      await page.waitForTimeout(1100); // Let the actual autosave debounce elapse.
      assert(await draft.locator('textarea').first().evaluate(el => document.activeElement === el));
      assert.equal(attempts.length, 0, 'An empty draft must not start autosave');
      assert.equal(await workspace.getByText('Исправьте ошибки в форме', { exact: true }).count(), 0);
      assert.equal(await draft.locator('[role="alert"]').count(), 0);
      const cancel = draft.getByRole('button', { name: 'Отмена: товар #8', exact: true });
      assert(await cancel.isVisible());
      const cancelBox = await cancel.boundingBox(); assert(cancelBox.y >= 0 && cancelBox.y + cancelBox.height < bar.y);
      await screenshot('empty-draft');
      if (width === 390) {
        // Simulate an overlay keyboard's VisualViewport signal; physical IME QA is separate.
        await page.evaluate(() => {
          Object.defineProperty(window.visualViewport, 'height', { configurable: true, get: () => 500 });
          window.visualViewport.dispatchEvent(new Event('resize'));
        });
        await page.waitForTimeout(100);
        const keyboardBar = await footer.boundingBox();
        const fieldBox = await draft.locator('textarea').first().boundingBox();
        assert(keyboardBar.y + keyboardBar.height <= 501, JSON.stringify(keyboardBar));
        assert(fieldBox.y >= 0 && fieldBox.y + fieldBox.height <= keyboardBar.y + 1, JSON.stringify({ fieldBox, keyboardBar }));
        await page.evaluate(() => { delete window.visualViewport.height; window.visualViewport.dispatchEvent(new Event('resize')); });
        await page.waitForTimeout(50);
      }
      await cancel.click();
      assert.equal(await rows.count(), 7);
      assert.deepEqual(current().proposals, original);

      await workspace.getByRole('checkbox', { name: 'Себестоимость', exact: true }).check();
      await footer.getByTestId('add-product-line').click();
      const manual = rows.last();
      await manual.locator('textarea').first().fill('Декоративный экран для кондиционера');
      await manual.locator('input[type="number"]').nth(0).fill('350');
      await manual.locator('input[type="number"]').nth(1).fill('2');
      await manual.locator('input[type="number"]').nth(2).fill('200');
      await manual.locator('[data-order-usage="order_product_description"]').fill('Белый, по размерам заказчика');
      await screenshot('manual-entry');
      await manual.getByRole('button', { name: 'Добавить товар #8', exact: true }).click();
      await page.waitForTimeout(1200);
      const saved = current().proposals[0].product_lines.find(line => !line.product_id);
      assert(saved && saved.product_title === 'Декоративный экран для кондиционера' && saved.quantity === 2 && saved.price === 350 && saved.cost === 200);
      assert.equal(current().proposals[0].service_lines.length, 0);
      assert.deepEqual(current().proposals[0].product_lines.slice(0, 7).map(line => [line.id, line.product_id, line.quantity, line.price]), original[0].product_lines.map(line => [line.id, line.product_id, line.quantity, line.price]));
      assert.deepEqual(current().proposals[1], original[1]);
      await screenshot('manual-saved');
      await footer.getByTestId('add-service-line').click();
      const service = workspace.getByRole('region', { name: 'Услуги', exact: true });
      await service.getByRole('button', { name: 'Отмена', exact: true }).click();
      assert.equal(current().proposals[0].service_lines.length, 0);

      await page.reload();
      await workspace.getByText('Декоративный экран для кондиционера', { exact: true }).waitFor();
      assert.equal(await rows.count(), 8);
      assert.equal(new URL(page.url()).searchParams.get('proposalId'), '24');
      assert.equal(new URL(page.url()).searchParams.get('returnTo'), '/manager/orders?segment=b2b');
      await rows.last().getByRole('button', { name: 'Редактировать товар #8', exact: true }).click();
      await rows.last().locator('[data-order-usage="order_product_description"]').fill('Белый экран с уточнёнными размерами');
      await workspace.getByRole('button', { name: 'Предпросмотр для клиента', exact: true }).click();
      await page.getByRole('button', { name: 'Продолжить ввод', exact: true }).click();
      assert.equal(await rows.last().locator('[data-order-usage="order_product_description"]').inputValue(), 'Белый экран с уточнёнными размерами');
      assert.equal(await workspace.getByTestId('proposal-client-preview').count(), 0);
      await workspace.getByRole('button', { name: 'Предпросмотр для клиента', exact: true }).click();
      await page.getByRole('button', { name: 'Применить и сохранить', exact: true }).click();
      const preview = workspace.getByTestId('proposal-client-preview');
      await preview.getByText('Декоративный экран для кондиционера', { exact: true }).waitFor();
      await preview.getByText('Белый экран с уточнёнными размерами', { exact: true }).waitFor();
      assert.equal(await preview.getByText('Товар не связан с каталогом; наличие и цена не подтверждены', { exact: true }).count(), 0);
      await screenshot('client-preview');
      await workspace.getByRole('button', { name: 'Вернуться в редактор', exact: true }).click();
      // Delete opens the existing confirmation; cancelling it preserves every row.
      await rows.first().getByRole('button', { name: 'Удалить товар #1', exact: true }).click();
      await page.getByRole('button', { name: 'Отмена', exact: true }).click();
      assert.equal(await rows.count(), 8);
      assert.deepEqual(current().proposals[1], original[1]);
      const layout = await page.evaluate(() => ({ width: innerWidth, scroll: document.documentElement.scrollWidth }));
      assert(layout.scroll <= layout.width + 1, JSON.stringify(layout));
      assert.deepEqual(errors, []);
      checks.push({ viewport: { width, height }, saves: attempts.length, emptyDraft: true, focus: true, cancel: true, manualRoundtrip: true, clientPreview: true, neighbours: true, variantIsolation: true, returnTo: true, horizontalOverflow: false });
      await context.close();
    }
    fs.writeFileSync(path.join(output, 'checks.json'), JSON.stringify(checks, null, 2));
    console.log(JSON.stringify({ output, checks }, null, 2));
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
