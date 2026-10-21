// Production-build benchmark. Own HTTP fixture server preserves Chromium HTTP cache.
// Never contacts a real API or changes a real order.
const { chromium } = require(process.env.KITLANE_PLAYWRIGHT_MODULE || 'playwright');
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
const zlib = require('node:zlib');
const crypto = require('node:crypto');
const assert = require('node:assert/strict');
const { auth, stores } = require('../kitlane/fixtures.json');
const dist = path.resolve(process.env.KITLANE_BENCH_DIST || 'dist');
const output = path.resolve(process.env.KITLANE_SCREENSHOTS || '/tmp/order-workspace-package');
const label = process.env.KITLANE_BENCH_LABEL || 'baseline';
const cachePolicy = process.env.KITLANE_BENCH_CACHE_POLICY || 'immutable';
assert(['no-store','immutable'].includes(cachePolicy));
const iconFont = process.env.KITLANE_BENCH_ICON_FONT;
const pairs = Number(process.env.KITLANE_BENCH_PAIRS || 5);
const port = Number(process.env.KITLANE_BENCH_PORT || 5193);
const base = `http://127.0.0.1:${port}`;
const serviceTitle = 'Выездная диагностика кондиционеров на нескольких объектах с учётом транспортных расходов';
const settings = { cpuSlowdown: 4, latencyMs: 80, downloadBytesPerSecond: 200000, uploadBytesPerSecond: 93750, viewport: { width: 384, height: 850 }, pairs,
  cachePolicy, requestInterception: false, nodeVersion: process.version, iconFontSha256: iconFont ? crypto.createHash('sha256').update(fs.readFileSync(iconFont)).digest('hex') : null };
