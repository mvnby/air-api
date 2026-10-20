// Run against a local dev/preview server. Every API response is synthetic.
const { chromium } = require(process.env.KITLANE_PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { auth, stores } = require('../kitlane/fixtures.json');
const base = process.env.KITLANE_PREVIEW_URL || 'http://127.0.0.1:5184';
const origin = new URL(base).origin;
const out = path.resolve(process.env.KITLANE_SCREENSHOTS || '.codex-tmp/order-page');
assert(['localhost', '127.0.0.1'].includes(new URL(base).hostname), 'Only local preview is allowed');
fs.mkdirSync(out, { recursive: true });

const service = { id: 1, proposal_id: 25, service_title: 'Выездная диагностика кондиционеров на нескольких объектах с учётом транспортных расходов', quantity: 1, price: 1200, cost: 0, line_total: 1200 };
const order = {
  id: 477, title: 'Тестовая диагностика', status: 'negotiation', lead_source: 'email', workflow_type: 'repair',
  negotiation_status: 'awaiting_offer', execution_status: 'needs_schedule', created_at: '2026-10-20T08:00:00Z',
  is_paid: false, total_amount: 1200, total_cost: 0, margin: 1200, total_payments: 0, balance_due: 1200,
  payments: [], documents: [], product_lines: [], service_lines: [service], work_stages: [],
  customer: { id: 12, name: 'Тестовая компания', type: 'company' },
  proposals: [{ id: 25, name: 'Основное', status: 'sent', is_selected: true, is_archived: false, product_lines: [], service_lines: [service], total_amount: 1200 }],
};

async function run() {
  const browser = await chromium.launch({ headless: true });
  const errors = [], measurements = [];
  try {
    for (const width of [320, 360, 384, 412, 768, 1440]) {
      const context = await browser.newContext({ viewport: { width, height: 850 }, isMobile: width < 768, hasTouch: width < 768 });
      const page = await context.newPage();
      page.on('pageerror', error => errors.push(error.message));
      let current = structuredClone(order), failSave = false, detailRequests = 0, listRequests = 0;
      const patches = [];
      await page.route('**/*', async route => {
        const url = new URL(route.request().url());
        if (['fonts.googleapis.com', 'fonts.gstatic.com'].includes(url.hostname)) return route.continue();
        if (url.origin !== origin) return route.abort();
        if (!url.pathname.startsWith('/api') && !url.pathname.startsWith('/login')) return route.continue();
        let data = { items: [], total: 0, meta: { pages: 1 }, enabled: false };
        if (url.pathname === '/api/manager/account/companies') data = {
          staff_user_id: 999, username: auth.username, is_platform_owner: true, default_tenant_id: 999,
          items: [{ tenant_id: 999, slug: 'test', display_name: 'Тестовая компания', role: 'owner', membership_id: 999, access_kind: 'membership', is_system: true, demo_read_only: false, default_storefront_slug: 'minsk' }],
          total: 1, page: 1, limit: 100,
        };
        else if (url.pathname.endsWith('/me')) data = auth;
        else if (url.pathname.endsWith('/storefronts')) data = { items: stores.map(store => ({ ...store, id: store.slug === 'minsk' ? 999 : 998 })) };
        else if (url.pathname === '/api/manager/orders') {
          listRequests++;
          data = { items: Array.from({ length: 18 }, (_, index) => ({ ...current, id: index === 8 ? 477 : 500 + index, title: index === 8 ? current.title : `Тестовый заказ ${index + 1}` })), meta: { pages: 1, total: 18 } };
        }
        else if (url.pathname === '/api/manager/orders/477') {
          if (route.request().method() === 'PATCH') {
            if (failSave) return route.fulfill({ status: 500, json: { detail: 'Synthetic save failure' } });
            patches.push(route.request().postDataJSON());
            current = { ...current, ...patches.at(-1) };
          } else detailRequests++;
          data = current;
        }
        else if (url.pathname.endsWith('/installer-workspace')) data = { order_id: 477, assignments: [], materials: [], collection: { version: 1, assignment_id: null, amount: null, currency: null, status: 'not_assigned', updated_at: null }, balances: [], financial_fingerprint: 'synthetic' };
        else if (url.pathname.endsWith('/worker-pay')) data = { order_id: 477, agreements: [], candidates: [] };
        else if (url.pathname.endsWith('/tender-workflow')) data = { order_id: 477, stage: null, deadline_at: null, price_enquiry: null, publications: [], history: [] };
        return route.fulfill({ json: data });
      });
      const workspace = page.getByRole('region', { name: 'Рабочая область заказа', exact: true });
      const measure = async (state, withFooter = true) => {
        if (withFooter) await workspace.locator('footer').waitFor();
        const size = await workspace.evaluate(element => {
          const bounds = element.getBoundingClientRect(), viewport = window.visualViewport;
          const footer = element.querySelector('footer')?.getBoundingClientRect() || bounds;
          const scroller = element.querySelector('.overflow-y-auto');
          return { viewportWidth: viewport.width, viewportHeight: viewport.height, left: bounds.left, right: bounds.right, bottom: bounds.bottom, footerBottom: footer.bottom, contentWidth: scroller.scrollWidth, availableWidth: scroller.clientWidth, documentWidth: document.documentElement.scrollWidth, clientWidth: document.documentElement.clientWidth, scrollX: window.scrollX, offsetLeft: viewport.offsetLeft };
        });
        measurements.push({ width, state, ...size });
        assert(size.left >= -1 && size.right <= size.viewportWidth + 1, `Workspace exceeds viewport: ${JSON.stringify(measurements.at(-1))}`);
        assert(size.footerBottom <= size.viewportHeight + 1, `Footer exceeds viewport: ${JSON.stringify(measurements.at(-1))}`);
        assert(size.contentWidth <= size.availableWidth + 1, `Content overflow: ${JSON.stringify(measurements.at(-1))}`);
        assert(size.documentWidth <= size.clientWidth + 1 && Math.abs(size.scrollX) < 1 && Math.abs(size.offsetLeft) < 1, `Page can pan horizontally: ${JSON.stringify(measurements.at(-1))}`);
        assert.equal(await page.locator('article[draggable]').count(), 0, 'The background board must be unmounted');
        assert.equal(await page.getByRole('dialog', { name: 'Рабочая область заказа' }).count(), 0);
      };
      // Every existing address opens the order directly without listing orders first.
      for (const legacy of ['/manager/orders', '/manager/orders/list', '/manager/orders/kanban']) {
        await page.goto(`${base}${legacy}?company=999&site=minsk&segment=b2b&view=kanban&groupBy=customer&orderId=477&proposalId=25`);
        await workspace.waitFor();
        await page.evaluate(() => document.fonts.ready);
        assert(await page.evaluate(() => document.fonts.check('16px \"Material Icons Round\"')), 'The icon font must be available for layout checks');
        assert.equal(new URL(page.url()).pathname, '/manager/orders/477');
        assert.equal(new URL(page.url()).searchParams.get('proposalId'), '25');
        assert.equal(new URL(page.url()).searchParams.get('company'), '999');
        assert.equal(new URL(page.url()).searchParams.get('site'), 'minsk');
        await measure(legacy);
      }
      assert.equal(listRequests, 0);
      assert.equal(detailRequests, 3);
      if (width < 768) {
        const cdp = await context.newCDPSession(page);
        for (const [from, to] of [[width - 25, 25], [25, width - 25]]) {
          await cdp.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [{ x: from, y: 450 }] });
          for (let step = 1; step <= 6; step++) await cdp.send('Input.dispatchTouchEvent', { type: 'touchMove', touchPoints: [{ x: from + (to - from) * step / 6, y: 450 }] });
          await cdp.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] });
        }
        await measure('horizontal finger swipes');
        if (width === 384) {
          await cdp.send('Input.synthesizePinchGesture', { x: 190, y: 420, scaleFactor: 1.5, relativeSpeed: 800, gestureSourceType: 'touch' });
          await cdp.send('Input.synthesizePinchGesture', { x: 190, y: 420, scaleFactor: 1 / 1.5, relativeSpeed: 800, gestureSourceType: 'touch' });
          await measure('after zooming in and out');
        }
        await cdp.detach();
      }
      const sections = workspace.getByRole('navigation', { name: 'Рабочая область заказа', exact: true });
      for (const section of ['Документы', 'Ремонт', 'Оплаты']) {
        await sections.getByRole('button', { name: section, exact: true }).click();
        await page.waitForTimeout(350); // Let the sticky header resize animation finish.
        await measure(section, false);
      }
      await sections.getByRole('button', { name: 'Предложение', exact: true }).click();
      if (width < 768) {
        const contextToggle = workspace.getByRole('button', { name: 'Ответственный, клиент и объект' });
        await contextToggle.click(); await page.waitForTimeout(350); await measure('expanded customer context'); await contextToggle.click();
      }
      await page.screenshot({ path: path.join(out, `${width}.png`), animations: 'disabled' });
      if (width === 384) {
        await page.setViewportSize({ width, height: 600 });
        await measure('short viewport');
        await page.screenshot({ path: path.join(out, '384-short.png'), animations: 'disabled' });
        await page.setViewportSize({ width, height: 850 });
      }
      // Reload a canonical URL, not just a client-side transition.
      await page.reload(); await workspace.waitFor(); await measure('canonical reload');
      if ([384, 1440].includes(width)) {
        const filters = 'segment=b2b&view=kanban&groupBy=none&search=office&assigned_to_me=1&status=negotiation&sort=margin_desc&workFilter=unpaid&hideOnHold=false&filtersOpen=true';
        await page.goto(`${base}/manager/orders/kanban?${filters}`);
        await page.locator('article[draggable]').first().waitFor();
        const board = page.locator('div.flex.gap-4.overflow-x-auto.pb-4');
        const column = board.locator(':scope > section').first();
        await column.getByTitle('Фильтр: Все').click();
        await column.getByRole('button', { name: /Ждет предложение/ }).click();
        const card = column.locator('article').filter({ hasText: '№477' });
        await card.getByRole('button', { name: 'Раскрыть заказ', exact: true }).click();
        await card.getByRole('button', { name: 'Открыть заказ', exact: true }).waitFor();
        await board.evaluate(el => { el.scrollLeft = 160; });
        await page.evaluate(() => window.scrollTo(0, 500));
        const expectedUrl = new URL(page.url()).pathname + new URL(page.url()).search;
        await card.getByRole('button', { name: 'Открыть заказ', exact: true }).evaluate(el => el.click());
        await workspace.waitFor(); await measure('opened from board');
        await workspace.getByTitle('Изменить название').click();
        await workspace.getByRole('textbox', { name: 'Название заказа', exact: true }).fill('Название сохранено при возврате');
        await workspace.getByRole('button', { name: 'К заказам', exact: true }).click();
        await page.waitForURL(url => url.pathname !== '/manager/orders/477');
        await page.locator('article[draggable]').first().waitFor();
        assert(patches.some(patch => patch.title === 'Название сохранено при возврате'));
        assert.equal(new URL(page.url()).pathname + new URL(page.url()).search, expectedUrl);
        await page.waitForFunction(() => Math.abs(window.scrollY - 500) < 2);
        assert.equal(await board.evaluate(el => el.scrollLeft), 160);
        assert.equal(await column.getByTitle('Фильтр: Ждет предложение').count(), 1);
        assert.equal(await column.locator('article').filter({ hasText: '№477' }).getByRole('button', { name: 'Свернуть заказ', exact: true }).count(), 1);
        // Browser Back must be blocked on an unsuccessful save, then remain usable after recovery.
        await column.locator('article').filter({ hasText: '№477' }).getByRole('button', { name: 'Открыть заказ', exact: true }).evaluate(el => el.click());
        await workspace.waitFor();
        failSave = true;
        await workspace.getByTitle('Изменить название').click();
        await workspace.getByRole('textbox', { name: 'Название заказа', exact: true }).fill('Не потерять при ошибке');
        await page.evaluate(() => window.history.back());
        await workspace.getByText(/Не удалось сохранить заказ/).waitFor();
        assert.equal(new URL(page.url()).pathname, '/manager/orders/477');
        assert.equal(await workspace.getByRole('textbox', { name: 'Название заказа', exact: true }).inputValue(), 'Не потерять при ошибке');
        failSave = false;
        await workspace.getByRole('button', { name: 'К заказам', exact: true }).click();
        await page.waitForURL(url => url.pathname !== '/manager/orders/477');
        assert.equal(new URL(page.url()).pathname + new URL(page.url()).search, expectedUrl);
      }
      await context.close();
    }
    assert.deepEqual(errors, []);
    fs.writeFileSync(path.join(out, 'results.json'), JSON.stringify({ errors, measurements }, null, 2));
    console.log(JSON.stringify({ errors, checks: measurements.length, screenshots: out }, null, 2));
  } finally { await browser.close(); }
}
run().catch(error => { console.error(error); process.exitCode = 1; });
