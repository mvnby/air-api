// Real Manager with two issuers, selectable waybills and synthetic order data.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require(process.env.KITLANE_PLAYWRIGHT_MODULE || 'playwright');
const { createFixtureServer } = require('../proposal-mail/server.cjs');

const port = Number(process.env.KITLANE_FIXTURE_PORT || 5253);
const origin = `http://127.0.0.1:${port}`;
const output = process.env.KITLANE_SCREENSHOTS || '/tmp/mvn-ttn-route-screens';
const fixture = createFixtureServer(port, async (req, res, {url, state, json, body}) => {
  const p = url.pathname;
  if (p.endsWith('/waybill-composition')) {
    assert.equal(url.searchParams.get('proposal_id'), '586');
    json(res, {source_revision: 'd'.repeat(64), lines: [{order_product_line_id: 10, product_id: 10,
      title: 'Вентилятор', country: '', quantity: 1, unit_price: '500.00', components: null}]});
    return true;
  }
  if (p.endsWith('/request-context')) json(res, { sources: [], warnings: [], files: [] });
  else if (p.endsWith('/customers/541/contracts')) json(res, { items: [] });
  else if (p.endsWith('/document-system/legal-entities')) {
    json(res, {items: [5, 6].map(id => ({id, tenant_id: 999, display_name: id === 5 ? 'Продавец' : 'Второе юрлицо',
      is_default: id === 5, status: 'active', requisites: { city: 'Витебск' }}))});
  } else if (p.endsWith('/document-system/templates') && ['tn2','ttn1'].includes(url.searchParams.get('doc_type'))) {
    const type = url.searchParams.get('doc_type'), issuer = Number(url.searchParams.get('legal_entity_id'));
    const ids = type === 'tn2' ? [110,111] : [210,211];
    const name = type === 'tn2' ? 'ТН-2' : 'ТТН-1';
    json(res, {items: issuer === 5 ? ids.map((id, index) => ({id, tenant_id: 999, legal_entity_id: issuer,
      name: name + (index ? ' — второй бланк' : ' — основной'), doc_type: type, is_active: true, is_default: !index,
      sort_order: index, created_at: '2026-11-06'})) : []});
  } else if (/\/templates\/(110|111|210|211)\/versions$/.test(p)) {
    const id = Number(p.split('/').at(-2));
    json(res, {items: [{id: id+1000, template_id: id, version: 1, status: id === 210 ? 'archived' : 'active',
      renderer: 'docx', checksum_sha256: 'b'.repeat(64), placeholder_schema: {}, created_at: '2026-11-06'}]});
  } else if (p.endsWith('/orders/590/documents/drafts')) {
    const payload = await body(req);
    state.creates.push(payload);
    const doc = {id: payload.document_type === 'ttn1' ? 863 : 862, order_id: 590, proposal_id: 586, doc_type: payload.document_type, status: 'draft', provider: 'native',
      date: '2026-11-06', created_at: '2026-11-06', legal_entity_id: 5, artifacts: []};
    state.documents.unshift(doc);
    state.route = payload.transport_terms;
    json(res, doc);
  } else if (p.endsWith('/documents/863/draft/parameters')) {
    if (req.method === 'PATCH') {
      Object.assign(state.route, (await body(req)).transport_terms);
      json(res, state.documents[0]);
    } else json(res, {document_id: 863, doc_type: 'ttn1', issue_date: '2026-11-06', issue_city: '', total_amount: '500',
      transport_terms: state.route, revision: 'test', has_editable_copy: false, order_conditions: ''});
  } else return false;
  return true;
});

