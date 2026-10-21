const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

module.exports = async ({runCase,base,output}) => {
 const discarded = 'Отменённое название';
 const fresh = 'Актуальное серверное название';
 const input = f => f.workspace.getByRole('textbox',{name:'Название заказа',exact:true});
 const trigger = f => f.workspace.getByRole('button',{name:`Изменить название: ${fresh}`,exact:true});
 const saved = f => f.workspace.locator('header [role="status"]').filter({hasText:'Сохранено'});
 const drafts = f => f.page.evaluate(()=>Object.fromEntries(Object.entries(sessionStorage).filter(([key])=>key.startsWith('manager_order_drawer_draft_477_24_'))));
 const state = async f => ({editorOpen:await input(f).count()>0,field:await input(f).count()?await input(f).inputValue():null,title:await f.workspace.locator('header [aria-label^="Изменить название:"]').getAttribute('aria-label').catch(()=>null),drafts:await drafts(f),requests:structuredClone(f.requests),patches:structuredClone(f.attempts)});
 const open = async (f,automatic) => {
  await f.page.goto(base+'/manager/orders/477?proposalId=24'); await f.workspace.waitFor();
  if(!automatic) await f.workspace.getByRole('switch',{name:'Автосохранение заказа'}).click();
  await f.workspace.getByRole('button',{name:/^Изменить название:/}).click();
  await input(f).fill(discarded);
 };
 for(const width of [320,384,1440]) {
  for(const automatic of [true,false]) {
   for(const delay of [0,1500]) await runCase(width,`title discard open editor autosave ${automatic} delay ${delay}`,async f=>{
    await open(f,automatic); f.current().title=fresh; f.detailDelay(delay);
    await f.workspace.getByRole('button',{name:'Отменить изменения',exact:true}).click();
    if(delay) {await f.page.waitForTimeout(900);assert.equal(f.attempts.length,0);assert.equal(await input(f).inputValue(),discarded);}
    await f.page.getByText('Изменения отменены',{exact:true}).waitFor(); await saved(f).waitFor();
    const afterCancel=await state(f);
    fs.writeFileSync(path.join(output,`title-cancel-${width}-${automatic}-${delay}.json`),JSON.stringify({afterCancel},null,2));
    assert.equal(afterCancel.editorOpen,false); assert.equal(afterCancel.title,`Изменить название: ${fresh}`);
    assert.equal(JSON.stringify(afterCancel.drafts).includes(discarded),false);assert.equal(f.attempts.length,0);
    assert.equal(await trigger(f).evaluate(el=>document.activeElement===el),true);
    // Enter on the restored title trigger opens the fresh value, never the discarded buffer.
    await f.page.keyboard.press('Enter');assert.equal(await input(f).inputValue(),fresh);await input(f).press('Enter');
    await trigger(f).click();assert.equal(await input(f).inputValue(),fresh);await f.workspace.getByRole('button',{name:'Применить название',exact:true}).click();
    await trigger(f).click();await input(f).press('Tab');
    assert.equal(await input(f).inputValue(),fresh);await f.page.waitForTimeout(1100);await saved(f).waitFor();
    assert.equal(f.attempts.length,0);assert.equal(Object.keys(await drafts(f)).length,0);
    fs.writeFileSync(path.join(output,`title-cancel-${width}-${automatic}-${delay}.json`),JSON.stringify({afterCancel,afterEnterApplyBlur:await state(f)},null,2));
    if(delay) await f.page.screenshot({path:path.join(output,`title-cancel-${width}-${automatic}.png`)});
   });
   await runCase(width,`title discard failed GET preserves open input autosave ${automatic}`,async f=>{
    await open(f,automatic);const before=await drafts(f);f.failDetail(true);
    await f.workspace.getByRole('button',{name:'Отменить изменения',exact:true}).click();
    await f.page.getByText(/Не удалось отменить черновик:/).waitFor();await f.page.waitForTimeout(1100);
    assert.equal(await input(f).inputValue(),discarded);assert.deepEqual(await drafts(f),before);assert.equal(f.attempts.length,0);
    fs.writeFileSync(path.join(output,`title-cancel-failure-${width}-${automatic}.json`),JSON.stringify(await state(f),null,2));
    await f.workspace.getByRole('button',{name:'К заказам',exact:true}).click();await f.page.waitForURL(url=>url.pathname==='/manager/orders/kanban');
    assert.deepEqual(await drafts(f),before);assert.equal(f.attempts.length,0);
   });
  }
  await runCase(width,'title normal save response preserves open input focus and caret',async f=>{
   let first=true;
   await f.page.route('**/api/manager/orders/477',async route=>{
    if(first&&route.request().method()==='PATCH'){first=false;await new Promise(done=>setTimeout(done,900));}
    await route.fallback();
   });
   await f.page.goto(base+'/manager/orders/477');await f.workspace.waitFor();
   await f.workspace.getByRole('button',{name:/^Изменить название:/}).click();
   const request=f.page.waitForRequest(r=>r.method()==='PATCH');await input(f).fill('Первая правка');await request;
   await input(f).fill('Более новая правка');await input(f).evaluate(el=>el.setSelectionRange(3,8));
   await saved(f).waitFor();
   assert.equal(await input(f).inputValue(),'Более новая правка');
   assert.deepEqual(await input(f).evaluate(el=>({focused:document.activeElement===el,start:el.selectionStart,end:el.selectionEnd})),{focused:true,start:3,end:8});
   assert.equal(f.current().title,'Более новая правка');assert.deepEqual(f.attempts,[{title:'Первая правка'},{title:'Более новая правка'}]);
  });
 }
};
