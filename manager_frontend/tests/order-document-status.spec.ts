import { effectScope, ref, type EffectScope } from 'vue';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { ManagerOrderDetailResponse, PaymentResponse } from '../src/client';
import { useOrderDocumentStatus } from '../src/composables/useOrderDocumentStatus';

const mailMock = vi.hoisted(() => ({
  listManagerOrderOutgoingEmails: vi.fn(),
}));
const documentMock = vi.hoisted(() => ({
  listManagerManagedOrderDocuments: vi.fn(),
}));

vi.mock('../src/client', () => ({ ManagerMailService: mailMock, ManagerDocumentSystemService: documentMock }));

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

  it('counts an issued CRM invoice in payment references and a sent CRM offer in follow-up', async () => {
    const order = ref({ id: 43, documents: [] } as ManagerOrderDetailResponse);
    const payments = ref([{
      id: 9, amount: 100, currency: 'BYN', comment: 'Оплата по счёту INV-43',
    }] as PaymentResponse[]);
    documentMock.listManagerManagedOrderDocuments.mockResolvedValue({ items: [
      { id: 4, provider: 'native', doc_type: 'invoice', status: 'issued', official_full_number: 'INV-43' },
      { id: 5, provider: 'native', doc_type: 'offer', status: 'sent' },
    ] });
    scope = effectScope();
    const status = scope.run(() => useOrderDocumentStatus({ order, payments }))!;
    await status.loadManagedDocuments(43);

    expect(status.missingReferencedInvoice.value).toBeNull();
    expect(status.sentDocumentTypes.value).toContain('offer');
    expect(status.managedDocuments.value).toHaveLength(2);
  });
});
