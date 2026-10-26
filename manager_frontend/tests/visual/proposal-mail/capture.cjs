const { chromium } = require(process.env.KITLANE_PLAYWRIGHT_MODULE || 'playwright');
const { createFixtureServer } = require('./server.cjs');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const output=path.resolve(process.env.KITLANE_SCREENSHOTS||'/tmp/proposal-mail-acceptance');
fs.mkdirSync(output,{recursive:true});
for(const name of fs.readdirSync(output))if(name==='results.json'||name.endsWith('-FAILURE.png'))fs.unlinkSync(path.join(output,name));
const fixture=createFixtureServer(Number(process.env.KITLANE_FIXTURE_PORT||5198));
const base=`http://127.0.0.1:${fixture.port}`;
const checks=[];
let browser;
async function run(width,name,task,kind='service',options={}){
 fixture.reset(kind,options);
 const context=await browser.newContext({viewport:{width,height:width<768?844:1000},isMobile:width<768,hasTouch:width<768,serviceWorkers:'block'});
 const page=await context.newPage();page.setDefaultTimeout(10000);
 const errors=[];page.on('pageerror',error=>errors.push(error.message));
 await context.route('**/*',route=>{const url=new URL(route.request().url());return url.origin===base||['fonts.googleapis.com','fonts.gstatic.com'].includes(url.hostname)?route.continue():route.abort();});
 const screenshot=async state=>{await page.screenshot({path:path.join(output,`${width}-${name}-${state}.png`),animations:'disabled'});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth),width);};
 try{await task(page,screenshot);assert.deepEqual(errors,[]);checks.push({width,name,kind,passed:true});console.log(width,name,'passed');}
 catch(error){await page.screenshot({path:path.join(output,`${width}-${name}-FAILURE.png`)}).catch(()=>{});console.error(await page.locator('body').innerText());throw error;}
 finally{await context.close();}
}
const gotoOrder=(page,proposal=586,section='proposal')=>page.goto(`${base}/manager/orders/590?company=999&site=minsk&proposalId=${proposal}&section=${section}`);
async function openLetter(page){await page.getByTestId('native-document-email').click();await page.getByRole('button',{name:/Подготовить письмо/}).click();await page.getByRole('region',{name:'Редактор черновика'}).waitFor();}
async function send(page){await page.getByRole('button',{name:'Отправить письмо',exact:true}).click();}
(async()=>{
 await new Promise(resolve=>fixture.server.listen(fixture.port,'127.0.0.1',resolve));
 browser=await chromium.launch({headless:true, ...(process.env.KITLANE_CHROMIUM_PATH?{executablePath:process.env.KITLANE_CHROMIUM_PATH}:{})});
 try{
  for(const width of [1440,390,320]){
   await run(width,'viewed-proposal',async(page,shot)=>{
    await gotoOrder(page,587);await page.getByTestId('proposal-totals-bar').getByRole('button',{name:'Подготовить КП',exact:true}).waitFor();
    await shot('composition');
    await page.getByRole('button',{name:'Изменить название: Обслуживание',exact:true}).click();
    await page.getByRole('textbox',{name:'Название заказа',exact:true}).fill('Шумное название, сохранённое перед КП');
    await page.getByTestId('proposal-totals-bar').getByRole('button',{name:'Подготовить КП',exact:true}).click();
    await page.getByTestId('create-native-draft').waitFor();
    assert.equal(fixture.getState().order.title,'Шумное название, сохранённое перед КП');
    assert((await page.getByTestId('document-proposal-context').innerText()).includes('Альтернатива'));
    const chooser=page.getByTestId('native-document-type-offer');
    const chooserBox=await chooser.boundingBox(), viewport=await page.locator('[data-order-scroll]').boundingBox();
    assert(chooserBox && viewport && chooserBox.y >= viewport.y && chooserBox.y+chooserBox.height <= viewport.y+viewport.height,JSON.stringify({chooserBox,viewport}));
    await shot('prepare');
    await page.getByTestId('create-native-draft').click();await page.getByRole('button',{name:'Выпустить',exact:true}).waitFor();
    assert.equal(fixture.getState().creates.length,1);assert.equal(fixture.getState().creates[0].proposal_id,587);
    assert.equal(fixture.getState().order.proposals[0].status,'sent');assert.equal(fixture.getState().order.proposals[1].status,'draft');
    await shot('document-draft');await page.getByRole('button',{name:'Выпустить',exact:true}).click();
    await page.waitForFunction(()=>!document.body.innerText.includes('Выпустить'));
    await page.getByTestId('native-document-email').click();await shot('sources');
    await page.getByRole('button',{name:/Подготовить письмо/}).click();await page.getByRole('region',{name:'Редактор черновика'}).waitFor();
    assert.equal(await page.locator('textarea[aria-label="Текст"]').count(),1);
    assert((await page.getByRole('textbox',{name:'Тема',exact:true}).inputValue()).includes('диагностику'));
    await page.getByRole('textbox',{name:'Копия',exact:true}).fill('copy@example.test');
    await page.getByRole('textbox',{name:'Скрытая копия',exact:true}).fill('private@example.test');
    await page.getByRole('textbox',{name:'Текст',exact:true}).fill((await page.getByRole('textbox',{name:'Текст',exact:true}).inputValue())+'\nРучное уточнение менеджера.');
    await shot('editor');await page.getByRole('button',{name:'Отправить письмо',exact:true}).scrollIntoViewIfNeeded();await shot('send');
    const visible=await page.getByRole('textbox',{name:'Текст',exact:true}).inputValue();await send(page);await page.getByText('Принято почтовым сервером',{exact:true}).waitFor();
    assert.equal(fixture.getState().draft.body_text,visible);assert.deepEqual(fixture.getState().draft.cc,['copy@example.test']);assert.equal(fixture.getState().sends,1);assert.equal(fixture.getState().approvals,1);
    await shot('result');
   },'service',{alternative:true});
   for(const kind of ['service','goods','mixed','repair','maintenance'])await run(width,`590-${kind}`,async(page,shot)=>{
    await gotoOrder(page,586,'documents');await openLetter(page);
    assert((await page.getByRole('textbox',{name:'Текст',exact:true}).inputValue()).includes('С уважением,\nВадим\nМастер Воздуха'));
    assert((await page.getByRole('textbox',{name:'Тема',exact:true}).inputValue()).includes({service:'монтаж',goods:'поставку товаров',mixed:'доставку',repair:'диагностику',maintenance:'обслуживание'}[kind]));
    await shot('editor');await page.getByRole('button',{name:'Отправить письмо',exact:true}).scrollIntoViewIfNeeded();await shot('footer');
   },kind);
   await run(width,'save-error',async(page,shot)=>{
    await gotoOrder(page,587);await page.getByRole('button',{name:'Изменить название: Обслуживание',exact:true}).click();await page.getByRole('textbox',{name:'Название заказа',exact:true}).fill('Не сохранено');
    await page.getByTestId('proposal-totals-bar').getByRole('button',{name:'Подготовить КП',exact:true}).click();
    await page.getByText(/Не удалось сохранить заказ:/).first().waitFor();assert.equal(fixture.getState().creates.length,0);await shot('blocked');
   },'service',{alternative:true,failSave:true});
   await run(width,'create-recovery',async(page,shot)=>{
    await gotoOrder(page,586,'documents');fixture.getState().flags.lostCreate=true;
    await page.getByTestId('native-document-email').click();await page.getByRole('button',{name:/Подготовить письмо/}).click();
    await page.getByText(/Выбор зафиксирован/).waitFor();assert(await page.locator('input[type=checkbox]').first().isDisabled());await shot('unknown');
    await page.getByRole('button',{name:/Подготовить письмо/}).click();await page.getByRole('region',{name:'Редактор черновика'}).waitFor();
    assert.equal(fixture.getState().mailCreates.length,2);assert.equal(fixture.getState().mailCreates[0].key,fixture.getState().mailCreates[1].key);
    assert.equal(fixture.getState().createKeys.size,1);assert.equal(fixture.getState().sends,0);await shot('recovered');
   });
   await run(width,'ai-unavailable',async(page,shot)=>{
    await gotoOrder(page,586,'documents');fixture.getState().flags.failAI=true;await openLetter(page);
    const text=page.getByRole('textbox',{name:'Текст',exact:true});await text.fill((await text.inputValue())+'\nРучная правка сохранена.');
    await page.waitForTimeout(800);assert((await text.inputValue()).endsWith('Ручная правка сохранена.'));await shot('fallback');
    await send(page);await page.getByText('Принято почтовым сервером',{exact:true}).waitFor();assert.equal(fixture.getState().sends,1);
   });
   for(const failure of ['conflict','unknown','failed','lostResponse'])await run(width,`mail-${failure}`,async(page,shot)=>{
    await gotoOrder(page,586,'documents');await openLetter(page);fixture.getState().flags[failure]=true;if(failure==='lostResponse')fixture.getState().flags.unknown=true;
    await send(page);
    await page.getByText(failure==='conflict'?/Черновик изменён в другом окне/:failure==='failed'?/Почтовый сервер отклонил/:/Повторная отправка может создать дубликат|Почтовый сервер мог принять/).first().waitFor();
    const feedback=page.getByTestId('mail-feedback');
    const bounds=await feedback.boundingBox(), modal=await page.getByRole('region',{name:'Редактор черновика'}).locator('..').boundingBox();
    assert(bounds && modal && bounds.y >= modal.y && bounds.y+bounds.height <= modal.y+modal.height+1,JSON.stringify({bounds,modal}));
    assert.equal(fixture.getState().sends,failure==='conflict'?0:1);await shot('blocked');
   });
  }
  fs.writeFileSync(path.join(output,'results.json'),JSON.stringify({base,checks},null,2));console.log(`Screenshots: ${output}`);
 }finally{await browser.close();fixture.server.close();}
})().catch(error=>{console.error(error);fixture.server.close();process.exitCode=1;});
