const { chromium }=require(process.env.KITLANE_PLAYWRIGHT_MODULE||'playwright');
const {createFixtureServer}=require('./server.cjs');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const output=path.resolve(process.env.KITLANE_SCREENSHOTS||'/tmp/order-request-acceptance');fs.mkdirSync(output,{recursive:true});
for(const name of fs.readdirSync(output))if(name==='results.json'||name.endsWith('-FAILURE.png'))fs.unlinkSync(path.join(output,name));
const fixture=createFixtureServer(Number(process.env.KITLANE_FIXTURE_PORT||5200)),base=`http://127.0.0.1:${fixture.port}`;
let browser;const checks=[];
const orderUrl=id=>`${base}/manager/orders/${id}?company=999&site=minsk${id===590?'&proposalId=586':''}`;
async function run(width,scenario,task){
 await fetch(`${base}/__request/reset?scenario=${scenario}`);
 const context=await browser.newContext({viewport:{width,height:width<768?844:1000},isMobile:width<768,hasTouch:width<768,serviceWorkers:'block'});
 const page=await context.newPage();page.setDefaultTimeout(12000);const errors=[];page.on('pageerror',error=>errors.push(error.message));
 await context.route('**/*',route=>{const url=new URL(route.request().url());return url.origin===base||['fonts.googleapis.com','fonts.gstatic.com'].includes(url.hostname)?route.continue():route.abort();});
 const shot=async name=>{await page.screenshot({path:path.join(output,`${width}-${scenario}-${name}.png`),animations:'disabled'});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth),width);};
 try{await task(page,shot);assert.deepEqual(errors,[]);checks.push({width,scenario,passed:true});console.log(width,scenario,'passed');}
 catch(error){await shot('FAILURE').catch(()=>{});console.error(await page.locator('body').innerText());throw error;}
 finally{await context.close();}
}
const trigger=page=>page.getByTestId('order-request-trigger');
const panel=page=>page.getByRole('region',{name:'Заявка и файлы',exact:true});
async function open(page){
 if(!await trigger(page).isVisible())await page.locator('[data-order-scroll]').evaluate(el=>el.scrollTo({top:0,behavior:'instant'}));
 await trigger(page).click();await panel(page).waitFor();
}
async function inViewport(locator,width){const b=await locator.boundingBox();assert(b&&b.x>=0&&b.x+b.width<=width+1,JSON.stringify(b));}
(async()=>{
 await new Promise(resolve=>fixture.server.listen(fixture.port,'127.0.0.1',resolve));
 browser=await chromium.launch({headless:true,...(process.env.KITLANE_CHROMIUM_PATH?{executablePath:process.env.KITLANE_CHROMIUM_PATH}:{})});
 try{
  for(const width of [1440,390,320]){
   await run(width,'email',async(page,shot)=>{
    await page.goto(orderUrl(590));await trigger(page).filter({hasText:'Файлов: 2'}).waitFor();
    assert.deepEqual(fixture.getEvidenceState().accesses,[]);await shot('closed');await open(page);
    const bounds=await panel(page).boundingBox();assert(bounds && bounds.height > 300,JSON.stringify(bounds));if(width>=1024)assert(bounds.width>=440&&bounds.width<=520,JSON.stringify(bounds));
    assert(await panel(page).getByText('Рабочее описание заказа',{exact:true}).isVisible());await shot('open');
    await panel(page).getByRole('button',{name:'Читать полностью',exact:true}).click();
    await panel(page).getByText(/Объект 8:/).scrollIntoViewIfNeeded();await shot('description');
    await panel(page).getByRole('button',{name:'Свернуть описание',exact:true}).click();
    const fileRows=panel(page).locator('li');assert.equal(await fileRows.count(),2);
    await fileRows.first().getByRole('button',{name:'Открыть',exact:true}).scrollIntoViewIfNeeded();await shot('files');
    assert.deepEqual(fixture.getEvidenceState().accesses,[]);
    for(let index=0;index<2;index++){
     const row=fileRows.nth(index),button=row.getByRole('button',{name:'Открыть',exact:true});await button.click();
     const viewer=page.getByRole('dialog',{name:/Просмотр файла/});await viewer.locator('iframe').waitFor();
     await shot(`viewer-${index}`);await page.keyboard.press('Escape');await viewer.waitFor({state:'hidden'});
     assert(await panel(page).isVisible());assert.equal(await button.evaluate(el=>el===document.activeElement),true);
     const download=page.waitForEvent('download');await row.getByRole('button',{name:'Скачать',exact:true}).click();
     const item=await download;const target=path.join(output,`${width}-original-${index}.pdf`);await item.saveAs(target);assert(fs.readFileSync(target).subarray(0,5).equals(Buffer.from('%PDF-')));
     await inViewport(button,width);
    }
    await panel(page).getByRole('button',{name:'Закрыть заявку и файлы',exact:true}).click();assert.equal(await trigger(page).evaluate(el=>el===document.activeElement),true);
    // Evidence stays available during input; leaving a changed row is explicit.
    const edit=page.getByRole('button',{name:/Редактировать услугу #1/}).first();await edit.click();
    const prices=page.locator('label').filter({has:page.locator('span',{hasText:'Цена'})}).locator('input[type=number]');
    const field=prices.first();await field.fill('987.65');await open(page);await page.keyboard.press('Escape');
    assert.equal(await field.inputValue(),'987.65');
    await page.getByRole('navigation',{name:'Рабочая область заказа'}).getByRole('button',{name:'Документы',exact:true}).click();
    await page.getByRole('button',{name:'Продолжить ввод',exact:true}).click();
    assert.equal(new URL(page.url()).searchParams.get('section'),'proposal');
    assert.equal(await field.inputValue(),'987.65');await shot('draft-preserved');
   });
   for(const scenario of ['tender','manual','empty','unavailable'])await run(width,scenario,async(page,shot)=>{
    await page.goto(orderUrl(590));await trigger(page).filter({hasText:'Файлов:'}).waitFor();await shot('closed');await open(page);
    if(scenario==='tender')await panel(page).getByText('Проработанная заявка тендера',{exact:true}).waitFor();
    if(scenario==='unavailable'){const missing=panel(page).getByText(/Недоступен:/);await missing.scrollIntoViewIfNeeded();assert.equal(await panel(page).locator('li').count(),3);}
    if(['manual','empty'].includes(scenario))assert(await panel(page).getByText('Сохранённых файлов нет.',{exact:true}).isVisible());
    await shot('open');await panel(page).getByRole('button',{name:'Закрыть заявку и файлы',exact:true}).click();
   });
   await run(width,'error',async(page,shot)=>{
    await page.goto(orderUrl(590));await trigger(page).filter({hasText:'Файлы не загружены'}).waitFor();assert(!(await trigger(page).innerText()).includes('Файлов: 0'));await open(page);await shot('error');
    fixture.getState().flags.contextError=false;await panel(page).getByRole('button',{name:'Повторить загрузку',exact:true}).click();await trigger(page).filter({hasText:'Файлов: 2'}).waitFor();await shot('recovered');
    fixture.getState().flags.accessError=true;await panel(page).getByRole('button',{name:'Открыть',exact:true}).first().click();
    const viewer=page.getByRole('dialog',{name:/Просмотр файла/});await viewer.getByText('Оригинал временно недоступен',{exact:true}).waitFor();await shot('access-error');
    fixture.getState().flags.accessError=false;await viewer.getByRole('button',{name:'Повторить',exact:true}).click();await viewer.locator('iframe').waitFor();await page.keyboard.press('Escape');
   });
   await run(width,'race',async(page,shot)=>{
    fixture.getState().flags.contextDelay=1000;await page.goto(orderUrl(590));await trigger(page).filter({hasText:'Проверяем файлы…'}).waitFor();await open(page);await shot('loading');
    await page.evaluate(url=>{history.pushState({},'',url);window.dispatchEvent(new PopStateEvent('popstate'));},orderUrl(591));
    await page.getByRole('button',{name:'Изменить название: Второй синтетический заказ',exact:true}).waitFor();
    await trigger(page).filter({hasText:'Файлов: 1'}).waitFor();await open(page);
    assert.equal(await panel(page).getByTestId('request-filename').innerText(),'Только второй заказ.pdf');assert(!(await panel(page).innerText()).includes('Puremind'));await shot('new-order');
   });
  }
  fs.writeFileSync(path.join(output,'results.json'),JSON.stringify({base,checks},null,2));console.log('Evidence:',output);
 }finally{await browser?.close();fixture.server.close();}
})().catch(error=>{console.error(error);fixture.server.close();process.exitCode=1;});
