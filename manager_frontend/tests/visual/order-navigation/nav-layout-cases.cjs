const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

module.exports = async ({runCase,base,output}) => {
 // Extra narrow CSS widths cover reflow; KITLANE_NATIVE_ZOOM separately uses chrome.tabs.setZoom.
 const nativeZoom=Number(process.env.KITLANE_NATIVE_ZOOM||1);
 for(const width of (nativeZoom===1?[160,180,192,320,360,384,720,768,1440]:[320,360,384,768,1440])) for(const workflow of ['sales_installation','repair']) for(const dark of [false,true]) {
  await runCase(width,`nav labels ${workflow} ${dark?'dark':'light'}`,async f=>{
   f.current().workflow_type=workflow;
   await f.page.goto(base+'/manager/orders/477');await f.workspace.waitFor();
   await f.setNativeZoom();
   await f.page.evaluate(dark=>document.documentElement.classList.toggle('dark',dark),dark);
   await f.page.evaluate(()=>document.fonts.ready);
   const nav=f.workspace.getByRole('navigation',{name:'Рабочая область заказа',exact:true});
   const labels=['Предложение','Документы',workflow==='repair'?'Ремонт':'Работы','Оплаты'];
   const metrics=await nav.evaluate(el=>{
    const rect=r=>({left:r.left,right:r.right,top:r.top,bottom:r.bottom,width:r.width,height:r.height});
    return {viewport:innerWidth,devicePixelRatio,nav:rect(el.getBoundingClientRect()),buttons:[...el.querySelectorAll('button')].filter(b=>b.dataset.orderUsage!=='workspace-add-product').map(button=>{
     const text=document.createRange();text.selectNodeContents(button.querySelector('[data-workspace-label]')||button);
     return {label:button.textContent.trim(),button:rect(button.getBoundingClientRect()),text:rect(text.getBoundingClientRect())};
    })};
   });
   const name=`nav-${width}-${workflow}-${dark?'dark':'light'}`;
   fs.writeFileSync(path.join(output,name+'.json'),JSON.stringify(metrics,null,2));
   assert.deepEqual(metrics.buttons.map(b=>b.label),labels);
   for(const item of metrics.buttons) {
    const b=item.button,t=item.text;
    assert(t.left>=b.left-0.5&&t.right<=b.right+0.5&&t.top>=b.top-0.5&&t.bottom<=b.bottom+0.5,`${width}: label escapes its own tap area ${JSON.stringify(item)}`);
    assert(b.width>=44&&b.height>=44,`${width}: undersized tap area ${JSON.stringify(item)}`);
    assert(b.left>=metrics.nav.left&&b.right<=metrics.nav.right,`${width}: button escapes navigation`);
   }
   for(let i=0;i<metrics.buttons.length;i++) for(let j=i+1;j<metrics.buttons.length;j++) {
    const a=metrics.buttons[i].button,b=metrics.buttons[j].button;
    assert(a.right<=b.left+0.5||b.right<=a.left+0.5||a.bottom<=b.top+0.5||b.bottom<=a.top+0.5,`${width}: overlapping tap areas`);
   }
   // Native keyboard activation and sequential focus retain one stop per section.
   for(let i=0;i<labels.length;i++) {
    const button=nav.getByRole('button',{name:labels[i],exact:true});
    if(i===0) await button.focus();
    assert.equal(await button.evaluate(el=>document.activeElement===el),true);
    await f.page.keyboard.press(i%2?'Space':'Enter');
    await f.page.waitForFunction(label=>[...document.querySelectorAll('[data-order-usage="workspace-navigation"] button')].some(b=>b.textContent.trim()===label&&b.getAttribute('aria-current')==='page'),labels[i]);
    if(i<labels.length-1) await f.page.keyboard.press('Tab');
   }
   if(width<768&&nativeZoom===1) for(const label of labels) {
    const button=nav.getByRole('button',{name:label,exact:true});await button.tap();
    assert.equal(await button.getAttribute('aria-current'),'page');
   }
   assert(metrics.nav.left>=0&&metrics.nav.right<=metrics.viewport,`${width}: navigation escapes viewport`);
   if(workflow==='repair') await f.page.screenshot({path:path.join(output,name+'.png')});
  });
 }
};
