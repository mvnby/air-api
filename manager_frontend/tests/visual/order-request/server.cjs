// Synthetic local-only request evidence on the real production Manager build.
const { createFixtureServer: createBase } = require('../proposal-mail/server.cjs');
function pdf() {
 const chunks=['%PDF-1.4\n']; const offsets=[0];
 const objects=['<< /Type /Catalog /Pages 2 0 R >>','<< /Type /Pages /Kids [3 0 R] /Count 1 >>','<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>','<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>'];
 const content='BT /F1 20 Tf 50 770 Td (Synthetic equipment specification) Tj 0 -40 Td (Original test PDF - no customer data) Tj ET';
 objects.push(`<< /Length ${content.length} >>\nstream\n${content}\nendstream`);
 objects.forEach((object,i)=>{offsets.push(Buffer.byteLength(chunks.join('')));chunks.push(`${i+1} 0 obj\n${object}\nendobj\n`);});
 const xref=Buffer.byteLength(chunks.join(''));chunks.push(`xref\n0 6\n0000000000 65535 f \n${offsets.slice(1).map(offset=>String(offset).padStart(10,'0')+' 00000 n \n').join('')}trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF`);
 return Buffer.from(chunks.join(''));
}
const original=pdf();
const description='Требуется заменить два старых кондиционера. Сравнить характеристики новых моделей и проверить возможность использования существующей трассы.\n\n'+Array.from({length:8},(_,i)=>`Объект ${i+1}: технические требования и подробное описание помещения. Модель PMDT50W6-24BCH, данные для проверки в приложенном оригинале. Ручное уточнение менеджера.`).join('\n\n');
function file(id,filename,extra={}) { return {id,filename,mime_type:'application/pdf',size_bytes:original.length,file_kind:'pdf',source:'email_lead_intake',origin_label:'Из письма заказчика',category:'document',created_at:'2026-10-26T08:00:00Z',preview_available:false,processing_status:'ready',processing_error:null,caption:null,transcript:null,captured_at:null,available:true,...extra}; }
function evidence(scenario='email') {
 if(scenario==='empty'||scenario==='manual')return {sources:[],files:[],warnings:[]};
 const files=[file(143,'Техническое задание — замена существующих кондиционеров, проверка трасс и электрического питания.pdf'),file(-144,'!!Сплит-системы Puremind PMDT50W6-24BCH — подробные технические характеристики внутреннего и наружного блоков.pdf',{mail_message_id:-187,mail_attachment_id:144,source:'incoming_mail'})];
 if(scenario==='unavailable')files.push(file(null,'Старый недоступный оригинал с длинным названием.pdf',{legacy_key:'old:1',legacy:true,available:false,processing_error:'Оригинал не сохранён. Требуется восстановление.'}));
 return {sources:[{label:scenario==='tender'?'Проработанная заявка тендера':'Исходное письмо: Заявка на замену кондиционеров',text:scenario==='tender'?'Замена оборудования по техническому заданию.':'Добрый день!\n\nДокументы во вложении.\n\nС уважением,\nТестовый заказчик\n+375 29 000-00-00',url:scenario==='tender'?'https://example.test/tender/123':'/manager/mail?emailId=-187',truncated:false}],files,warnings:[]};
}
function createFixtureServer(port=5199) {
 let scenario='email',reads=[],accesses=[];
 const fixture=createBase(port,async(req,res,{url,state,json,body})=>{
  const p=url.pathname;
  if(p==='/__request/reset'){
   scenario=url.searchParams.get('scenario')||'email';fixture.reset();reads=[];accesses=[];
   state=fixture.getState();state.order.lead_source=scenario==='tender'?'belzakupki':scenario==='manual'?'manager':'email';state.order.comment=scenario==='empty'?'':description;
   if(scenario==='error')state.flags.contextError=true;
   return json(res,{ok:true,scenario}),true;
  }
  if(p==='/__request/state')return json(res,{scenario,reads,accesses,...fixture.getState()}),true;
  if(/\/orders\/(590|591)\/request-context$/.test(p)){
   const orderId=Number(p.split('/')[4]);reads.push(orderId);
   const data=orderId===591?{sources:[],files:[file(591,'Только второй заказ.pdf')],warnings:[]}:evidence(scenario);
   await new Promise(resolve=>setTimeout(resolve,Number(state.flags.contextDelay||80)));
   if(state.flags.contextError)return json(res,{detail:'Тестовая ошибка загрузки заявки. Повторите попытку.'},503),true;
   return json(res,data),true;
  }
  if(p==='/api/manager/orders/591')return json(res,{...state.order,id:591,title:'Второй синтетический заказ',lead_source:'manager',comment:'Только описание второго заказа',proposals:[]}),true;
  if(/\/service-attachments\/\d+\/access$/.test(p)){
   accesses.push(req.url);if(state.flags.accessError)return json(res,{detail:'Оригинал временно недоступен'},503),true;
   return json(res,{url:`http://127.0.0.1:${port}/__request/original.pdf?download=${url.searchParams.get('download')||false}`,variant:'original',expires_at:'2099-01-01T00:00:00Z'}),true;
  }
  if(p==='/api/manager/mail/messages/-187/attachments/144'||p==='/__request/original.pdf'){
   accesses.push(req.url);if(state.flags.accessError)return json(res,{detail:'Оригинал временно недоступен'},503),true;
   res.writeHead(200,{'Content-Type':'application/pdf','Cache-Control':'no-store','Content-Disposition':p.startsWith('/api/')?'attachment; filename="specification.pdf"':url.searchParams.get('download')==='true'?'attachment; filename="specification.pdf"':'inline'});res.end(original);return true;
  }
  return false;
 });
 // Ensure the first interactive page is representative without a reset request.
 fixture.getState().order.lead_source='email';fixture.getState().order.comment=description;
 return {...fixture,getEvidenceState:()=>({reads,accesses,scenario})};
}
module.exports={createFixtureServer,evidence};
if(require.main===module){const port=Number(process.env.KITLANE_FIXTURE_PORT||5199);const fixture=createFixtureServer(port);fixture.server.listen(port,'127.0.0.1',()=>console.log(`Synthetic request preview http://127.0.0.1:${port}/manager/orders/590?company=999&site=minsk&proposalId=586`));}
