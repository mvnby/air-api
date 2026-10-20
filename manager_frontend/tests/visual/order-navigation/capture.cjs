// Behavioral regressions on a local production build; every API response is synthetic.
const { chromium } = require(process.env.KITLANE_PLAYWRIGHT_MODULE || 'playwright');
const fs = require('node:fs');
const { auth, stores } = require('../kitlane/fixtures.json');
const assert = require('node:assert/strict');
const path = require('node:path');
const base = process.env.KITLANE_PREVIEW_URL || 'http://127.0.0.1:5187';
assert(['127.0.0.1', 'localhost'].includes(new URL(base).hostname), 'Only local preview is allowed');
const output = path.resolve(process.env.KITLANE_SCREENSHOTS || '.codex-tmp/order-navigation');
fs.mkdirSync(output, {recursive:true});
const checks = [];
const caseFilter = process.env.KITLANE_NAV_CASES && new RegExp(process.env.KITLANE_NAV_CASES);
const line = (id, title, price) => ({ id, proposal_id: id, service_title: title, quantity: 1, price, cost: 0, line_total: price });
const order = {
  id: 477, title: 'Аудит заказа', status: 'negotiation', lead_source: 'email', workflow_type: 'repair',
  negotiation_status: 'awaiting_offer', execution_status: 'needs_schedule', created_at: '2026-10-20T08:00:00Z',
  is_paid: false, total_amount: 1200, total_cost: 0, margin: 1200, total_payments: 0, balance_due: 1200,
  payments: [], documents: [], product_lines: [], service_lines: [line(24, 'Услуга варианта А', 1200)], work_stages: [],
  customer: { id: 12, name: 'Тестовый клиент', type: 'company' },
  proposals: [
    { id: 24, name: 'Вариант А', status: 'draft', is_selected: true, is_archived: false, product_lines: [], service_lines: [line(24, 'Услуга варианта А', 1200)], total_amount: 1200 },
    { id: 25, name: 'Вариант Б', status: 'draft', is_selected: false, is_archived: false, product_lines: [], service_lines: [line(25, 'Услуга варианта Б', 2300)], total_amount: 2300 },
  ],
};
let browser;
async function fixture(width = 1440, height = 900) {
  const context = await browser.newContext({ viewport: { width, height }, isMobile: width < 768, hasTouch: width < 768 });
  const page = await context.newPage();
  page.setDefaultTimeout(7000);
  const requests = [], patches = [], errors = [];
  let current = {...structuredClone(order), workflow_type:'sales_installation'}, failSave = false;
  const documents = [];
  page.on('pageerror', e => errors.push(e.message));
  await page.route('**/*', async route => {
    const url = new URL(route.request().url());
    if (['fonts.googleapis.com', 'fonts.gstatic.com'].includes(url.hostname)) return route.continue();
    if (url.origin !== base) return route.abort();
    if (!url.pathname.startsWith('/api') && !url.pathname.startsWith('/login')) return route.continue();
    requests.push({ method: route.request().method(), path: url.pathname + url.search });
    let data = { items: [], total: 0, meta: { pages: 1 }, enabled: false };
    if (url.pathname === '/api/manager/account/companies') data = {
      staff_user_id: 999, username: auth.username, is_platform_owner: true, default_tenant_id: 999,
      items: [{ tenant_id: 999, slug: 'test', display_name: 'Тестовая компания', role: 'owner', membership_id: 999, access_kind: 'membership', is_system: true, demo_read_only: false, default_storefront_slug: 'minsk' }], total: 1, page: 1, limit: 100,
    };
    else if (url.pathname.endsWith('/me')) data = auth;
    else if (url.pathname.endsWith('/storefronts')) data = { items: stores.map(store => ({ ...store, id: store.slug === 'minsk' ? 999 : 998 })) };
    else if (url.pathname === '/api/manager/orders') data = { items: Array.from({ length: 18 }, (_, index) => ({ ...current, id: index === 8 ? 477 : 500 + index, title: index === 8 ? current.title : `Тестовый заказ ${index + 1}` })), meta: { pages: 1, total: 18 } };
    else if (url.pathname === '/api/manager/orders/477') {
      if (route.request().method() === 'PATCH') { if (failSave) return route.fulfill({status:500,json:{detail:'Synthetic save failure'}}); patches.push(route.request().postDataJSON()); current = { ...current, ...patches.at(-1) }; }
      data = current;
    }
    else if (url.pathname === '/api/manager/orders/477/proposals/25/archive' && route.request().method() === 'POST') {
      current.proposals[1].is_archived = true;
      data = current;
    }
    else if (url.pathname === '/api/manager/document-system/orders/477/documents') data = {items:documents};
    else if (url.pathname === '/api/manager/calendar/events') data = [];
    else if (url.pathname === '/api/manager/orders/work-stages/stale') data = {items:[{id:1,order_id:477,order_title:current.title,name:'Тестовая работа',status:'scheduled',customer_name:current.customer.name}],total:1};
    else if (url.pathname === '/api/manager/customers/12') data = current.customer;
    else if (url.pathname.endsWith('/installer-workspace')) data = { order_id: 477, assignments: [], materials: [], collection: { version: 1, assignment_id: null, amount: null, currency: null, status: 'not_assigned', updated_at: null }, balances: [], financial_fingerprint: 'synthetic' };
    else if (url.pathname.endsWith('/worker-pay')) data = { order_id: 477, agreements: [], candidates: [] };
    else if (url.pathname.endsWith('/tender-workflow')) data = { order_id: 477, stage: null, deadline_at: null, price_enquiry: null, publications: [], history: [] };
    return route.fulfill({ json: data });
  });
  const workspace = page.getByRole('region', { name: 'Рабочая область заказа', exact: true });
  return { context, page, workspace, requests, patches, errors, documents, current:()=>current, failSave:(value)=>{failSave=value;} };
}

