<script setup lang="ts">
import { computed, provide, ref, watch } from 'vue';
import { ManagerContractsService, ManagerDocsService, ManagerOrdersService } from '../../client';
import type {
  DocumentTemplateItem,
  ManagerCustomerContractItemResponse,
  ManagerOrderDetailResponse,
  ManagerOrderDocumentItem,
  OrderProposalResponse,
  OrderServiceLineResponse,
} from '../../client';
import { getApiErrorMessage } from '../../utils/api-errors';
import { getOrderDocumentAccess } from './order-document-access';
import LegacyDocumentsShell from '../../features/documents/components/LegacyDocumentsShell.vue';
import { DocumentGenerationContextKey } from '../../features/documents/model/document-generation-context';
import { useDocumentFileActions } from '../../features/documents/composables/use-document-file-actions';
import { useExternalContractRegistration } from '../../features/documents/composables/use-external-contract-registration';
import { useActDocumentScope } from '../../features/documents/composables/use-act-document-scope';
import { useWaybillDocumentScope } from '../../features/documents/composables/use-waybill-document-scope';
import {
  BASE_DOCUMENT_TYPES,
  DATED_DOCUMENT_TYPES,
  DOCUMENT_FILE_ACCEPT,
  DOCUMENT_TYPES,
  OPEN_CONTRACT_PREFIX,
  ORDER_DOCUMENT_PREFIX,
} from '../../features/documents/model/document-constants';
import {
  documentTypeLabel,
  getRoleLabel,
  isClosingDocumentType,
  isWaybillType,
  normalizeRoleType,
} from '../../features/documents/model/document-formatters';
import type { BeforeGenerateResult, ToastType, WaybillProductLine } from '../../features/documents/model/document-types';

const props = defineProps<{
  order: ManagerOrderDetailResponse;
  activeProposalId?: number | null;
  productLines?: WaybillProductLine[];
  beforeGenerate?: (type: string) => BeforeGenerateResult | Promise<BeforeGenerateResult>;
}>();

const emit = defineEmits<{
  refresh: [];
  toast: [payload: { message: string; type?: ToastType }];
}>();
const documents = ref<ManagerOrderDocumentItem[]>([]);
const documentAccess = computed(() => getOrderDocumentAccess(props.order.status));
const canSendDocuments = computed(() => (
  documentAccess.value.canSend
  && (documentAccess.value.mode === 'active' || documents.value.length > 0)
));
const customerContracts = ref<ManagerCustomerContractItemResponse[]>([]);
const contractTemplates = ref<DocumentTemplateItem[]>([]);
const selectedCustomerContractId = ref<number | null>(props.order.customer_contract_id || null);
const selectedDocumentRoleType = ref<string | null>(props.order.document_role_type || null);
const selectedContractTemplateId = ref<string>('');
const selectedBaseDocumentValue = ref<string>('');
const additionalConditions = ref(props.order.additional_conditions || '');
const additionalConditionsSaved = ref(props.order.additional_conditions || '');
const documentDate = ref(new Date().toISOString().slice(0, 10));
const isGeneratingDoc = ref(false);
const processingDocId = ref<number | null>(null);
const isCreatePanelOpen = ref(false);
const showAdvancedSettings = ref(false);
const selectedDocumentType = ref('contract');
const showDocumentSendModal = ref(false);
const emailHistoryRefreshKey = ref(0);
const isUploadingDoc = ref(false);
const fileInputRef = ref<HTMLInputElement | null>(null);
const externalContractOpen = ref(false);
const externalContractNumber = ref('');
const externalContractDate = ref(new Date().toISOString().slice(0, 10));
const externalContractUrl = ref('');
const externalContractFile = ref<File | null>(null);
const isRegisteringExternalContract = ref(false);
let documentsRequestId = 0;
let contractTemplatesRequestId = 0;
let customerContractsRequestId = 0;

const notify = (message: string, type: ToastType = 'success') => {
  emit('toast', { message, type });
};

