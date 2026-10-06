import { effectScope } from 'vue';
import { DOMWrapper, flushPromises, mount } from '@vue/test-utils';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { OpenAPI } from '../src/client';
import { facsimileApi } from '../src/features/documents/integrations/facsimile-api';
import { useFacsimileEditor } from '../src/features/documents/composables/use-facsimile-editor';
import { canEditDocumentFacsimile, constrainStamp, pagePoint, type FacsimilePreview } from '../src/features/documents/model/facsimile-placement';
import FacsimilePdfEditor from '../src/features/documents/components/FacsimilePdfEditor.vue';

const preview: FacsimilePreview = {
  document_id: 77, source_checksum_sha256: 'checksum', signed_artifact_id: 'old-signed', can_save: true,
  pages: [{ page_number: 1, width_mm: 210, height_mm: 297 }, { page_number: 2, width_mm: 297, height_mm: 210 }],
  signature: { asset_id: 'signature-v2', width_px: 200, height_px: 100 },
  seal: { asset_id: 'seal-v3', width_px: 100, height_px: 100 },
  placement: { signature: { page_number: 1, x_mm: 20, y_mm: 100, width_mm: 40 }, seal: { page_number: 2, x_mm: 70, y_mm: 120, width_mm: 30 } },
};
const scopes: ReturnType<typeof effectScope>[] = [];
const wrappers: ReturnType<typeof mount>[] = [];
const session = () => { const scope = effectScope(); scopes.push(scope); return scope.run(() => useFacsimileEditor())!; };
const deferred = <T>() => {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => { resolve = done; });
  return { promise, resolve };
};
beforeEach(() => {
  vi.spyOn(facsimileApi, 'preview').mockResolvedValue(structuredClone(preview));
  vi.spyOn(facsimileApi, 'page').mockResolvedValue(new Blob(['page']));
  vi.spyOn(facsimileApi, 'asset').mockResolvedValue(new Blob(['stamp']));
  vi.spyOn(facsimileApi, 'save').mockResolvedValue({ id: 'new', kind: 'signed_pdf', filename: 'signed.pdf' });
  let count = 0;
  vi.stubGlobal('URL', class extends URL {
    static createObjectURL = vi.fn(() => `blob:preview-${++count}`);
    static revokeObjectURL = vi.fn();
  });
  Object.defineProperty(HTMLDialogElement.prototype, 'showModal', { configurable: true, value: vi.fn(function (this: HTMLDialogElement) { this.setAttribute('open', ''); }) });
});
afterEach(() => {
  wrappers.splice(0).forEach((wrapper) => wrapper.unmount()); scopes.splice(0).forEach((scope) => scope.stop());
  document.body.innerHTML = '';
  vi.restoreAllMocks(); vi.unstubAllGlobals();
});

