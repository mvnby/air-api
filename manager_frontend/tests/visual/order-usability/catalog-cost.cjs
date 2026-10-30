// Exact catalog values, real master-search capability, synthetic localhost saves only.
const { chromium } = require(process.env.KITLANE_PLAYWRIGHT_MODULE || 'playwright');
const { createFixtureServer } = require('../order-request/server.cjs');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const output = path.resolve(process.env.KITLANE_SCREENSHOTS || '/tmp/order-catalog-cost');
fs.mkdirSync(output, { recursive:true });
const fixture = createFixtureServer(Number(process.env.KITLANE_FIXTURE_PORT || 5208));
const base = `http://127.0.0.1:${fixture.port}`;
// Values from the read-only investigation of the reported TCL selection.
const product = { id:117, title:'TCL Elite TAC-24CHSA/XAB1N', price:2470, min_cost_byn:1559.65, availability_status:'available', vitebsk_qty:0, minsk_qty:20, product_kind:'complete_split_system', is_inverter:false };
const scenarios = [
  { width:1440, height:900, action:'direct' }, { width:1440, height:900, action:'navigate' },
  { width:320, height:684, action:'direct' }, { width:320, height:684, action:'navigate' },
  { width:320, height:684, action:'direct', restored:true }, { width:320, height:684, action:'navigate', restored:true },
];
const results = [];
const settle = page => page.waitForTimeout(450);
async function viewport(page, height) {
  await page.evaluate(height => {
    Object.defineProperty(visualViewport, 'height', { configurable:true, get:() => height });
    visualViewport.dispatchEvent(new Event('resize'));
  }, height);
}
async function click(page, locator, mobile) {
  if (!mobile) return locator.click();
  const b = await locator.boundingBox(); assert(b);
  assert(await locator.evaluate(el => { const r=el.getBoundingClientRect(), h=document.elementFromPoint(r.x+r.width/2,r.y+r.height/2); return h===el || el.contains(h); }), 'First touch target is unobscured');
  return page.touchscreen.tap(b.x+b.width/2, b.y+b.height/2);
}
// The existing fixture owns persistence; hydrate catalog snapshots and totals as
// the actual order response does, so reload assertions inspect saved state.
function hydrate() {
  const order = fixture.getState().order, proposal = order.proposals[0];
  for (const row of proposal.product_lines) { row.product_title=product.title; row.line_total=row.price*row.quantity; }
  order.product_lines=proposal.product_lines;
  proposal.total_amount=[...proposal.product_lines,...proposal.service_lines].reduce((sum,row) => sum+row.price*row.quantity, 0);
  order.total_amount=proposal.total_amount; order.balance_due=order.total_amount;
}
let browser;
(async () => {
  await new Promise(resolve => fixture.server.listen(fixture.port, '127.0.0.1', resolve));
  browser = await chromium.launch({ headless:true, ...(process.env.KITLANE_CHROMIUM_PATH ? { executablePath:process.env.KITLANE_CHROMIUM_PATH } : {}) });
  try {
    for (const cfg of scenarios) {
      const name=`${cfg.width}-${cfg.restored ? 'restored-' : ''}${cfg.action}`;
      if (process.env.KITLANE_CASE && process.env.KITLANE_CASE !== name) continue;
      fixture.reset('service');
      const state=fixture.getState(), mobile=cfg.width<768;
      const context=await browser.newContext({ viewport:{width:cfg.width,height:cfg.height}, isMobile:mobile, hasTouch:mobile, serviceWorkers:'block' });
      if (cfg.restored) await context.addInitScript(product => {
        if (sessionStorage.getItem('__catalogCostSeeded')) return;
        const row={ product_id:product.id, product_query:product.title, price:product.price, cost:product.min_cost_byn, quantity:2, editor:{original:null} };
        sessionStorage.setItem('manager_order_drawer_draft_590_586', JSON.stringify({ version:2, orderId:590, proposalId:586, baseForm:{}, baseLines:{products:[],services:[]}, linesDraft:{products:[row],services:[]}, productLines:[row], serviceLines:[] }));
        sessionStorage.setItem('__catalogCostSeeded','1');
      }, product);
      let searches=0;
      await context.route('**/*', async route => {
        const url=new URL(route.request().url());
        if (url.origin!==base) return route.abort();
        if (url.pathname.endsWith('/me')) {
          const response=await route.fetch(), data=await response.json();
          return route.fulfill({ json:{...data,capabilities:[...data.capabilities,'catalog.master.edit']} });
        }
        if (url.pathname==='/api/manager/products/smart-search') { searches++; return route.fulfill({ json:{items:[product],total:1} }); }
        if (url.pathname==='/api/manager/tenant-catalog/products') assert.fail('Master-search regression must not silently use the tenant mapper that omits purchase cost');
        if (url.pathname==='/api/manager/orders/590') {
          const response=await route.fetch(); hydrate(); return route.fulfill({ json:fixture.getState().order });
        }
        return route.continue();
      });
      const page=await context.newPage(); page.setDefaultTimeout(12000);
      const errors=[]; page.on('pageerror',error=>errors.push(error.message));
      const title=page.getByPlaceholder('Найти в каталоге или ввести название');
      const shot=suffix=>page.screenshot({path:path.join(output,`${name}-${suffix}.png`),animations:'disabled'});
      try {
        await page.goto(`${base}/manager/orders/590?company=999&site=minsk&proposalId=586`);
        await page.getByTestId('add-product-line').waitFor();
        if (!cfg.restored) await page.getByTestId('add-product-line').click();
        await title.waitFor(); await title.focus();
        if (mobile) await viewport(page,360);
        if (!cfg.restored) { await title.fill('TCL'); await click(page,page.getByTestId('select-product-117'),mobile); }
        const row=page.getByTestId('product-line-row').filter({has:title});
        assert.equal(await row.getByRole('spinbutton',{name:/^Цена/}).inputValue(),'2470','Untouched retail price');
        assert.equal(await row.getByRole('spinbutton',{name:'Себестоимость'}).count(),0,'Cost is hidden by default');
        await row.getByRole('spinbutton',{name:/Кол-во/}).fill('2'); await settle(page);
        await shot('before');
        if (cfg.action==='direct') {
          await click(page,row.locator('[data-line-editor-actions] button').last(),mobile);
          await title.waitFor({state:'hidden'});
        } else {
          if (mobile) { await viewport(page,cfg.height); await settle(page); }
          await page.getByRole('button',{name:'Документы',exact:true}).click();
          await page.getByRole('button',{name:'Применить и сохранить',exact:true}).click();
          await page.getByTestId('native-documents-workspace').waitFor();
        }
        await page.waitForFunction(() => document.querySelector('[aria-label="Рабочая область заказа"] > header [role="status"]')?.textContent==='Сохранено');
        assert.equal(state.patches.length,1,'Exactly one order PATCH must occur');
        const saved=state.order.proposals[0].product_lines;
        assert.equal(saved.length,1); assert.equal(saved[0].product_id,117);
        assert.equal(saved[0].price,2470); assert.equal(saved[0].cost,1560); assert.equal(saved[0].quantity,2);
        assert.equal(saved[0].line_total,4940); assert.equal(state.order.total_amount,6560);
        assert.equal(product.min_cost_byn,1559.65,'Raw catalog metadata is preserved');
        assert.equal(searches>0,!cfg.restored,'Restored draft does not need a fresh selection');
        if (mobile) await viewport(page,cfg.height);
        await page.reload();
        await page.getByRole('region',{name:'Рабочая область заказа',exact:true}).locator(':scope > header').waitFor();
        if (cfg.action==='navigate') await page.getByRole('button',{name:'Предложение',exact:true}).click();
        await page.getByTestId('product-line-row').filter({hasText:product.title}).waitFor();
        assert.equal(await title.count(),0,'No trapped editor returns after reload');
        assert((await page.locator('[data-order-scroll]').innerText()).includes(product.title));
        assert.equal(await page.getByTestId('proposal-grand-total').textContent().then(text=>Number(text.replace(/[^\d]/g,''))),6560);
        await shot('saved'); assert.deepEqual(errors,[]);
        results.push({name,searches,patches:state.patches,saved,total:state.order.total_amount}); console.log(`${name} passed`);
      } catch(error) { await shot('FAILURE').catch(()=>{}); throw error; }
      finally { await context.close(); }
    }
    fs.writeFileSync(path.join(output,'results.json'),JSON.stringify({product,results},null,2));
    console.log(JSON.stringify({cases:results.length,output}));
  } finally { await browser?.close(); await new Promise(resolve=>fixture.server.close(resolve)); }
})().catch(error=>{console.error(error);fixture.server.close();process.exitCode=1;});
