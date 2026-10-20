// Run against a local dev/preview server. Every API response is synthetic.
const { chromium } = require(process.env.KITLANE_PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { auth, stores } = require('../kitlane/fixtures.json');
const base = process.env.KITLANE_PREVIEW_URL || 'http://127.0.0.1:5184';
const origin = new URL(base).origin;
const out = path.resolve(process.env.KITLANE_SCREENSHOTS || '.codex-tmp/order-drawer');
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
  const errors = [];
  const measurements = [];
  try {
    for (const width of [320, 360, 384, 412, 768, 1440]) {
      const context = await browser.newContext({ viewport: { width, height: 850 }, isMobile: width < 768, hasTouch: width < 768 });
      const page = await context.newPage();
      page.on('pageerror', error => errors.push(error.message));
      await page.route('**/*', async route => {
        const url = new URL(route.request().url());
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
        else if (url.pathname === '/api/manager/orders') data = { items: [order], meta: { pages: 1, total: 1 } };
        else if (url.pathname === '/api/manager/orders/477') data = order;
        else if (url.pathname.endsWith('/tender-workflow')) data = { order_id: 477, stage: null, deadline_at: null, price_enquiry: null, publications: [], history: [] };
        return route.fulfill({ json: data });
      });
      await page.goto(`${base}/manager/orders/kanban?segment=b2b&view=kanban&groupBy=customer&orderId=477`);
      const drawer = page.getByRole('dialog', { name: 'Рабочая область заказа', exact: true });
      await drawer.waitFor();
      await drawer.locator('footer').waitFor();
      // A mobile fixed inset overlay can inherit the wide document's dimensions.
      await page.getByTestId('manager-root').evaluate(element => { element.style.minWidth = '1800px'; });
      assert.deepEqual(await page.evaluate(() => {
        const style = getComputedStyle(document.documentElement);
        return [style.overflowX, style.overflowY];
      }), ['hidden', 'hidden'], 'The open drawer must lock background scrolling');
      const measure = async state => {
        const size = await drawer.evaluate(element => {
          const bounds = element.getBoundingClientRect();
          const viewport = window.visualViewport;
          const footer = element.querySelector('footer').getBoundingClientRect();
          const scroller = element.querySelector('.overflow-y-auto');
          return { viewportWidth: viewport.width, viewportHeight: viewport.height, left: bounds.left, right: bounds.right, bottom: bounds.bottom, footerBottom: footer.bottom, contentWidth: scroller.scrollWidth, availableWidth: scroller.clientWidth };
        });
        measurements.push({ width, state, ...size });
        assert(size.left >= -1 && size.right <= size.viewportWidth + 1, `Drawer exceeds viewport: ${JSON.stringify(measurements.at(-1))}`);
        assert(size.bottom <= size.viewportHeight + 1 && size.footerBottom <= size.viewportHeight + 1, `Footer exceeds viewport: ${JSON.stringify(measurements.at(-1))}`);
        assert(size.contentWidth <= size.availableWidth + 1, `Horizontal content overflow: ${JSON.stringify(measurements.at(-1))}`);
      };
      await measure('wide background');
      await page.screenshot({ path: path.join(out, `${width}.png`), animations: 'disabled' });
      // Check the size guard independently of the background scroll lock.
      await page.evaluate(() => { document.documentElement.style.overflow = ''; document.body.style.overflow = ''; });
      await measure('wide background without scroll lock');
      if (width === 384) {
        await page.setViewportSize({ width, height: 600 });
        await measure('shorter viewport');
        await page.screenshot({ path: path.join(out, '384-short.png'), animations: 'disabled' });
      }
      await drawer.getByRole('button', { name: 'Закрыть карточку заказа', exact: true }).click();
      await drawer.waitFor({ state: 'detached' });
      assert.equal(await page.evaluate(() => document.documentElement.style.overflow), '');
      await context.close();
    }
    assert.deepEqual(errors, []);
    fs.writeFileSync(path.join(out, 'results.json'), JSON.stringify({ errors, measurements }, null, 2));
    console.log(JSON.stringify({ errors, measurements }, null, 2));
  } finally { await browser.close(); }
}
run().catch(error => { console.error(error); process.exitCode = 1; });
