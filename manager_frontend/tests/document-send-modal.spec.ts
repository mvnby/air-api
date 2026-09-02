import { flushPromises, mount } from '@vue/test-utils';
import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  ManagerDocumentSystemService,
  ManagerMailService,
  type ManagerOrderDetailResponse,
} from '../src/client';
import DocumentSendModal from '../src/components/orders/DocumentSendModal.vue';

const order = {
  id: 42,
  customer: {
    id: 11,
    name: 'ООО Климат',
    email: 'client@example.com',
  },
} as ManagerOrderDetailResponse;

afterEach(() => {
  vi.restoreAllMocks();
});

describe('DocumentSendModal', () => {
  it('composes and sends managed documents through the native endpoints', async () => {
    vi.spyOn(ManagerDocumentSystemService, 'composeManagerNativeOrderEmail').mockResolvedValue({
      template_key: 'contract',
      template_options: [{ key: 'contract', label: 'Договор', requires_documents: true }],
      subject: 'Договор D-2026-12',
      body_text: 'Добрый день! Договор во вложении.',
      document_ids: [77],
      document_labels: ['Договор D-2026-12'],
      missing_requisites: [],
    });
    vi.spyOn(ManagerDocumentSystemService, 'sendManagerNativeOrderEmail').mockResolvedValue({} as never);
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

    await wrapper.setProps({ modelValue: false });
    await wrapper.setProps({ modelValue: true });
    await flushPromises();

    expect(ManagerDocumentSystemService.composeManagerNativeOrderEmail).toHaveBeenCalledWith(
      42,
      { document_ids: [77], template_key: 'auto' },
    );
    expect(ManagerDocumentSystemService.composeManagerNativeOrderEmail).toHaveBeenCalledTimes(1);
    expect(document.body.textContent).toContain('Договор D-2026-12');
    const sendButton = Array.from(document.body.querySelectorAll('button'))
      .find((button) => button.textContent?.includes('Отправить'));
    expect(sendButton).toBeDefined();
    sendButton!.click();
    await flushPromises();

    expect(ManagerDocumentSystemService.sendManagerNativeOrderEmail).toHaveBeenCalledWith(
      42,
      expect.objectContaining({
        to_email: 'client@example.com',
        subject: 'Договор D-2026-12',
        document_ids: [77],
      }),
    );
    expect(legacyCompose).not.toHaveBeenCalled();
    expect(legacySend).not.toHaveBeenCalled();
    wrapper.unmount();
  });
});
