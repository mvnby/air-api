const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');

module.exports=async({runCase,base,output,openBoard,assertBoard})=>{
 const recovery=f=>f.workspace.getByRole('alert',{name:'Восстановление черновика'});
 const save=f=>f.workspace.getByRole('button',{name:'Сохранить изменения',exact:true});
 const saved=f=>f.workspace.locator('header [role="status"]').filter({hasText:'Сохранено'});
 const storage=f=>f.page.evaluate(()=>Object.fromEntries(Object.entries(sessionStorage).filter(([key])=>key.startsWith('manager_order_drawer_draft_477_24_'))));
 const reload=async f=>{if(!f.draftDialogsInstalled){f.draftDialogsInstalled=true;f.page.on('dialog',dialog=>dialog.accept());}await f.page.reload();await f.workspace.waitFor();};
 const editPrice=async(f,kind,price,index=1)=>{
  await f.workspace.getByRole('button',{name:kind==='services'?`Редактировать услугу #${index}.1`:`Редактировать товар #${index}`,exact:true}).click();
  await f.workspace.getByLabel('Цена',{exact:true}).fill(String(price));
 };
 const seedDeleted=async(f,kind)=>{
  const field=kind==='services'?'service_lines':'product_lines';
  const row=(id,price)=>kind==='services'?{id,service_id:7,service_title:id===81?'Восстановить услугу':'Оставшаяся услуга',description:'Описание клиента',quantity:1,price,cost:100}:{id,product_id:id===81?9:10,product_title:id===81?'Тестовый товар':'Другой товар',client_description:'Описание товара',quantity:1,price,cost:100,logistics_components:[{title:'Блок',country:'Китай',unit:'шт.',quantity_per_parent:1,unit_price:1200}]};
  f.current().proposals[0][field]=[row(81,1200),row(82,300)];
  await f.page.goto(base+'/manager/orders/477');await f.workspace.waitFor();
  await f.workspace.getByRole('switch',{name:'Автосохранение заказа'}).click();
  await editPrice(f,kind,1400);
  await f.page.waitForFunction(()=>Object.values(sessionStorage).some(raw=>raw.includes('"price":1400')));
  f.current().proposals[0][field].shift();f.current().proposals[0][field][0].price=600;f.current().comment='Свежий комментарий коллеги';
  await reload(f);await recovery(f).waitFor();return field;
 };
 const seedPartial=async f=>{
  const expected=await openBoard(f,true);
  await f.workspace.getByRole('switch',{name:'Автосохранение заказа'}).click();
  await f.workspace.getByRole('button',{name:/^Изменить название:/}).click();await f.page.getByRole('textbox',{name:'Название заказа',exact:true}).fill('Мой заголовок');await f.page.getByRole('textbox',{name:'Название заказа',exact:true}).press('Enter');
  await editPrice(f,'services',1400);
  f.current().title='Заголовок коллеги';f.current().proposals[0].service_lines[0].price=1800;
  await reload(f);await recovery(f).waitFor();
  await recovery(f).locator('article').filter({has:f.page.getByRole('heading',{name:'Название',exact:true})}).getByRole('button',{name:'Использовать черновик',exact:true}).click();
  assert.equal(await recovery(f).locator('article').count(),1);assert.equal(f.attempts.length,0);
  return expected;
 };
 for(const width of [320,384,1440]) {
  for(const kind of ['services','products']) {
   for(const automatic of [false,true]) await runCase(width,`followup deleted ${kind} restored ${automatic?'automatic':'manual'}`,async f=>{
    const field=await seedDeleted(f,kind);
    assert.equal(await save(f).isDisabled(),true);
    if(automatic) await f.workspace.getByRole('switch',{name:'Автосохранение заказа'}).click();
    await recovery(f).getByRole('button',{name:'Использовать черновик',exact:true}).click();
    if(!automatic) await save(f).click();
    await f.page.waitForFunction(()=>document.querySelector('header [role="status"]')?.textContent?.includes('Сохранено')||document.querySelector('header [role="status"]')?.textContent?.includes('Не удалось сохранить'));
    fs.writeFileSync(path.join(output,`followup-${kind}-${width}-${automatic}-patch.json`),JSON.stringify(f.attempts,null,2));
    assert.equal(f.attempts[0][kind].find(row=>row.price===1400).link_id,null);
    await saved(f).waitFor();assert.equal(f.current().proposals[0][field].length,2);
    assert.equal(f.current().proposals[0][field].find(row=>row.id===82).price,600);
    assert.equal(f.current().comment,'Свежий комментарий коллеги');
    assert.equal(f.attempts[0][kind].find(row=>row.price===1400)[kind==='services'?'description':'client_description'],kind==='services'?'Описание клиента':'Описание товара');
    const id=f.current().proposals[0][field].find(row=>row.price===1400).id;
    await reload(f);assert.equal(await recovery(f).count(),0);assert.equal(f.current().proposals[0][field].find(row=>row.id===id).price,1400);
    assert.equal(f.patches.length,1);
   });
   await runCase(width,`followup deleted ${kind} server choice`,async f=>{
    const field=await seedDeleted(f,kind);await recovery(f).getByRole('button',{name:'Оставить серверное',exact:true}).click();
    assert.equal(f.current().proposals[0][field].length,1);assert.equal(f.attempts.length,0);await reload(f);assert.equal(await recovery(f).count(),0);
   });
   for(const lostAck of [false,true]) await runCase(width,`followup deleted ${kind} retry reload ${lostAck?'lost ACK':'offline'}`,async f=>{
    const field=await seedDeleted(f,kind);await recovery(f).getByRole('button',{name:'Использовать черновик',exact:true}).click();
    if(lostAck) f.loseNextSave(); else f.failSave(true);
    await save(f).click();await f.workspace.locator('header [role="status"]').filter({hasText:'Не удалось сохранить'}).waitFor();
    f.failSave(false);await reload(f);
    if(lostAck) {await recovery(f).waitFor();await recovery(f).getByRole('button',{name:'Оставить серверное',exact:true}).click();}
    else {await save(f).waitFor();await save(f).click();await saved(f).waitFor();}
    assert.equal(f.current().proposals[0][field].length,2);assert.equal(f.current().proposals[0][field].filter(row=>row.price===1400).length,1);
    assert.equal(f.current().proposals[0][field].some(row=>row.id===81),false);
    assert.equal(f.patches.length,1);assert.equal(f.attempts.some(payload=>payload[kind].some(row=>row.link_id===81)),false);
   });
  }
  for(const method of ['button','browser Back']) await runCase(width,`followup partial conflict leave ${method} and cancel`,async f=>{
   const expected=await seedPartial(f),before=await storage(f);
   assert.equal(await save(f).isDisabled(),true);
   const back=f.workspace.getByRole('button',{name:'К заказам',exact:true});assert.equal(await back.isEnabled(),true);
   if(method==='button') {await back.focus();await f.page.keyboard.press('Enter');}else await f.page.evaluate(()=>history.back());
   await assertBoard(f,expected);assert.deepEqual(await storage(f),before);assert.equal(f.attempts.length,0);
   await expected.column.locator('article[draggable]').filter({hasText:'№477'}).getByRole('link',{name:'Открыть заказ',exact:true}).evaluate(el=>el.click());
   await recovery(f).waitFor();assert.equal(await recovery(f).locator('article').count(),1);assert.equal(await f.workspace.getByRole('button',{name:'Изменить название: Мой заголовок',exact:true}).count(),1);
   await f.page.evaluate(()=>sessionStorage.setItem('manager_order_drawer_draft_477_25_other','other draft'));
   f.current().comment='Ещё более свежий комментарий';const cancel=f.workspace.getByRole('button',{name:'Отменить изменения',exact:true});await cancel.focus();await f.page.keyboard.press('Enter');
   await saved(f).waitFor();assert.equal(await recovery(f).count(),0);assert.equal(Object.keys(await storage(f)).length,0);assert.equal(f.attempts.length,0);
   assert.equal(await f.page.evaluate(()=>sessionStorage.getItem('manager_order_drawer_draft_477_25_other')),'other draft');
   assert.equal(await f.page.getByText('Сначала выберите значения в восстановленном черновике.',{exact:true}).count(),0);
   assert.equal(await f.page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
   await f.page.screenshot({path:path.join(output,`followup-cancel-${width}-${method.replace(' ','-')}.png`)});
   await reload(f);assert.equal(await recovery(f).count(),0);assert.equal(f.attempts.length,0);
  });
  await runCase(width,'followup failed cancellation keeps conflict and allows safe exit',async f=>{
   const expected=await seedPartial(f),before=await storage(f);f.failDetail(true);
   await f.workspace.getByRole('button',{name:'Отменить изменения',exact:true}).click();await f.page.getByText(/Не удалось отменить черновик:/).waitFor();
   assert.deepEqual(await storage(f),before);assert.equal(f.attempts.length,0);f.failDetail(false);
   await f.workspace.getByRole('button',{name:'К заказам',exact:true}).click();await assertBoard(f,expected);assert.deepEqual(await storage(f),before);assert.equal(f.attempts.length,0);
  });
 }
};
