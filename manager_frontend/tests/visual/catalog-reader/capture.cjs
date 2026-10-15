const {chromium}=require(process.env.KITLANE_PLAYWRIGHT_MODULE || 'playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const out=path.resolve(process.env.KITLANE_SCREENSHOTS || '.codex-tmp/catalog-reader');
fs.mkdirSync(out,{recursive:true});
const base=process.env.KITLANE_PREVIEW_URL || 'http://127.0.0.1:5173';
assert(['localhost','127.0.0.1'].includes(new URL(base).hostname),'Only local preview is allowed');
const allCaps=['crm.manage','catalog.master.read','storefront.offers.read','storefront.collections.manage','services.manage','settings.manage','documents.manage'];
let owner=false;
const auth=()=>({username:'lesson-manager',display_name:'Учебный менеджер',status:'authenticated',staff_user_id:999,role:'owner',tenant_id:999,storefront_id:999,is_system_tenant:owner,capabilities:owner?[...allCaps,'platform.manage','analytics.manage','infrastructure.manage']:allCaps});
const names=['MDV INFINI Loft ERP 09','TCL Ocarina T Pro 12'];
const products=names.map((title,i)=>({id:i+1,title,slug:'lesson-'+i,brand_title:i?'TCL':'MDV',series_title:i?'Ocarina T Pro':'INFINI Loft',main_image:'/reader-front.svg',retail_price_byn:2490+i*330,purchase_cost_byn:1900+i*100,recommended_price_byn:2490+i*330,margin_abs_byn:590+i*230,margin_pct:.24,supplier_name:'Учебный поставщик',supplier_qty:4+i,availability:'in_stock',cooling_power_kw:i?3.51:2.64,heating_min_c:-25,area_m2:i?35:25,category:'household',indoor_form_factor:'wall',is_inverter:true,wifi:'builtin',is_published:true}));
const meta={page:1,pages:1,total:2,limit:40};
const field=(key,label,value,unit)=>({key,label,value,unit});
const details=p=>({...p,effective_price:p.retail_price_byn,allowed:true,selection_item:p,description:'Инверторная сплит-система для комфортного охлаждения и обогрева.\nУчебный пример: данные и иллюстрации подготовлены для проверки интерфейса.',images:[{url:'/reader-front.svg',alt:'Внутренний блок'},{url:'/reader-side.svg',alt:'Вид сбоку'}],summary_fields:[field('capacity_cooling_kw','Мощность охлаждения',String(p.cooling_power_kw),'кВт'),field('area_m2','Рекомендуемая площадь',String(p.area_m2),'м²'),field('inverter','Инвертор','Да',null),field('noise_level_db','Уровень шума','20 … 39','дБ'),field('wifi_state','Wi-Fi','Встроенный',null)],specification_groups:[{key:'performance',label:'Производительность',items:[field('capacity_cooling_kw','Мощность охлаждения',String(p.cooling_power_kw),'кВт'),field('capacity_heating_kw','Мощность обогрева','3,2','кВт')]},{key:'efficiency',label:'Энергоэффективность',items:[field('energy_efficiency_class','Класс энергоэффективности','A++',null),field('seer','SEER','6,8',null)]},{key:'installation',label:'Размеры и монтаж',items:[field('indoor_dimensions','Внутренний блок','790 × 275 × 192','мм'),field('indoor_weight','Вес внутреннего блока','8','кг')]}],manuals:[{title:'Инструкция по эксплуатации (учебный пример)',url:'/reader-manual.pdf'}]});
const svg=side=>`<svg xmlns="http://www.w3.org/2000/svg" width="800" height="460" viewBox="0 0 800 460"><rect width="800" height="460" fill="#fff"/><rect x="90" y="125" width="620" height="190" rx="35" fill="#f8fafc" stroke="#cbd5e1" stroke-width="4"/><path d="M120 255 H680" stroke="#94a3b8" stroke-width="6"/><text x="130" y="180" font-size="21" font-family="sans-serif" fill="#64748b">${side?'Вид сбоку':'Учебный пример'}</text><circle cx="660" cy="175" r="7" fill="#2563eb"/></svg>`;
(async()=>{const browser=await chromium.launch({headless:true});const results={errors:[],unknown:[],widths:[],firstModel:{}};try{
const page=await browser.newPage({viewport:{width:1440,height:900}});page.on('pageerror',e=>results.errors.push(e.message));
await page.route('**/*',async route=>{const u=new URL(route.request().url());if(u.origin!==base)return route.abort();if(u.pathname.startsWith('/reader-')&&u.pathname.endsWith('.svg'))return route.fulfill({contentType:'image/svg+xml',body:svg(u.pathname.includes('side'))});if(!u.pathname.startsWith('/api')&&!u.pathname.startsWith('/login'))return route.continue();let data={};
if(u.pathname.endsWith('/me'))data=auth();
else if(u.pathname.endsWith('/storefronts'))data={items:[{slug:'training-demo',display_name:'Учебная компания Kitlane',city:'Полоцк',currency:'BYN',default_locale:'ru-BY',is_default:true,is_current:true}]};
else if(u.pathname.endsWith('/storefront-settings/brand'))data={};
else if(/\/tenant-catalog\/products\/\d+$/.test(u.pathname))data=details(products[Number(u.pathname.split('/').pop())-1]);
else if(u.pathname.endsWith('/tenant-catalog/products'))data={items:products.map(p=>({...p,effective_price:p.retail_price_byn,allowed:true})),meta};
else if(u.pathname.endsWith('/filter-options'))data={brands:[{id:1,title:'MDV'},{id:2,title:'TCL'}],series:[]};
else if(u.pathname.endsWith('/catalog-decision/products')){const ids=u.searchParams.getAll('product_ids').map(Number);data={items:ids.length?products.filter(p=>ids.includes(p.id)):products,meta};}
else if(u.pathname.endsWith('/catalog-management/query'))data={items:products.map(p=>({...p,price:p.retail_price_byn,gallery_images:[],tags:[],specs:{},manuals:[],created_at:'2026-10-15T00:00:00Z'})),meta};
else if(['/api/manager/suppliers','/api/manager/features'].includes(u.pathname))data={items:[]};
else if(u.pathname.includes('counter'))data={count:0};
else if(u.pathname.includes('rebuild'))data={needs_rebuild:false,state:'fresh'};
else {results.unknown.push(u.pathname);data={items:[],meta:{page:1,pages:1,total:0,limit:40}};}
await route.fulfill({json:data});});
const screenshot=async name=>page.screenshot({path:out+'/release-'+name+'.png',animations:'disabled'});
const check=async width=>{const actual=await page.evaluate(()=>({width:innerWidth,scroll:document.documentElement.scrollWidth}));results.widths.push(actual);assert(actual.scroll<=actual.width,'horizontal document overflow');};
await page.goto(base+'/manager/products');await page.getByRole('button',{name:'Открыть карточку '+names[0],exact:true}).click();
const dialog=page.getByRole('dialog');await dialog.getByRole('button',{name:'Добавить в подбор',exact:true}).click();await dialog.getByRole('button',{name:'Убрать из подбора',exact:true}).waitFor();assert(!await dialog.getByText('Редактировать',{exact:true}).count());await screenshot('partner-reader-desktop');
await dialog.getByRole('button',{name:'Все характеристики',exact:true}).click();await dialog.getByText('Энергоэффективность',{exact:true}).waitFor();await screenshot('reader-specs-desktop');await dialog.getByRole('button',{name:'Фото и документы',exact:true}).click();await dialog.getByRole('link',{name:'Инструкция по эксплуатации (учебный пример)'}).waitFor();
await dialog.getByRole('button',{name:'Фото 2',exact:true}).click();await dialog.getByRole('button',{name:'Увеличить фото '+names[0]}).click();await dialog.getByRole('button',{name:'Закрыть увеличенное фото'}).waitFor();await page.keyboard.press('Escape');assert(await dialog.isVisible());await page.keyboard.press('Escape');await page.getByRole('link',{name:'Открыть подбор →'}).waitFor();
await page.goto(base+'/manager/catalog-decision');await page.getByRole('button',{name:'Выбрано: 1 из 24'}).waitFor();await screenshot('compact-desktop');
for(const width of [1440,1280,768,390,320]){await page.setViewportSize({width,height:844});await page.evaluate(()=>window.scrollTo(0,0));await check(width);const triggers=page.getByRole('button',{name:'Открыть карточку '+names[0],exact:true});const trigger=width<768?triggers.first():triggers.last();results.firstModel[width]=await trigger.boundingBox();if(width===390)await screenshot('compact-mobile');}
await page.setViewportSize({width:390,height:844});const trigger=page.getByRole('button',{name:'Открыть карточку '+names[0],exact:true}).first();await trigger.click();await dialog.getByRole('button',{name:'Убрать из подбора',exact:true}).waitFor();await screenshot('reader-mobile');await dialog.getByRole('button',{name:'Все характеристики',exact:true}).click();await check(390);await screenshot('reader-specs-mobile');await page.keyboard.press('Escape');
await page.getByRole('button',{name:'Тёмная тема',exact:true}).click();await trigger.click();await dialog.getByText('Цена клиенту',{exact:true}).waitFor();await screenshot('reader-dark-mobile');await page.keyboard.press('Escape');
owner=true;await page.setViewportSize({width:1440,height:900});await page.goto(base+'/manager/products');await page.locator('[title="Открыть товар"]').first().click();await dialog.getByRole('link',{name:'Редактировать',exact:true}).waitFor();await screenshot('owner-reader-desktop');await page.keyboard.press('Escape');await page.getByTitle('Таблица',{exact:true}).click();await page.getByRole('button',{name:'Открыть карточку '+names[0],exact:true}).focus();await page.keyboard.press('Enter');await dialog.getByRole('link',{name:'Редактировать',exact:true}).waitFor();
assert.deepEqual(results.errors,[]);fs.writeFileSync(out+'/release-browser-results.json',JSON.stringify(results,null,2));console.log(JSON.stringify(results,null,2));
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exitCode=1;});
