import { flushPromises, mount } from '@vue/test-utils';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ManagerDocumentSystemService, type ManagerOrderDetailResponse } from '../src/client';
import { managerSession } from '../src/services/manager-session';
import * as certificates from '../src/features/documents/registration-certificates';
import RegistrationCertificatePanel from '../src/features/documents/settings/RegistrationCertificatePanel.vue';
import DocumentSendModal from '../src/components/orders/DocumentSendModal.vue';
import { mailApi, type MailMessage } from '../src/services/mail-workspace-api';
const item = { id: 'a'.repeat(32), legal_entity_id: 7, filename: 'scan.png', mime_type: 'image/png', checksum_sha256: 'b'.repeat(64), size_bytes: 100, is_current: true, created_at: '2026-10-09T00:00:00Z' };
const wrappers: ReturnType<typeof mount>[] = [];
beforeEach(() => {
  managerSession.currentUserRole.value = 'owner';
  vi.spyOn(mailApi, 'suggest').mockRejectedValue(new Error('AI unavailable'));
  vi.spyOn(certificates, 'listCertificates').mockResolvedValue([item]);
  vi.spyOn(certificates, 'certificateRequest').mockResolvedValue(new Response('{}'));
  vi.spyOn(certificates, 'downloadCertificate').mockResolvedValue(undefined);
});
afterEach(() => { wrappers.splice(0).forEach((wrapper) => wrapper.unmount()); vi.restoreAllMocks(); managerSession.currentUserRole.value = ''; document.body.innerHTML = ''; });
describe('registration certificates', () => {
  it('shows the current scan and uploads only after choosing a file', async () => {
    const wrapper = mount(RegistrationCertificatePanel, { props: { legalEntityId: 7 } }); wrappers.push(wrapper); await flushPromises();
    expect(wrapper.text()).toContain('Текущая версия'); expect(wrapper.text()).toContain('scan.png');
    expect(certificates.certificateRequest).not.toHaveBeenCalled();
    const input = wrapper.find('input[type=file]'); Object.defineProperty(input.element, 'files', { value: [new File(['bytes'], 'new.png', { type: 'image/png' })] });
    await input.trigger('change'); await flushPromises();
    expect(certificates.certificateRequest).toHaveBeenCalledWith('/api/manager/document-system/legal-entities/7/registration-certificates', 'POST', expect.any(FormData));
    expect(certificates.listCertificates).toHaveBeenCalledTimes(2);
  });
  it('lets a manager download but hides upload and selection', async () => {
    managerSession.currentUserRole.value = 'manager'; const wrapper = mount(RegistrationCertificatePanel, { props: { legalEntityId: 7 } }); wrappers.push(wrapper); await flushPromises();
    expect(wrapper.find('input[type=file]').exists()).toBe(false); await wrapper.find('button').trigger('click'); await flushPromises();
    expect(certificates.downloadCertificate).toHaveBeenCalledWith(item);
  });
  const templateOptions = [
    { key: 'auto', label: 'Автоматически', requires_documents: true },
    { key: 'documents', label: 'Комплект документов', requires_documents: true },
    { key: 'request_requisites', label: 'Запросить реквизиты', requires_documents: false },
  ];
  async function certificateOnlyModal() {
    vi.spyOn(ManagerDocumentSystemService, 'listManagerDocumentLegalEntities').mockResolvedValue({ items: [{ id: 7, status: 'active', display_name: 'ИП Климат' }] } as never);
    const compose = vi.spyOn(ManagerDocumentSystemService, 'composeManagerNativeOrderEmail').mockImplementation(async (_orderId, payload) => ({
      template_key: payload.template_key === 'auto' ? 'documents' : payload.template_key || 'request_requisites',
      template_options: templateOptions,
      subject: payload.template_key === 'auto' ? 'Свидетельство о регистрации' : 'Запрос реквизитов',
      body_text: payload.template_key === 'auto' ? 'Направляем свидетельство во вложении.' : 'Просим сообщить реквизиты.',
      document_ids: [], document_labels: [], missing_requisites: [],
    }));
    const send = vi.spyOn(ManagerDocumentSystemService, 'sendManagerNativeOrderEmail').mockResolvedValue({} as never);
    vi.spyOn(mailApi, 'accounts').mockResolvedValue({ items: [{ id: 'system', name: 'ИП Климат', email: 'office@example.com', signature: '' }] });
    const createDraft = vi.spyOn(mailApi, 'createOrderDraft').mockImplementation(async (_orderId, payload): Promise<MailMessage> => ({
      id: 80, version: 1, status: 'draft', folder: 'drafts', account_id: 'system',
      sender_email: 'office@example.com', sender_name: 'ИП Климат',
      to: payload.to_email ? [payload.to_email] : [], cc: [], bcc: [],
      subject: payload.template_key === 'auto' ? 'Свидетельство о регистрации' : 'Запрос реквизитов',
      body_text: payload.template_key === 'auto' ? 'Направляем свидетельство во вложении.' : 'Просим сообщить реквизиты.',
      attachments: payload.registration_certificate_id ? [{ id: 900, filename: item.filename, mime_type: item.mime_type, size: item.size_bytes, sha256: item.checksum_sha256, available: true, download_url: '/api/manager/mail/drafts/80/attachments/900' }] : [],
      order_id: 42, customer_id: null, manager_url: '/manager/mail?emailId=80',
      created_at: item.created_at, updated_at: item.created_at, sent_at: null, error: null,
      confirmed_version: null,
    }));
    const mailSend = vi.spyOn(mailApi, 'send');
    const wrapper = mount(DocumentSendModal, { props: { modelValue: false, transport: 'native', order: { id: 42, customer: { email: 'client@example.com' } } as ManagerOrderDetailResponse, documents: [] }, attachTo: document.body }); wrappers.push(wrapper);
    await wrapper.setProps({ modelValue: true }); await flushPromises();
    const select = document.body.querySelectorAll('select')[1] as HTMLSelectElement;
    const templateSelect = document.body.querySelectorAll('select')[0] as HTMLSelectElement;
    async function chooseCertificate(id: string) {
      select.value = id; select.dispatchEvent(new Event('change', { bubbles: true })); await flushPromises();
    }
    return { compose, send, createDraft, mailSend, templateSelect, chooseCertificate };
  }
  it('automatically composes a certificate-only draft and retains its private file in the shared editor', async () => {
    const { compose, send, createDraft, mailSend, templateSelect, chooseCertificate } = await certificateOnlyModal();
    expect(templateSelect.value).toBe('request_requisites'); expect(send).not.toHaveBeenCalled();
    expect(compose).toHaveBeenCalledTimes(1);
    await chooseCertificate(item.id);
    expect(templateSelect.value).toBe('auto');
    expect(compose).toHaveBeenCalledTimes(2);
    expect(compose).toHaveBeenLastCalledWith(42, expect.objectContaining({ document_ids: [], registration_certificate_id: item.id, legal_entity_id: 7, template_key: 'auto' }));
    expect(document.body.querySelector('textarea')).toBeNull();
    const button = Array.from(document.body.querySelectorAll('button')).find((button) => button.textContent?.includes('Подготовить письмо'));
    expect(button).toBeDefined(); expect(button!.disabled).toBe(false); button!.click(); await flushPromises();
    expect(createDraft).toHaveBeenCalledWith(42, expect.objectContaining({ to_email: 'client@example.com', document_ids: [], registration_certificate_id: item.id, legal_entity_id: 7, template_key: 'auto', subject: '', body_text: null }), 'native', expect.any(String));
    const editor = document.body.querySelector('[aria-label="Редактор черновика"]');
    expect(editor?.textContent).toContain('Черновик #80');
    expect(editor?.textContent).toContain('scan.png');
    expect((editor?.querySelector('input[aria-label="Тема"]') as HTMLInputElement)?.value).toBe('Свидетельство о регистрации');
    expect((editor?.querySelector('textarea[aria-label="Текст"]') as HTMLTextAreaElement)?.value).toBe('Направляем свидетельство во вложении.');
    expect(send).not.toHaveBeenCalled();
    expect(mailSend).not.toHaveBeenCalled();
  });
  it('returns to the requisites template when removing the certificate before the single editor opens', async () => {
    const { compose, templateSelect, chooseCertificate } = await certificateOnlyModal();
    await chooseCertificate(item.id);
    await chooseCertificate('');
    expect(templateSelect.value).toBe('request_requisites'); expect(compose).toHaveBeenCalledTimes(3);
    expect(document.body.querySelector('textarea')).toBeNull();
    await chooseCertificate(item.id);
    expect(templateSelect.value).toBe('auto');
    await chooseCertificate('');
    expect(templateSelect.value).toBe('request_requisites');
    const button = Array.from(document.body.querySelectorAll('button')).find(button => button.textContent?.includes('Подготовить письмо'))!;
    button.click(); await flushPromises();
    expect(document.body.querySelectorAll('textarea')).toHaveLength(1);
    expect(document.body.querySelector('textarea')?.value).toBe('Просим сообщить реквизиты.');
  });
  it('preserves an explicitly chosen requisites template when adding or removing the certificate', async () => {
    const { compose, templateSelect, chooseCertificate } = await certificateOnlyModal();
    templateSelect.value = 'request_requisites'; templateSelect.dispatchEvent(new Event('change', { bubbles: true })); await flushPromises();
    expect(compose).toHaveBeenCalledTimes(2);
    await chooseCertificate(item.id);
    expect(templateSelect.value).toBe('request_requisites'); expect(compose).toHaveBeenCalledTimes(3);
    expect(compose).toHaveBeenLastCalledWith(42, expect.objectContaining({ registration_certificate_id: item.id, template_key: 'request_requisites' }));
    expect(document.body.querySelector('textarea')).toBeNull();
    await chooseCertificate('');
    expect(templateSelect.value).toBe('request_requisites'); expect(compose).toHaveBeenCalledTimes(4);
  });
});
