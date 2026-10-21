// Local production-preview QA. API responses are synthetic; no remote requests or writes.
const { chromium } = require(process.env.KITLANE_PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { auth, stores } = require('../kitlane/fixtures.json');
const base = process.env.KITLANE_PREVIEW_URL || 'http://127.0.0.1:5189';
assert(['127.0.0.1', 'localhost'].includes(new URL(base).hostname), 'Only local preview is allowed');
const output = path.resolve(process.env.KITLANE_SCREENSHOTS || '/private/tmp/mvn-catalog-evidence/visual');
fs.mkdirSync(output, { recursive: true });
const checks = [];
const models = [
  { id: 11, title: 'Zeta Wall 24', indoor_form_factor: 'wall', retail_price_byn: 3400, cooling_power_kw: 7 },
  { id: 22, title: 'Alpha Console 24', indoor_form_factor: 'console', retail_price_byn: 2900, cooling_power_kw: 7 },
  { id: 33, title: 'Beta Cassette 36', indoor_form_factor: 'cassette', retail_price_byn: 4800, cooling_power_kw: 10.5 },
].map(model => ({ ...model, slug: `fixture-${model.id}`, brand_title: 'Fixture', series_title: 'Comfort',
  purchase_cost_byn: 2100, recommended_price_byn: 3500, margin_abs_byn: model.retail_price_byn - 2100,
  margin_pct: (model.retail_price_byn - 2100) / model.retail_price_byn, supplier_name: 'Тестовый поставщик',
  supplier_qty: 5, availability: 'in_stock', heating_min_c: -25, is_inverter: true, wifi: 'builtin', is_published: true,
}));
let browser;
async function fixture(width, editable) {
  const context = await browser.newContext({ serviceWorkers: 'block', viewport: { width, height: 1000 }, isMobile: width < 768, hasTouch: width < 768 });
  const page = await context.newPage();
  page.setDefaultTimeout(7000);
  const errors = [], requests = [], mutations = [];
  page.on('pageerror', error => errors.push(error.message));
  await context.route('**/*', async route => {
    const url = new URL(route.request().url());
    if (url.origin !== base) return route.abort();
    if (!url.pathname.startsWith('/api') && !url.pathname.startsWith('/login')) return route.continue();
    if (route.request().method() !== 'GET') {
      mutations.push({ method: route.request().method(), path: url.pathname });
      return route.fulfill({ status: 405, json: { detail: 'No writes in visual QA' } });
    }
    let data = { items: [], total: 0, meta: { page: 1, pages: 1, total: 0 }, enabled: false };
    if (url.pathname === '/api/manager/account/companies') data = {
      staff_user_id: 999, username: auth.username, is_platform_owner: false, default_tenant_id: 999,
      items: [{ tenant_id: 999, slug: 'test', display_name: 'Тестовая компания', role: 'manager', membership_id: 999,
        access_kind: 'membership', is_system: true, demo_read_only: false, default_storefront_slug: 'minsk' }], total: 1, page: 1, limit: 100,
    };
    else if (url.pathname.endsWith('/me')) data = { ...auth, role: 'manager', capabilities: [
      'crm.manage', 'catalog.master.read', 'storefront.offers.read', ...(editable ? ['catalog.master.edit'] : []),
    ] };
    else if (url.pathname.endsWith('/storefronts')) data = { items: stores.map(store => ({ ...store, id: store.slug === 'minsk' ? 999 : 998 })) };
    else if (url.pathname === '/api/manager/catalog-decision/filter-options') data = { brands: [{ id: 1, title: 'Fixture' }], series: [] };
    else if (url.pathname === '/api/manager/catalog-decision/products') {
      requests.push({ ...Object.fromEntries(url.searchParams), cooling_btu_classes: url.searchParams.getAll('cooling_btu_classes') });
      let items = url.searchParams.get('indoor_form_factor') === 'floor_ceiling' ? [] : [...models];
      const sort = url.searchParams.get('sort');
      if (sort === 'title') items.sort((a, b) => a.title.localeCompare(b.title));
      if (sort === 'retail_price') items.sort((a, b) => a.retail_price_byn - b.retail_price_byn);
      if (url.searchParams.get('direction') === 'desc') items.reverse();
      data = { items, meta: { page: 1, pages: 1, total: items.length, limit: 40 } };
    }
    else if (url.pathname === '/api/manager/catalog/products/11' || url.pathname === '/api/manager/tenant-catalog/products/11') data = {
      ...models[0], effective_price: 3400, allowed: true, selection_item: models[0], images: [], manuals: [], specification_groups: [], summary_fields: [],
    };
    return route.fulfill({ json: data });
  });
  const workspace = page.getByTestId('catalog-decision-workspace');
  const ready = async () => {
    await workspace.waitFor();
    await page.waitForFunction(() => document.querySelector('[data-testid="catalog-decision-workspace"] [aria-busy]')?.getAttribute('aria-busy') === 'false');
  };
  const latest = () => requests.at(-1);
  const noOverflow = async () => assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth), false);
  return { context, page, workspace, ready, latest, requests, errors, mutations, noOverflow };
}
async function caseFor(width, editable, task) {
  const f = await fixture(width, editable);
  try {
    await task(f);
    assert.deepEqual(f.errors, []);
    assert.deepEqual(f.mutations, []);
    checks.push({ width, editable, passed: true, catalogRequests: f.requests.length });
  } catch (error) {
    await f.page.screenshot({ path: path.join(output, `failure-${width}-${editable}.png`), fullPage: true });
    console.error(await f.page.locator('body').innerText());
    throw error;
  } finally { await f.context.close(); }
}
const emptyQuery = '?form=floor_ceiling&coolingBtuClasses=36%2C42%2C60&heating=-25';
(async () => {
  browser = await chromium.launch({ headless: true, ...(process.env.KITLANE_BROWSER_PATH ? { executablePath: process.env.KITLANE_BROWSER_PATH } : {}) });
  try {
    for (const width of [1440, 390]) await caseFor(width, true, async f => {
      const { page, workspace } = f;
      await page.goto(base + '/manager/catalog-decision'); await f.ready();
      assert.equal(f.latest().sort, 'recommended');
      assert.equal(f.latest().indoor_form_factor, undefined);
      assert.equal(f.latest().category, undefined);
      const select = workspace.getByRole('combobox', { name: 'Сортировать модели' });
      assert.equal(await select.inputValue(), 'recommended');
      assert.ok((await select.boundingBox()).width >= 180, 'Recommended ordering remains legible on mobile');
      await workspace.getByText('Другие формы блоков тоже в подборе.', { exact: true }).waitFor();
      const rows = width >= 768 ? workspace.locator('tbody tr') : workspace.locator('article');
      assert.equal(await rows.count(), 3);
      assert.match(await rows.first().innerText(), /Zeta Wall/);
      assert.match(await rows.nth(1).innerText(), /Console/);
      assert.equal(await workspace.getByRole('link', { name: 'Проверить в управлении каталогом' }).count(), 1);
      assert.match(await workspace.getByText('«7 кВт»', { exact: false }).innerText(), /номинальная мощность охлаждения 7 кВт/);
      await f.noOverflow();
      await page.evaluate(() => scrollTo(0, 0));
      await page.screenshot({ path: path.join(output, `catalog-${width}.png`), fullPage: true });
      for (const sort of ['retail_price', 'title']) {
        await select.selectOption(sort); await f.ready();
        assert.equal(f.latest().sort, sort);
        assert.equal(new URL(page.url()).searchParams.get('sort'), sort);
        assert.match(await rows.first().innerText(), /Alpha Console/);
      }
      await select.selectOption('recommended'); await f.ready();
      assert.equal(f.latest().sort, 'recommended');
      assert.equal(new URL(page.url()).searchParams.has('sort'), false);
      assert.equal(new URL(page.url()).searchParams.has('direction'), false);
      assert.match(await rows.first().innerText(), /Zeta Wall/);
      await workspace.getByRole('button', { name: 'Открыть карточку Zeta Wall 24' }).filter({ visible: true }).first().click();
      await page.getByRole('link', { name: 'Редактировать', exact: true }).waitFor();
      await page.getByRole('button', { name: 'Закрыть карточку товара' }).click();
      await page.goto(base + '/manager/catalog-decision' + emptyQuery); await f.ready();
      await workspace.getByText('Подтверждённых комплектов по этим условиям нет', { exact: true }).waitFor();
      assert.equal(await workspace.getByText('Другие формы блоков тоже в подборе.', { exact: true }).count(), 0);
      const chips = workspace.locator('[aria-label="Выбранные фильтры"]');
      for (const label of ['Напольно-потолочный', '36 тыс. БТЕ/ч', '42 тыс. БТЕ/ч', '60 тыс. БТЕ/ч', 'Обогрев до -25 °C']) assert.match(await chips.innerText(), new RegExp(label));
      await f.noOverflow();
      await page.evaluate(() => scrollTo(0, 0));
      await page.screenshot({ path: path.join(output, `empty-${width}.png`), fullPage: true });
      const before = { ...f.latest() };
      assert.deepEqual(before.cooling_btu_classes, ['36', '42', '60']);
      await workspace.getByRole('button', { name: 'Показать также заказные', exact: true }).click(); await f.ready();
      assert.equal(f.latest().include_orderable, 'true');
      for (const key of ['indoor_form_factor', 'heating_min', 'heating_min_c', 'cooling_btu_classes']) if (before[key] !== undefined) assert.deepEqual(f.latest()[key], before[key]);
      assert.equal(new URL(page.url()).searchParams.get('form'), 'floor_ceiling');
      assert.equal(new URL(page.url()).searchParams.get('heating'), '-25');
      assert.equal(new URL(page.url()).searchParams.get('coolingBtuClasses'), '36,42,60');
      await f.noOverflow();
    });
    await caseFor(390, false, async f => {
      await f.page.goto(base + '/manager/catalog-decision'); await f.ready();
      assert.equal(await f.workspace.getByRole('link', { name: 'Проверить в управлении каталогом' }).count(), 0);
      await f.workspace.getByRole('button', { name: 'Открыть карточку Zeta Wall 24' }).filter({ visible: true }).first().click();
      await f.page.getByRole('button', { name: 'Закрыть карточку товара' }).waitFor();
      await f.page.getByText('Основные характеристики пока не заполнены.', { exact: true }).waitFor();
      assert.equal(await f.page.getByRole('link', { name: 'Редактировать', exact: true }).count(), 0);
    });
    fs.writeFileSync(path.join(output, 'results.json'), JSON.stringify({ syntheticApi: true, checks }, null, 2));
    console.log(JSON.stringify({ passed: checks.length, output }));
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