const isWaybillDocument = computed(() => isWaybillType(selectedDocumentType.value));
const selectedOrderProposal = computed(() => {
  const proposals = props.order.proposals || [];
  if (props.activeProposalId) {
    const byId = proposals.find((proposal) => proposal.id === props.activeProposalId && !proposal.is_archived);
    if (byId) return byId;
  }
  return proposals.find((proposal) => proposal.is_selected && !proposal.is_archived)
    || proposals.find((proposal) => !proposal.is_archived)
    || null;
});
const activeActServiceLines = computed<OrderServiceLineResponse[]>(() => {
  const proposal = selectedOrderProposal.value as OrderProposalResponse | null;
  if (proposal?.service_lines?.length) return proposal.service_lines;
  return props.order.service_lines || [];
});
const normalizeServiceSearchText = (value: unknown) => String(value || '').toLowerCase().replace(/ё/g, 'е');
const isMaintenanceServiceLine = (line: OrderServiceLineResponse) => {
  const category = normalizeServiceSearchText(line.service_category);
  const title = normalizeServiceSearchText(line.service_title);
  const titleWords = title.split(/[^a-zа-я0-9]+/u).filter(Boolean);
  return category === 'maintenance'
    || title.includes('техническое обслуживание')
    || title.includes('обслуживание')
    || titleWords.includes('то');
};
const hasMaintenanceServiceLines = computed(() => activeActServiceLines.value.some(isMaintenanceServiceLine));
const {
  address: actScopeAddress,
  createBranch: createActBranch,
  creatingBranch: creatingActBranch,
  customerBranches,
  loadBranches: loadCustomerBranches,
  maxQuantity: maxActServiceQuantity,
  newBranchAddress: newActBranchAddress,
  newBranchName: newActBranchName,
  onBranchChange: onActBranchChange,
  onCheckboxChange: onActServiceCheckboxChange,
  quantity: actServiceQuantity,
  reset: syncActScopeDefaults,
  selectAllServices: syncActServiceSelection,
  selectedBranchId: selectedActBranchId,
  selectedServiceLineIds: selectedActServiceLineIds,
  selectedServiceLines: selectedActServiceLines,
  setQuantity: setActServiceLineQuantity,
  title: actScopeTitle,
} = useActDocumentScope({
  order: () => props.order,
  activeServiceLines: activeActServiceLines,
  notify,
});
const {
  ensureComponents: ensureAllWaybillComponents,
  lines: waybillProductLines,
  proposalId: activeWaybillProposalId,
  save: saveWaybillProductLines,
  sync: syncWaybillProductLines,
} = useWaybillDocumentScope({
  order: () => props.order,
  productLines: () => props.productLines || [],
  selectedProposal: selectedOrderProposal,
  activeProposalId: () => props.activeProposalId ?? null,
  notify,
});

