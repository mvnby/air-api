const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
module.exports=async({runCase,base,output})=>{
 const isBackground=url=>url.pathname.includes('supply-requests')||url.pathname.endsWith('/outgoing-emails')||url.pathname.endsWith('/orders/477/documents');
 const delayBackground=async(f,failed)=>{
  const pending=[];
  await f.page.route('**/api/manager/**',async route=>{
   if(!isBackground(new URL(route.request().url())))return route.fallback();
   await new Promise(done=>setTimeout(done,5000));pending.push(route.request().url());
   if(failed)return route.fulfill({status:503,json:{detail:'Synthetic delayed background failure'}});
   return route.fallback();
  });
  return pending;
 };
 for(const width of [320,384,1440]) {
  for(const failed of [false,true]) await runCase(width,`focus background ${failed?'failure':'success'} preserves editing and scroll`,async f=>{
   const pending=await delayBackground(f,failed);
   f.current().proposals[0].service_lines=Array.from({length:15},(_,i)=>({id:100+i,service_title:`Длинная строка ${i+1}`,quantity:1,price:1200,cost:0}));
   await f.page.goto(base+'/manager/orders/477');await f.workspace.waitFor();
   assert.equal(await f.workspace.evaluate(el=>document.activeElement===el),true,'Initial focus must not await summaries');
   await f.workspace.getByRole('switch',{name:'Автосохранение заказа'}).click();
   await f.workspace.getByRole('button',{name:/^Изменить название:/}).click();
   const input=f.workspace.getByRole('textbox',{name:'Название заказа',exact:true});await input.fill('Продолжаю редактировать');
   await input.evaluate(el=>el.setSelectionRange(3,8));
   await f.workspace.locator(':scope > .grid').evaluate(el=>el.scrollTop=400);
   const read=()=>input.evaluate(el=>({value:el.value,focused:document.activeElement===el,start:el.selectionStart,end:el.selectionEnd,windowY:scrollY,scroll:el.closest('aside').querySelector(':scope > .grid').scrollTop}));
   const before=await read();assert(before.scroll>0);
   await f.page.waitForTimeout(5400);assert(pending.length>=3,'All three delayed summaries completed');
   const after=await read();assert.deepEqual(after,before);
   await f.page.keyboard.type('X');assert.equal(await input.inputValue(),before.value.slice(0,3)+'X'+before.value.slice(8));
   assert.equal(f.attempts.length,0);
   fs.writeFileSync(path.join(output,`focus-${width}-${failed}.json`),JSON.stringify({before,after,backgroundResponses:pending},null,2));
   await f.page.screenshot({path:path.join(output,`focus-${width}-${failed}.png`)});
  });
  await runCase(width,'focus late background after order switch cannot steal new title',async f=>{
   await delayBackground(f,false);
   await f.page.route('**/api/manager/orders/478',route=>route.fulfill({json:{...structuredClone(f.current()),id:478,title:'Следующий заказ'}}));
   await f.page.goto(base+'/manager/orders/477');await f.workspace.waitFor();
   await f.page.evaluate(()=>{history.pushState({},'', '/manager/orders/478');dispatchEvent(new PopStateEvent('popstate'));});
   await f.workspace.getByRole('button',{name:'Изменить название: Следующий заказ',exact:true}).click();
   await f.workspace.getByRole('switch',{name:'Автосохранение заказа'}).click();
   const input=f.workspace.getByRole('textbox',{name:'Название заказа',exact:true});await input.fill('Ввожу в другом заказе');await input.evaluate(el=>el.setSelectionRange(3,8));
   await f.page.waitForTimeout(5400);
   assert.deepEqual(await input.evaluate(el=>({focus:document.activeElement===el,start:el.selectionStart,end:el.selectionEnd,value:el.value})),{focus:true,start:3,end:8,value:'Ввожу в другом заказе'});
   assert.equal(f.attempts.length,0);
  });
  await runCase(width,'focus late background after leaving cannot steal list input',async f=>{
   await delayBackground(f,false);await f.page.goto(base+'/manager/orders/477');await f.workspace.waitFor();
   await f.workspace.getByRole('button',{name:'К заказам',exact:true}).click();
   const search=f.page.getByRole('searchbox',{name:'Поиск заказов',exact:true});await search.fill('проверка');await search.evaluate(el=>el.setSelectionRange(1,3));
   await f.page.waitForTimeout(5400);
   assert.deepEqual(await search.evaluate(el=>({focus:document.activeElement===el,start:el.selectionStart,end:el.selectionEnd})),{focus:true,start:1,end:3});
   assert.equal(f.attempts.length,0);
  });
 }
};