async function examine(browser, width) {
  await fetch(`${origin}/__fixture/reset?kind=mixed&documents=false`);
  const state = fixture.getState();
  state.documents.push({id: 900, order_id: 590, doc_type: 'contract', status: 'issued', legal_entity_id: 5,
    proposal_id: 586, provider: 'native', official_full_number: 'Д-2026-020', date: '2026-01-03', created_at: '2026-01-03', artifacts: []});
  state.documents.push({id: 901, order_id: 590, doc_type: 'tn2', status: 'draft', legal_entity_id: 6,
    proposal_id: 586, provider: 'native', date: '2026-11-05', created_at: '2026-11-05', artifacts: []});
  const context = await browser.newContext({ viewport: { width, height: width <= 390 ? 844 : 960 }, serviceWorkers: 'block' });
  await context.route('**/*', route => new URL(route.request().url()).origin === origin ? route.continue() : route.abort());
  const page = await context.newPage();
  page.setDefaultTimeout(10000);
  const errors = [];
  page.on('pageerror', err => errors.push(err.message));
  try {
    await page.goto(`${origin}/manager/orders/590?company=999&site=minsk&proposalId=586`);
    await page.getByRole('navigation', {name: 'Рабочая область заказа'}).getByRole('button', {name:'Документы', exact:true}).click();
    await page.getByTestId('native-document-type-tn2').click();
    const panel = page.getByTestId('transport-terms-panel');
    const chooser = page.getByTestId('native-document-template');
    const create = page.getByTestId('create-native-draft');
    const more = page.getByTestId('native-document-more').locator('summary');
    await more.click();
    await page.getByTestId('native-legal-entity').selectOption('6');
    await more.click();
    const warning = page.getByTestId('waybill-template-status');
    await warning.getByText('Для «Второе юрлицо» нужно подключить шаблон ТН-2.').waitFor();
    assert.equal(await panel.count(),0);
    assert.equal(await page.getByTestId('native-waybill-composition').count(),0);
    assert.equal(await create.isEnabled(),false);
    assert(await page.getByTestId('current-document-901').getByRole('button',{name:'Выпустить',exact:true}).isEnabled());
    await warning.screenshot({path:path.join(output,`${width}-missing-template.png`),animations:'disabled'});
    await more.click();
    await page.getByTestId('native-legal-entity').selectOption('5');
    await more.click();
    await chooser.selectOption('111');
    assert.equal(await chooser.inputValue(),'111');
    await warning.waitFor({state:'detached'});
    assert.equal(await panel.count(),0);
    const templateDetails = page.getByTestId('native-document-options');
    const caption = templateDetails.locator('summary');
    assert((await caption.innerText()).includes('ТН-2 — второй бланк'));
    assert(await caption.evaluate(el => el.scrollWidth <= el.clientWidth+1));
    await templateDetails.evaluate(el => el.scrollIntoView({block:'center',behavior:'instant'}));
    await caption.click({trial:true});
    await templateDetails.screenshot({path:path.join(output,`${width}-template-choice.png`),animations:'disabled'});
    const basis = page.getByTestId('native-document-basis');
    async function selectContract() {
      const option = basis.locator('option').filter({hasText:'Д-2026-020'});
      await option.waitFor({state: 'attached'});
      await basis.selectOption(await option.getAttribute('value'));
    }
    await selectContract();
    await create.scrollIntoViewIfNeeded();
    await page.screenshot({path:path.join(output,`${width}-tn2.png`),animations:'disabled'});
    await create.click();
    await page.getByTestId('current-document-862').waitFor();
    assert.equal(state.creates[0].document_type,'tn2');
    assert.equal(state.creates[0].template_id,111);
    assert.equal(state.creates[0].waybill_composition.source_revision,'d'.repeat(64));
    assert(!Object.hasOwn(state.creates[0],'transport_terms'));
    await page.getByTestId('native-document-type-ttn1').click();
    await warning.getByText(/нет активной версии DOCX/).waitFor();
    assert.equal(await panel.count(),0);
    await chooser.selectOption('211');
    await selectContract();
    await panel.waitFor();
    assert.equal(await create.isEnabled(),true);
    await panel.locator(':scope > summary').click();
    for (const [label, value] of Object.entries({
      'Регистрационный номер':'1234 АА-1','Водитель':'Водитель','Перевозчик':'Перевозчик',
      'Пункт погрузки':'Витебск, учебный склад 1','Пункт разгрузки':'Витебск, учебный склад с длинным названием 2',
      'Номер путевого листа':'б/н','Заказчик автоперевозки (плательщик)':'Грузоотправитель',
    })) await panel.getByLabel(label, {exact:true}).fill(value);
    const loading = panel.getByTestId('ttn-loading-operation');
    await loading.locator('summary').click();
    for (const [label, value] of Object.entries({
      'Исполнитель':'Отправитель', 'Способ':'ручной', 'Прибытие':'2026-11-05T23:55', 'Убытие':'2026-11-05T12:00', 'Время простоя, мин':'30',
    })) await loading.getByLabel(label).fill(value);
    assert.equal(await create.isEnabled(),false);
    await loading.getByLabel('Убытие').fill('2026-11-06T00:25');
    assert.equal(await create.isEnabled(),true);
    for (const control of await panel.locator('input:visible,textarea:visible,summary').all()) {
      const box = await control.boundingBox();
      assert(box && box.x>=0 && box.x+box.width <= width+1, `overflow at ${width}`);
    }
    await panel.getByLabel('Пункт разгрузки').scrollIntoViewIfNeeded();
    await page.screenshot({path:path.join(output,`${width}-route.png`),animations:'disabled'});
    await loading.scrollIntoViewIfNeeded();
    await page.screenshot({path:path.join(output,`${width}-operations.png`),animations:'disabled'});
    await create.click();
    const card = page.getByTestId('current-document-863');
    await card.waitFor();
    assert.equal(state.creates[1].template_id,211);
    const editor = card.getByTestId('transport-terms-panel');
    assert.equal(await editor.getByLabel('Номер путевого листа').inputValue(), 'б/н');
    await editor.getByLabel('Пункт разгрузки').fill('Склад 3');
    await card.getByTestId('save-draft-parameters').click();
    await editor.waitFor({state:'detached'});
    assert.equal(state.route.unloading_point,'Склад 3');
    assert.equal(state.route.loading.downtime_minutes,30);
    assert(await page.evaluate(()=>document.documentElement.scrollWidth <= document.documentElement.clientWidth));
    assert.deepEqual(errors, []);
    console.log(`${width}px: TN-2, TTN-1, route, handling, draft edit OK`);
  } catch(error) {
    console.error({width,text:(await page.locator('body').innerText()).slice(-1200)});
    await page.screenshot({path:path.join(output,`${width}-failure.png`)});
    throw error;
  } finally {await context.close();}
}
(async()=>{
  fs.mkdirSync(output, {recursive:true});
  await new Promise(resolve=>fixture.server.listen(port,'127.0.0.1',resolve));
  let browser;
  try {
    browser=await chromium.launch({headless:true,executablePath:process.env.KITLANE_CHROMIUM_PATH});
    for(const width of [320,390,1440]) await examine(browser,width);
  } finally {await browser?.close();fixture.server.close();}
})().catch(err=>{console.error(err);process.exitCode=1;});