const isCompanyOrder = computed(() => props.order.customer?.type === 'company' || !!props.order.customer?.inn);
const oneTimeContractDocument = computed(() => (
  [...documents.value]
    .filter((doc) => doc.doc_type === 'contract')
    .sort((a, b) => b.id - a.id)[0] || null
));
const hasOrderContract = computed(() => !!oneTimeContractDocument.value);
const hasContract = computed(() => (isCompanyOrder.value ? !!selectedCustomerContractId.value : false) || hasOrderContract.value);
const hasOrderInvoice = computed(() => documents.value.some((doc) => doc.doc_type === 'invoice'));
const baseOrderDocuments = computed(() => (
  [...documents.value]
    .filter((doc) => BASE_DOCUMENT_TYPES.has(doc.doc_type))
    .sort((a, b) => b.id - a.id)
));
const baseDocumentOptions = computed(() => {
  const options: Array<{ value: string; label: string }> = [];
  for (const contract of customerContracts.value) {
    options.push({
      value: `${OPEN_CONTRACT_PREFIX}${contract.id}`,
      label: `Открытый договор · ${contract.number}`,
    });
  }
  for (const doc of baseOrderDocuments.value) {
    options.push({
      value: `${ORDER_DOCUMENT_PREFIX}${doc.id}`,
      label: `${documentTypeLabel(doc.doc_type)} · ${doc.number}`,
    });
  }
  return options;
});
const hasClosingBaseDocument = computed(() => baseDocumentOptions.value.length > 0);
const selectedContractTemplate = computed(() => contractTemplates.value.find((template) => template.id === selectedContractTemplateId.value) || null);
const selectedDocumentTypeItem = computed(() => DOCUMENT_TYPES.find((item) => item.type === selectedDocumentType.value) || DOCUMENT_TYPES[0]!);
const selectedOpenContract = computed(() => (
  customerContracts.value.find((contract) => contract.id === selectedCustomerContractId.value) || null
));
const inheritedDocumentRoleType = computed(() => normalizeRoleType(
  selectedDocumentRoleType.value
    || selectedOpenContract.value?.document_role_type
    || selectedContractTemplate.value?.document_role_type
    || props.order.effective_document_role_type
));
const documentSummary = computed(() => {
  const count = documents.value.length;
  if (!count) return 'Документов нет';
  const mod100 = count % 100;
  const mod10 = count % 10;
  const noun = mod100 >= 11 && mod100 <= 14 ? 'документов' : mod10 === 1 ? 'документ' : mod10 >= 2 && mod10 <= 4 ? 'документа' : 'документов';
  return `${count} ${noun}${hasContract.value ? '' : ' · договор не создан'}`;
});
const hasDocumentSetupWarning = computed(() => isCompanyOrder.value && !selectedCustomerContractId.value && !hasClosingBaseDocument.value);
const suggestedDocumentType = computed(() => {
  if (isCompanyOrder.value && hasClosingBaseDocument.value) return 'act';
  if (isCompanyOrder.value && !hasContract.value) return 'contract';
  if (isCompanyOrder.value && !hasOrderInvoice.value) return 'invoice';
  if ((props.order.product_lines || []).length) return 'retail_receipt';
  if (hasMaintenanceServiceLines.value) return 'maintenance_service_act';
  return 'service_act';
});
const needsContractBinding = computed(() => (
  isClosingDocumentType(selectedDocumentType.value)
));
const selectedTemplateLabel = computed(() => (
  selectedDocumentType.value === 'contract'
    ? (selectedContractTemplate.value?.name || 'Шаблон договора')
    : 'Оставить по шаблону'
));
const showsDocumentRoleControl = computed(() => selectedDocumentType.value !== 'tn2' && selectedDocumentType.value !== 'ttn1');
const showsAdditionalConditions = computed(() => (
  selectedDocumentType.value === 'contract'
  || selectedDocumentType.value === 'invoice'
  || selectedDocumentType.value === 'offer'
  || selectedDocumentType.value === 'retail_receipt'
  || selectedDocumentType.value === 'service_act'
  || selectedDocumentType.value === 'maintenance_service_act'
));
const additionalConditionsMode = computed(() => (selectedDocumentType.value === 'contract' ? 'contract' : 'invoice'));
const contractBindingLabel = computed(() => {
  if (selectedDocumentType.value === 'contract') return 'будет создан разовый договор заказа';
  if (selectedDocumentType.value === 'retail_receipt' || selectedDocumentType.value === 'service_act' || selectedDocumentType.value === 'maintenance_service_act') return 'публичная оферта';
  if (!needsContractBinding.value) return 'не требуется';
  return baseDocumentOptions.value.find((option) => option.value === selectedBaseDocumentValue.value)?.label || 'не выбран';
});
const roleChecklistLabel = computed(() => (
  selectedDocumentRoleType.value ? getRoleLabel(selectedDocumentRoleType.value) : 'Оставить по шаблону'
));
const createChecklist = computed(() => {
  const items = [
    { label: 'Тип', value: selectedDocumentTypeItem.value.label },
    { label: 'Дата', value: new Date(`${documentDate.value}T00:00:00`).toLocaleDateString('ru-RU') },
    { label: 'Шаблон', value: selectedTemplateLabel.value },
    { label: 'Основание', value: contractBindingLabel.value },
  ];
  if (selectedDocumentType.value === 'act') {
    items.push({
      label: 'Объект',
      value: [actScopeTitle.value.trim(), actScopeAddress.value.trim()].filter(Boolean).join(' · ') || 'адрес заказа',
    });
    items.push({
      label: 'Строки акта',
      value: selectedActServiceLines.value.length
        ? `${selectedActServiceLines.value.length} услуг`
        : 'все услуги предложения',
    });
  }
  if (showsAdditionalConditions.value) {
    items.push({ label: 'Условия', value: additionalConditions.value.trim() ? 'есть выбранные условия' : 'Оставить по шаблону' });
  }
  if (showsDocumentRoleControl.value) {
    items.push({ label: 'Роли', value: roleChecklistLabel.value });
  }
  return items;
});

