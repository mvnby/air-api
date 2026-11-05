import { DOMWrapper, flushPromises, mount } from '@vue/test-utils';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ManagerDocumentSystemService as Documents, type NativeTemplateVersionItem } from '../src/client';
import OrderTemplateEditor from '../src/features/documents/components/OrderTemplateEditor.vue';
import { googleDocumentEditorApi } from '../src/features/documents/integrations/google-document-editor-api';
import { fetchDraftPreviewWithPage } from '../src/features/documents/integrations/native-document-preview';

vi.mock('../src/features/documents/integrations/native-document-preview', () => ({ fetchDraftPreviewWithPage: vi.fn() }));
const version = (id: number, status: string): NativeTemplateVersionItem => ({
  id, version: id - 10, template_id: 24, renderer: 'docx', status,
  checksum_sha256: 'abc', placeholder_schema: {}, created_at: '', source_filename: 'Договор.docx',
});
const revision = 'a'.repeat(64);
const parameters = { revision, template_version_id: 11, has_editable_copy: false, issue_date: '2026-01-17', total_amount: '80' };
const props = { draftId: 1002, sourceVersionId: 11, templateId: 24, legalEntityId: 5, documentType: 'contract' };
const wrappers: ReturnType<typeof mount>[] = [];
const open = async () => {
  const wrapper = mount(OrderTemplateEditor, { props, attachTo: document.body });
  wrappers.push(wrapper);
  await flushPromises();
  return new DOMWrapper(document.body.querySelector('dialog')!);
};

beforeEach(() => {
  HTMLDialogElement.prototype.showModal = vi.fn();
  vi.clearAllMocks();
  vi.stubGlobal('URL', class extends URL {
    static createObjectURL = vi.fn(() => 'blob:http://localhost/preview');
    static revokeObjectURL = vi.fn();
  });
  vi.spyOn(googleDocumentEditorApi, 'getConnectionStatus').mockResolvedValue({ connected: false } as never);
  vi.spyOn(Documents, 'listManagerNativeDocumentTemplates').mockResolvedValue({ items: [{ id: 24, name: 'Договор поставки', is_active: true } as never] });
  vi.spyOn(Documents, 'listManagerNativeTemplateVersions').mockResolvedValue({ items: [version(11, 'active')] });
  vi.spyOn(Documents, 'getManagerManagedDocumentDraftParameters').mockResolvedValue(parameters);
  vi.spyOn(Documents, 'uploadManagerNativeTemplateVersion').mockResolvedValue(version(12, 'draft'));
  vi.spyOn(Documents, 'activateManagerNativeTemplateVersion').mockResolvedValue(version(12, 'active'));
  vi.spyOn(Documents, 'updateManagerManagedDocumentDraftParameters').mockResolvedValue({ id: 1002 } as never);
  vi.mocked(fetchDraftPreviewWithPage).mockResolvedValue({ pdf: new Blob(['%PDF-'], { type: 'application/pdf' }), firstPage: new Blob(['png'], { type: 'image/png' }) });
});
afterEach(() => {
  for (const wrapper of wrappers.splice(0)) wrapper.unmount();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});
