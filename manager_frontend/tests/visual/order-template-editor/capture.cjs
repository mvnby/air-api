// Exercises only the synthetic local order and immutable template versions.
const assert = require('node:assert/strict');
const { execFileSync } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require(process.env.KITLANE_PLAYWRIGHT_MODULE || 'playwright');
const { createFixtureServer } = require('../proposal-mail/server.cjs');

const output = process.env.KITLANE_SCREENSHOTS || '/tmp/order-template-editor';
const port = Number(process.env.KITLANE_FIXTURE_PORT || 5213);
const base = `http://127.0.0.1:${port}`;
const orderUrl = base + '/manager/orders/590?company=999&site=minsk&proposalId=586&section=documents';
const revision = 'a'.repeat(64);
const now = '2026-11-05T08:00:00Z';
const templateName = 'Договор подряда на обслуживание климатической техники';
const sourceId = 335;
let state;
let pdf;
let firstPage;

function version(id, status) {
  return { id, template_id: 33, version: id - 328, status, renderer: 'docx',
    source_filename: 'Шаблон договора.docx', placeholder_schema: {}, checksum_sha256: 'b'.repeat(64), created_at: now };
}

const site = createFixtureServer(port, async (req, res, { url, json, body }) => {
  const p = url.pathname;
  const reply = (value, status = 200) => { json(res, value, status); return true; };
  if (p.endsWith('/orders/590/request-context')) return reply({ sources: [], files: [], warnings: [] });
  if (p.endsWith('/me')) {
    const { auth } = require('../kitlane/fixtures.json');
    return reply({ ...auth, capabilities: [...auth.capabilities, 'documents.manage'] });
  }
  if (p.endsWith('/document-drive/status')) return reply({ connected: true, provider: 'google_drive' });
  if (p.endsWith('/document-system/templates') && url.searchParams.get('legal_entity_id') === '8') {
    return reply({ items: [{ id: 33, tenant_id: 999, legal_entity_id: 8, name: templateName, doc_type: 'contract', is_active: true }] });
  }
  if (p.endsWith('/templates/33/versions')) {
    assert.equal(url.searchParams.get('legal_entity_id'), '8');
    return reply({ items: state.versions });
  }
  if (p.endsWith('/document-system/orders/590/documents')) return reply({ items: [state.draft] });
  if (p.endsWith('/documents/863/draft/parameters')) {
    if (req.method === 'PATCH') {
      assert.deepEqual(await body(req), { expected_revision: revision, template_version_id: 336, reset_editable_copy: true });
      assert.equal(state.versions.find(v => v.id === 336).status, 'active');
      state.draft.template_version_id = 336;
      state.applies++;
      return reply(state.draft);
    }
    return reply({ revision, issue_date: '2026-11-05', total_amount: '1620', has_editable_copy: true, template_version_id: state.draft.template_version_id });
  }
  if (p.endsWith('/templates/33/versions/336/activate')) {
    assert.equal(req.method, 'POST');
    assert.equal(url.searchParams.get('expected_active_version_id'), String(sourceId));
    assert.equal(url.searchParams.get('legal_entity_id'), '8');
    state.activations++;
    state.versions = [version(336, 'active'), version(sourceId, 'retired')];
    return reply(state.versions[0]);
  }
  if (p.endsWith('/documents/863/preview')) {
    assert.equal(state.draft.template_version_id, 336);
    assert.equal(url.searchParams.get('include_first_page'), 'true');
    state.previewReads++;
    if (state.previewMode === 'pdf-only') {
      res.writeHead(200, { 'Content-Type': 'application/pdf' });
      res.end(pdf);
    } else {
      const files = new FormData();
      files.append('pdf', new Blob([pdf], { type: 'application/pdf' }), 'draft.pdf');
      files.append('first_page', new Blob([state.previewMode === 'invalid-image' ? 'unreadable' : firstPage], { type: 'image/png' }), 'page.png');
      const response = new Response(files);
      res.writeHead(200, { 'Content-Type': response.headers.get('Content-Type') });
      res.end(Buffer.from(await response.arrayBuffer()));
    }
    return true;
  }
  if (p.endsWith('/templates/33/versions/335/google-edit-session')) {
    assert.equal(url.searchParams.get('legal_entity_id'), '8');
    if (req.method === 'POST') state.editOpened = true;
    return state.editOpened ? reply({
      id: 'fixture-editor', status: state.remoteChanged ? 'changed' : 'ready', can_edit: true,
      base_checksum_sha256: 'b'.repeat(64), remote_revision: 'fixture-revision', edit_url: base + '/__fixture/template-editor',
    }) : reply({ detail: 'No session' }, 404);
  }
  if (p.endsWith('/templates/33/versions/335/google-edit-session/sync')) {
    const command = await body(req);
    assert.equal(command.expected_remote_revision, 'fixture-revision');
    assert.equal(state.remoteChanged, true);
    state.versions = [version(336, 'draft'), version(sourceId, 'active')];
    state.remoteChanged = false;
    return reply({ session: { id: 'fixture-editor', status: 'ready', can_edit: true, edit_url: base + '/__fixture/template-editor' },
      new_template_version: state.versions[0] });
  }
  if (p.endsWith('/google-edit-session')) return reply({ detail: 'No session' }, 404);
  if (p === '/__fixture/template-editor' && req.method === 'POST') {
    state.remoteChanged = true;
    return reply({ ok: true });
  }
  if (p === '/__fixture/template-editor') {
    res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
    res.end('<button onclick="fetch(location.href,{method:\'POST\'}).then(()=>window.close())">Сохранить выравнивание</button>');
    return true;
  }
  return false;
});

