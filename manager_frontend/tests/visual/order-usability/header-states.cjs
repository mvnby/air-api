// Actual shell and order, synthetic local data, deliberate save/error checks only.
const { chromium } = require(process.env.KITLANE_PLAYWRIGHT_MODULE || 'playwright');
const { createFixtureServer } = require('../order-request/server.cjs');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const output = path.resolve(process.env.KITLANE_SCREENSHOTS || '/tmp/order-unified-header-states');
fs.mkdirSync(output, { recursive: true });
const fixture = createFixtureServer(Number(process.env.KITLANE_FIXTURE_PORT || 5206));
const base = `http://127.0.0.1:${fixture.port}`;
const sizes = [{ width: 973, height: 684 }, { width: 390, height: 844 }, { width: 320, height: 684 }, { width: 1440, height: 900 }];
const results = [];
const longCustomer = 'ООО «Синтетический заказчик по обслуживанию промышленного оборудования и систем вентиляции»';
const settle = page => page.waitForTimeout(500);
const box = async locator => { const value = await locator.boundingBox(); assert(value); return value; };
let browser;
(async () => {
  await new Promise(resolve => fixture.server.listen(fixture.port, '127.0.0.1', resolve));
  browser = await chromium.launch({ headless:true, ...(process.env.KITLANE_CHROMIUM_PATH ? { executablePath:process.env.KITLANE_CHROMIUM_PATH } : {}) });
  try {
    for (const viewport of sizes) {
      if (process.env.KITLANE_VIEWPORT && Number(process.env.KITLANE_VIEWPORT) !== viewport.width) continue;
      await fetch(`${base}/__request/reset?scenario=${viewport.width === 1440 ? 'email' : 'manual'}`);
      const state = fixture.getState();
      const context = await browser.newContext({ viewport, isMobile:viewport.width < 768, hasTouch:viewport.width < 768, serviceWorkers:'block' });
      let releaseSave, holdSave = false;
      await context.route('**/*', async route => {
        const url = new URL(route.request().url());
        if (url.origin !== base) return route.abort();
        if (url.pathname === '/api/manager/orders/590' && route.request().method() === 'PATCH' && holdSave) await new Promise(resolve => { releaseSave = resolve; });
        return route.continue();
      });
      const page = await context.newPage(); page.setDefaultTimeout(12000);
      const errors = []; page.on('pageerror', error => errors.push(error.message));
      const workspace = page.getByRole('region', { name:'Рабочая область заказа', exact:true });
      const header = workspace.locator(':scope > header');
      const status = header.getByRole('status');
      const autosave = header.getByRole('switch', { name:'Автосохранение заказа' });
      const nav = page.getByRole('navigation', { name:'Рабочая область заказа', exact:true });
      const shot = name => page.screenshot({ path:path.join(output, `${viewport.width}-${name}.png`), animations:'disabled' });
      const geometry = async () => ({ header:await box(header), customer:await box(header.locator('[data-order-header-customer]')), toggle:await box(autosave), status:await box(status), actions:await box(header.locator('.order-header-save-actions')) });
      const assertLayout = async (baseline, label) => {
        const current = await geometry();
        assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth), false, `${label}: no horizontal overflow`);
        for (const key of ['toggle','status','actions','customer']) assert(Math.abs(current[key].x - baseline[key].x) < 1 && Math.abs(current[key].width - baseline[key].width) < 1, `${label}: stable ${key} position/width ${JSON.stringify({baseline,current})}`);
        assert(current.status.x + current.status.width <= current.actions.x + 1, `${label}: status and actions do not overlap`);
        assert(await status.evaluate(el => el.scrollWidth <= el.clientWidth + 1 && el.scrollHeight <= el.clientHeight + 1), `${label}: complete save status fits`);
        assert.equal(await header.getByRole('switch', { name:'Автосохранение заказа' }).count(), 1, 'One direct autosave control');
        return current;
      };
      try {
        await page.goto(`${base}/manager/orders/590?company=999&site=minsk&proposalId=586`);
        await workspace.getByTestId('add-service-line').waitFor(); await settle(page);
        const initial = await geometry(); await shot('normal');
        if (viewport.width === 1440) {
          const request = workspace.getByTestId('order-request-trigger');
          const count = request.locator('.order-request-file-count');
          assert((await count.innerText()).includes('2'), 'Wide request trigger keeps its numeric file count visible');
          const requestChevron = await box(request.locator('svg').last());
          const countBox = await box(count);
          assert(countBox.x + countBox.width < requestChevron.x, 'File count fits before the permanent chevron');
          const client = workspace.getByRole('button', { name:'Ответственный, клиент и объект', exact:true });
          const label = await box(client.locator('.order-context-short-label'));
          assert(label.x + label.width < (await box(client.locator('svg').last())).x, 'Concise client label fits before its chevron');
        }
        if (await autosave.getAttribute('aria-checked') === 'true') await autosave.click();
        assert.equal(await autosave.getAttribute('aria-checked'), 'false'); await assertLayout(initial, 'manual'); await shot('manual');
        await header.getByRole('button', { name:/^Изменить название:/ }).click();
        await header.getByRole('textbox', { name:'Название заказа' }).fill('Синтетическая проверка сохранения');
        await header.getByRole('textbox', { name:'Название заказа' }).press('Enter');
        await status.filter({ hasText:'Есть изменения' }).waitFor(); await assertLayout(initial, 'dirty'); await shot('dirty');
        holdSave = true; state.flags.failSave = true;
        await header.getByRole('button', { name:'Сохранить изменения', exact:true }).click();
        await status.filter({ hasText:'Сохраняем' }).waitFor(); await assertLayout(initial, 'saving'); await shot('saving');
        assert.equal(await header.getByRole('button', { name:'Сохраняем изменения' }).isDisabled(), true);
        holdSave = false; releaseSave();
        await status.filter({ hasText:'Не удалось сохранить' }).waitFor(); await assertLayout(initial, 'failed'); await shot('error');
        state.flags.failSave = false;
        await header.getByRole('button', { name:'Повторить сохранение' }).click();
        await status.filter({ hasText:'Сохранено' }).waitFor(); await assertLayout(initial, 'saved'); await shot('saved');
        await workspace.getByTestId('add-service-line').click();
        await workspace.getByTestId('service-title-input').fill('Синтетическая неприменённая услуга');
        await nav.getByRole('button').first().focus(); await page.keyboard.press('Home'); await settle(page);
        await status.filter({ hasText:'Строка не применена' }).waitFor(); await assertLayout(initial, 'pending'); await shot('pending');
        state.order.customer.name = state.order.customer.full_legal_name = longCustomer;
        await page.reload(); await workspace.getByTestId('add-service-line').waitFor(); await settle(page);
        const customer = header.locator('[data-order-header-customer]');
        assert((await customer.textContent()).includes(longCustomer));
        if (viewport.width < 768) assert((await box(customer)).height <= 37, 'Mobile customer uses at most two readable lines');
        assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth), false);
        await shot('long-customer');
        await page.getByRole('button', { name:'Ответственный, клиент и объект', exact:true }).click();
        await workspace.locator('#order-context-details').waitFor({ state:'visible' });
        assert((await workspace.locator('#order-context-details').innerText()).includes(longCustomer), 'Existing context panel exposes the complete customer name');
        await shot('long-customer-context');
        assert.deepEqual(errors, [], 'No browser exceptions');
        results.push({ viewport, initial, longCustomer:await box(customer), saves:state.patches.length });
        console.log(`${viewport.width} header states passed`);
      } catch (error) { await shot('FAILURE').catch(() => {}); throw error; }
      finally { releaseSave?.(); await context.close(); }
    }
    fs.writeFileSync(path.join(output, 'results.json'), JSON.stringify({ results }, null, 2));
    console.log(JSON.stringify({ cases:results.length, output }));
  } finally { await browser?.close(); await new Promise(resolve => fixture.server.close(resolve)); }
})().catch(error => { console.error(error); fixture.server.close(); process.exitCode = 1; });