describe('facsimile placement', () => {
  it('maps screen coordinates to the real page and keeps the stamp inside its bounds', () => {
    expect(pagePoint(310, 445, { left: 100, top: 148, width: 420, height: 594 }, preview.pages[0]!)).toEqual({ x_mm: 105, y_mm: 148.5 });
    expect(constrainStamp({ page_number: 99, x_mm: -3, y_mm: 290, width_mm: 400 }, preview.pages[0]!, preview.signature)).toEqual({ page_number: 1, x_mm: 0, y_mm: 192, width_mm: 210 });
  });
  it('allows issued edits and preserves existing sent or signed copies', () => {
    expect(canEditDocumentFacsimile({ status: 'issued', artifacts: [{ kind: 'signed_pdf' }] })).toBe(true);
    expect(canEditDocumentFacsimile({ status: 'sent', artifacts: [{ kind: 'signed_pdf' }] })).toBe(false);
    expect(canEditDocumentFacsimile({ status: 'signed', artifacts: [{ kind: 'signed_pdf' }] })).toBe(false);
    expect(canEditDocumentFacsimile({ status: 'signed', artifacts: [] })).toBe(true);
    expect(canEditDocumentFacsimile({ status: 'draft' })).toBe(false);
  });
  it('preserves independent pages and submits exact preview identities and placement', async () => {
    const editor = session(); await editor.open(77); await editor.setPage(2);
    editor.updateStamp('signature', { page_number: 2, x_mm: 250, y_mm: 190, width_mm: 40 });
    await editor.setPage(1); expect(editor.placement.value!.signature.page_number).toBe(2);
    expect(await editor.save()).toBe(true);
    expect(facsimileApi.save).toHaveBeenCalledWith(77, {
      source_checksum_sha256: 'checksum', expected_signed_artifact_id: 'old-signed',
      signature_asset_id: 'signature-v2', seal_asset_id: 'seal-v3',
      signature: { page_number: 2, x_mm: 250, y_mm: 190, width_mm: 40 }, seal: preview.placement.seal,
    }, expect.any(AbortSignal));
  });
  it('discards stale page and document loads, aborts requests and revokes URLs', async () => {
    const editor = session(); await editor.open(77);
    const original = editor.pageUrl.value;
    const late = deferred<Blob>(); vi.mocked(facsimileApi.page).mockReturnValueOnce(late.promise);
    const pending = editor.setPage(2); const signal = vi.mocked(facsimileApi.page).mock.calls.at(-1)![2];
    await editor.setPage(1); const current = editor.pageUrl.value;
    late.resolve(new Blob(['stale'])); await pending;
    expect(signal.aborted).toBe(true); expect(editor.pageUrl.value).toBe(current);
    const latePreview = deferred<FacsimilePreview>(); vi.mocked(facsimileApi.preview).mockReturnValueOnce(latePreview.promise);
    const opening = editor.open(88); editor.close(); latePreview.resolve({ ...preview, document_id: 88 }); await opening;
    expect(editor.preview.value).toBeNull();
    expect(URL.revokeObjectURL).toHaveBeenCalledWith(original); expect(URL.revokeObjectURL).toHaveBeenCalledWith(current);
    expect(URL.revokeObjectURL).toHaveBeenCalledTimes(4);
  });
  it('suppresses completion after closing during save', async () => {
    const editor = session(); await editor.open(77);
    const late = deferred<{ id: string; kind: string; filename: string }>(); vi.mocked(facsimileApi.save).mockReturnValue(late.promise);
    const saving = editor.save(); const signal = vi.mocked(facsimileApi.save).mock.calls[0]![2];
    editor.close(); late.resolve({ id: 'new', kind: 'signed_pdf', filename: 'signed.pdf' });
    expect(await saving).toBe(false); expect(signal.aborted).toBe(true); expect(URL.revokeObjectURL).toHaveBeenCalledTimes(3);
  });
  it('shows authorization failures and prevents saving', async () => {
    vi.mocked(facsimileApi.preview).mockRejectedValue(new Error('Нет доступа к документу'));
    const editor = session(); await editor.open(77);
    expect(editor.error.value).toBe('Нет доступа к документу'); expect(await editor.save()).toBe(false); expect(facsimileApi.save).not.toHaveBeenCalled();
  });
});

