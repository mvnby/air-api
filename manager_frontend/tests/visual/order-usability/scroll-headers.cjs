// Full Manager shell, production build, synthetic localhost data only.
const { chromium } = require(process.env.KITLANE_PLAYWRIGHT_MODULE || 'playwright');
const { createFixtureServer } = require('../order-request/server.cjs');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const output = path.resolve(process.env.KITLANE_SCREENSHOTS || '/tmp/order-scroll-headers');
fs.mkdirSync(output, { recursive: true });
const fixture = createFixtureServer(Number(process.env.KITLANE_FIXTURE_PORT || 5204));
const base = `http://127.0.0.1:${fixture.port}`;
const sizes = [{ width: 973, height: 684 }, { width: 390, height: 844 }, { width: 320, height: 684 }, { width: 1440, height: 900 }];
const results = [];
const geometry = page => page.evaluate(() => {
  const measure = selector => { const el = document.querySelector(selector), rect = el.getBoundingClientRect(); return { y: rect.y, height: rect.height, scrollTop: el.scrollTop, scrollHeight: el.scrollHeight, clientHeight: el.clientHeight }; };
  return { shell: measure('.kitlane-topbar'), order: measure('[aria-label="Рабочая область заказа"] > header'), tabs: measure('[data-testid="order-section-navigation"]'), content: measure('[data-order-scroll]') };
});
const settle = page => page.waitForTimeout(500);
let browser;
(async () => {
  await new Promise(resolve => fixture.server.listen(fixture.port, '127.0.0.1', resolve));
  browser = await chromium.launch({ headless: true, ...(process.env.KITLANE_CHROMIUM_PATH ? { executablePath: process.env.KITLANE_CHROMIUM_PATH } : {}) });
  try {
    for (const viewport of sizes) {
      if (process.env.KITLANE_VIEWPORT && Number(process.env.KITLANE_VIEWPORT) !== viewport.width) continue;
      for (const scenario of ['documents', 'short-proposal']) {
        if (process.env.KITLANE_SCENARIO && process.env.KITLANE_SCENARIO !== scenario) continue;
        await fetch(`${base}/__request/reset?scenario=manual`);
        const state = fixture.getState();
        if (scenario === 'documents') state.documents = Array.from({ length: 12 }, (_, index) => ({ ...state.documents[0], id: 862 + index, display_number: `КП-2026-${index + 1}`, official_full_number: `КП-2026-${index + 1}` }));
        else state.order.service_lines = state.order.proposals[0].service_lines = Array.from({ length: 3 }, (_, index) => ({ ...state.order.service_lines[0], id: index + 1, service_title: `Обслуживание ${index + 1}` }));
        const context = await browser.newContext({ viewport, isMobile: viewport.width < 768, hasTouch: viewport.width < 768, serviceWorkers: 'block' });
        await context.route('**/*', route => new URL(route.request().url()).origin === base ? route.continue() : route.abort());
        const page = await context.newPage(); page.setDefaultTimeout(12000);
        const errors = []; page.on('pageerror', error => errors.push(error.message));
        try {
          await page.goto(`${base}/manager/orders/590?company=999&site=minsk&proposalId=586`);
          const workspace = page.getByRole('region', { name: 'Рабочая область заказа', exact: true });
          await workspace.getByTestId('add-service-line').waitFor();
          const nav = page.getByRole('navigation', { name: 'Рабочая область заказа', exact: true });
          if (scenario === 'documents') { await nav.getByRole('button', { name: 'Документы', exact: true }).click(); await page.getByTestId('native-documents-workspace').waitFor(); }
          await page.evaluate(() => document.fonts.ready); await settle(page);
          const scroller = workspace.locator('[data-order-scroll]');
          const shot = suffix => page.screenshot({ path: path.join(output, `${viewport.width}-${scenario}-${suffix}.png`), animations: 'disabled' });
          const initial = await geometry(page); await shot('initial');
          await scroller.hover(); await page.mouse.wheel(0, 400); await settle(page);
          const down = await geometry(page); await shot('down');
          assert(down.shell.height < 1 && down.order.height < 1, `Both headers collapse: ${JSON.stringify({viewport,scenario,down})}`);
          assert(down.content.y <= 64, `Only section navigation remains: ${JSON.stringify(down)}`);
          assert(down.content.height >= initial.content.height + 195, 'Full upper stack is reclaimed');
          await settle(page); assert.deepEqual(await geometry(page), down, 'No resize oscillation after settling');
          await page.mouse.wheel(0, -60); await settle(page);
          const up = await geometry(page); await shot('up');
          assert(up.shell.height > 40 && up.order.height > 40, 'Reverse scroll restores both headers');
          await scroller.evaluate(el => { el.scrollTop = 0; }); await settle(page);
          const top = await geometry(page); assert.equal(top.content.y, initial.content.y, 'Returning to top restores initial layout');
          await scroller.hover(); await page.mouse.wheel(0, 400); await settle(page);
          await nav.getByRole('button').first().focus(); await page.keyboard.press('Home'); await settle(page);
          assert((await geometry(page)).shell.height > 40 && (await geometry(page)).order.height > 40, `Home from navigation restores headers: ${JSON.stringify(await geometry(page))}`);
          await scroller.hover(); await page.mouse.wheel(0, 400); await settle(page);
          await nav.getByRole('button').first().focus(); await page.keyboard.press('Shift+Tab'); await settle(page);
          assert(await workspace.locator(':scope > header').evaluate(el => el.contains(document.activeElement)), 'Shift+Tab restores and enters order header');
          await scroller.evaluate(el => { el.scrollTop = 0; }); await settle(page);
          await scroller.hover(); await page.mouse.wheel(0, 400); await page.waitForTimeout(60); await page.mouse.wheel(0, -60); await settle(page);
          assert((await geometry(page)).shell.height > 40 && (await geometry(page)).order.height > 40, 'Reversal during resize restores headers');
          await scroller.evaluate(el => { el.scrollTop = 0; }); await settle(page);
          const title = workspace.getByRole('button', { name: /^Изменить название:/ });
          await title.focus(); await scroller.evaluate(el => { el.scrollTop = 220; }); await settle(page);
          assert((await geometry(page)).order.height > 40, 'Focused title remains visible');
          await scroller.evaluate(el => { el.scrollTop = 0; }); await settle(page); await title.evaluate(el => el.blur()); await scroller.hover(); await page.mouse.wheel(0, -60); await settle(page);
          await workspace.getByRole('button', { name: 'Дополнительные действия', exact: true }).click();
          await scroller.evaluate(el => { el.scrollTop = 220; }); await settle(page);
          assert((await geometry(page)).order.height > 40, 'Open order menu remains visible');
          await page.keyboard.press('Escape');
          await nav.getByRole('button').first().focus(); await page.keyboard.press('Home'); await settle(page);
          const account = page.getByRole('button', { name: /^Аккаунт:/ });
          await account.click(); await account.evaluate(el => el.blur());
          await scroller.evaluate(el => { el.scrollTop = 220; }); await settle(page);
          assert((await geometry(page)).shell.height > 40, 'Open account menu remains visible after trigger blur');
          await page.keyboard.press('Escape');
          assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth), false, 'No horizontal page overflow');
          assert.deepEqual(errors, [], 'No browser exceptions'); assert.equal(state.patches.length, 0, 'Read-only verification never saves order');
          results.push({ viewport, scenario, initial, down, up, top });
          console.log(`${viewport.width} ${scenario} passed`);
        } catch (error) { await page.screenshot({ path: path.join(output, `${viewport.width}-${scenario}-FAILURE.png`) }); throw error; }
        finally { await context.close(); }
      }
    }
    fs.writeFileSync(path.join(output, 'results.json'), JSON.stringify({ results }, null, 2));
    console.log(JSON.stringify({ cases: results.length, output }));
  } finally { await browser?.close(); await new Promise(resolve => fixture.server.close(resolve)); }
})().catch(error => { console.error(error); fixture.server.close(); process.exitCode = 1; });