const getDocumentDateForType = (type: string) => (
  DATED_DOCUMENT_TYPES.has(type) && documentDate.value ? `${documentDate.value}T00:00:00` : undefined
);
const normalizeBeforeGenerateResult = (result: BeforeGenerateResult) => {
  if (result === false) return { proceed: false, mutated: false };
  if (result && typeof result === 'object') {
    return {
      proceed: result.proceed !== false,
      mutated: result.mutated === true,
    };
  }
  return { proceed: true, mutated: false };
};

const isDocumentTypeLocked = (type: string) => (
  isClosingDocumentType(type) && !hasClosingBaseDocument.value
);
const lockedDocumentTitle = (type: string) => (
  isClosingDocumentType(type) ? 'Сначала создайте договор, счет или оферту' : ''
);

const syncBaseDocumentSelection = () => {
  if (!isClosingDocumentType(selectedDocumentType.value)) {
    selectedBaseDocumentValue.value = '';
    return;
  }
  const options = baseDocumentOptions.value;
  if (selectedBaseDocumentValue.value && options.some((option) => option.value === selectedBaseDocumentValue.value)) {
    return;
  }
  if (selectedCustomerContractId.value) {
    const openValue = `${OPEN_CONTRACT_PREFIX}${selectedCustomerContractId.value}`;
    if (options.some((option) => option.value === openValue)) {
      selectedBaseDocumentValue.value = openValue;
      return;
    }
  }
  selectedBaseDocumentValue.value = options.length === 1 ? options[0]!.value : '';
};

const selectedBaseDocumentBinding = computed({
  get: () => selectedBaseDocumentValue.value,
  set: (value: string) => {
    void updateBaseDocumentBinding(value);
  },
});

const selectedDocumentRoleBinding = computed({
  get: () => selectedDocumentRoleType.value || '',
  set: (value: string) => {
    void updateDocumentRoleBinding(value);
  },
});

const hasAdditionalConditionsChanges = computed(() => additionalConditions.value !== additionalConditionsSaved.value);

const loadDocuments = async () => {
  const requestId = ++documentsRequestId;
  const orderId = props.order.id;
  try {
    const res = await ManagerDocsService.getManagerOrderDocuments(orderId);
    if (requestId !== documentsRequestId || props.order.id !== orderId) return;
    documents.value = res.items;
    if (!isCreatePanelOpen.value) selectedDocumentType.value = suggestedDocumentType.value;
    syncBaseDocumentSelection();
  } catch (error) {
    console.error('Failed to load documents', error);
  }
};

const loadContractTemplates = async () => {
  const requestId = ++contractTemplatesRequestId;
  const orderId = props.order.id;
  try {
    const res = await ManagerDocsService.getDocTemplates('contract', orderId);
    if (requestId !== contractTemplatesRequestId || props.order.id !== orderId) return;
    contractTemplates.value = res.items.filter((template) => !template.is_open_contract);
    if (contractTemplates.value.length > 0 && contractTemplates.value[0]) {
      selectedContractTemplateId.value = contractTemplates.value[0].id;
    }
  } catch (error) {
    console.warn('Failed to load contract templates', error);
  }
};

const loadCustomerContracts = async () => {
  const requestId = ++customerContractsRequestId;
  const customerId = props.order.customer?.id;
  if (!customerId) {
    customerContracts.value = [];
    selectedCustomerContractId.value = null;
    syncBaseDocumentSelection();
    return;
  }
  try {
    const res = await ManagerContractsService.getManagerCustomerContracts(customerId);
    if (requestId !== customerContractsRequestId || props.order.customer?.id !== customerId) return;
    customerContracts.value = res.items.filter((contract) => contract.status === 'active');
    selectedCustomerContractId.value = props.order.customer_contract_id || null;
    syncBaseDocumentSelection();
  } catch (error) {
    console.error('Failed to load customer contracts', error);
  }
};

