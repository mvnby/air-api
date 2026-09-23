import { computed, ref, type Ref } from 'vue';
import type { ManagedDocumentItem, ManagerOrderDetailResponse, OutgoingEmailResponse, PaymentResponse } from '../client';
import { ManagerDocumentSystemService, ManagerMailService } from '../client';

type UseOrderDocumentStatusOptions = {
  order: Readonly<Ref<ManagerOrderDetailResponse | null>>;
  payments: Readonly<Ref<PaymentResponse[]>>;
};

const normalizeDocumentIdentity = (value: unknown) => (
  String(value || '').toUpperCase().replace(/[^A-ZА-ЯЁ0-9]/g, '')
);

export const useOrderDocumentStatus = ({ order, payments }: UseOrderDocumentStatusOptions) => {
  const orderEmails = ref<OutgoingEmailResponse[]>([]);
  const managedDocuments = ref<ManagedDocumentItem[]>([]);
  const orderEmailsLoaded = ref(false);
  let orderEmailsRequestId = 0;
  let managedDocumentsRequestId = 0;
  const orderDocuments = computed(() => order.value?.documents || []);

  const documentEmailStatus = computed<'unknown' | 'none' | 'pending' | 'sent' | 'failed'>(() => {
    if (!orderEmailsLoaded.value) return 'unknown';
    const latest = [...orderEmails.value]
      .filter((email) => Boolean(email.attachments?.length))
      .sort((left, right) => Date.parse(right.created_at) - Date.parse(left.created_at))[0];
    if (!latest) return 'none';
    if (latest.status === 'sent') return 'sent';
    if (latest.status === 'pending') return 'pending';
    if (latest.status === 'failed') return 'failed';
    return 'none';
  });

  const sentDocumentTypes = computed(() => {
    const types = new Set<string>();
    for (const document of managedDocuments.value) {
      if (document.status === 'sent' || document.status === 'signed') types.add(document.doc_type);
    }
    const documentsByNumber = new Map(
      orderDocuments.value
        .filter((document) => document.number)
        .map((document) => [normalizeDocumentIdentity(document.number), document.doc_type]),
    );
    for (const email of orderEmails.value) {
      if (email.status !== 'sent') continue;
      for (const attachment of email.attachments || []) {
        const metadata = attachment as typeof attachment & {
          document_type?: string | null;
          document_number?: string | null;
        };
        if (metadata.document_type) {
          types.add(metadata.document_type);
          continue;
        }
        const filename = normalizeDocumentIdentity(metadata.document_number || metadata.filename);
        for (const [number, documentType] of documentsByNumber) {
          if (number && filename.includes(number)) {
            types.add(documentType);
            break;
          }
        }
      }
    }
    return [...types];
  });

  const missingReferencedInvoice = computed(() => {
    const invoiceNumbers = new Set(
      [
        ...orderDocuments.value.filter((document) => document.doc_type === 'invoice').map((document) => document.number),
        ...managedDocuments.value.filter((document) => document.doc_type === 'invoice' && !['void', 'replaced'].includes(document.status))
          .map((document) => document.official_full_number || document.official_number || document.display_number),
      ]
        .map(normalizeDocumentIdentity)
        .filter(Boolean),
    );
    for (const payment of payments.value) {
      const purpose = payment.bank_receipt?.payment_purpose || payment.comment || '';
      const match = purpose.match(/сч[её]т(?:у|а|ом|е)?\s*(?:№\s*)?([A-ZА-ЯЁ0-9][A-ZА-ЯЁ0-9/-]{2,})/iu);
      const referencedNumber = match?.[1]?.trim();
      if (referencedNumber && !invoiceNumbers.has(normalizeDocumentIdentity(referencedNumber))) {
        return referencedNumber;
      }
    }
    return null;
  });

  const resetOrderEmails = () => {
    orderEmailsRequestId += 1;
    managedDocumentsRequestId += 1;
    orderEmails.value = [];
    orderEmailsLoaded.value = false;
    managedDocuments.value = [];
  };

  const loadOrderEmails = async (orderId: number) => {
    const requestId = ++orderEmailsRequestId;
    try {
      const response = await ManagerMailService.listManagerOrderOutgoingEmails(orderId, 20);
      if (requestId !== orderEmailsRequestId || order.value?.id !== orderId) return;
      orderEmails.value = response.items || [];
      orderEmailsLoaded.value = true;
    } catch (error) {
      if (requestId !== orderEmailsRequestId) return;
      console.warn('Failed to load order email summary', error);
      orderEmails.value = [];
      orderEmailsLoaded.value = false;
    }
  };

  const loadManagedDocuments = async (orderId: number) => {
    const requestId = ++managedDocumentsRequestId;
    try {
      const response = await ManagerDocumentSystemService.listManagerManagedOrderDocuments(orderId);
      if (requestId !== managedDocumentsRequestId || order.value?.id !== orderId) return;
      managedDocuments.value = response.items.filter((item) => item.provider === 'native');
    } catch (error) {
      if (requestId !== managedDocumentsRequestId) return;
      console.warn('Failed to load managed order documents', error);
      managedDocuments.value = [];
    }
  };

  return {
    documentEmailStatus,
    loadOrderEmails,
    loadManagedDocuments,
    managedDocuments,
    missingReferencedInvoice,
    orderDocuments,
    resetOrderEmails,
    sentDocumentTypes,
  };
};
