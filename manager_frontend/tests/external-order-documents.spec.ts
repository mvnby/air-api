import { flushPromises, mount, type VueWrapper } from '@vue/test-utils';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import ExternalOrderDocuments from '../src/features/documents/components/ExternalOrderDocuments.vue';
import { externalOrderDocumentsApi as api, type OrderDocumentWithEvidence } from '../src/features/documents/integrations/external-order-documents-api';

const now = '2026-11-20T09:00:00Z';
const sites = [{ id: 10, title: 'Объект A', address: 'Адрес A' }, { id: 20, title: 'Объект B', address: 'Адрес B' }];
const evidence = (id: number, doc_type: string, scope_meta: Record<string, unknown> = {}): OrderDocumentWithEvidence => ({
  id, doc_type, number: `ВН-${id}`, date: now, scope_meta, origin: 'external_upload', external_status: 'received', file_version: 1,
  external_files: [{ version: 1, role: 'original', filename: `Исходник-${id}.pdf`, mime_type: 'application/pdf', size_bytes: 200, checksum_sha256: 'a'.repeat(64), uploaded_at: now, uploaded_by: 'Менеджер' }],
});
const wrappers: VueWrapper[] = [];
const select = (wrapper: VueWrapper, id: string) => wrapper.get(`[data-testid="${id}"]`);
const showWorkspace = (canImport = true, canWrite = true) => {
  const wrapper = mount(ExternalOrderDocuments, { props: { orderId: 42, proposalId: 11, scopeKey: '1:1', canImport, canWrite } });
  wrappers.push(wrapper);
  return wrapper;
};
const chooseFile = async (wrapper: VueWrapper, id: string, file: File) => {
  const field = select(wrapper, id);
  Object.defineProperty(field.element, 'files', { value: [file], configurable: true });
  await field.trigger('change');
};

