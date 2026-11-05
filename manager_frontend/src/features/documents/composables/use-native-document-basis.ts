import { computed, ref, watch, type Ref } from 'vue';
import {
  ManagerContractsService,
  type DocumentLegalEntityItem,
  type ManagedDocumentItem,
  type ManagerCustomerContractItemResponse,
  type ManagerOrderDetailResponse,
  type ManagerOrderDocumentItem,
  type OrderCustomerContractBrief,
} from '../../../client';
import { managerSession } from '../../../services/manager-session';
import { getApiErrorMessage } from '../../../utils/api-errors';
import { documentTypeName, officialDocumentTitle } from '../model/native-document-options';

export const formatDocumentDate = (value: string | null | undefined) =>
  value ? value.slice(0, 10).split('-').reverse().join('.') : '—';

type RegisteredContract = OrderCustomerContractBrief & Pick<ManagerCustomerContractItemResponse, 'source_document_id'>;

type BasisOption = {
  value: string;
  label: string;
  documentId?: number;
  contract?: RegisteredContract;
  isContract: boolean;
};

type BasisInput = {
  order: () => ManagerOrderDetailResponse;
  documents: Ref<ManagedDocumentItem[]>;
  orderDocuments: Ref<ManagerOrderDocumentItem[]>;
  documentType: Ref<string>;
  issueDate: Ref<string>;
  legalEntityId: Ref<number | null>;
  legalEntities: Ref<DocumentLegalEntityItem[]>;
  baseDocumentId: Ref<number | null>;
  baseCustomerContractId: Ref<number | null>;
};

export function useNativeDocumentBasis(input: BasisInput) {
  const required = computed(() => ['act', 'tn2', 'ttn1'].includes(input.documentType.value));
  const supported = computed(() => required.value || input.documentType.value === 'invoice');
  const contracts = ref<RegisteredContract[]>([]);
  const loading = ref(false);
  const loadError = ref('');
  const chosen = ref('');
  const registered = ref('');
  const retry = ref(0);
  const customerId = computed(() => input.order().customer?.id);

  watch([
    customerId, () => input.order().id, input.legalEntityId, () => managerSession.auth.value?.tenant_id,
    () => managerSession.auth.value?.storefront_id,
  ], () => { chosen.value = ''; registered.value = ''; }, { flush: 'sync' });

  watch([
    supported, customerId, () => managerSession.auth.value?.tenant_id,
    () => managerSession.auth.value?.storefront_id, retry,
  ], async ([enabled, id], _previous, onCleanup) => {
    let current = true;
    onCleanup(() => { current = false; });
    contracts.value = [];
    loadError.value = '';
    loading.value = Boolean(enabled && id && input.order().customer?.type !== 'individual');
    if (!loading.value || !id) return;
    try {
      const response = await ManagerContractsService.getManagerCustomerContracts(id);
      if (current) contracts.value = response.items;
    } catch (error) {
      if (current) loadError.value = getApiErrorMessage(error);
    } finally {
      if (current) loading.value = false;
    }
  }, { immediate: true });

  const registeredContracts = computed(() => {
    const linked = input.order().customer_contract;
    const byId = new Map<number, RegisteredContract>();
    if (linked && linked.customer_id === customerId.value) byId.set(linked.id, linked);
    for (const contract of contracts.value) {
      if (contract.customer_id === customerId.value) byId.set(contract.id, contract);
    }
    return [...byId.values()];
  });
  const inTerm = computed(() => {
    const date = input.issueDate.value;
    return registeredContracts.value.filter(contract => contract.status === 'active' && Boolean(date)
      && date >= contract.valid_from.slice(0, 10) && date <= contract.valid_until.slice(0, 10));
  });
  const multipleIssuers = computed(() => input.legalEntities.value.filter(item => item.status === 'active').length > 1);
  const missingIssuer = computed(() => multipleIssuers.value ? inTerm.value.filter(contract => !contract.legal_entity_id) : []);
  const options = computed<BasisOption[]>(() => {
    const result: BasisOption[] = [];
    const sourceIds = new Set(registeredContracts.value.map(item => item.source_document_id).filter(id => id != null));
    for (const contract of inTerm.value) {
      if (contract.legal_entity_id ? contract.legal_entity_id !== input.legalEntityId.value : multipleIssuers.value) continue;
      result.push({
        value: `customer-contract:${contract.id}`, contract, isContract: true,
        label: `Открытый договор № ${contract.number} · ${formatDocumentDate(contract.valid_from)}–${formatDocumentDate(contract.valid_until)}`,
      });
    }
    const nativeIds = new Set(input.documents.value.map((item) => item.id));
    for (const item of input.documents.value) {
      if (sourceIds.has(item.id) || (item.legal_entity_id && item.legal_entity_id !== input.legalEntityId.value)) continue;
      if (!['issued', 'sent', 'signed'].includes(item.status)) continue;
      if (!['contract', 'offer'].includes(item.doc_type) && !(item.doc_type === 'invoice' && item.business_role === 'offer')) continue;
      result.push({
        value: `document:${item.id}`, documentId: item.id, isContract: item.doc_type === 'contract',
        label: `${officialDocumentTitle(item)} от ${formatDocumentDate(item.official_date || item.date)}`,
      });
    }
    for (const item of input.orderDocuments.value) {
      if (nativeIds.has(item.id) || sourceIds.has(item.id) || !['contract', 'offer'].includes(item.doc_type)) continue;
      result.push({
        value: `document:${item.id}`, documentId: item.id, isContract: item.doc_type === 'contract',
        label: `${documentTypeName(item.doc_type)} № ${item.number} от ${formatDocumentDate(item.date)}`,
      });
    }
    const priority = (item: BasisOption) => item.contract ? 0 : item.isContract ? 1 : 2;
    return result.sort((a, b) => priority(a) - priority(b) ||
      (a.isContract && b.isContract ? (b.documentId || 0) - (a.documentId || 0) : 0));
  });

  const selected = computed(() => {
    if (!supported.value) return undefined;
    const items = options.value;
    if (chosen.value) return items.find((item) => item.value === chosen.value);
    const previous = items.find((item) => item.value === registered.value)
      || items.find((item) => item.contract && item.contract.id === input.order().customer_contract_id);
    if (previous) return previous;
    // Losing eligibility must not silently replace the order's agreed contract.
    if (input.order().customer_contract_id || missingIssuer.value.length) return undefined;
    // With a choice between an unbound customer contract and another basis, let the manager decide.
    if (items.length > 1 && items.some((item) => item.contract)) return undefined;
    return items[0];
  });
  const value = computed({
    get: () => selected.value?.value || '',
    set: (next: string) => { chosen.value = next; },
  });
  watch(selected, (item) => {
    input.baseDocumentId.value = item?.documentId || null;
    input.baseCustomerContractId.value = item?.contract?.id || null;
  }, { immediate: true, flush: 'sync' });

  return {
    required, supported, options, selected, value, loading, loadError, missingIssuer,
    reload: () => { retry.value++; },
    preferRegistered: (id: number) => { registered.value = `document:${id}`; chosen.value = ''; },
  };
}