const resetFromOrder = () => {
  selectedCustomerContractId.value = props.order.customer_contract_id || null;
  selectedDocumentRoleType.value = props.order.document_role_type || null;
  additionalConditionsSaved.value = props.order.additional_conditions || '';
  additionalConditions.value = props.order.additional_conditions || '';
  syncActScopeDefaults();
};

watch(() => props.order.id, () => {
  resetFromOrder();
  waybillProductLines.value = [];
  selectedDocumentType.value = suggestedDocumentType.value;
  selectedBaseDocumentValue.value = '';
  isCreatePanelOpen.value = false;
  showAdvancedSettings.value = false;
  void loadDocuments();
  void loadContractTemplates();
  void loadCustomerContracts();
  void loadCustomerBranches();
}, { immediate: true });

watch(selectedDocumentType, () => {
  if (!showsAdditionalConditions.value) showAdvancedSettings.value = false;
  syncBaseDocumentSelection();
  if (selectedDocumentType.value === 'act' && selectedActServiceLineIds.value.length === 0) {
    syncActServiceSelection();
  }
});

watch(() => [
  props.order.customer_contract_id,
  props.order.document_role_type,
  props.order.additional_conditions,
], () => {
  resetFromOrder();
});

const useOneTimeContractForClosingDocs = async () => {
  if (!selectedCustomerContractId.value) return;
  selectedCustomerContractId.value = null;
  await ManagerOrdersService.patchManagerOrder(props.order.id, {
    customer_contract_id: null,
  });
  syncBaseDocumentSelection();
};

const updateBaseDocumentBinding = async (value: string) => {
  const nextCustomerContractId = value.startsWith(OPEN_CONTRACT_PREFIX) ? Number(value.slice(OPEN_CONTRACT_PREFIX.length)) : null;
  if (nextCustomerContractId !== null && Number.isNaN(nextCustomerContractId)) return;
  try {
    selectedBaseDocumentValue.value = value;
    selectedCustomerContractId.value = nextCustomerContractId;
    if (value.startsWith(OPEN_CONTRACT_PREFIX) || props.order.customer_contract_id) {
      await ManagerOrdersService.patchManagerOrder(props.order.id, {
        customer_contract_id: nextCustomerContractId,
      });
      emit('refresh');
    }
  } catch (error) {
    notify(`Ошибка выбора основания: ${getApiErrorMessage(error)}`, 'error');
  }
};

const updateDocumentRoleBinding = async (value: string) => {
  const nextRole = value ? normalizeRoleType(value) : null;
  try {
    selectedDocumentRoleType.value = nextRole;
    await ManagerOrdersService.patchManagerOrder(props.order.id, {
      document_role_type: nextRole,
    });
    emit('refresh');
  } catch (error) {
    notify(`Ошибка выбора ролей: ${getApiErrorMessage(error)}`, 'error');
  }
};

const openCustomerProfileForContract = () => {
  const customerId = props.order.customer?.id;
  if (!customerId) return;
  const currentPath = `${window.location.pathname}${window.location.search}`;
  const target = `/manager/customers/profile?customerId=${customerId}&openContract=1&returnTo=${encodeURIComponent(currentPath)}`;
  window.history.pushState({}, '', target);
  window.dispatchEvent(new PopStateEvent('popstate'));
};

const openDocumentSendModal = () => {
  if (!canSendDocuments.value) {
    notify('В завершённом заказе можно повторно отправить только существующие документы.', 'error');
    return;
  }
  showDocumentSendModal.value = true;
};

const openCreatePanel = () => {
  if (!documentAccess.value.canCreate) {
    notify(documentAccess.value.summary, 'error');
    return;
  }
  selectedDocumentType.value = suggestedDocumentType.value;
  showAdvancedSettings.value = false;
  isCreatePanelOpen.value = true;
  if (selectedDocumentType.value === 'act') syncActScopeDefaults();
  syncBaseDocumentSelection();
  if (isWaybillDocument.value) {
    syncWaybillProductLines();
    ensureAllWaybillComponents();
  }
};

defineExpose({
  openSend: openDocumentSendModal,
  openCreate: openCreatePanel,
});

