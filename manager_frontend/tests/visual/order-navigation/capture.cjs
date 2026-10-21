// Behavioral regressions on a local production build; every API response is synthetic.
const { chromium } = require(process.env.KITLANE_PLAYWRIGHT_MODULE || 'playwright');
const fs = require('node:fs');
const { auth, stores } = require('../kitlane/fixtures.json');
const assert = require('node:assert/strict');
const path = require('node:path');
const iconFont = process.env.KITLANE_ICON_FONT && fs.readFileSync(process.env.KITLANE_ICON_FONT);
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
  const context = await browser.newContext({ serviceWorkers: 'block', viewport: { width, height }, isMobile: width < 768, hasTouch: width < 768 });
  const page = await context.newPage();
  page.setDefaultTimeout(7000);
  const requests = [], patches = [], attempts = [], errors = [], scripts = [];
  let nextLinkId=1000, loseResponse=false;
  let current = {...structuredClone(order), workflow_type:'sales_installation'}, failSave = false;
  const documents = [];
  const tender = {order_id:477,stage:null,deadline_at:null,price_enquiry:null,publications:[],history:[]};
  let failWorkers = false, failDetail = false, detailDelay = 0, failWorkChunk = false;
  page.on('pageerror', e => errors.push(e.message));
  page.on('request', request => { if(request.resourceType()==='script') scripts.push(request.url()); });
  await context.route('**/*', async route => {
    const url = new URL(route.request().url());
    if (url.hostname === 'fonts.googleapis.com') return iconFont ? route.fulfill({contentType:'text/css',body:"@font-face{font-family:'Material Icons Round';font-style:normal;font-weight:400;src:url('https://fonts.gstatic.com/kitlane-fixture-icons.woff2') format('woff2')}.material-icons-round{font-family:'Material Icons Round';font-weight:normal;font-style:normal;font-size:24px;line-height:1;letter-spacing:normal;text-transform:none;display:inline-block;white-space:nowrap;word-wrap:normal;direction:ltr;-webkit-font-feature-settings:'liga';-webkit-font-smoothing:antialiased}"}) : route.continue();
    if (url.hostname === 'fonts.gstatic.com') return iconFont ? route.fulfill({contentType:'font/woff2',body:iconFont}) : route.continue();
    if (url.origin !== base) return route.abort();
    if (failWorkChunk && /OrderWorkWorkspace-[^/]+\.js$/.test(url.pathname)) { failWorkChunk=false;return route.abort('failed'); }
    if (!url.pathname.startsWith('/api') && !url.pathname.startsWith('/login')) return route.continue();
    requests.push({ method: route.request().method(), path: url.pathname + url.search });
    let data = { items: [], total: 0, meta: { pages: 1 }, enabled: false };
    if (url.pathname === '/api/manager/account/companies') data = {
      staff_user_id: 999, username: auth.username, is_platform_owner: true, default_tenant_id: 999,
      items: [{ tenant_id: 999, slug: 'test', display_name: 'Тестовая компания', role: 'owner', membership_id: 999, access_kind: 'membership', is_system: true, demo_read_only: false, default_storefront_slug: 'minsk' }], total: 1, page: 1, limit: 100,
    };
    else if (url.pathname.endsWith('/me')) data = {...auth,capabilities:[...auth.capabilities,'worker.pay.read','worker.pay.manage']};
    else if (url.pathname.endsWith('/storefronts')) data = { items: stores.map(store => ({ ...store, id: store.slug === 'minsk' ? 999 : 998 })) };
    else if (url.pathname === '/api/manager/orders') data = { items: Array.from({ length: 18 }, (_, index) => ({ ...current, id: index === 8 ? 477 : 500 + index, title: index === 8 ? current.title : `Тестовый заказ ${index + 1}` })), meta: { pages: 1, total: 18 } };
    else if (url.pathname === '/api/manager/orders/477') {
      if(route.request().method()==='GET' && failDetail) return route.fulfill({status:503,json:{detail:'Synthetic order failure'}});
      if(route.request().method()==='GET' && detailDelay) await new Promise(done=>setTimeout(done,detailDelay));
      if (route.request().method() === 'PATCH') {
        const payload=route.request().postDataJSON();attempts.push(payload);
        if(failSave) return route.fulfill({status:500,json:{detail:'Synthetic save failure'}});
        const proposal=current.proposals.find(item=>item.id===payload.line_proposal_id);
        for(const [field,rows] of [['products','product_lines'],['services','service_lines']]) if(payload[field]) {
          const ids=new Set((proposal?.[rows]||[]).map(row=>row.id));const incoming=payload[field].filter(row=>row.link_id!=null).map(row=>row.link_id);
          if(new Set(incoming).size!==incoming.length||incoming.some(id=>!ids.has(id))) return route.fulfill({status:400,json:{detail:'Line does not belong to the target proposal'}});
        }
        const {products,services,line_proposal_id,...form}=payload;current={...current,...form};
        if(products) proposal.product_lines=products.map(row=>({...row,id:row.link_id??nextLinkId++,product_title:row.product_id===9?'Тестовый товар':'Другой товар'}));
        if(services) proposal.service_lines=services.map(row=>({...row,id:row.link_id??nextLinkId++,service_title:row.title}));
        const selected=current.proposals.find(item=>item.is_selected);current.product_lines=selected.product_lines;current.service_lines=selected.service_lines;
        patches.push(payload);
        if(loseResponse) {loseResponse=false;return route.abort('failed');}
      }
      data = current;
    }
    else if (url.pathname === '/api/manager/orders/477/proposals/25/archive' && route.request().method() === 'POST') {
      current.proposals[1].is_archived = true;
      data = current;
    }
    else if (url.pathname === '/api/manager/document-system/orders/477/documents') data = {items:documents};
    else if (url.pathname === '/api/manager/document-system/runtime/pdf') data = {available:true,backend:'gotenberg',configured_backend:'gotenberg',reason:null};
    else if (url.pathname === '/api/manager/document-system/legal-entities') data = {items:[{id:5,tenant_id:999,display_name:'Тестовый поставщик',is_active:true,is_default:true,signing_mode:'director',requisites:{full_name:'ООО Тест',unp:'123456789',legal_address:'Минск',director_name:'Тестовый',director_position:'Директор',director_basis:'Устав'}}]};
    else if (url.pathname === '/api/manager/calendar/events') data = [];
    else if (url.pathname === '/api/manager/orders/work-stages/stale') data = {items:[{id:1,order_id:477,order_title:current.title,name:'Тестовая работа',status:'scheduled',customer_name:current.customer.name}],total:1};
    else if (url.pathname === '/api/manager/customers/12') data = current.customer;
    else if (url.pathname.endsWith('/installer-workspace')) {
      if(failWorkers) return route.fulfill({status:503,json:{detail:'Работы временно недоступны'}});
      data = { order_id: 477, assignments: [], materials: [], collection: { version: 1, assignment_id: null, amount: null, currency: null, status: 'not_assigned', updated_at: null }, balances: [], financial_fingerprint: 'synthetic' };
    }
    else if (url.pathname.endsWith('/worker-pay')) data = { order_id: 477, agreements: [], candidates: [] };
    else if (url.pathname.endsWith('/tender-workflow')) data = tender;
    return route.fulfill({ json: data });
  });
  const workspace = page.getByRole('region', { name: 'Рабочая область заказа', exact: true });
  return { context, page, workspace, requests, patches, attempts, loseNextSave:()=>{loseResponse=true;}, errors, scripts, documents, tender, current:()=>current, failSave:(value)=>{failSave=value;}, failWorkers:value=>{failWorkers=value;}, failDetail:value=>{failDetail=value;}, detailDelay:value=>{detailDelay=value;}, failWorkChunk:value=>{failWorkChunk=value;} };
}

