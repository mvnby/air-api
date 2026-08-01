import { effectScope, ref, type EffectScope } from 'vue';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { ManagerOrderDetailResponse, PaymentResponse } from '../src/client';
import { useOrderDocumentStatus } from '../src/composables/useOrderDocumentStatus';

const mailMock = vi.hoisted(() => ({
  listManagerOrderOutgoingEmails: vi.fn(),
}));

vi.mock('../src/client', () => ({ ManagerMailService: mailMock }));

let scope: EffectScope;

afterEach(() => {
  scope?.stop();
  vi.clearAllMocks();
});

describe('useOrderDocumentStatus', () => {
  it('derives sent document types and detects a payment referencing an absent invoice', async () => {
    const order = ref({
      id: 42,
      documents: [{ id: 1, doc_type: 'invoice', number: 'INV-1' }],
    } as ManagerOrderDetailResponse);
    const payments = ref([{
      id: 8,
      amount: 100,
      currency: 'BYN',
      comment: 'Оплата по счету ABC-2',
    }] as PaymentResponse[]);
    mailMock.listManagerOrderOutgoingEmails.mockResolvedValue({
      items: [{
        id: 9,
        status: 'sent',
        created_at: '2026-07-31T10:00:00Z',
        attachments: [{ filename: 'invoice-INV-1.pdf' }],
      }],
    });
    scope = effectScope();
    const status = scope.run(() => useOrderDocumentStatus({ order, payments }))!;

    await status.loadOrderEmails(42);

    expect(status.documentEmailStatus.value).toBe('sent');
    expect(status.sentDocumentTypes.value).toEqual(['invoice']);
    expect(status.missingReferencedInvoice.value).toBe('ABC-2');
  });
});
