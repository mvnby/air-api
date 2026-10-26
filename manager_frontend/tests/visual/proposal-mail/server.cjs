// Local-only, synthetic API and the real Manager production build. No mail transport.
const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const { auth, stores } = require('../kitlane/fixtures.json');
const now = '2026-10-26T08:00:00Z';
const account = { id:'system', name:'Мастер Воздуха', email:'office@example.test', signature:'Мастер Воздуха\n+375 29 000-00-00\noffice@example.test' };
const scopes = { service:'монтаж оборудования', goods:'поставку товаров', mixed:'поставку товаров и доставку', repair:'диагностику оборудования и ремонт оборудования', maintenance:'техническое обслуживание оборудования' };
const line = (title,id=1) => ({id,proposal_id:586,service_title:title,quantity:2,price:810,cost:0,line_total:1620});
const product = {id:10,proposal_id:586,product_id:10,product_title:'Вентилятор',quantity:1,price:400,cost:0,line_total:400};
function makeOrder(kind='service') {
  const services = kind==='goods'?[]:[line(kind==='mixed'?'Доставка':kind==='repair'?'Диагностика и ремонт':kind==='maintenance'?'Техническое обслуживание':'Стандартный монтаж настенного кондиционера свыше 4,2 и менее 8 кВт')];
  const products = ['goods','mixed'].includes(kind)?[{...product}]:[];
  return { id:590,title:'Обслуживание',status:'negotiation',lead_source:'manager',workflow_type:'service_work',negotiation_status:'awaiting_offer',execution_status:'needs_schedule',created_at:now,is_paid:false,total_amount:1620,total_cost:0,margin:1620,total_payments:0,balance_due:1620,payments:[],documents:[],product_lines:products,service_lines:services,work_stages:[],attachment_count:0,responsible_staff_user_id:null,
    customer:{id:541,name:'Тестовый заказчик',type:'company',email:'customer@example.test',phone:'+375290000001',inn:'123456789',full_legal_name:'ООО Тестовый заказчик'},
    proposals:[{id:586,name:'Основное',status:'draft',is_selected:true,is_archived:false,product_lines:products,service_lines:services,total_amount:1620},
      {id:587,name:'Альтернатива — диагностика',status:'draft',is_selected:false,is_archived:false,product_lines:[],service_lines:[{...line('Диагностика',2),proposal_id:587}],total_amount:1620}] };
}
function doc(id=862,proposal=586,status='issued') {return {id,order_id:590,legal_entity_id:5,proposal_id:proposal,doc_type:'offer',status,provider:'native',official_full_number:status==='draft'?null:'КП-2026-024',display_number:status==='draft'?'Черновик КП':'КП-2026-024',date:now,created_at:now,document_template_id:100,template_version_id:101,artifacts:[{id:1,kind:'source_docx',mime_type:'application/vnd.openxmlformats-officedocument.wordprocessingml.document',filename:'KP.docx'}]};}
function createFixtureServer(port=5198, handleRequest) {
 const dist=path.resolve(__dirname,'../../../dist');
 let state;
 const reset=(kind='service', options={})=>{state={kind,order:makeOrder(kind),documents:options.documents===false?[]:[doc()],draft:null,patches:[],creates:[],sends:0,approvals:0,mailCreates:[],createKeys:new Map(),flags:{...options}};if(options.alternative){state.order.proposals[0].status='sent';state.order.negotiation_status='proposal_sent';state.documents=[doc(),doc(861),doc(860)];}return state;};
 reset();
 const json=(res,data,status=200)=>{res.writeHead(status,{'Content-Type':'application/json','Cache-Control':'no-store'});res.end(JSON.stringify(data));};
 const body=async req=>{let raw='';for await(const chunk of req)raw+=chunk;return raw?JSON.parse(raw):{};};
 const compose=ids=>{const chosen=state.documents.find(item=>ids.includes(item.id));const scenario=chosen?.proposal_id===587?'диагностику оборудования':scopes[state.kind];return {template_key:'offer',template_options:[{key:'auto',label:'Автоматически',requires_documents:true},{key:'request_requisites',label:'Запросить реквизиты',requires_documents:false}],subject:`Коммерческое предложение на ${scenario}`,body_text:`Добрый день!\n\nНаправляем коммерческое предложение на ${scenario}.\nДокумент приложен к письму.\n\nПосмотрите, подходит ли вам состав предложения. Напишите, если нужно что-то изменить; после согласования обсудим следующий шаг.\n\nС уважением,\nВадим\nМастер Воздуха\n+375 29 000-00-00\noffice@example.test`,document_ids:ids,document_labels:['КП-2026-024'],missing_requisites:[]};};
 const server=http.createServer(async(req,res)=>{try {
   const url=new URL(req.url,`http://127.0.0.1:${port}`),p=url.pathname;
   if(handleRequest && await handleRequest(req,res,{url,state,json,body}))return;
   if(p==='/__fixture/reset'){reset(url.searchParams.get('kind')||'service',Object.fromEntries([...url.searchParams].filter(([key])=>key!=='kind').map(([key,value])=>[key,value==='true'?true:value==='false'?false:value])));return json(res,{ok:true});}
   if(p==='/__fixture/state')return json(res,{...state,createKeys:undefined});
   if(p==='/__fixture/flags'){Object.assign(state.flags,await body(req));return json(res,{ok:true});}
   if(p.startsWith('/api/')||p.startsWith('/login')){
     let data={items:[],total:0,page:1,limit:100,meta:{pages:1},enabled:false};
     if(p==='/api/manager/account/companies')data={staff_user_id:999,username:auth.username,is_platform_owner:true,default_tenant_id:999,items:[{tenant_id:999,slug:'test',display_name:'Тестовая компания',role:'owner',membership_id:999,access_kind:'membership',is_system:true,demo_read_only:false,default_storefront_slug:'minsk'}],total:1,page:1,limit:100};
     else if(p.endsWith('/me'))data={...auth,display_name:'Вадим',capabilities:[...auth.capabilities,'worker.pay.read','worker.pay.manage']};
     else if(p.endsWith('/storefronts'))data={items:stores.map(store=>({...store,id:999}))};
     else if(p==='/api/manager/orders/590'){
       if(req.method==='PATCH'){
         const payload=await body(req);state.patches.push(payload);
         if(state.flags.failSave)return json(res,{detail:{message:'Тестовая ошибка сохранения заказа'}},503);
         const target=state.order.proposals.find(item=>item.id===payload.line_proposal_id);
         const {products,services,line_proposal_id,...form}=payload;Object.assign(state.order,form);
         for(const [incoming,field]of [[products,'product_lines'],[services,'service_lines']])if(incoming){assert(target);target[field]=incoming.map((row,i)=>({...row,id:row.link_id||100+i,proposal_id:target.id,service_title:row.title,product_title:row.title||'Вентилятор'}));}
       } data=state.order;
     }
     else if(p==='/api/manager/customers/541')data=state.order.customer;
     else if(p.endsWith('/installer-workspace'))data={order_id:590,assignments:[],materials:[],collection:{version:1,assignment_id:null,amount:null,currency:null,status:'not_assigned',updated_at:null},balances:[],financial_fingerprint:'synthetic'};
     else if(p.endsWith('/worker-pay'))data={order_id:590,agreements:[],candidates:[],can_manage:true};
     else if(p.endsWith('/tender-workflow'))data={order_id:590,stage:null,deadline_at:null,price_enquiry:null,publications:[],history:[]};
     else if(p==='/api/manager/calendar/events')data=[];
     else if(p.endsWith('/document-drive/status'))data={connected:false,provider:'google_drive'};
     else if(p.endsWith('/document-system/legal-entities'))data={items:[{id:5,tenant_id:999,display_name:'Мастер Воздуха',is_default:true,status:'active',requisites:{city:'Витебск'}}]};
     else if(p.endsWith('/registration-certificates'))data=[];
     else if(p.endsWith('/document-system/runtime/pdf'))data={available:true,provider:'gotenberg',detail:'healthy'};
     else if(p.endsWith('/document-system/templates'))data={items:[{id:100,tenant_id:999,legal_entity_id:5,name:'КП',doc_type:url.searchParams.get('document_type')||'offer',is_default:true,is_active:true,sort_order:0,created_at:now}]};
     else if(p.endsWith('/templates/100/versions'))data={items:[{id:101,template_id:100,version:1,status:'active',renderer:'docx',checksum_sha256:'a'.repeat(64),placeholder_schema:{},created_at:now}]};
     else if(p.endsWith('/orders/590/documents/drafts')){const payload=await body(req);state.creates.push(payload);const created=doc(863,payload.proposal_id,'draft');state.documents.unshift(created);data=created;}
     else if(p.endsWith('/documents/863/issue')){Object.assign(state.documents.find(item=>item.id===863),doc(863,state.documents[0].proposal_id));data=state.documents[0];}
     else if(p.endsWith('/document-system/orders/590/documents'))data={items:state.documents};
     else if(p.endsWith('/mail/accounts'))data={items:[account]};
     else if(p.endsWith('/email/compose'))data=compose((await body(req)).document_ids);
     else if(p.endsWith('/email/draft')){
       const key=req.headers['idempotency-key'],payload=await body(req);state.mailCreates.push({key,payload});
       if(state.flags.failCreate)return json(res,{detail:{message:'Выбранный документ недоступен'}},400);
       if(state.createKeys.has(key))return json(res,state.createKeys.get(key),201);
       const content=compose(payload.document_ids);state.draft={id:80,version:1,status:'draft',folder:'drafts',account_id:'system',sender_email:account.email,sender_name:account.name,to:[payload.to_email],cc:[],bcc:[],subject:content.subject,body_text:content.body_text,order_id:590,customer_id:541,manager_url:'/manager/mail?emailId=80',confirmed_version:null,content_hash:'a'.repeat(64),csrf_token:'synthetic-csrf',created_at:now,updated_at:now,attachments:[{id:9,filename:'КП-2026-024.pdf',mime_type:'application/pdf',size:14368,sha256:'f'.repeat(64),available:true,download_url:'/api/manager/mail/drafts/80/attachments/9'}]};state.createKeys.set(key,structuredClone(state.draft));if(state.flags.lostCreate){state.flags.lostCreate=false;return json(res,{detail:'Synthetic lost create response after commit'},503);}data=state.draft;
     }
     else if(p.endsWith('/drafts/80/suggest')){await body(req);const initial=structuredClone(state.draft),fail=state.flags.failAI;await new Promise(resolve=>setTimeout(resolve,500));if(fail)return json(res,{detail:'AI unavailable'},503);data={version:initial.version,subject:initial.subject,body_text:initial.body_text.replace('Направляем коммерческое предложение','Во вложении коммерческое предложение')};}
     else if(p.endsWith('/drafts/80/preview')){if(state.flags.conflict)return json(res,{detail:{message:'Версия письма изменилась'}},409);data=state.draft;}
     else if(p.endsWith('/drafts/80/confirm')){state.approvals++;const payload=await body(req);assert.equal(payload.expected_version,state.draft.version);assert.equal(payload.content_hash,state.draft.content_hash);assert.equal(req.headers['x-csrf-token'],'synthetic-csrf');state.draft.confirmed_version=state.draft.version;data=state.draft;}
     else if(p.endsWith('/drafts/80/send')){await body(req);assert.equal(state.draft.confirmed_version,state.draft.version);if(state.draft.status!=='draft')return json(res,{detail:'Already attempted'},409);state.sends++;state.draft.status=state.flags.unknown?'unknown':state.flags.failed?'failed':'sent';state.draft.folder='outbox';state.draft.error=state.flags.failed?'Почтовый сервер отклонил письмо':null;if(state.flags.lostResponse){res.destroy();return;}data=state.draft;}
     else if(p.endsWith('/drafts/80')&&req.method==='PATCH'){const payload=await body(req);if(payload.expected_version!==state.draft.version||state.flags.conflict)return json(res,{detail:{message:'Письмо уже изменилось'}},409);Object.assign(state.draft,payload,{version:state.draft.version+1,confirmed_version:null});data=state.draft;}
     else if(p.endsWith('/messages/80')||p.endsWith('/drafts/80'))data=state.draft;
     else if(/\/mail\/drafts\/80\/attachments\/9$/.test(p)){res.writeHead(200,{'Content-Type':'application/pdf'});return res.end('%PDF-1.4 synthetic attachment');}
     return json(res,data);
   }
   let filename=path.resolve(dist,'.'+p.replace(/^\/manager(?=\/assets\/)/,''));
   if(!filename.startsWith(dist+path.sep)||!fs.existsSync(filename)||fs.statSync(filename).isDirectory())filename=path.join(dist,'index.html');
   const mime={'.html':'text/html','.js':'text/javascript','.css':'text/css','.svg':'image/svg+xml','.png':'image/png','.woff2':'font/woff2'}[path.extname(filename)]||'application/octet-stream';
   res.writeHead(200,{'Content-Type':mime,'Cache-Control':'no-store'});res.end(fs.readFileSync(filename));
 }catch(error){console.error(error);json(res,{detail:{message:error.message}},500);}});
 return {server,getState:()=>state,reset,port};
}
module.exports={createFixtureServer};
if(require.main===module){const port=Number(process.env.KITLANE_FIXTURE_PORT||5198);const {server}=createFixtureServer(port);server.listen(port,'127.0.0.1',()=>console.log(`Synthetic preview http://127.0.0.1:${port}/manager/orders/590?company=999&site=minsk&proposalId=586`));}
