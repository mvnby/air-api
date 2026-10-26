import { flushPromises, mount } from '@vue/test-utils';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  ManagerDocumentSystemService,
  ManagerMailService,
  type ManagerOrderDetailResponse,
} from '../src/client';
import DocumentSendModal from '../src/components/orders/DocumentSendModal.vue';
import { mailApi, type MailMessage } from '../src/services/mail-workspace-api';

const order = {
  id: 42,
  customer: {
    id: 11,
    name: 'ООО Климат',
    email: 'client@example.com',
  },
} as ManagerOrderDetailResponse;

beforeEach(() => {
  vi.spyOn(mailApi, 'suggest').mockRejectedValue(new Error('AI unavailable'));
  vi.spyOn(ManagerDocumentSystemService, 'listManagerDocumentLegalEntities').mockResolvedValue({ items: [] });
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('DocumentSendModal', () => {
  it('keeps an unfinished order letter as a shared draft without sending', async () => {
    vi.spyOn(ManagerMailService, 'composeManagerOrderEmail').mockResolvedValue({ template_key: 'request_requisites', template_options: [{ key: 'request_requisites', label: 'Запросить реквизиты', requires_documents: false }], subject: '', body_text: '', document_ids: [], document_labels: [], missing_requisites: [] });
    vi.spyOn(mailApi, 'accounts').mockResolvedValue({ items: [{ id: 'system', name: 'Компания', email: 'office@example.com', signature: '' }] });
    const createDraft = vi.spyOn(mailApi, 'createOrderDraft').mockResolvedValue({ id: 81, version: 1, status: 'draft', account_id: 'system', to: [], cc: [], bcc: [], subject: '', body_text: '', attachments: [], order_id: 42, customer_id: 11 } as unknown as MailMessage);
    const send = vi.spyOn(mailApi, 'send');
    const wrapper = mount(DocumentSendModal, { props: { modelValue: true, order: { ...order, customer: { ...order.customer!, email: '' } }, documents: [] }, attachTo: document.body });
    await flushPromises();
    const saveButton = Array.from(document.body.querySelectorAll('button')).find(item => item.textContent?.includes('Подготовить письмо'))!;
    saveButton.click();
    await flushPromises();
    expect(createDraft).toHaveBeenCalledWith(42, expect.objectContaining({ to_email: '', subject: '', body_text: null, template_key: 'request_requisites', document_ids: [] }), 'legacy', expect.any(String));
    expect(document.body.textContent).toContain('Черновик #81');
    expect(send).not.toHaveBeenCalled();
    wrapper.unmount();
  });

  it('creates a shared draft with frozen native document attachments before sending', async () => {
    vi.spyOn(ManagerDocumentSystemService, 'composeManagerNativeOrderEmail').mockResolvedValue({
      template_key: 'contract',
      template_options: [{ key: 'contract', label: 'Договор', requires_documents: true }],
      subject: 'Договор D-2026-12',
      body_text: 'Добрый день! Договор во вложении.',
      document_ids: [77],
      document_labels: ['Договор D-2026-12'],
      missing_requisites: [],
    });
    const nativeSend = vi.spyOn(ManagerDocumentSystemService, 'sendManagerNativeOrderEmail');
    const createDraft = vi.spyOn(mailApi, 'createOrderDraft').mockResolvedValue({ id: 80, version: 1, status: 'draft', account_id: 'system', to: ['client@example.com'], cc: [], bcc: [], subject: 'Договор D-2026-12', body_text: 'Договор во вложении.', attachments: [], order_id: 42, customer_id: 11 } as unknown as MailMessage);
    vi.spyOn(mailApi, 'accounts').mockResolvedValue({ items: [{ id: 'system', name: 'Компания', email: 'office@example.com', signature: '' }] });
    const mailSend = vi.spyOn(mailApi, 'send');
    const legacyCompose = vi.spyOn(ManagerMailService, 'composeManagerOrderEmail');
    const legacySend = vi.spyOn(ManagerMailService, 'sendManagerOrderEmail');
    const wrapper = mount(DocumentSendModal, {
      props: {
        modelValue: true,
        transport: 'native',
        order,
        documents: [{
          id: 77,
          doc_type: 'contract',
          display_number: 'D-2026-12',
          date: '2026-09-02',
        }],
      },
      attachTo: document.body,
    });

    await flushPromises();

    expect(ManagerDocumentSystemService.composeManagerNativeOrderEmail).toHaveBeenCalledWith(
      42,
      { document_ids: [77], template_key: 'auto', registration_certificate_id: null, legal_entity_id: null },
    );
    expect(ManagerDocumentSystemService.composeManagerNativeOrderEmail).toHaveBeenCalledTimes(1);
    expect(document.body.textContent).toContain('Договор D-2026-12');
    const sendButton = Array.from(document.body.querySelectorAll('button'))
      .find((button) => button.textContent?.includes('Подготовить письмо'));
    expect(sendButton).toBeDefined();
    sendButton!.click();
    await flushPromises();

    expect(createDraft).toHaveBeenCalledWith(
      42,
      expect.objectContaining({
        to_email: 'client@example.com',
        subject: '',
        body_text: null,
        template_key: 'auto',
        document_ids: [77],
      }),
      'native',
      expect.any(String),
    );
    expect(document.body.textContent).toContain('Черновик #80');
    expect(nativeSend).not.toHaveBeenCalled();
    expect(mailSend).not.toHaveBeenCalled();
    expect(legacyCompose).not.toHaveBeenCalled();
    expect(legacySend).not.toHaveBeenCalled();
    wrapper.unmount();
  });
  it('retries a lost create with the same key and blocks duplicate clicks', async () => {
    vi.spyOn(ManagerMailService, 'composeManagerOrderEmail').mockResolvedValue({ template_key: 'offer', template_options: [{ key: 'auto', label: 'Автоматически' }], subject: 'КП', body_text: 'КП', document_ids: [77], document_labels: [], missing_requisites: [] });
    vi.spyOn(mailApi, 'accounts').mockResolvedValue({ items: [] });
    const create = vi.spyOn(mailApi, 'createOrderDraft').mockRejectedValue(new TypeError('Connection lost'));
    const wrapper = mount(DocumentSendModal, { props: { modelValue: true, order, documents: [{ id: 77, doc_type: 'offer', date: '2026-10-26' }] }, attachTo: document.body });
    await flushPromises();
    const action = Array.from(document.body.querySelectorAll('button')).find(item => item.textContent?.includes('Подготовить письмо'))!;
    action.click(); action.click(); await flushPromises();
    expect(create).toHaveBeenCalledOnce();
    expect(document.body.querySelector<HTMLInputElement>('input[type=checkbox]')!.disabled).toBe(true);
    expect(document.body.textContent).toContain('Выбор зафиксирован');
    action.click(); await flushPromises();
    expect(create).toHaveBeenCalledTimes(2);
    expect(create.mock.calls[0]).toEqual(create.mock.calls[1]);
    wrapper.unmount();
  });

  it('uses edited selection with a new key after a definitive create rejection', async () => {
    vi.spyOn(ManagerMailService, 'composeManagerOrderEmail').mockResolvedValue({ template_key: 'offer', template_options: [{ key: 'auto', label: 'Автоматически' }], subject: 'КП', body_text: 'КП', document_ids: [77], document_labels: [], missing_requisites: [] });
    vi.spyOn(mailApi, 'accounts').mockResolvedValue({ items: [] });
    const create = vi.spyOn(mailApi, 'createOrderDraft').mockRejectedValue({ status: 400, message: 'Документ недоступен' });
    const wrapper = mount(DocumentSendModal, { props: { modelValue: true, order, documents: [{ id: 77, doc_type: 'offer', date: '2026-10-26' }, { id: 78, doc_type: 'offer', date: '2026-10-26' }] }, attachTo: document.body });
    await flushPromises();
    const action = () => Array.from(document.body.querySelectorAll('button')).find(item => item.textContent?.includes('Подготовить письмо'))!;
    action().click(); await flushPromises();
    const boxes = document.body.querySelectorAll<HTMLInputElement>('input[type=checkbox]');
    expect(boxes[0]!.disabled).toBe(false);
    boxes[1]!.click(); await flushPromises(); boxes[0]!.click(); await flushPromises();
    action().click(); await flushPromises();
    expect(create.mock.calls[0]![1].document_ids).toEqual([77]);
    expect(create.mock.calls[1]![1].document_ids).toEqual([78]);
    expect(create.mock.calls[0]![3]).not.toBe(create.mock.calls[1]![3]);
    wrapper.unmount();
  });

});