fs.mkdirSync(output, { recursive: true });
let workflow = 'sales_installation';
const makeOrder = () => {
  const line = { id: 1, proposal_id: 25, service_title: serviceTitle, description: 'Согласованный объём диагностики и выезда.', quantity: 1, price: 1200, cost: 0, line_total: 1200 };
  return { id: 477, title: 'Тестовая диагностика', status: 'negotiation', lead_source: 'email', workflow_type: workflow,
    negotiation_status: 'awaiting_offer', execution_status: 'needs_schedule', created_at: '2026-10-20T08:00:00Z',
    is_paid: false, total_amount: 1200, total_cost: 0, margin: 1200, total_payments: 0, balance_due: 1200,
    payments: [], documents: [], product_lines: [], service_lines: [line], work_stages: [], attachment_count: 0,
    customer: { id: 12, name: 'Тестовая компания', type: 'company' },
    proposals: [{ id: 25, name: 'Основное', status: 'draft', is_selected: true, is_archived: false, product_lines: [], service_lines: [line], total_amount: 1200 }] };
};
const fixture = pathname => {
  if (pathname === '/api/manager/account/companies') return { staff_user_id: 999, username: auth.username, is_platform_owner: true, default_tenant_id: 999,
    items: [{ tenant_id: 999, slug: 'test', display_name: 'Тестовая компания', role: 'owner', membership_id: 999, access_kind: 'membership', is_system: true, demo_read_only: false, default_storefront_slug: 'minsk' }], total: 1, page: 1, limit: 100 };
  if (pathname.endsWith('/me')) return { ...auth, capabilities: [...auth.capabilities, 'worker.pay.read', 'worker.pay.manage'] };
  if (pathname.endsWith('/storefronts')) return { items: stores.map(store => ({ ...store, id: store.slug === 'minsk' ? 999 : 998 })) };
  if (pathname === '/api/manager/orders/477') return makeOrder();
  if (pathname.endsWith('/installer-workspace')) return { order_id: 477, assignments: [], materials: [], collection: { version: 1, assignment_id: null, amount: null, currency: null, status: 'not_assigned', updated_at: null }, balances: [], financial_fingerprint: 'synthetic' };
  if (pathname.endsWith('/worker-pay')) return { order_id: 477, agreements: [], candidates: [], can_manage: true };
  if (pathname.endsWith('/tender-workflow')) return { order_id: 477, stage: null, deadline_at: null, price_enquiry: null, publications: [], history: [] };
  if (pathname === '/api/manager/calendar/events') return [];
  if (pathname === '/api/manager/customers/12') return makeOrder().customer;
  return { items: [], total: 0, page: 1, limit: 100, meta: { pages: 1 }, enabled: false };
};
const mime = filename => ({ '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.woff2': 'font/woff2', '.svg': 'image/svg+xml', '.png': 'image/png' }[path.extname(filename)] || 'application/octet-stream');
const assetCache = new Map();
const server = http.createServer((req, res) => {
  const url = new URL(req.url, base);
  if (iconFont && url.pathname === '/__fixture/icons.woff2') {
    res.writeHead(200, { 'Content-Type': 'font/woff2', 'Cache-Control': 'public, max-age=31536000, immutable' });
    return res.end(fs.readFileSync(iconFont));
  }
  if (iconFont && url.pathname === '/__fixture/icons.css') {
    res.writeHead(200, { 'Content-Type': 'text/css', 'Cache-Control': 'public, max-age=31536000, immutable' });
    return res.end("@font-face{font-family:'Material Icons Round';font-style:normal;font-weight:400;src:url('/__fixture/icons.woff2') format('woff2')}.material-icons-round{font-family:'Material Icons Round';font-weight:normal;font-style:normal;font-size:24px;line-height:1;letter-spacing:normal;text-transform:none;display:inline-block;white-space:nowrap;word-wrap:normal;direction:ltr;-webkit-font-feature-settings:'liga';-webkit-font-smoothing:antialiased}");
  }
  if (url.pathname.startsWith('/api/') || url.pathname.startsWith('/login')) {
    if (url.pathname === '/api/manager/order-workspace-usage/batch' && req.method === 'POST') {
      let body = ''; req.on('data', chunk => { body += chunk; });
      req.on('end', () => { res.writeHead(200, { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' }); res.end(JSON.stringify({ accepted: JSON.parse(body).events?.length || 0 })); });
      return;
    }
    if (req.method !== 'GET') { res.writeHead(409, { 'Content-Type': 'application/json' }); return res.end(JSON.stringify({ detail: 'Read-only synthetic benchmark' })); }
    res.writeHead(200, { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' });
    return res.end(JSON.stringify(fixture(url.pathname)));
  }
  let filename = path.resolve(dist, '.' + url.pathname.replace(/^\/manager(?=\/assets\/)/, ''));
  if (!filename.startsWith(dist + path.sep)) filename = path.join(dist, 'index.html');
  if ((!fs.existsSync(filename) || fs.statSync(filename).isDirectory()) && url.pathname.startsWith('/manager/assets/')) { res.writeHead(404, {'Cache-Control':'no-store'}); return res.end('Missing build asset'); }
  if (!fs.existsSync(filename) || fs.statSync(filename).isDirectory()) filename = path.join(dist, 'index.html');
  if (!assetCache.has(filename)) {
    let body = fs.readFileSync(filename);
    if (iconFont && filename.endsWith('index.html')) body = Buffer.from(body.toString().replace('https://fonts.googleapis.com/icon?family=Material+Icons+Round', '/__fixture/icons.css'));
    assetCache.set(filename, { raw: body, gzip: zlib.gzipSync(body, { level: 9 }) });
  }
  const asset = assetCache.get(filename), gzip = /gzip/.test(req.headers['accept-encoding'] || '') && /\.(js|css|html|svg)$/.test(filename);
  res.writeHead(200, { 'Content-Type': mime(filename), 'Cache-Control': filename.endsWith('index.html') || (/\.(js|css)$/.test(filename) && cachePolicy === 'no-store') ? 'no-store, no-cache, must-revalidate, max-age=0' : 'public, max-age=31536000, immutable',
    ...(gzip ? { 'Content-Encoding': 'gzip', Vary: 'Accept-Encoding' } : {}),
    'Content-Security-Policy': "default-src 'self' data: blob:; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; connect-src 'self'; font-src 'self' data:; img-src 'self' data: blob:" });
  res.end(gzip ? asset.gzip : asset.raw);
});
const median = values => { const v = [...values].sort((a, b) => a - b); return v.length % 2 ? v[(v.length - 1) / 2] : (v[v.length / 2 - 1] + v[v.length / 2]) / 2; };
const rounded = value => Math.round(value * 10) / 10;
const isBuildFile = request => { const name=new URL(request.url).pathname;return name.startsWith('/manager/assets/') && /\.(js|css)$/.test(name); };
const rows = [], errors = [];
async function measure(context, type, iteration, screenshots) {
  const page = await context.newPage();
  page.setDefaultTimeout(25000);
  const cdp = await context.newCDPSession(page);
  await cdp.send('Network.enable');
  await cdp.send('Network.setCacheDisabled', { cacheDisabled: false });
  await cdp.send('Emulation.setCPUThrottlingRate', { rate: settings.cpuSlowdown });
  await cdp.send('Network.emulateNetworkConditions', { offline: false, latency: settings.latencyMs, downloadThroughput: settings.downloadBytesPerSecond, uploadThroughput: settings.uploadBytesPerSecond, connectionType: 'cellular4g' });
  const requests = [], byId = new Map();
  let stage = 'initial';
  cdp.on('Network.requestWillBeSent', event => {
    if (!event.request.url.startsWith(base)) return;
    const request = { id: event.requestId, url: event.request.url, method: event.request.method, stage, bytes: 0, cached: false };
    requests.push(request); byId.set(event.requestId, request);
  });
  cdp.on('Network.requestServedFromCache', event => { if (byId.has(event.requestId)) byId.get(event.requestId).cached = true; });
  cdp.on('Network.responseReceived', event => { if (byId.has(event.requestId)) Object.assign(byId.get(event.requestId), { status: event.response.status, cached: byId.get(event.requestId).cached || !!event.response.fromDiskCache, encoding: event.response.headers['Content-Encoding'] }); });
  cdp.on('Network.loadingFinished', event => { if (byId.has(event.requestId)) byId.get(event.requestId).bytes = event.encodedDataLength; });
  page.on('pageerror', error => errors.push({ workflow, type, iteration, error: error.message }));
  await page.goto(`${base}/manager/orders/477?company=999&site=minsk&proposalId=25`, { waitUntil: 'commit' });
  const workspace = page.getByRole('region', { name: 'Рабочая область заказа', exact: true });
  try { await workspace.getByText(serviceTitle, { exact: true }).waitFor(); }
  catch (error) {
    fs.writeFileSync(path.join(output, `${label}-failure.json`), JSON.stringify({ requests, errors, body: await page.locator('body').innerText() }, null, 2));
    await page.screenshot({ path: path.join(output, `${label}-failure.png`) });
    throw error;
  }
  const estimateVisibleMs = await page.evaluate(() => performance.now());
  await workspace.getByTestId('add-service-line').click({ trial: true });
  const readyMs = await page.evaluate(() => performance.now());
  await page.waitForLoadState('networkidle');
  const initial = requests.filter(r => r.stage === 'initial');
  const js = [...new Set(initial.filter(r => new URL(r.url).pathname.endsWith('.js')).map(r => new URL(r.url).pathname))];
  const initialJsGzipBytes = js.reduce((sum, name) => sum + zlib.gzipSync(fs.readFileSync(path.join(dist, name.replace(/^\/manager(?=\/assets\/)/, ''))), { level: 9 }).length, 0);
  const initialApis = initial.filter(r => new URL(r.url).pathname.startsWith('/api/')).map(r => ({ method: r.method, path: new URL(r.url).pathname + new URL(r.url).search }));
  fs.writeFileSync(path.join(output, `${label}-${workflow}-initial.json`), JSON.stringify({ readyMs, initialJsGzipBytes, initialApis, initialJsFiles: js, errors }, null, 2));
  const layout = await workspace.evaluate(el => {
    const rect = el.getBoundingClientRect();
    return { left: rect.left, right: rect.right, viewport: innerWidth, documentWidth: document.documentElement.scrollWidth, clientWidth: document.documentElement.clientWidth };
  });
  assert(layout.left >= -1 && layout.right <= layout.viewport + 1 && layout.documentWidth <= layout.clientWidth + 1, JSON.stringify(layout));
  if (screenshots) { await page.evaluate(() => document.fonts.ready); await page.screenshot({ path: path.join(output, `${label}-${workflow}-384-proposal.png`), animations: 'disabled' }); }
  const nav = workspace.getByRole('navigation', { name: 'Рабочая область заказа', exact: true });
  const section = async (name, phase) => {
    stage = phase;
    const start = await page.evaluate(() => performance.now());
    await nav.getByRole('button', { name, exact: true }).click();
    if (name === 'Документы') {
      await workspace.locator('[data-order-usage="workspace-documents-panel"]').getByTestId('document-provider-toggle').waitFor();
      await workspace.getByText('Внутренних документов пока нет', { exact: true }).waitFor();
    } else {
      await workspace.getByRole('combobox', { name: 'Исполнитель работы', exact: true }).waitFor();
      await page.waitForFunction(() => [...document.querySelectorAll('select')].some(el => el.getAttribute('aria-label') === 'Исполнитель работы' && !el.disabled && el.getBoundingClientRect().width > 0));
      await workspace.getByText('Вознаграждения пока не согласованы.', { exact: true }).waitFor();
    }
    const ms = await page.evaluate(() => performance.now()) - start;
    await page.waitForLoadState('networkidle');
    if (screenshots && !phase.endsWith('repeat')) await page.screenshot({ path: path.join(output, `${label}-${workflow}-384-${name === 'Документы' ? 'documents' : 'work'}.png`), animations: 'disabled' });
    stage = 'return'; await nav.getByRole('button', { name: 'Предложение', exact: true }).click();
    await workspace.getByText(serviceTitle, { exact: true }).waitFor();
    return ms;
  };
  const documentsFirstMs = await section('Документы', 'documents-first');
  const documentsRepeatMs = await section('Документы', 'documents-repeat');
  const workName = workflow === 'repair' ? 'Ремонт' : 'Работы';
  const workFirstMs = await section(workName, 'work-first');
  const workRepeatMs = await section(workName, 'work-repeat');
  if (screenshots) {
    await page.setViewportSize({ width: 1440, height: 850 });
    await page.screenshot({ path: path.join(output, `${label}-${workflow}-1440-proposal.png`), animations: 'disabled' });
    await nav.getByRole('button', { name: 'Документы', exact: true }).click();
    await page.screenshot({ path: path.join(output, `${label}-${workflow}-1440-documents.png`), animations: 'disabled' });
    await nav.getByRole('button', { name: workName, exact: true }).click();
    await page.screenshot({ path: path.join(output, `${label}-${workflow}-1440-work.png`), animations: 'disabled' });
  }
  let reloadReadyMs = null, reloadEstimateVisibleMs = null, reloadBuildNetworkBytes = null, reloadBuildCachedFiles = null;
  if (type === 'warm') {
    stage = 'reload';
    await page.reload({waitUntil:'commit'});
    await workspace.getByText(serviceTitle,{exact:true}).waitFor();
    reloadEstimateVisibleMs = await page.evaluate(()=>performance.now());
    await workspace.getByTestId('add-service-line').click({trial:true});
    reloadReadyMs = await page.evaluate(()=>performance.now());
    await page.waitForLoadState('networkidle');
    const build = requests.filter(r=>r.stage==='reload' && isBuildFile(r));
    reloadBuildNetworkBytes=build.reduce((sum,r)=>sum+r.bytes,0);
    reloadBuildCachedFiles=build.filter(r=>r.cached).length;
  }
  const result = { workflow, type, iteration, estimateVisibleMs, readyMs, reloadReadyMs, reloadEstimateVisibleMs, reloadBuildNetworkBytes, reloadBuildCachedFiles,
    initialBuildNetworkBytes: initial.filter(r=>isBuildFile(r)).reduce((sum,r)=>sum+r.bytes,0),
    initialFileNetworkBytes: initial.filter(r=>!new URL(r.url).pathname.startsWith('/api/')).reduce((sum,r)=>sum+r.bytes,0), documentsFirstMs, documentsRepeatMs, workFirstMs, workRepeatMs, initialJsGzipBytes,
    initialJsNetworkBytes: initial.filter(r => new URL(r.url).pathname.endsWith('.js')).reduce((s, r) => s + r.bytes, 0),
    initialJsCachedFiles: initial.filter(r => new URL(r.url).pathname.endsWith('.js') && r.cached).length, initialJsFiles: js, initialApis, requests, layout };
  assert.deepEqual(requests.filter(r => r.status >= 400), [], 'All synthetic HTTP responses must succeed');
  rows.push(result);
  fs.writeFileSync(path.join(output, `${label}-raw.json`), JSON.stringify({ label, dist, settings, errors, rows }, null, 2));
  console.log(JSON.stringify({ workflow, type, iteration, readyMs: rounded(readyMs), initialJsGzipBytes, startupApis: initialApis.length, documentsFirstMs: rounded(documentsFirstMs), workFirstMs: rounded(workFirstMs), cachedFiles: result.initialJsCachedFiles }));
  await page.close();
}
(async () => {
  await new Promise(resolve => server.listen(port, '127.0.0.1', resolve));
  const browser = await chromium.launch({ headless: true });
  settings.browserVersion = browser.version();
  try {
    for (workflow of ['sales_installation', 'repair']) for (let iteration = 1; iteration <= pairs; iteration++) {
      const context = await browser.newContext({ viewport: settings.viewport, isMobile: true, hasTouch: true, serviceWorkers: 'block' });
      await measure(context, 'cold', iteration, iteration === 1);
      await measure(context, 'warm', iteration, false);
      await context.close();
    }
    assert.deepEqual(errors, []);
    const summary = [];
    for (const wf of ['sales_installation', 'repair']) for (const type of ['cold', 'warm']) {
      const group = rows.filter(row => row.workflow === wf && row.type === type), item = { workflow: wf, type, n: group.length };
      for (const key of ['estimateVisibleMs', 'readyMs', 'documentsFirstMs', 'documentsRepeatMs', 'workFirstMs', 'workRepeatMs', 'initialJsGzipBytes', 'initialJsNetworkBytes', 'initialJsCachedFiles','initialBuildNetworkBytes','initialFileNetworkBytes','reloadReadyMs','reloadEstimateVisibleMs','reloadBuildNetworkBytes','reloadBuildCachedFiles']) item[key] = rounded(median(group.map(row => row[key])));
      item.startupApiCount = median(group.map(row => row.initialApis.length)); summary.push(item);
    }
    fs.writeFileSync(path.join(output, `${label}-summary.json`), JSON.stringify({ label, dist, settings, summary, errors }, null, 2));
    console.log(JSON.stringify({ label, summary, output }, null, 2));
  } finally { await browser.close(); await new Promise(resolve => server.close(resolve)); }
})().catch(error => { console.error(error); server.close(); process.exitCode = 1; });
