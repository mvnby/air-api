// Real Manager with isolated source, contract and drafts. No product updates permitted.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require(process.env.KITLANE_PLAYWRIGHT_MODULE || 'playwright');
const { createFixtureServer } = require('../proposal-mail/server.cjs');
const port = Number(process.env.KITLANE_FIXTURE_PORT || 5268);
const origin = `http://127.0.0.1:${port}`;
const output = process.env.KITLANE_SCREENSHOTS || '/tmp/mvn-waybill-composition-ui';
const revision = 'c'.repeat(64);
const fixture = createFixtureServer(port, async (req, res, { url, json }) => {
  if (url.pathname.endsWith('/waybill-composition')) {
    assert.equal(url.searchParams.get('proposal_id'), '586');
    json(res, { source_revision: revision, lines: [{ order_product_line_id:10, product_id:15, quantity:1, unit_price:'7400.00',
      country:'', title:'Сплит-система Atlas с удлинённым названием оборудования', components:null }] });
  } else if (url.pathname.endsWith('/customers/541/contracts')) {
    json(res, { items:[{id:71,customer_id:541,number:'ОД-2026-001',status:'active',valid_from:'2020-04-25',valid_until:'2099-04-25'}] });
  } else if (url.pathname.endsWith('/request-context')) json(res,{sources:[],files:[],warnings:[]});
  else return false;
  return true;
});

async function widthCheck(browser,width) {
  await fetch(`${origin}/__fixture/reset?kind=mixed&documents=false`);
  const context=await browser.newContext({viewport:{width,height:850},serviceWorkers:'block'});
  try {
    await context.route('**/*',route=>new URL(route.request().url()).origin===origin?route.continue():route.abort());
    const page=await context.newPage();
    page.setDefaultTimeout(10000);
    const errors=[], productWrites=[];
    page.on('pageerror',err=>errors.push(err.message));
    page.on('request',req=>{ if(req.method()==='PATCH' && req.postData()?.includes('"products"')) productWrites.push(req.url()); });
    await page.goto(`${origin}/manager/orders/590?company=999&site=minsk&proposalId=586`);
    await page.getByRole('navigation',{name:'Рабочая область заказа'}).getByRole('button',{name:'Документы',exact:true}).click();
    const create=page.getByTestId('create-native-draft');
    for (const kind of ['tn2','ttn1']) {
      await page.getByTestId(`native-document-type-${kind}`).click();
      const compose=page.getByTestId('native-waybill-composition');
      await compose.getByText('Сплит-система Atlas с удлинённым названием оборудования').waitFor();
      if(kind==='tn2') {
        await compose.getByRole('button',{name:'По частям'}).click();
        const names=compose.getByLabel('Название позиции'), prices=compose.getByLabel('Цена за единицу, BYN');
        await names.nth(0).fill('Внутренний блок Atlas');
        await names.nth(1).fill('Наружный блок Atlas');
        await prices.nth(0).fill('2465,00');
        await prices.nth(1).fill('4935,01');
        assert.equal(await create.isEnabled(),false);
        await prices.nth(1).fill('4935,00');
        await compose.getByRole('button',{name:'Целиком'}).click();
        await compose.getByRole('button',{name:'По частям'}).click();
        assert.equal(await prices.nth(1).inputValue(),'4935,00');
        const info = compose.getByText('Страна · шт.', {exact:true}).first();
        await info.click();
        await compose.getByLabel('Страна', {exact:true}).first().fill('Малайзия');
        await compose.scrollIntoViewIfNeeded();
        for(const item of await compose.locator('input:visible,textarea:visible,button:visible,label:visible,strong:visible').all()) {
          const box=await item.boundingBox();
          assert(box && box.x>=0 && box.x+box.width<=width+1,`Overflow ${width}`);
        }
        await compose.screenshot({path:path.join(output,`${width}-split.png`),animations:'disabled'});
      } else {
        assert.equal(await compose.getByRole('button',{name:'Целиком'}).getAttribute('aria-pressed'),'true');
        const country=compose.getByLabel('Страна происхождения');
        assert.equal(await country.inputValue(),'');
        await country.fill('Беларусь');
        await compose.screenshot({path:path.join(output,`${width}-whole.png`),animations:'disabled'});
      }
      await Promise.all([page.waitForResponse(r=>r.url().endsWith('/documents/drafts') && r.request().method()==='POST'), create.click()]);
      const payload=fixture.getState().creates.at(-1);
      assert.equal(payload.waybill_composition.source_revision,revision);
      const row=payload.waybill_composition.lines[0];
      assert.equal(row.order_product_line_id,10);
      assert.deepEqual(row.components?.map(item=>item.unit_price) || null,kind==='tn2'?['2465.00','4935.00']:null);
      if (kind === 'tn2') assert.deepEqual(row.components.map(item=>item.country),['Малайзия','']);
      else assert.equal(row.whole_country,'Беларусь');
      assert.equal(payload.document_type,kind);
    }
    assert.deepEqual(errors,[]); assert.deepEqual(productWrites,[]);
    console.log(`${width}px: split and whole waybills, exact cents, no order mutation`);
  } finally {await context.close();}
}
(async()=>{
  fs.mkdirSync(output,{recursive:true});
  await new Promise(resolve=>fixture.server.listen(port,'127.0.0.1',resolve));
  let browser;
  try { browser=await chromium.launch({headless:true,executablePath:process.env.KITLANE_CHROMIUM_PATH});
    for(const width of [320,390,1440]) await widthCheck(browser,width);
  } finally {await browser?.close();fixture.server.close();}
})().catch(err=>{console.error(err);process.exitCode=1;});