async function exercise(browser, width, previewMode = 'with-image') {
  const ctx = await browser.newContext({ viewport: { width, height: width < 700 ? 844 : 980 }, serviceWorkers: 'block' });
  await ctx.route('**/*', route => new URL(route.request().url()).origin === base ? route.continue() : route.abort());
  const page = await ctx.newPage();
  const errors = [];
  const diagnostics = [];
  page.on('console', msg => { if (msg.type() === 'error' || msg.type() === 'warn') diagnostics.push(msg.text()); });
  page.on('requestfailed', req => diagnostics.push(req.url() + ': ' + req.failure()?.errorText));
  page.on('pageerror', error => errors.push(error.message));
  page.setDefaultTimeout(12_000);
  const screenshot = async name => {
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    assert(overflow < 2, `Viewport overflow: ${overflow}`);
    const modal = page.getByRole('dialog');
    if (await modal.count()) {
      assert(await modal.evaluate(el => el.scrollWidth <= el.clientWidth + 1));
      const box = await modal.boundingBox();
      assert(box && box.x >= 0 && box.x + box.width <= width + 1);
    }
    await page.screenshot({ path: path.join(output, width + (previewMode === 'with-image' ? '-' : '-' + previewMode + '-') + name + '.png'), animations: 'disabled' });
  };
  site.reset();
  state = { previewMode, previewReads: 0, versions: [version(sourceId, 'active')], editOpened: false, remoteChanged: false, activations: 0, applies: 0,
    draft: { id: 863, order_id: 590, doc_type: 'contract', legal_entity_id: 8, document_template_id: 33,
      template_version_id: sourceId, internal_reference: 'doc_fixture', display_number: 'Черновик договора', date: now,
      created_at: now, status: 'draft', provider: 'native', artifacts: [{ id: 40, kind: 'source_docx', filename: 'Договор.docx' }] } };
  try {
    await page.goto(orderUrl);
    const docs = page.getByTestId('native-documents-workspace');
    const createForm = docs.getByTestId('native-document-create-form');
    await createForm.getByText('Шаблон и реквизиты').click();
    await docs.getByTestId('edit-selected-template').click();
    const modal = page.getByRole('dialog');
    await modal.getByText('КП · версия 1').waitFor();
    await modal.getByRole('button', { name: 'Вернуться к заказу' }).click();
    assert.equal(page.url(), orderUrl);
    assert(await docs.getByTestId('edit-selected-template').evaluate(el => document.activeElement === el));
    const editDraft = docs.getByTestId('edit-draft-template');
    await editDraft.scrollIntoViewIfNeeded();
    await screenshot('order');
    await editDraft.click();
    await modal.getByText(templateName + ' · версия 7').waitFor();
    await screenshot('template');
    const popupReady = page.waitForEvent('popup');
    await modal.getByRole('button', { name: 'Редактировать в Google Docs' }).click();
    const popup = await popupReady;
    await popup.getByRole('button', { name: 'Сохранить выравнивание' }).click();
    await page.bringToFront();
    const savedVersion = modal.getByTestId('apply-template-version');
    // Explicit sync is available if headless Chromium does not send OS focus events.
    if (!await savedVersion.isVisible()) await modal.getByRole('button', { name: 'Забрать изменения' }).click();
    await savedVersion.getByText(/Версия 8 станет основной/).waitFor();
    assert.equal(await modal.getByRole('combobox').count(), 0);
    assert.equal(state.activations, 0);
    await modal.getByRole('checkbox').check();
    await screenshot('apply');
    await modal.getByRole('button', { name: 'Применить и посмотреть черновик' }).click();
    const fullPdf = modal.getByRole('link', { name: 'Открыть весь PDF' });
    await fullPdf.waitFor();
    assert.equal(await fullPdf.evaluate(async el => (await (await fetch(el.href)).arrayBuffer()).byteLength), pdf.length);
    if (previewMode !== 'with-image') {
      await modal.getByText('Для просмотра откройте файл PDF.').waitFor();
      assert.equal(await modal.locator('img, iframe').count(), 0);
      assert((await modal.boundingBox()).height < 400, 'PDF fallback must not leave a blank pane');
    } else {
      const image = modal.getByRole('img', { name: 'Первая страница обновлённого черновика' });
      await image.waitFor();
      const ink = await image.evaluate(async el => {
        await el.decode();
        const canvas = document.createElement('canvas');
        canvas.width = el.naturalWidth; canvas.height = el.naturalHeight;
        const ctx = canvas.getContext('2d');
        ctx.drawImage(el, 0, 0);
        const data = ctx.getImageData(0, 0, canvas.width, Math.floor(canvas.height / 5)).data;
        let pixels = 0, sum = 0;
        for (let i = 0; i < data.length; i += 4) {
          if (data[i + 2] > data[i] + 50 && data[i + 2] > data[i + 1] + 30) {
            pixels++; sum += (i / 4) % canvas.width;
          }
        }
        return { pixels, headingCenter: sum / (pixels * canvas.width), shown: el.getBoundingClientRect().width };
      });
      assert(ink.shown > 240 && ink.pixels > 30 && ink.headingCenter > .65, JSON.stringify(ink));
    }
    assert.equal(state.previewReads, 1);
    assert.equal(state.activations, 1); assert.equal(state.applies, 1);
    await screenshot('preview');
    await modal.getByRole('button', { name: 'Вернуться к заказу' }).click();
    assert.equal(page.url(), orderUrl);
    assert(await editDraft.evaluate(el => document.activeElement === el), 'Focus must return to the same draft');
    assert.deepEqual(errors, []);
    assert.deepEqual(diagnostics.filter(line => /TypeError|ReferenceError|RangeError|SyntaxError/.test(line)), []);
    console.log(width + ' px: selected template, saved draft, external editor, activation, snapshot, preview and focus passed');
  } catch (error) {
    console.error('Browser errors', errors, diagnostics.slice(-16), 'location', page.url(), (await page.locator('main').allTextContents()).map(text => text.slice(0, 500)));
    await page.screenshot({ path: path.join(output, width + '-failure.png') }).catch(() => {});
    throw error;
  } finally {
    await ctx.close();
  }
}

(async () => {
  fs.mkdirSync(output, { recursive: true });
  await new Promise(resolve => site.server.listen(port, '127.0.0.1', resolve));
  let browser;
  try {
    browser = await chromium.launch({ headless: true,
      ...(process.env.KITLANE_CHROMIUM_PATH ? { executablePath: process.env.KITLANE_CHROMIUM_PATH } : {}) });
    const fixtureDocument = await browser.newPage();
    await fixtureDocument.setContent('<h1 style="text-align:right;color:#145dc0">Договор</h1><p>Синтетический черновик. Версия 8.</p>');
    pdf = await fixtureDocument.pdf({ format: 'A4', printBackground: true });
    firstPage = execFileSync('pdftoppm', ['-singlefile', '-scale-to', '1200', '-png', '-cropbox', '-'], { input: pdf, maxBuffer: 16 * 1024 * 1024 });
    await fixtureDocument.close();
    for (const width of [1440, 390, 320]) await exercise(browser, width);
    await exercise(browser, 390, 'pdf-only');
    await exercise(browser, 390, 'invalid-image');
  } finally {
    if (browser) await browser.close();
    site.server.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
