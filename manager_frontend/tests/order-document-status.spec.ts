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
  it.each([['sending', 'sending'], ['unknown', 'uncertain']] as const)('keeps %s SMTP attempts distinct from unsent documents and unavailable history', async (mailStatus, expectedStatus) => {
    const order = ref({ id: 42, documents: [{ id: 1, doc_type: 'invoice', number: 'INV-1' }] } as ManagerOrderDetailResponse);
    mailMock.listManagerOrderOutgoingEmails.mockResolvedValue({ items: [
      { id: 10, status: 'draft', created_at: '2026-10-13T11:00:00Z', attachments: [{ filename: 'invoice-INV-1.pdf' }] },
      { id: 9, status: mailStatus, created_at: '2026-10-13T10:00:00Z', attachments: [{ filename: 'invoice-INV-1.pdf' }] },
    ] });
    scope = effectScope();
    const status = scope.run(() => useOrderDocumentStatus({ order, payments: ref([]) }))!;
    expect(status.documentEmailStatus.value).toBe('unknown');
    await status.loadOrderEmails(42);
    expect(status.documentEmailStatus.value).toBe(expectedStatus);
    expect(status.sentDocumentTypes.value).toEqual([]);
  });

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
  it('tracks sent and unknown mail only for the viewed proposal, including alternatives', async () => {
    const proposalId = ref<number | null>(25);
    const order = ref({ id: 42, documents: [
      { id: 1, proposal_id: 24, doc_type: 'invoice', number: 'INV-A' },
      { id: 2, proposal_id: 25, doc_type: 'offer', number: 'KP-B' },
    ] } as ManagerOrderDetailResponse);
    mailMock.listManagerOrderOutgoingEmails.mockResolvedValue({ items: [
      { id: 9, status: 'sent', created_at: '2026-10-26T11:00:00Z', attachments: [{ document_id: 1, document_type: 'invoice' }] },
      { id: 8, status: 'unknown', created_at: '2026-10-26T10:00:00Z', attachments: [{ document_id: 2, document_type: 'offer' }] },
    ] });
    scope = effectScope();
    const status = scope.run(() => useOrderDocumentStatus({ order, payments: ref([]), proposalId }))!;
    await status.loadOrderEmails(42);
    expect(status.documentEmailStatus.value).toBe('uncertain');
    expect(status.sentDocumentTypes.value).toEqual([]);
    proposalId.value = 24;
    expect(status.documentEmailStatus.value).toBe('sent');
    expect(status.sentDocumentTypes.value).toEqual(['invoice']);
  });

});
