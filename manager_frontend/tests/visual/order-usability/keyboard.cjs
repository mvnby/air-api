// VisualViewport-only simulation: this does not emulate a device IME or Safari.
const { chromium } = require(process.env.KITLANE_PLAYWRIGHT_MODULE || 'playwright');
const { createFixtureServer } = require('../order-request/server.cjs');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const output = path.resolve(process.env.KITLANE_SCREENSHOTS || '/tmp/order-keyboard-acceptance');
fs.mkdirSync(output, { recursive:true });
const fixture = createFixtureServer(Number(process.env.KITLANE_FIXTURE_PORT || 5207));
const base = `http://127.0.0.1:${fixture.port}`;
const products = Array.from({ length:8 }, (_, i) => ({ id:101+i, title:`Кондиционер синтетический ${i+1} — настенный инверторный для тестового помещения`, price:500+i*20, min_cost_byn:300, availability_status:'available', vitebsk_qty:5, minsk_qty:3, product_kind:'unknown', is_inverter:true, effective_price:500+i*20, allowed:true, slug:`test-${i}` }));
const tariffs = Array.from({ length:8 }, (_, i) => ({ tariff_id:91+i, service_kind:'installation', short_name:`Монтаж ${i+1}`, title:`Монтаж оборудования — вариант ${i+1}`, full_description:'Трасса 3 м, отверстие, подключение и проверка оборудования', price:'600' }));
const scenarios = [
  { width:390, height:844, visible:500, offset:0, kind:'service', action:'commit', focus:'quantity' },
  { width:390, height:844, visible:500, offset:80, kind:'service', action:'cancel', focus:'title' },
  { width:320, height:684, visible:360, offset:80, kind:'product', action:'commit', focus:'quantity' },
  { width:320, height:684, visible:360, offset:0, kind:'product', action:'cancel', focus:'title' },
  { width:320, height:684, visible:360, offset:0, kind:'service', action:'cancel', focus:'quantity', existing:true },
  { width:390, height:844, visible:500, offset:80, kind:'product', action:'cancel', focus:'title', existing:true },
];
const results = [];
const settle = page => page.waitForTimeout(450);
const box = async locator => { const value = await locator.boundingBox(); assert(value); return value; };
async function viewport(page, height, offset = 0) {
  await page.evaluate(({ height, offset }) => {
    window.__keyboardViewport = { height, offset };
    for (const [key, get] of Object.entries({
      height:() => window.__keyboardViewport.height,
      offsetTop:() => window.__keyboardViewport.offset,
    })) Object.defineProperty(window.visualViewport, key, { configurable:true, get });
    window.visualViewport.dispatchEvent(new Event('resize'));
    window.visualViewport.dispatchEvent(new Event('scroll'));
  }, { height, offset });
}
async function measure(page, field, row) {
  return page.evaluate(({ field, row }) => {
    const vv = visualViewport, top = vv.offsetTop, bottom = top + vv.height;
    const rect = element => { const b = element.getBoundingClientRect(); return { x:b.x, y:b.y, width:b.width, height:b.height, bottom:b.bottom }; };
    const target = element => {
      const b = rect(element), hit = document.elementFromPoint(b.x+b.width/2, b.y+b.height/2);
      return { ...b, visible:b.y >= top-1 && b.bottom <= bottom+1, hit:hit === element || element.contains(hit) };
    };
    const actions = row.querySelector('[data-line-editor-actions]'), buttons = actions.querySelectorAll('button');
    const scroll = document.querySelector('[data-order-scroll]'), area = rect(scroll);
    return { field:target(field), commit:target(buttons[buttons.length-1]), cancel:target(buttons[buttons.length-2]), actions:rect(actions),
      header:rect(document.querySelector('.order-header-unified')), innerHeight,
      useful:Math.min(bottom, area.bottom, actions.getBoundingClientRect().top) - Math.max(top, area.y),
      footerHidden:getComputedStyle(document.querySelector('[data-testid="proposal-totals-bar"]')).display === 'none',
    };
  }, { field:await field.elementHandle(), row:await row.elementHandle() });
}
function accessible(state, cfg, label, checkField = true) {
  assert.equal(state.innerHeight, cfg.height, `${label}: layout viewport is unchanged`);
  assert(state.header.height < 1 && state.footerHidden, `${label}: line keyboard session stays compact`);
  assert(state.useful >= (cfg.visible === 360 ? 200 : 300), `${label}: useful space ${state.useful}`);
  for (const key of checkField ? ['field','commit','cancel'] : ['commit','cancel']) assert(state[key].visible && state[key].hit, `${label}: ${key} is visible and hit-testable: ${JSON.stringify(state)}`);
}
async function tap(page, locator) {
  const b = await box(locator);
  await page.touchscreen.tap(b.x+b.width/2, b.y+b.height/2);
}
async function chooseSuggestion(page, option, row, cfg) {
  const menu = row.locator('[data-line-suggestions]'); await option.waitFor();
  for (let attempt = 0; attempt < 6; attempt++) {
    const bounds = await box(option), menuBox = await box(menu), actions = await box(row.locator('[data-line-editor-actions]'));
    const center = bounds.y+bounds.height/2;
    const hit = await option.evaluate(el => { const b=el.getBoundingClientRect(), h=document.elementFromPoint(b.x+b.width/2,b.y+b.height/2); return h===el || el.contains(h); });
    if (hit && center >= cfg.offset && center < cfg.offset+cfg.visible) { await tap(page, option); return; }
    const top = Math.max(menuBox.y, cfg.offset), bottom = Math.min(menuBox.y+menuBox.height, actions.y, cfg.offset+cfg.visible);
    assert(bottom > top+20, 'Suggestion list has a visible scroll target');
    await page.mouse.move(menuBox.x+menuBox.width/2, (top+bottom)/2);
    await page.mouse.wheel(0, center < top ? -60 : 60);
    await page.waitForTimeout(60);
  }
  assert.fail('A real suggestion must remain selectable by internal scrolling and touch');
}
let browser;
(async () => {
  await new Promise(resolve => fixture.server.listen(fixture.port, '127.0.0.1', resolve));
  browser = await chromium.launch({ headless:true, ...(process.env.KITLANE_CHROMIUM_PATH ? { executablePath:process.env.KITLANE_CHROMIUM_PATH } : {}) });
  try {
    for (const cfg of scenarios) {
      const name = `${cfg.width}-${cfg.offset}-${cfg.kind}-${cfg.existing ? 'existing-' : ''}${cfg.action}`;
      if (process.env.KITLANE_CASE && process.env.KITLANE_CASE !== name) continue;
      fixture.reset('mixed');
      const context = await browser.newContext({ viewport:{ width:cfg.width, height:cfg.height }, isMobile:true, hasTouch:true, serviceWorkers:'block' });
      await context.route('**/*', route => {
        const url = new URL(route.request().url());
        if (url.origin !== base) return route.abort();
        if (url.pathname === '/api/manager/tenant-catalog/products' || url.pathname.includes('smart-search')) return route.fulfill({ json:{ items:products, total:products.length, page:1, limit:20 } });
        if (url.pathname.endsWith('/tariffs/quick-add')) return route.fulfill({ json:{ items:tariffs } });
        return route.continue();
      });
      const page = await context.newPage(); page.setDefaultTimeout(10000);
      const errors = []; page.on('pageerror', error => errors.push(error.message));
      const shot = suffix => page.screenshot({ path:path.join(output, `${name}-${suffix}.png`), clip:{ x:0, y:cfg.offset, width:cfg.width, height:cfg.visible }, animations:'disabled' });
      try {
        await page.goto(`${base}/manager/orders/590?company=999&site=minsk&proposalId=586`);
        await page.getByTestId('add-service-line').waitFor();
        const autosave = page.getByRole('switch', { name:'Автосохранение заказа' });
        if (await autosave.getAttribute('aria-checked') === 'true') await autosave.click();
        const total = () => page.getByTestId('proposal-grand-total').textContent().then(text => Number(text.replace(/[^\d.,-]/g,'').replace(',','.')));
        const beforeTotal = await total();
        const originalTitle = cfg.kind === 'product' ? fixture.getState().order.product_lines[0].product_title : fixture.getState().order.service_lines[0].service_title;
        if (cfg.existing) await page.locator(`[data-order-usage="order_${cfg.kind}_edit"]`).first().click();
        else await page.getByTestId(`add-${cfg.kind}-line`).click();
        const title = cfg.kind === 'product' ? page.getByPlaceholder('Найти в каталоге или ввести название') : page.getByTestId('service-title-input');
        const row = title.locator('xpath=ancestor::*[@data-testid="product-line-row"][1]').or(title.locator('xpath=ancestor::*[contains(concat(" ",normalize-space(@class)," ")," order-line-form ")][1]/..')).first();
        await viewport(page, cfg.visible, cfg.offset);
        await title.fill('Подробное синтетическое оборудование и обслуживание систем кондиционирования. '.repeat(4)); await settle(page);
        if (!cfg.existing && cfg.action === 'commit') {
          await title.fill(cfg.kind === 'product' ? 'Кондиционер' : 'Монтаж');
          const option = page.getByTestId(cfg.kind === 'product' ? 'select-product-101' : 'select-service-91');
          await chooseSuggestion(page, option, row, cfg); await settle(page);
        }
        const price = row.getByRole('spinbutton', { name:/^Цена/ }), quantity = row.getByRole('spinbutton', { name:/Кол-во/ });
        await price.fill('650'); await price.focus(); await settle(page); accessible(await measure(page, price, row), cfg, 'price');
        await quantity.fill('2'); await quantity.focus(); await settle(page); accessible(await measure(page, quantity, row), cfg, 'quantity');
        await page.locator('[data-order-scroll]').evaluate(el => { el.scrollTop = Math.max(0, el.scrollTop-70); }); await settle(page);
        // Intentional scrolling may move the old focus outside view; it must
        // not expand chrome or lose the action row. Refocusing reveals it again.
        accessible(await measure(page, quantity, row), cfg, 'upward scroll', false);
        await quantity.evaluate(el => el.blur()); await quantity.focus(); await settle(page);
        accessible(await measure(page, quantity, row), cfg, 'refocused quantity');
        const actions = row.locator('[data-line-editor-actions]'), buttons = actions.locator('button');
        const commit = buttons.last(), cancel = buttons.nth((await buttons.count())-2);
        if (cfg.action === 'commit') {
          await quantity.fill('0'); await tap(page, commit); await page.waitForTimeout(100);
          assert.equal(await quantity.evaluate(el => el === document.activeElement), true, 'Invalid quantity receives focus without dismissing keyboard');
          accessible(await measure(page, quantity, row), cfg, 'invalid quantity');
          await quantity.fill('2');
        }
        if (cfg.focus === 'title') { await title.focus(); await settle(page); }
        const focused = cfg.focus === 'title' ? title : quantity;
        const before = await measure(page, focused, row); accessible(before, cfg, 'before first touch');
        await shot('before'); const expectedTitle = await title.inputValue();
        await row.evaluate(el => {
          window.__keyboardEvents=[];
          for (const type of ['touchstart','mousedown','focusout','focusin','mouseup','click']) document.addEventListener(type, event => {
            const action=el.querySelector('[data-line-editor-actions]');
            window.__keyboardEvents.push({ type, y:action?.getBoundingClientRect().y, target:event.target.getAttribute?.('aria-label') || event.target.textContent?.slice(0,80), height:visualViewport.height });
          }, true);
        });
        await tap(page, cfg.action === 'commit' ? commit : cancel); await page.waitForTimeout(100);
        assert.equal(await title.count(), 0, 'FIRST touch applies/removes/reverts the editor before viewport restoration');
        assert.equal(await total(), beforeTotal+(cfg.action === 'commit' ? 1300 : 0), 'First-touch totals match committed changes or cancellation');
        assert((await page.locator('[data-order-scroll]').innerText()).includes(cfg.action === 'commit' ? expectedTitle : originalTitle), 'Committed title or original cancelled row is present');
        const events = await page.evaluate(() => window.__keyboardEvents);
        // Removing a successfully applied/cancelled row may move its detached
        // nodes. Only the touch sequence up to dispatching click must be stable.
        const clickIndex = events.findIndex(e => e.type === 'click');
        const positions = events.slice(0, clickIndex+1).filter(e => Number.isFinite(e.y)).map(e => e.y);
        assert(Math.max(...positions)-Math.min(...positions) <= 1, `Action geometry stays stable across touch focusout: ${JSON.stringify(events)}`);
        assert(events.some(e => e.type === 'click' && /Добавить|Применить|Отмена/.test(e.target)), 'Click reaches the line action');
        assert.equal(await page.locator('[data-order-keyboard-line]').count(), 1, 'Line geometry remains latched before real keyboard close');
        await shot('after-first-touch');
        await viewport(page, cfg.height); await settle(page);
        assert.equal(await page.locator('[data-order-keyboard-line]').count(), 0, 'Keyboard restore releases line layout');
        assert(await page.getByTestId('proposal-totals-bar').isVisible(), 'Normal footer returns');
        assert.equal(fixture.getState().patches.length, 0, 'Manual-mode touch checks never save the order');
        assert.deepEqual(errors, []); results.push({ name, cfg, before, events, beforeTotal, afterTotal:await total() });
        console.log(`${name} passed`);
      } catch (error) { await shot('FAILURE').catch(() => {}); throw error; }
      finally { await context.close(); }
    }
    fs.writeFileSync(path.join(output, 'results.json'), JSON.stringify({ method:'Chromium touch with fixed layout viewport and synthetic visualViewport signals; no native IME', results }, null, 2));
    console.log(JSON.stringify({ cases:results.length, output }));
  } finally { await browser?.close(); await new Promise(resolve => fixture.server.close(resolve)); }
})().catch(error => { console.error(error); fixture.server.close(); process.exitCode=1; });