const boardPath='/manager/orders/kanban?segment=b2b&view=kanban&groupBy=none&search=office&assigned_to_me=1&status=negotiation&sort=margin_desc&workFilter=unpaid&hideOnHold=false&filtersOpen=true';
const location=page=>page.evaluate(()=>window.location.pathname+window.location.search);
async function runCase(width,name,task) {
 if(caseFilter && !caseFilter.test(name)) return;
 const f=await fixture(width,850);
 try { await task(f);assert.deepEqual(f.errors,[]);checks.push({width,name});console.log(width,name,'passed'); }
 catch(error) { await f.page.screenshot({path:path.join(output,`${width}-failure.png`)}).catch(()=>{});console.error(await f.page.evaluate(()=>({url:location.pathname+location.search,top:scrollY,height:document.documentElement.scrollHeight,saved:history.state?.orderListPosition})));throw error; }
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
 await card.getByRole('link',{name:'Открыть заказ',exact:true}).evaluate(el=>el.click());await f.workspace.waitFor();
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
 await require('./draft-recovery-cases.cjs')({runCase,base,output,openBoard,assertBoard});
 for(const width of [384,1440]) {
  await runCase(width,'draft restore preserves fresh server fields and estimate',async f=>{
   await f.page.goto(base+'/manager/orders/477?proposalId=24');await f.page.getByText('Услуга варианта А',{exact:true}).waitFor();
   f.failSave(true);
   await f.workspace.getByRole('button',{name:/^Изменить название:/}).click();
   await f.page.getByRole('textbox',{name:'Название заказа',exact:true}).fill('Моё новое название');
   await f.workspace.locator('header [role="status"]').filter({hasText:'Не удалось сохранить'}).waitFor();
   Object.assign(f.current(),{comment:'Комментарий коллеги',installation_date:'2026-11-15T12:00:00',status:'execution',delivery_address:'Другой объект'});
   f.current().proposals[0].service_lines[0].price=1800;
   f.current().service_lines[0].price=1800;
   f.failSave(false);f.page.on('dialog',dialog=>dialog.accept());
   await f.page.reload();await f.workspace.waitFor();
   await f.workspace.locator('header [role="status"]').filter({hasText:'Сохранено'}).waitFor();
   fs.writeFileSync(path.join(output,`draft-patch-${width}.json`),JSON.stringify(f.patches,null,2));
   assert.deepEqual(f.patches,[{title:'Моё новое название'}]);
   assert.equal(f.current().comment,'Комментарий коллеги');assert.equal(f.current().installation_date,'2026-11-15T12:00:00');
   assert.equal(f.current().proposals[0].service_lines[0].price,1800);
   fs.writeFileSync(path.join(output,`draft-patch-${width}.json`),JSON.stringify(f.patches,null,2));
  });
  for(const automatic of [true,false]) await runCase(width,'draft conflict blocks writes and survives reload '+automatic,async f=>{
   await f.page.goto(base+'/manager/orders/477');await f.page.getByText('Услуга варианта А',{exact:true}).waitFor();
   if(!automatic) await f.workspace.getByRole('switch',{name:'Автосохранение заказа'}).click();
   f.failSave(true);await f.workspace.getByRole('button',{name:/^Изменить название:/}).click();
   await f.page.getByRole('textbox',{name:'Название заказа',exact:true}).fill('Локальная версия');
   if(automatic) await f.workspace.locator('header [role="status"]').filter({hasText:'Не удалось сохранить'}).waitFor();
   else await f.page.getByRole('textbox',{name:'Название заказа',exact:true}).press('Enter');
   f.current().title='Версия коллеги';f.failSave(false);f.page.on('dialog',dialog=>dialog.accept());
   await f.page.reload();const recovery=f.page.getByRole('alert',{name:'Восстановление черновика'});await recovery.waitFor();
   await recovery.getByText('Локальная версия',{exact:true}).waitFor();await recovery.getByText('Версия коллеги',{exact:true}).waitFor();
   await f.page.waitForTimeout(1000);assert.equal(f.patches.length,0);
   await f.page.reload();await recovery.waitFor();assert.equal(f.patches.length,0);
   assert.equal(await f.page.evaluate(()=>document.documentElement.scrollWidth>document.documentElement.clientWidth),false);
   await f.page.screenshot({path:path.join(output,`draft-conflict-${width}-${automatic}.png`)});
   await recovery.getByRole('button',{name:'Использовать черновик',exact:true}).click();
   if(!automatic) {assert.equal(f.patches.length,0);await f.workspace.getByRole('button',{name:'Сохранить изменения',exact:true}).click();}
   await f.workspace.locator('header [role="status"]').filter({hasText:'Сохранено'}).waitFor();assert.deepEqual(f.patches,[{title:'Локальная версия'}]);
  });
  for(const conflict of [false,true]) await runCase(width,'draft estimate field recovery '+conflict,async f=>{
   await f.page.goto(base+'/manager/orders/477');await f.page.getByText('Услуга варианта А',{exact:true}).waitFor();
   await f.workspace.getByRole('switch',{name:'Автосохранение заказа'}).click();
   await f.workspace.getByRole('button',{name:'Редактировать услугу #1.1',exact:true}).click();
   await f.workspace.getByLabel(conflict?'Цена':'Кол-во',{exact:true}).fill(conflict?'1400':'2');
   f.current().proposals[0].service_lines[0].price=1800;f.current().service_lines[0].price=1800;
   f.page.on('dialog',dialog=>dialog.accept());await f.page.reload();await f.workspace.waitFor();
   if(conflict) {const recovery=f.page.getByRole('alert',{name:'Восстановление черновика'});await recovery.waitFor();assert.equal(f.patches.length,0);await recovery.getByRole('button',{name:'Оставить серверное',exact:true}).click();assert.equal(f.patches.length,0);}
   else {await f.page.getByText('Услуга варианта А',{exact:true}).waitFor();await f.workspace.getByRole('button',{name:'Сохранить изменения',exact:true}).click();await f.workspace.locator('header [role="status"]').filter({hasText:'Сохранено'}).waitFor();assert.equal(f.patches.length,1);assert.equal(f.patches[0].services[0].quantity,2);assert.equal(f.patches[0].services[0].price,1800);}
  });
  await runCase(width,'draft legacy requires explicit review',async f=>{
   await f.page.goto(base+'/manager/orders/477');await f.page.getByText('Услуга варианта А',{exact:true}).waitFor();
   await f.workspace.getByRole('switch',{name:'Автосохранение заказа'}).click();
   await f.workspace.getByRole('button',{name:/^Изменить название:/}).click();await f.page.getByRole('textbox',{name:'Название заказа',exact:true}).fill('Старый черновик');
   await f.page.evaluate(()=>{const key=Object.keys(sessionStorage).find(k=>k.startsWith('manager_order_drawer_draft_477_24'));const draft=JSON.parse(sessionStorage.getItem(key));delete draft.version;delete draft.baseForm;delete draft.baseLines;delete draft.linesDraft;sessionStorage.removeItem(key);sessionStorage.setItem('manager_order_drawer_draft_477_24',JSON.stringify(draft));});
   f.current().comment='Новый комментарий';f.page.on('dialog',dialog=>dialog.accept());await f.page.reload();
   const recovery=f.page.getByRole('alert',{name:'Восстановление черновика'});await recovery.waitFor();await recovery.getByText(/В старом черновике нет исходной версии/).waitFor();assert.equal(f.patches.length,0);
   while(await recovery.locator('article').count()) await recovery.locator('article').first().getByRole('button',{name:'Оставить серверное',exact:true}).click();
   assert.equal(f.patches.length,0);assert.equal(f.current().comment,'Новый комментарий');
  });
  await runCase(width,'draft lost save response cannot duplicate a service',async f=>{
   await f.page.goto(base+'/manager/orders/477');await f.page.getByText('Услуга варианта А',{exact:true}).waitFor();
   await f.workspace.getByRole('switch',{name:'Автосохранение заказа'}).click();
   await f.page.getByTestId('add-service-line').click();await f.page.getByTestId('service-title-input').fill('Уже сохраненная услуга');
   await f.workspace.getByLabel('Цена',{exact:true}).fill('50');
   // The server committed this row, but the local editor never received its link ID.
   f.current().proposals[0].service_lines.push({id:82,service_title:'Уже сохраненная услуга',quantity:1,price:50,cost:0});
   f.page.on('dialog',dialog=>dialog.accept());await f.page.reload();
   const recovery=f.page.getByRole('alert',{name:'Восстановление черновика'});await recovery.waitFor();assert.equal(f.patches.length,0);
   await recovery.getByRole('button',{name:'Оставить серверное',exact:true}).click();
   assert.equal(f.patches.length,0);assert.equal(f.current().proposals[0].service_lines.length,2);
  });
  await runCase(width,'second package invalid section defaults to proposal',async f=>{
   await f.page.goto(base+'/manager/orders/477?proposalId=25&section=unknown');await f.page.getByText('Услуга варианта Б',{exact:true}).waitFor();
   assert.equal(await f.workspace.getByRole('navigation').getByRole('button',{name:'Предложение',exact:true}).getAttribute('aria-current'),'page');
  });
  for(const origin of ['board','list']) await runCase(width,'second package order link URL '+origin+(width>=768?' and native tabs':''),async f=>{
   await f.page.goto(base+(origin==='board'?boardPath:'/manager/orders/list?segment=b2b&view=list&groupBy=none'));
   let link;
   if(origin==='board') {const card=f.page.locator('article[draggable]').filter({hasText:'№477'});await card.getByRole('button',{name:'Раскрыть заказ',exact:true}).click();link=card.getByRole('link',{name:'Открыть заказ',exact:true});}
   else link=f.page.getByRole('link',{name:'Открыть заказ №477',exact:true});
   const previous=await location(f.page),target=new URL(await link.getAttribute('href'),base);assert.equal(target.pathname,'/manager/orders/477');assert.equal(target.searchParams.get('returnTo'),previous);
   if(width<768) return; // Native mouse/keyboard browser actions are exercised at desktop width.
   for(const click of [{modifiers:[process.platform==='darwin'?'Meta':'Control']},{button:'middle'}]) {
    const [tab]=await Promise.all([f.context.waitForEvent('page'),link.click(click)]);await tab.getByText('Услуга варианта А',{exact:true}).waitFor();assert.equal(new URL(tab.url()).pathname,'/manager/orders/477');assert.equal(await location(f.page),previous);await tab.close();
   }
  });
  await runCase(width,'second package retained sections and copied URL',async f=>{
   const query=new URLSearchParams({proposalId:'25',company:'999',site:'minsk',returnTo:boardPath,section:'proposal'});
   await f.page.goto(base+'/manager/orders/477?'+query);await f.page.getByText('Услуга варианта Б',{exact:true}).waitFor();
   const nav=f.workspace.getByRole('navigation'),entry=await f.page.evaluate(()=>history.state.managerNavigation.id),length=await f.page.evaluate(()=>history.length);
   assert.equal(f.requests.filter(r=>r.path.includes('/installers')||r.path.includes('/repair-complaints')).length,0);
   assert.equal(f.scripts.some(url=>/OrderWorkWorkspace-|OrderDocumentsWorkspace-|OrderPaymentWorkspace-/.test(url)),false);
   await f.workspace.getByRole('switch',{name:'Автосохранение заказа'}).click();
   await f.workspace.getByRole('button',{name:/^Изменить название:/}).click();await f.page.getByRole('textbox',{name:'Название заказа',exact:true}).fill('Черновик во всех разделах');
   for(const [section,label] of [['documents','Документы'],['work','Работы'],['payments','Оплаты'],['proposal','Предложение']]) {
    await nav.getByRole('button',{name:label,exact:true}).click();
    assert.equal(new URL(f.page.url()).searchParams.get('section'),section);
    assert.equal(await f.page.evaluate(()=>history.state.managerNavigation.id),entry);
    assert.equal(await f.page.evaluate(()=>history.length),length);
    assert.equal(await f.page.getByRole('textbox',{name:'Название заказа',exact:true}).inputValue(),'Черновик во всех разделах');
   }
   assert.equal(f.patches.length,0);assert.equal(f.current().proposals.find(p=>p.is_selected).id,24);
   await nav.getByRole('button',{name:'Документы',exact:true}).click();await f.page.getByTestId('native-documents-workspace').waitFor();
   const copied=await location(f.page);await f.page.reload();await f.page.getByTestId('native-documents-workspace').waitFor();
   assert.equal(await location(f.page),copied);assert.equal(new URL(f.page.url()).searchParams.get('proposalId'),'25');
   await f.workspace.getByRole('button',{name:/^Изменить название:/}).click();
   assert.equal(await f.page.getByRole('textbox',{name:'Название заказа',exact:true}).inputValue(),'Черновик во всех разделах');
   assert.match(await f.page.title(),/Заказ №477 · Тестовый клиент · KitLane/);
  });
  for(const section of ['documents','work','payments']) await runCase(width,'second package direct '+section,async f=>{
   await f.page.goto(base+`/manager/orders/477?proposalId=25&section=${section}`);
   const panel=f.page.locator(`[data-order-usage="workspace-${section}-panel"]`);await panel.waitFor();
   await panel.locator('button,input,select').first().waitFor();
   assert.equal(f.requests.filter(r=>r.path==='/api/manager/orders/477'&&r.method==='GET').length,1);
   assert.equal(f.requests.some(r=>r.path.startsWith('/api/manager/orders?')),false);
   assert.equal(f.patches.length,0);
   if(section==='documents') {assert.equal(f.scripts.some(url=>/OrderWorkWorkspace-|OrderPaymentWorkspace-|OrderProposalWorkspace-/.test(url)),false);assert.equal(f.requests.some(r=>r.path.includes('/installers')||r.path.includes('/repair-complaints')),false);}
   if(section==='work') {const field=panel.getByRole('combobox',{name:'Исполнитель работы',exact:true});await field.waitFor();await field.evaluate(el=>el.dataset.retained='yes');await f.workspace.getByRole('button',{name:'Предложение',exact:true}).click();const count=f.requests.filter(r=>r.path.endsWith('/installer-workspace')).length;await f.workspace.getByRole('button',{name:'Работы',exact:true}).click();assert.equal(await field.getAttribute('data-retained'),'yes');assert.equal(f.requests.filter(r=>r.path.endsWith('/installer-workspace')).length,count);}
  });
  if(width>=768) await runCase(width,'second package first add product from documents',async f=>{
   await f.page.goto(base+'/manager/orders/477?section=documents');await f.page.getByTestId('native-documents-workspace').waitFor();
   await f.workspace.getByRole('navigation').getByRole('button',{name:'Товар',exact:true}).click();
   await f.page.getByTestId('product-line-row').waitFor();assert.equal(await f.page.getByTestId('product-line-row').count(),1);
   assert.equal(new URL(f.page.url()).searchParams.get('section'),'proposal');
  });
  await runCase(width,'second package local work error and retry',async f=>{
   f.failWorkers(true);await f.page.goto(base+'/manager/orders/477?section=work');
   const panel=f.page.locator('[data-order-usage="workspace-work-panel"]'),error=panel.getByRole('alert').filter({hasText:'Работы временно недоступны'});await error.waitFor();
   assert.equal(await f.workspace.count(),1);f.failWorkers(false);await error.getByRole('button',{name:'Повторить',exact:true}).click();
   await panel.getByRole('combobox',{name:'Исполнитель работы',exact:true}).waitFor();
   await f.workspace.getByRole('button',{name:'Предложение',exact:true}).click();await f.page.getByText('Услуга варианта А',{exact:true}).waitFor();
  });
  await runCase(width,'second package repair lazy work and populated tender',async f=>{
   f.current().workflow_type='repair';f.tender.stage='announced';f.tender.deadline_at='2026-10-25T20:59:00Z';
   await f.page.goto(base+'/manager/orders/477');await f.page.getByText('Услуга варианта А',{exact:true}).waitFor();
   assert.equal(f.requests.some(r=>r.path.includes('/repair-complaints')||r.path.includes('/installers')||r.path.includes('/equipment')),false);
   const tender=f.workspace.getByRole('region',{name:'Этапы закупки'});await tender.getByText(/Объявлена/).waitFor();await tender.getByText(/Срок текущего этапа:/).waitFor();
   await f.workspace.getByRole('button',{name:'Ремонт',exact:true}).click();await f.workspace.getByText('Библиотека жалоб',{exact:true}).waitFor();
   assert.equal(f.requests.some(r=>r.path.includes('/repair-complaints')),true);
   await tender.getByText(/Срок текущего этапа:/).waitFor();
   await f.workspace.getByRole('button',{name:'Документы',exact:true}).click();await f.page.getByTestId('native-documents-workspace').waitFor();await tender.getByText(/Объявлена/).waitFor();
  });
  await runCase(width,'second package slow order and detail retry',async f=>{
   f.detailDelay(900);await f.page.goto(base+'/manager/orders/477?section=documents');await f.page.getByText('Загружаем заказ…',{exact:true}).waitFor();
   await f.page.getByTestId('native-documents-workspace').waitFor();
   f.failDetail(true);await f.page.reload();const alert=f.page.getByRole('alert').filter({hasText:'Не удалось открыть заказ'});await alert.waitFor();
   f.failDetail(false);f.detailDelay(0);await alert.getByRole('button',{name:'Повторить',exact:true}).click();await f.page.getByTestId('native-documents-workspace').waitFor();
  });
  await runCase(width,'second package saving retry and keyboard focus',async f=>{
   await f.page.goto(base+'/manager/orders/477');await f.page.getByText('Услуга варианта А',{exact:true}).waitFor();f.failSave(true);
   await f.workspace.getByRole('button',{name:/^Изменить название:/}).click();await f.page.getByRole('textbox',{name:'Название заказа',exact:true}).fill('Сохранить после ошибки');
   await f.workspace.locator('header [role="status"]').filter({hasText:'Не удалось сохранить'}).waitFor();
   assert.equal(await f.page.getByRole('textbox',{name:'Название заказа',exact:true}).inputValue(),'Сохранить после ошибки');
   f.failSave(false);await f.workspace.getByRole('button',{name:'Повторить сохранение',exact:true}).click();await f.workspace.locator('header [role="status"]').filter({hasText:'Сохранено'}).waitFor();
   await f.page.getByRole('textbox',{name:'Название заказа',exact:true}).press('Enter');
   const menu=f.workspace.getByRole('button',{name:'Дополнительные действия',exact:true});await menu.focus();await f.page.keyboard.press('Enter');await f.page.keyboard.press('Escape');
   assert.equal(await menu.evaluate(el=>el===document.activeElement),true);
  });
  await runCase(width,'second package chunk failure and guarded refresh',async f=>{
   const query=new URLSearchParams({proposalId:'25',company:'999',site:'minsk',returnTo:boardPath,section:'documents'});
   await f.page.goto(base+'/manager/orders/477?'+query);await f.page.getByTestId('native-documents-workspace').waitFor();
   await f.workspace.getByRole('switch',{name:'Автосохранение заказа'}).click();
   await f.workspace.getByRole('button',{name:/^Изменить название:/}).click();await f.page.getByRole('textbox',{name:'Название заказа',exact:true}).fill('Сохранить перед восстановлением');
   f.failWorkChunk(true);await f.workspace.getByRole('navigation').getByRole('button',{name:'Работы',exact:true}).click();
   await f.workspace.getByText('Не удалось загрузить раздел «Работы».',{exact:true}).waitFor();
   const url=await location(f.page),length=await f.page.evaluate(()=>history.length);
   await f.workspace.getByRole('button',{name:'Обновить страницу',exact:true}).click();await f.page.getByRole('button',{name:'Отмена',exact:true}).click();
   assert.equal(await location(f.page),url);assert.equal(await f.page.evaluate(()=>history.length),length);
   assert.equal(await f.workspace.getByRole('button',{name:'Обновить страницу',exact:true}).evaluate(el=>el===document.activeElement),true);
   assert.equal(await f.page.getByRole('textbox',{name:'Название заказа',exact:true}).inputValue(),'Сохранить перед восстановлением');assert.equal(f.patches.length,0);
   await f.workspace.getByRole('button',{name:'Сохранить изменения',exact:true}).click();await f.workspace.locator('header [role="status"]').filter({hasText:'Сохранено'}).waitFor();
   const refreshed=f.page.waitForEvent('domcontentloaded');await f.workspace.getByRole('button',{name:'Обновить страницу',exact:true}).click();await refreshed;
   await f.workspace.getByRole('combobox',{name:'Исполнитель работы',exact:true}).waitFor();
   assert.equal(await location(f.page),url);assert.equal(await f.page.evaluate(()=>history.length),length);
   assert.equal(f.current().title,'Сохранить перед восстановлением');assert.equal(f.current().proposals.find(p=>p.is_selected).id,24);
   await f.workspace.getByRole('navigation').getByRole('button',{name:'Предложение',exact:true}).click();await f.page.getByText('Услуга варианта Б',{exact:true}).waitFor();
  });
  await runCase(width,'second package chunk recovery with explicit discard',async f=>{
   const query=new URLSearchParams({proposalId:'25',company:'999',site:'minsk',returnTo:boardPath,section:'documents'});
   await f.page.goto(base+'/manager/orders/477?'+query);await f.page.getByTestId('native-documents-workspace').waitFor();
   await f.workspace.getByRole('switch',{name:'Автосохранение заказа'}).click();
   await f.workspace.getByRole('button',{name:/^Изменить название:/}).click();await f.page.getByRole('textbox',{name:'Название заказа',exact:true}).fill('Явно отменённый черновик');
   f.failWorkChunk(true);await f.workspace.getByRole('navigation').getByRole('button',{name:'Работы',exact:true}).click();
   await f.workspace.getByText('Не удалось загрузить раздел «Работы».',{exact:true}).waitFor();
   const url=await location(f.page),length=await f.page.evaluate(()=>history.length);let nativeDialogs=0;
   f.page.on('dialog',async dialog=>{ nativeDialogs++;await dialog.dismiss(); });
   await f.workspace.getByRole('button',{name:'Обновить страницу',exact:true}).click();
   const refreshed=f.page.waitForEvent('domcontentloaded');await f.page.getByRole('button',{name:'Закрыть без сохранения',exact:true}).click();await refreshed;
   await f.workspace.getByRole('combobox',{name:'Исполнитель работы',exact:true}).waitFor();
   assert.equal(nativeDialogs,0);assert.equal(await location(f.page),url);assert.equal(await f.page.evaluate(()=>history.length),length);
   assert.equal(f.patches.length,0);assert.equal(f.current().title,order.title);
   await f.workspace.getByRole('navigation').getByRole('button',{name:'Предложение',exact:true}).click();await f.page.getByText('Услуга варианта Б',{exact:true}).waitFor();
  });
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
   const entry=await f.page.evaluate(()=>history.state.managerNavigation.id);
   const fill=await openIncompleteDocument(f),orderUrl=await location(f.page);await fill.click();
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
   await f.workspace.getByRole('button', {name: /^Изменить название:/}).click();await f.workspace.getByRole('textbox',{name:'Название заказа',exact:true}).fill('Не терять из документов');
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
   await f.workspace.getByRole('button', {name: /^Изменить название:/}).click();await f.workspace.getByRole('textbox',{name:'Название заказа',exact:true}).fill('Не терять');
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
   await f.workspace.getByRole('button', {name: /^Изменить название:/}).click();await f.workspace.getByRole('textbox',{name:'Название заказа',exact:true}).fill('Не потерять при ошибке');
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
 for(const width of [320,384,768,1440]) await runCase(width,'second package layout all sections',async f=>{
  f.current().title='Очень длинное название заказа '.repeat(8);f.current().customer.name='Клиент с очень длинным названием '.repeat(8);
  await f.page.goto(base+'/manager/orders/477');await f.page.getByText('Услуга варианта А',{exact:true}).waitFor();
  await f.page.evaluate(()=>document.fonts.ready);
  const header=f.workspace.locator(':scope > header'),nav=f.workspace.getByRole('navigation');const heights=[];
  const probes=[['proposal','Предложение',()=>f.page.getByTestId('add-service-line')],['documents','Документы',()=>f.page.getByRole('button',{name:'Новый документ',exact:true})],['work','Работы',()=>f.page.getByRole('combobox',{name:'Исполнитель работы',exact:true})],['payments','Оплаты',()=>f.page.getByTestId('payment-amount')]];
  for(const [section,label,probe] of probes) {
   await nav.getByRole('button',{name:label,exact:true}).click();await probe().waitFor();
   const box=await probe().boundingBox(),navBox=await nav.boundingBox();assert(box.y>=navBox.y+navBox.height-1&&box.y+box.height<=850,`${width} ${section} primary control outside viewport ${JSON.stringify(box)}`);
   heights.push((await header.boundingBox()).height);
   assert.equal(await header.locator('[data-order-header-customer]').isVisible(),true);
   assert.equal(await f.page.evaluate(()=>document.documentElement.scrollWidth>document.documentElement.clientWidth),false);
   const scroller=f.workspace.locator('div.overflow-y-auto').first();await scroller.evaluate(el=>el.scrollTop=el.scrollHeight);
   const after=await nav.boundingBox();assert(Math.abs(after.y-navBox.y)<1,'Section navigation must remain available while scrolling');await scroller.evaluate(el=>el.scrollTop=0);
  }
  assert(Math.max(...heights)-Math.min(...heights)<=2,JSON.stringify(heights));
  assert.equal(await header.getByRole('button',{name:/^Изменить название:/}).getAttribute('title'),f.current().title.trim());
  assert.equal(await header.locator('[data-order-header-customer]').getAttribute('title'),f.current().customer.name);
 });
 fs.writeFileSync(path.join(output,'results.json'),JSON.stringify({checks},null,2));
 console.log(JSON.stringify({checks:checks.length,output}));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