describe('template editing from a draft', () => {
  it('opens its frozen version, activates the corrected upload and previews the very same draft', async () => {
    const wrapper = await open();
    expect(Documents.listManagerNativeTemplateVersions).toHaveBeenCalledWith(24, 5);
    expect(wrapper.text()).toContain('Договор поставки · версия 1');
    const input = wrapper.get<HTMLInputElement>('input[type=file]');
    const corrected = new File(['bytes'], 'Исправлен.docx');
    Object.defineProperty(input.element, 'files', { value: [corrected] });
    await input.trigger('change');
    await flushPromises();
    expect(Documents.uploadManagerNativeTemplateVersion).toHaveBeenCalledWith(24, { legal_entity_id: 5, file: corrected });
    await wrapper.get('button.editor-primary').trigger('click');
    await flushPromises();
    expect(Documents.activateManagerNativeTemplateVersion).toHaveBeenCalledWith(24, 12, 5, 11);
    expect(Documents.updateManagerManagedDocumentDraftParameters).toHaveBeenCalledWith(1002, {
      expected_revision: revision, template_version_id: 12, reset_editable_copy: false,
    });
    expect(fetchDraftPreviewWithPage).toHaveBeenCalledWith(1002);
    expect(wrapper.get('img[alt="Первая страница обновлённого черновика"]').attributes('src')).toContain('blob:');
    await wrapper.get('img').trigger('error');
    expect(wrapper.find('img').exists()).toBe(false);
    expect(wrapper.get('a').text()).toBe('Открыть весь PDF');
    expect(wrapper.get('a').attributes('href')).toContain('blob:');
  });

  it('uses the new template version returned by Google and keeps the order open when popups are blocked', async () => {
    vi.mocked(googleDocumentEditorApi.getConnectionStatus).mockResolvedValue({ connected: true } as never);
    const session = { id: 'template-11', edit_url: 'https://docs.google.com/edit', status: 'ready', can_edit: true } as const;
    vi.spyOn(googleDocumentEditorApi, 'getSession').mockResolvedValue(session as never);
    const sync = vi.spyOn(googleDocumentEditorApi, 'syncSession').mockResolvedValue({
      session: session as never, newTemplateVersionCreated: true, newTemplateVersion: version(13, 'draft'),
    });
    vi.spyOn(window, 'open').mockReturnValue(null);
    const wrapper = await open();
    const googleActions = wrapper.get('[data-testid="google-document-editor-actions"]');
    await googleActions.findAll('button')[0]!.trigger('click');
    await flushPromises();
    expect(wrapper.get('a[target=_blank]').attributes('href')).toBe(session.edit_url);
    await googleActions.findAll('button')[1]!.trigger('click');
    await flushPromises();
    expect(sync).toHaveBeenCalledWith({ kind: 'template-version', templateId: 24, legalEntityId: 5, versionId: 11 });
    expect(wrapper.get('[data-testid="apply-template-version"]').text()).toContain('Версия 3 станет основной');
    expect(wrapper.find('select').exists()).toBe(false);
    expect(Documents.activateManagerNativeTemplateVersion).not.toHaveBeenCalled();
  });

  it.each([false, true])('applies active version to a manual working copy only with consent (%s)', async (consent) => {
    vi.mocked(Documents.getManagerManagedDocumentDraftParameters).mockResolvedValue({ ...parameters, has_editable_copy: true });
    vi.mocked(Documents.listManagerNativeTemplateVersions).mockResolvedValue({ items: [version(12, 'active'), version(11, 'retired')] });
    const wrapper = await open();
    expect(wrapper.text()).toContain('версия 1');
    expect(wrapper.get('button.editor-primary').attributes('disabled')).toBeDefined();
    if (consent) await wrapper.get('input[type=checkbox]').setValue(true);
    await wrapper.get('button.editor-primary').trigger('click');
    await flushPromises();
    expect(Documents.activateManagerNativeTemplateVersion).not.toHaveBeenCalled();
    if (consent) expect(Documents.updateManagerManagedDocumentDraftParameters).toHaveBeenCalledWith(
      1002, { template_version_id: 12, expected_revision: revision, reset_editable_copy: true },
    );
    else expect(Documents.updateManagerManagedDocumentDraftParameters).not.toHaveBeenCalled();
  });

  it('shows a stale draft conflict without applying a copy or opening another document', async () => {
    vi.mocked(Documents.getManagerManagedDocumentDraftParameters).mockResolvedValue({ ...parameters, template_version_id: 15 });
    const wrapper = await open();
    expect(wrapper.get('[role=alert]').text()).toContain('другую версию');
    expect(wrapper.find('input[type=file]').exists()).toBe(false);
    expect(fetchDraftPreviewWithPage).not.toHaveBeenCalled();
  });
});