describe('visual editor', () => {
  it('reloads the full preview after a conflict and decodes assets on independent pages', async () => {
    const wrapper = mount(FacsimilePdfEditor, { props: { documentId: 77, title: 'Счёт № 1' }, attachTo: document.body });
    wrappers.push(wrapper); await flushPromises();
    const surface = new DOMWrapper(document.body);
    await surface.get('img[alt="Страница 1 PDF"]').trigger('load');
    for (const img of surface.findAll('.hidden img')) await img.trigger('load');
    expect(surface.get('[data-testid="save-facsimile"]').attributes('disabled')).toBeUndefined();
    vi.mocked(facsimileApi.save).mockRejectedValueOnce(new Error('Изображения изменились'));
    await surface.get('[data-testid="save-facsimile"]').trigger('click'); await flushPromises();
    expect(surface.get('[role="alert"]').text()).toContain('Изображения изменились');
    const refresh = surface.findAll('button').find((button) => button.text() === 'Обновить предпросмотр')!;
    await refresh.trigger('click'); await flushPromises();
    expect(facsimileApi.preview).toHaveBeenCalledTimes(2); expect(facsimileApi.asset).toHaveBeenCalledTimes(4);
    expect(surface.find('[role="alert"]').exists()).toBe(false);
    expect(surface.get('[data-testid="save-facsimile"]').attributes('disabled')).toBeDefined();
  });
  it('does not allow saving a preview that the server declares immutable', async () => {
    vi.mocked(facsimileApi.preview).mockResolvedValueOnce({ ...preview, can_save: false });
    const wrapper = mount(FacsimilePdfEditor, { props: { documentId: 77, title: 'Отправленный документ' }, attachTo: document.body });
    wrappers.push(wrapper); await flushPromises();
    const surface = new DOMWrapper(document.body);
    expect(surface.text()).toContain('доступно только для просмотра');
    expect(surface.get('[data-testid="save-facsimile"]').attributes('disabled')).toBeDefined();
    expect(surface.find('.stamp-resize').exists()).toBe(false);
  });
  it('drags with grab offset, resizes proportionally and places a stamp on another page', async () => {
    const wrapper = mount(FacsimilePdfEditor, { props: { documentId: 77, title: 'Счёт № 1' }, attachTo: document.body });
    wrappers.push(wrapper); await flushPromises();
    const surface = new DOMWrapper(document.body);
    const page = surface.get('[data-testid="facsimile-page"]');
    vi.spyOn(page.element, 'getBoundingClientRect').mockReturnValue({ left: 10, top: 20, width: 420, height: 594 } as DOMRect);
    await surface.get('img[alt="Страница 1 PDF"]').trigger('load');
    const stamp = surface.get('.stamp-image'); Object.assign(stamp.element, { setPointerCapture: vi.fn() });
    await stamp.trigger('pointerdown', { pointerId: 1, button: 0, clientX: 70, clientY: 230 });
    await stamp.trigger('pointermove', { pointerId: 1, clientX: 110, clientY: 250 }); await stamp.trigger('pointerup', { pointerId: 1 });
    expect(surface.get('.stamp').attributes('style')).toContain('left: 19.047619047619047%');
    const resize = surface.get('.stamp-resize'); Object.assign(resize.element, { setPointerCapture: vi.fn() });
    await resize.trigger('pointerdown', { pointerId: 2, button: 0, clientX: 170, clientY: 280 });
    await resize.trigger('pointermove', { pointerId: 2, clientX: 210, clientY: 300 }); await resize.trigger('pointerup', { pointerId: 2 });
    expect(surface.get('.stamp').attributes('style')).toContain('width: 28.57142857142857%');
    await surface.get('[aria-label="Следующая страница"]').trigger('click'); await flushPromises();
    await surface.get('img[alt="Страница 2 PDF"]').trigger('load');
    const landscape = surface.get('[data-testid="facsimile-page"]');
    vi.spyOn(landscape.element, 'getBoundingClientRect').mockReturnValue({ left: 0, top: 0, width: 594, height: 420 } as DOMRect);
    await landscape.trigger('click', { clientX: 200, clientY: 200 }); expect(surface.findAll('.stamp')).toHaveLength(2);
    await surface.get('img[alt="Подпись"]').trigger('load'); await surface.get('img[alt="Печать"]').trigger('load');
    await surface.get('[data-testid="save-facsimile"]').trigger('click'); await flushPromises();
    expect(facsimileApi.save).toHaveBeenCalledWith(77, expect.objectContaining({ signature: { page_number: 2, x_mm: 70, y_mm: 85, width_mm: 60 } }), expect.any(AbortSignal));
    expect(wrapper.emitted('saved')).toHaveLength(1);
  });
});

describe('private image transport', () => {
  it('uses auth and credentials and exposes structured errors', async () => {
    vi.mocked(facsimileApi.asset).mockRestore();
    const previous = { TOKEN: OpenAPI.TOKEN, BASE: OpenAPI.BASE, WITH_CREDENTIALS: OpenAPI.WITH_CREDENTIALS, CREDENTIALS: OpenAPI.CREDENTIALS };
    Object.assign(OpenAPI, { TOKEN: vi.fn(async () => 'private-token'), BASE: '/backend', WITH_CREDENTIALS: true, CREDENTIALS: 'include' });
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({ detail: { message: 'Нет доступа к изображению' } }), { status: 403 }));
    try {
      const signal = new AbortController().signal;
      await expect(facsimileApi.asset(77, 'signature/id', signal)).rejects.toThrow('Нет доступа к изображению');
      expect(fetch).toHaveBeenCalledWith('/backend/api/manager/document-system/documents/77/facsimile-preview/assets/signature%2Fid', expect.objectContaining({ credentials: 'include', signal, headers: { Authorization: 'Bearer private-token' } }));
    } finally { Object.assign(OpenAPI, previous); }
  });
});