beforeEach(() => {
  window.history.replaceState({}, '', '/manager/orders/42?section=documents');
  vi.spyOn(api, 'list').mockResolvedValue({ items: [] });
  vi.spyOn(api, 'sites').mockResolvedValue({ items: sites });
  vi.spyOn(api, 'equipment').mockImplementation(async (_orderId, id) => ({
    items: [{ equipment_id: id + 1, equipment: { display_name: `Кондиционер ${id}`, serial: null } }],
  }));
});
afterEach(() => {
  for (const wrapper of wrappers.splice(0)) wrapper.unmount();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe('External order evidence', () => {
  it('filters external documents by site and includes its common act', async () => {
    vi.mocked(api.list).mockResolvedValue({ items: [evidence(1, 'defect_act', { site_id: 10 }), evidence(2, 'technical_inspection_act', { site_id: 20 }), evidence(3, 'act', { site_ids: [10, 20] }), evidence(4, 'contract')] });
    const wrapper = showWorkspace();
    await flushPromises();
    expect(wrapper.findAll('article')).toHaveLength(4);
    await select(wrapper, 'external-document-site-filter').setValue('20');
    expect(wrapper.findAll('article').map(node => node.attributes('data-testid'))).toEqual(['external-document-2', 'external-document-3']);
    expect(wrapper.emitted('siteFilter')).toEqual([[20]]);
  });

  it('opens a scoped import and retries its Word upload with the same key', async () => {
    window.history.replaceState({}, '', '/manager/orders/42?section=documents&action=uploadExternalDocument&documentType=defect_act');
    vi.mocked(api.list).mockResolvedValue({ items: [evidence(4, 'contract')] });
    const word = new File(['fixture evidence'], 'Дефект.docx', { type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' });
    const upload = vi.spyOn(api, 'upload').mockRejectedValueOnce(new Error('Повторите запрос')).mockResolvedValueOnce(evidence(7, 'defect_act', { site_id: 20 }));
    const wrapper = showWorkspace();
    await flushPromises();
    expect((select(wrapper, 'external-document-type').element as HTMLSelectElement).value).toBe('defect_act');
    await select(wrapper, 'external-document-number').setValue('ДА-10');
    await select(wrapper, 'external-document-date').setValue('2026-11-20');
    await select(wrapper, 'external-document-site').setValue('10');
    await flushPromises();
    await select(wrapper, 'external-equipment-11').setValue(true);
    await select(wrapper, 'external-document-site').setValue('20');
    await flushPromises();
    expect(wrapper.find('[data-testid="external-equipment-11"]').exists()).toBe(false);
    await select(wrapper, 'external-equipment-21').setValue(true);
    await select(wrapper, 'external-document-basis').setValue('4');
    await chooseFile(wrapper, 'external-document-file', word);
    await select(wrapper, 'external-document-import-form').trigger('submit');
    await flushPromises();
    expect(wrapper.text()).toContain('Повторите запрос');
    expect(wrapper.emitted('refresh')).toBeUndefined();
    await select(wrapper, 'external-document-import-form').trigger('submit');
    await flushPromises();
    expect(upload).toHaveBeenCalledWith(42, {
      document_type: 'defect_act', number: 'ДА-10', document_date: '2026-11-20', external_status: 'received',
      site_id: 20, equipment_ids: [21], base_document_id: 4, proposal_id: 11, file: word,
    }, expect.any(String));
    expect(upload.mock.calls[0]?.[2]).toBe(upload.mock.calls[1]?.[2]);
    expect(select(wrapper, 'external-document-7').exists()).toBe(true);
  });

  it('requires an original to register a signed contract', async () => {
    const upload = vi.spyOn(api, 'upload');
    const wrapper = showWorkspace();
    await flushPromises();
    await select(wrapper, 'open-external-document-import').trigger('click');
    await select(wrapper, 'external-document-number').setValue('Д-10');
    await select(wrapper, 'external-document-status').setValue('signed');
    await select(wrapper, 'external-document-import-form').trigger('submit');
    expect(wrapper.text()).toContain('Выберите исходный файл.');
    expect(upload).not.toHaveBeenCalled();
  });

  it('attaches a signed PDF from a closed-order deep link, keeping the original', async () => {
    window.history.replaceState({}, '', '/manager/orders/42?section=documents&action=attachExternalDocument&documentId=5&fileRole=signed_copy');
    const current = evidence(5, 'act');
    vi.mocked(api.list).mockResolvedValue({ items: [current] });
    const attach = vi.spyOn(api, 'attach').mockResolvedValue({ ...current, file_version: 2, external_files: [
      { ...current.external_files![0]!, version: 2, role: 'signed_copy', filename: 'Подписано.pdf' }, ...current.external_files!,
    ] });
    const wrapper = showWorkspace(false, true);
    await flushPromises();
    expect(wrapper.find('[data-testid="open-external-document-import"]').exists()).toBe(false);
    expect(wrapper.find('[data-testid="replace-external-original-5"]').exists()).toBe(false);
    expect((select(wrapper, 'external-attach-document').element as HTMLSelectElement).value).toBe('5');
    const signed = new File(['signed PDF fixture'], 'Подписано.pdf', { type: 'application/pdf' });
    await chooseFile(wrapper, 'external-attach-file', signed);
    await select(wrapper, 'external-document-attach-form').trigger('submit');
    await flushPromises();
    expect(attach).toHaveBeenCalledWith(5, 'signed_copy', 1, signed, expect.any(String));
    expect(select(wrapper, 'download-external-file-5-1').exists()).toBe(true);
    expect(select(wrapper, 'download-external-file-5-2').exists()).toBe(true);
  });

  it('previews only the requested version through a private image URL', async () => {
    vi.mocked(api.list).mockResolvedValue({ items: [evidence(5, 'act')] });
    const file = vi.spyOn(api, 'file').mockResolvedValue(new Blob(['test'], { type: 'image/png' }));
    const revoke = vi.fn();
    vi.stubGlobal('URL', class extends URL {
      static createObjectURL() { return 'blob:private-preview'; }
      static revokeObjectURL = revoke;
    });
    const wrapper = showWorkspace(false, false);
    await flushPromises();
    expect(wrapper.find('[data-testid="open-signed-document-attachment"]').exists()).toBe(false);
    await select(wrapper, 'preview-external-file-5-1').trigger('click');
    await flushPromises();
    expect(file).toHaveBeenCalledWith(5, 1, expect.anything(), 1);
    expect(select(wrapper, 'external-pdf-preview').get('img').attributes('src')).toBe('blob:private-preview');
    await select(wrapper, 'external-pdf-preview').findAll('button').find(button => button.text() === 'Закрыть')!.trigger('click');
    expect(revoke).toHaveBeenCalledWith('blob:private-preview');
  });
});