const selectDocumentType = (type: string) => {
  selectedDocumentType.value = type;
  syncBaseDocumentSelection();
  if (isWaybillType(type)) {
    syncWaybillProductLines();
    ensureAllWaybillComponents();
  }
  if (type === 'act') syncActScopeDefaults();
};

const getSelectedBaseDocumentId = (type: string) => {
  if (!isClosingDocumentType(type)) return undefined;
  const value = selectedBaseDocumentValue.value;
  if (value.startsWith(ORDER_DOCUMENT_PREFIX)) {
    const docId = Number(value.slice(ORDER_DOCUMENT_PREFIX.length));
    return Number.isFinite(docId) ? docId : undefined;
  }
  if (value.startsWith(OPEN_CONTRACT_PREFIX)) return 0;
  return undefined;
};

const handleDocumentsSent = () => {
  notify('Письмо записано в историю отправок', 'success');
  emit('refresh');
};

const handleDocumentsSendSettled = () => {
  emailHistoryRefreshKey.value += 1;
};

const generateDocument = async (type: string) => {
  if (!documentAccess.value.canCreate) {
    notify(documentAccess.value.summary, 'error');
    return;
  }
  isGeneratingDoc.value = true;
  let mutatedOrderBeforeGeneration = false;
  let generatedDocument = false;
  try {
    syncBaseDocumentSelection();
    if (isClosingDocumentType(type) && !selectedBaseDocumentValue.value) {
      notify('Выберите документ-основание', 'error');
      return;
    }
    if (isWaybillType(type)) {
      if (!waybillProductLines.value.length) syncWaybillProductLines();
      ensureAllWaybillComponents();
    }
    const beforeState = normalizeBeforeGenerateResult(await props.beforeGenerate?.(type));
    if (!beforeState.proceed) return;
    if (beforeState.mutated) mutatedOrderBeforeGeneration = true;
    if (isWaybillType(type)) {
      if (!(await saveWaybillProductLines())) return;
      mutatedOrderBeforeGeneration = true;
    }
    if (type === 'act' && activeActServiceLines.value.length > 0 && selectedActServiceLineIds.value.length === 0) {
      notify('Выберите хотя бы одну услугу для акта', 'error');
      return;
    }
    const documentDraftPayload = hasAdditionalConditionsChanges.value
      ? { additional_conditions: additionalConditions.value }
      : undefined;
    if (type === 'contract' && isCompanyOrder.value) {
      if (selectedCustomerContractId.value) mutatedOrderBeforeGeneration = true;
      await useOneTimeContractForClosingDocs();
    }
    const template = (type === 'contract' && selectedContractTemplateId.value)
      ? selectedContractTemplate.value
      : undefined;
    const proposalId = (type === 'offer' || type === 'retail_receipt' || type === 'service_act' || type === 'maintenance_service_act' || type === 'act' || isWaybillType(type))
      ? (activeWaybillProposalId.value ?? undefined)
      : undefined;
    const baseDocumentId = getSelectedBaseDocumentId(type);
    const scopeCustomerBranchId = type === 'act' ? (selectedActBranchId.value ?? undefined) : undefined;
    const scopeTitle = type === 'act' ? (actScopeTitle.value.trim() || undefined) : undefined;
    const scopeAddress = type === 'act' ? (actScopeAddress.value.trim() || undefined) : undefined;
    const scopeServiceLineIds = type === 'act' && selectedActServiceLineIds.value.length
      ? selectedActServiceLineIds.value
      : undefined;
    const scopeServiceLineQuantities = type === 'act' && selectedActServiceLineIds.value.length
      ? JSON.stringify(selectedActServiceLineIds.value.map((lineId) => ({
        service_line_id: lineId,
        quantity: actServiceQuantity(lineId),
      })).filter((item) => item.quantity > 0))
      : undefined;
    const res = await ManagerOrdersService.generateManagerOrderDocument(
      props.order.id,
      type,
      template?.document_template_id ?? undefined,
      template && !template.document_template_id ? template.id : undefined,
      getDocumentDateForType(type),
      proposalId,
      baseDocumentId,
      scopeCustomerBranchId,
      scopeTitle,
      scopeAddress,
      scopeServiceLineIds,
      scopeServiceLineQuantities,
      undefined,
      documentDraftPayload,
    );
    generatedDocument = true;
    if (documentDraftPayload) {
      const normalizedConditions = (documentDraftPayload.additional_conditions || '').trim();
      additionalConditions.value = normalizedConditions;
      additionalConditionsSaved.value = normalizedConditions;
    }
    window.open(res.edit_url, '_blank');
    await loadDocuments();
    emit('refresh');
    notify('Документ создан', 'success');
    isCreatePanelOpen.value = false;
  } catch (error) {
    notify(`Ошибка генерации: ${getApiErrorMessage(error)}`, 'error');
  } finally {
    if (mutatedOrderBeforeGeneration && !generatedDocument) {
      emit('refresh');
    }
    isGeneratingDoc.value = false;
  }
};