const boardPath='/manager/orders/kanban?segment=b2b&view=kanban&groupBy=none&search=office&assigned_to_me=1&status=negotiation&sort=margin_desc&workFilter=unpaid&hideOnHold=false&filtersOpen=true';
const location=page=>page.evaluate(()=>window.location.pathname+window.location.search);
async function runCase(width,name,task) {
 if(caseFilter && !caseFilter.test(name)) return;
 const f=await fixture(width,850);
 try { await task(f);assert.deepEqual(f.errors,[]);checks.push({width,name});console.log(width,name,'passed'); }
 finally { await f.context.close(); }
}
async function openBoard(f,grouped=false) {
 await f.page.goto(base+(grouped?boardPath.replace('groupBy=none','groupBy=customer'):boardPath));
 const board=f.page.locator('div.flex.gap-4.overflow-x-auto.pb-4');
 const column=board.locator(':scope > section').first();
 await column.getByTitle('Фильтр: Все').click();
 await column.getByRole('button',{name:/Ждет предложение/}).click();
 if(grouped) await column.locator('div[role="button"][tabindex="0"][aria-expanded="false"]').first().click();
 const card=column.locator('article[draggable]').filter({hasText:'№477'});
 await card.getByRole('button',{name:'Раскрыть заказ',exact:true}).click();
 await board.evaluate(el=>el.scrollLeft=160);await f.page.evaluate(()=>scrollTo(0,500));
 const expected={url:await location(f.page),state:await f.page.evaluate(()=>({top:scrollY}))};
 await card.getByRole('button',{name:'Открыть заказ',exact:true}).evaluate(el=>el.click());await f.workspace.waitFor();
 return {...expected,board,column,grouped};
}
async function assertBoard(f,expected) {
 await f.page.waitForFunction(url=>location.pathname+location.search===url,expected.url);
 await f.page.waitForFunction(()=>Math.abs(scrollY-500)<2);
 assert.equal(await expected.board.evaluate(el=>el.scrollLeft),160);
 assert.equal(await expected.column.getByTitle('Фильтр: Ждет предложение').count(),1);
 assert.equal(await expected.column.getByRole('button',{name:'Свернуть заказ',exact:true}).count(),1);
 if(expected.grouped) assert.equal(await expected.column.locator('div[role="button"][tabindex="0"][aria-expanded="true"]').count(),1);
}
async function openCustomer(f) {
 if(await f.workspace.getByRole('button',{name:'Ответственный, клиент и объект',exact:true}).isVisible()) await f.workspace.getByRole('button',{name:'Ответственный, клиент и объект',exact:true}).click();
 await f.workspace.locator('[data-order-usage="context-customer"]').click();
 await f.workspace.getByRole('button',{name:'Открыть полную карточку клиента',exact:true}).click();
}
async function childRoundtrip(f,child) {
 if(child==='customer') {
  await openCustomer(f);
  await f.page.getByRole('button',{name:'Назад',exact:true}).click();
 }else{
  await f.workspace.getByRole('button',{name:'Подобрать по параметрам',exact:true}).click();
  assert.equal(new URL(f.page.url()).searchParams.get('proposalId'),'25');
  await f.page.getByRole('link',{name:'Вернуться в заказ',exact:true}).click();
 }
 await f.workspace.waitFor();
 await f.page.getByText('Услуга варианта Б',{exact:true}).waitFor();
 assert.equal(new URL(f.page.url()).searchParams.get('proposalId'),'25');
}
async function chooseB(f) {
 await f.workspace.getByRole('button',{name:/Вариант Б/}).click();
 await f.page.waitForURL(url=>url.searchParams.get('proposalId')==='25');
 await f.page.reload();await f.workspace.waitFor();
 await f.page.getByText('Услуга варианта Б',{exact:true}).waitFor();
}
async function openIncompleteDocument(f) {
 f.documents.push({id:77,order_id:477,proposal_id:25,legal_entity_id:5,doc_type:'contract',status:'draft',provider:'native',
  internal_reference:'draft77',display_number:'draft77',date:'2026-10-20',created_at:'2026-10-20T08:00:00Z',artifacts:[],
  customer_readiness:{checked:true,can_issue:false,missing_fields:[{key:'legal_address',label:'Юридический адрес клиента',critical:true}]}});
 await f.workspace.getByRole('button',{name:'Документы',exact:true}).click();
 const warning=f.page.getByTestId('native-draft-missing-fields');
 await warning.getByText(/Юридический адрес клиента/).waitFor();
 return warning.getByRole('button',{name:'Заполнить карточку',exact:true});
}
(async()=>{
 browser=await chromium.launch({headless:true});
 try{
 for(const width of [384,1440]) {
  for(const route of ['/manager/orders/477?proposalId=25','/manager/orders/kanban?orderId=477&proposalId=25']) await runCase(width,'alternative '+route,async f=>{
   await f.page.goto(base+route);await f.workspace.waitFor();
   await f.page.getByText('Услуга варианта Б',{exact:true}).waitFor();
   assert.equal(await f.page.getByText('Услуга варианта А',{exact:true}).isVisible(),false);
   assert.match((await f.workspace.locator('footer').innerText()).replace(/\s/g,''),/2300/);
   await f.page.reload();await f.workspace.waitFor();await f.page.getByText('Услуга варианта Б',{exact:true}).waitFor();
   assert.equal(f.patches.length,0);assert.equal(f.current().proposals.find(p=>p.is_selected).id,24);
  });
  for(const kind of ['archived','unavailable','invalid']) await runCase(width,'proposal '+kind,async f=>{
   if(kind==='archived') f.current().proposals[1].is_archived=true;
   const id=kind==='invalid'?'bad':kind==='unavailable'?'999':'25';
   await f.page.goto(base+'/manager/orders/kanban?orderId=477&proposalId='+id);
   await f.page.getByRole('alert').filter({hasText:kind==='archived'?'в архиве':'недоступен'}).waitFor();
   assert.equal(await f.workspace.count(),0);assert.equal(f.patches.length,0);
   await f.page.getByRole('button',{name:'К актуальному предложению',exact:true}).click();await f.workspace.waitFor();
   await f.page.getByText('Услуга варианта А',{exact:true}).waitFor();
  });
  await runCase(width,'archive viewed alternative',async f=>{
   const expected=await openBoard(f,true);await chooseB(f);
   const before=new URL(f.page.url()),entry=await f.page.evaluate(()=>history.state.managerNavigation.id);
   await f.workspace.getByRole('button',{name:'Действия с предложением',exact:true}).click();
   await f.page.getByRole('button',{name:'Перенести в архив',exact:true}).click();
   await f.page.getByRole('button',{name:'Архивировать',exact:true}).click();
   await f.page.getByText('Услуга варианта А',{exact:true}).waitFor();
   assert.equal(await f.workspace.count(),1);
   const after=new URL(f.page.url());
   assert.equal(after.searchParams.get('proposalId'),'24');
   before.searchParams.set('proposalId','24');assert.equal(after.href,before.href);
   assert.equal(await f.page.getByText('Вариант предложения по этой ссылке в архиве.',{exact:true}).count(),0);
   assert.equal(await f.page.evaluate(()=>history.state.managerNavigation.id),entry);
   assert.equal(f.requests.filter(r=>r.method==='POST' && r.path.endsWith('/proposals/25/archive')).length,1);
   assert.equal(f.patches.length,0);
   await f.page.reload();await f.workspace.waitFor();await f.page.getByText('Услуга варианта А',{exact:true}).waitFor();
   await f.workspace.getByRole('button',{name:'К заказам',exact:true}).click();await assertBoard(f,expected);
  });
  for(const grouped of [false,true]) await runCase(width,'documents customer return '+(grouped?'grouped-board':'board'),async f=>{
   const expected=await openBoard(f,grouped);await chooseB(f);
   const entry=await f.page.evaluate(()=>history.state.managerNavigation.id),orderUrl=await location(f.page);
   const fill=await openIncompleteDocument(f);await fill.click();
   await f.page.waitForURL(url=>url.pathname==='/manager/customers/profile');
   assert.equal(new URL(f.page.url()).searchParams.get('returnTo'),orderUrl);
   await f.page.getByRole('button',{name:'Назад',exact:true}).click();await f.workspace.waitFor();
   assert.equal(await f.page.evaluate(()=>history.state.managerNavigation.id),entry);
   assert.equal(await location(f.page),orderUrl);
   await f.workspace.getByRole('button',{name:'К заказам',exact:true}).click();await assertBoard(f,expected);
   assert.equal(f.requests.filter(r=>r.method!=='GET' && r.path.startsWith('/api/manager/')).length,0);
  });
  await runCase(width,'documents customer cancel unsaved exit',async f=>{
   const expected=await openBoard(f,true);
   await f.workspace.getByRole('switch',{name:'Автосохранение заказа'}).click();
   await f.workspace.getByTitle('Изменить название').click();await f.workspace.getByRole('textbox',{name:'Название заказа',exact:true}).fill('Не терять из документов');
   const fill=await openIncompleteDocument(f),orderUrl=await location(f.page),length=await f.page.evaluate(()=>history.length);
   await fill.click();await f.page.getByRole('button',{name:'Отмена',exact:true}).click();
   assert.equal(await location(f.page),orderUrl);assert.equal(await f.page.evaluate(()=>history.length),length);
   assert.equal(await f.workspace.getByRole('textbox',{name:'Название заказа',exact:true}).inputValue(),'Не терять из документов');
   await fill.click();await f.page.getByRole('button',{name:'Закрыть без сохранения',exact:true}).click();
   await f.page.waitForURL(url=>url.pathname==='/manager/customers/profile');
   await f.page.getByRole('button',{name:'Назад',exact:true}).click();await f.workspace.waitFor();
   await f.workspace.getByRole('button',{name:'К заказам',exact:true}).click();await assertBoard(f,expected);
   assert.equal(f.patches.length,0);
  });
  await runCase(width,'cancel customer then Back and Forward',async f=>{
   const expected=await openBoard(f);
   await f.workspace.getByRole('switch',{name:'Автосохранение заказа'}).click();
   await f.workspace.getByTitle('Изменить название').click();await f.workspace.getByRole('textbox',{name:'Название заказа',exact:true}).fill('Не терять');
   const orderUrl=await location(f.page),length=await f.page.evaluate(()=>history.length);
   await openCustomer(f);await f.page.getByRole('button',{name:'Отмена',exact:true}).click();
   assert.equal(await location(f.page),orderUrl);assert.equal(await f.page.evaluate(()=>history.length),length);
   assert.equal(await f.workspace.getByRole('textbox',{name:'Название заказа',exact:true}).inputValue(),'Не терять');
   await f.page.evaluate(()=>history.back());await f.page.getByRole('button',{name:'Отмена',exact:true}).click();
   await f.page.waitForURL(base+orderUrl);assert.equal(await f.page.evaluate(()=>history.length),length);
   await f.page.evaluate(()=>history.back());await f.page.getByRole('button',{name:'Закрыть без сохранения',exact:true}).click();
   await assertBoard(f,expected);
   await f.page.evaluate(()=>history.forward());await f.workspace.waitFor();assert.equal(await location(f.page),orderUrl);
  });
  await runCase(width,'failed save blocks customer and native Back',async f=>{
   const expected=await openBoard(f);f.failSave(true);
   await f.workspace.getByTitle('Изменить название').click();await f.workspace.getByRole('textbox',{name:'Название заказа',exact:true}).fill('Не потерять при ошибке');
   const orderUrl=await location(f.page),length=await f.page.evaluate(()=>history.length);
   await openCustomer(f);await f.workspace.getByText(/Не удалось сохранить заказ/).waitFor();
   assert.equal(await location(f.page),orderUrl);assert.equal(await f.page.evaluate(()=>history.length),length);
   await f.page.evaluate(()=>history.back());await f.page.waitForURL(base+orderUrl);
   assert.equal(await f.workspace.getByRole('textbox',{name:'Название заказа',exact:true}).inputValue(),'Не потерять при ошибке');
   f.failSave(false);await f.workspace.getByRole('button',{name:'К заказам',exact:true}).click();await assertBoard(f,expected);
  });
  for(const origin of ['board','grouped-board','calendar']) for(const child of ['customer','catalog']) await runCase(width,origin+' via '+child,async f=>{
   let expected;
   if(origin!=='calendar') expected=await openBoard(f,origin==='grouped-board');
   else {
    await f.page.goto(base+'/manager/calendar');await f.page.getByRole('button',{name:'Неделя',exact:true}).click();
    await f.page.locator('.fc-next-button').click();await f.page.locator('.fc-next-button').click();
    expected={title:await f.page.locator('.fc-toolbar-title').textContent()};
    await f.page.getByRole('button').filter({hasText:'#477'}).click();await f.workspace.waitFor();
   }
   await chooseB(f);
   const orderEntry=await f.page.evaluate(()=>history.state.managerNavigation.id);
   await childRoundtrip(f,child);
   assert.equal(await f.page.evaluate(()=>history.state.managerNavigation.id),orderEntry);
   await f.page.reload();await f.workspace.waitFor();await f.page.getByText('Услуга варианта Б',{exact:true}).waitFor();
   await f.workspace.getByRole('button',{name:origin!=='calendar'?'К заказам':'К календарю',exact:true}).click();
   if(origin!=='calendar') await assertBoard(f,expected);
   else {
    await f.page.locator('.fc-toolbar-title').waitFor();assert.equal(await f.page.locator('.fc-toolbar-title').textContent(),expected.title);
    assert.equal(await f.page.locator('.fc-timeGridWeek-view').count(),1);
   }
   await f.page.evaluate(()=>history.forward());await f.workspace.waitFor();await f.page.getByText('Услуга варианта Б',{exact:true}).waitFor();
   assert.equal(f.patches.length,0);
   assert.equal(f.requests.filter(r=>r.method!=='GET' && r.path.startsWith('/api/manager/orders/477')).length,0);
   await f.page.screenshot({path:path.join(output,width+'-'+origin+'-'+child+'.png')});
  });
 }
 fs.writeFileSync(path.join(output,'results.json'),JSON.stringify({checks},null,2));
 console.log(JSON.stringify({checks:checks.length,output}));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