const { triggerFileUpload, handleFileUpload, handleAttachDocumentFile, downloadDocument, deleteDocument } = useDocumentFileActions({
  orderId: () => props.order.id,
  access: documentAccess,
  fileInput: fileInputRef,
  isUploading: isUploadingDoc,
  processingDocumentId: processingDocId,
  loadDocuments,
  refresh: () => emit('refresh'),
  notify,
});
const { handleExternalContractFile, registerExternalContract } = useExternalContractRegistration({
  orderId: () => props.order.id,
  canCreate: () => documentAccess.value.canCreate,
  accessSummary: () => documentAccess.value.summary,
  number: externalContractNumber,
  date: externalContractDate,
  url: externalContractUrl,
  file: externalContractFile,
  isOpen: externalContractOpen,
  isSaving: isRegisteringExternalContract,
  loadDocuments,
  clearSelectedCustomerContract: () => { selectedCustomerContractId.value = null; },
  refresh: () => emit('refresh'),
  notify,
});

provide(DocumentGenerationContextKey, {
  activeActServiceLines,
  actScopeAddress,
  actScopeTitle,
  actServiceQuantity,
  additionalConditions,
  additionalConditionsMode,
  baseDocumentOptions,
  contractTemplates,
  createChecklist,
  creatingActBranch,
  customerBranches,
  customerContracts,
  documentDate,
  documentAccess,
  externalContractDate,
  externalContractFile,
  externalContractNumber,
  externalContractOpen,
  externalContractUrl,
  inheritedDocumentRoleType,
  hasClosingBaseDocument,
  isCreatePanelOpen,
  isDocumentTypeLocked,
  isGeneratingDoc,
  isRegisteringExternalContract,
  isWaybillDocument,
  needsContractBinding,
  newActBranchAddress,
  newActBranchName,
  selectedActBranchId,
  selectedBaseDocumentBinding,
  selectedContractTemplateId,
  selectedDocumentRoleBinding,
  selectedDocumentType,
  selectedDocumentTypeItem,
  showAdvancedSettings,
  showsAdditionalConditions,
  showsDocumentRoleControl,
  waybillProductLines,
  actions: {
    createActBranch,
    generateDocument,
    handleExternalContractFile,
    lockedDocumentTitle,
    maxActServiceQuantity,
    onActBranchChange,
    onActServiceCheckboxChange,
    openCustomerProfileForContract,
    registerExternalContract,
    selectDocumentType,
    setActServiceLineQuantity,
    syncActServiceSelection,
  },
});
</script>

<template>
  <input v-if="documentAccess.canUpload" ref="fileInputRef" type="file" class="hidden" :accept="DOCUMENT_FILE_ACCEPT" @change="handleFileUpload" />
  <LegacyDocumentsShell
    v-model:send-open="showDocumentSendModal"
    :order="order" :documents="documents" :access="documentAccess" :summary="documentSummary"
    :setup-warning="hasDocumentSetupWarning" :can-send="canSendDocuments" :uploading="isUploadingDoc"
    :generating="isGeneratingDoc" :processing-id="processingDocId" :email-history-refresh-key="emailHistoryRefreshKey"
    @sent="handleDocumentsSent" @settled="handleDocumentsSendSettled" @create="openCreatePanel" @upload="triggerFileUpload"
    @download="downloadDocument" @attach="handleAttachDocumentFile" @delete="deleteDocument" @toast="notify"
  />
</template>
