<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { ManagerContractsService, ManagerDocsService, ManagerOrdersService } from '../../client';
import { downloadManagerDocBlob } from '../../api';
import type {
  DocumentTemplateItem,
  ManagerCustomerContractItemResponse,
  ManagerOrderDetailResponse,
  ManagerOrderDocumentItem,
  OrderProductLineResponse,
  OrderProposalResponse,
} from '../../client';
import { getApiErrorMessage } from '../../utils/api-errors';
import AdditionalConditionsLibrary from './AdditionalConditionsLibrary.vue';
import DocumentSendModal from './DocumentSendModal.vue';

type ToastType = 'success' | 'error';
type DocumentRoleType = 'seller_buyer' | 'executor_customer' | 'contractor_customer';
type LogisticsComponentKind = 'indoor' | 'outdoor' | 'accessory' | 'other';

type ProductLogisticsTemplateComponent = {
  title: string;
  country?: string | null;
  unit?: string | null;
  quantity_per_parent?: number | null;
  price_weight?: number | null;
  kind?: LogisticsComponentKind | null;
};

type OrderLogisticsComponent = {
  title: string;
  country?: string | null;
  unit: string;
  quantity_per_parent: number;
  unit_price: number;
  kind?: LogisticsComponentKind | null;
};

type WaybillProductLine = {
  id?: number | null;
  proposal_id?: number | null;
  product_id?: number | null;
  product_query: string;
  quantity: number;
  price: number;
  cost?: number | null;
  product_country?: string | null;
  product_logistics_components?: ProductLogisticsTemplateComponent[];
  logistics_components?: OrderLogisticsComponent[] | null;
};

const props = defineProps<{
  order: ManagerOrderDetailResponse;
  activeProposalId?: number | null;
  productLines?: WaybillProductLine[];
  beforeGenerate?: (type: string) => boolean | void | Promise<boolean | void>;
}>();

const emit = defineEmits<{
  refresh: [];
  toast: [payload: { message: string; type?: ToastType }];
}>();

const DOCUMENT_FILE_ACCEPT = '.pdf,.doc,.docx,application/pdf,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document';
const OPEN_CONTRACT_PREFIX = 'open:';
const ORDER_DOCUMENT_PREFIX = 'doc:';
const BASE_DOCUMENT_TYPES = new Set(['offer', 'contract', 'invoice']);
const CLOSING_DOCUMENT_TYPES = new Set(['act', 'tn2', 'ttn1']);

const DOCUMENT_TYPES = [
  { type: 'contract', label: 'Договор' },
  { type: 'invoice', label: 'Счет' },
  { type: 'act', label: 'Акт' },
  { type: 'defect_act', label: 'Дефектный акт' },
  { type: 'offer', label: 'КП' },
  { type: 'tn2', label: 'ТН-2' },
  { type: 'ttn1', label: 'ТТН-1' },
];

const DOCUMENT_ROLE_OPTIONS: Array<{ value: DocumentRoleType; label: string }> = [
  { value: 'seller_buyer', label: 'Продавец / Покупатель' },
  { value: 'executor_customer', label: 'Исполнитель / Заказчик' },
  { value: 'contractor_customer', label: 'Подрядчик / Заказчик' },
];

const documents = ref<ManagerOrderDocumentItem[]>([]);
const customerContracts = ref<ManagerCustomerContractItemResponse[]>([]);
const contractTemplates = ref<DocumentTemplateItem[]>([]);
const selectedCustomerContractId = ref<number | null>(props.order.customer_contract_id || null);
const selectedDocumentRoleType = ref<string | null>(props.order.document_role_type || null);
const selectedContractTemplateId = ref<string>('');
const selectedBaseDocumentValue = ref<string>('');
const additionalConditions = ref(props.order.additional_conditions || '');
const additionalConditionsSaved = ref(props.order.additional_conditions || '');
const isSavingAdditionalConditions = ref(false);
const documentDate = ref(new Date().toISOString().slice(0, 10));
const isGeneratingDoc = ref(false);
const processingDocId = ref<number | null>(null);
const isCreatePanelOpen = ref(false);
const showAdvancedSettings = ref(false);
const selectedDocumentType = ref('contract');
const showDocumentSendModal = ref(false);
const isUploadingDoc = ref(false);
const fileInputRef = ref<HTMLInputElement | null>(null);
const externalContractOpen = ref(false);
const externalContractNumber = ref('');
const externalContractDate = ref(new Date().toISOString().slice(0, 10));
const externalContractUrl = ref('');
const externalContractFile = ref<File | null>(null);
const isRegisteringExternalContract = ref(false);

const notify = (message: string, type: ToastType = 'success') => {
  emit('toast', { message, type });
};

const formatMoney = (value: number | null | undefined) => `${Number(value || 0).toLocaleString('ru-RU')} BYN`;

const normalizeRoleType = (value: unknown): DocumentRoleType => {
  const raw = String(value || '').trim();
  if (raw === 'executor_customer' || raw === 'contractor_customer') return raw;
  return 'seller_buyer';
};

const isWaybillType = (type: string) => type === 'tn2' || type === 'ttn1';
const isClosingDocumentType = (type: string) => CLOSING_DOCUMENT_TYPES.has(type);
const isWaybillDocument = computed(() => isWaybillType(selectedDocumentType.value));
const documentTypeLabel = (type?: string | null) => DOCUMENT_TYPES.find((item) => item.type === type)?.label || type || 'Документ';
const hasUsableWaybillProductLine = (line: WaybillProductLine) => (
  String(line.product_query || '').trim().length > 0
  && Number(line.quantity || 0) > 0
);
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
const mapOrderProductLineToWaybillLine = (line: OrderProductLineResponse): WaybillProductLine => ({
  id: line.id,
  proposal_id: line.proposal_id,
  product_id: line.product_id,
  product_query: line.product_title || '',
  quantity: Number(line.quantity || 0),
  price: Number(line.price || 0),
  cost: Number(line.cost || 0),
  product_country: (line as any).product_country || null,
  product_logistics_components: Array.isArray((line as any).product_logistics_components)
    ? ((line as any).product_logistics_components as ProductLogisticsTemplateComponent[])
    : [],
  logistics_components: Array.isArray((line as any).logistics_components) && (line as any).logistics_components.length
    ? ((line as any).logistics_components as OrderLogisticsComponent[])
    : null,
});
const orderFallbackProductLines = computed<WaybillProductLine[]>(() => {
  const proposal = selectedOrderProposal.value as OrderProposalResponse | null;
  if (proposal?.product_lines?.length) {
    return proposal.product_lines.map(mapOrderProductLineToWaybillLine);
  }
  return (props.order.product_lines || []).map(mapOrderProductLineToWaybillLine);
});
const resolvedWaybillProductLines = computed(() => (
  ((props.productLines || []).some(hasUsableWaybillProductLine)
    ? (props.productLines || [])
    : orderFallbackProductLines.value
  ).filter(hasUsableWaybillProductLine)
));
const cloneWaybillProductLine = (line: WaybillProductLine): WaybillProductLine => ({
  ...line,
  product_logistics_components: (line.product_logistics_components || []).map((component) => ({ ...component })),
  logistics_components: line.logistics_components?.length
    ? line.logistics_components.map((component) => ({ ...component }))
    : null,
});
const waybillProductLines = ref<WaybillProductLine[]>([]);
const syncWaybillProductLines = () => {
  waybillProductLines.value = resolvedWaybillProductLines.value.map(cloneWaybillProductLine);
};

const LOGISTICS_COMPONENT_KINDS = new Set(['indoor', 'outdoor', 'accessory', 'other']);
const normalizeLogisticsKind = (value: unknown): LogisticsComponentKind => {
  const raw = String(value || '').trim();
  return LOGISTICS_COMPONENT_KINDS.has(raw) ? (raw as LogisticsComponentKind) : 'other';
};
const normalizePositiveInteger = (value: unknown, fallback = 1) => {
  const parsed = Math.trunc(Number(value));
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
};
const normalizePositiveNumber = (value: unknown, fallback = 0) => {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : fallback;
};
const roundToNearest10 = (value: number) => Math.floor((Number(value || 0) + 5) / 10) * 10;
const roundMoney = (value: number) => Number(Number(value || 0).toFixed(2));
const allocateLogisticsPrices = (templates: ProductLogisticsTemplateComponent[], price: number): OrderLogisticsComponent[] => {
  if (!templates.length) return [];
  const weights = templates.map((item) => Math.max(0, Number(item.price_weight ?? 1)));
  const totalWeight = weights.some((item) => item > 0)
    ? weights.reduce((sum, item) => sum + item, 0)
    : templates.length;
  let remaining = Number(price || 0);
  return templates.map((item, index) => {
    const quantityPerParent = normalizePositiveInteger(item.quantity_per_parent, 1);
    const componentTotal = index === templates.length - 1
      ? remaining
      : roundToNearest10(Number(price || 0) * ((weights[index] || 1) / totalWeight));
    if (index !== templates.length - 1) remaining -= componentTotal;
    return {
      title: item.title,
      country: item.country || 'Китай',
      unit: item.unit || 'шт.',
      quantity_per_parent: quantityPerParent,
      unit_price: roundMoney(componentTotal / quantityPerParent),
      kind: normalizeLogisticsKind(item.kind),
    };
  });
};
const createDefaultWaybillSplit = (line: WaybillProductLine): OrderLogisticsComponent[] => {
  const title = String(line.product_query || '').trim();
  const country = line.product_country || 'Китай';
  return allocateLogisticsPrices(
    [
      {
        title: title ? `Внутренний блок ${title}` : 'Внутренний блок',
        country,
        unit: 'шт.',
        quantity_per_parent: 1,
        price_weight: 1,
        kind: 'indoor',
      },
      {
        title: title ? `Наружный блок ${title}` : 'Наружный блок',
        country,
        unit: 'шт.',
        quantity_per_parent: 1,
        price_weight: 2,
        kind: 'outdoor',
      },
    ],
    Number(line.price || 0),
  );
};
const ensureWaybillComponents = (line: WaybillProductLine) => {
  if (line.logistics_components?.length) return;
  line.logistics_components = line.product_logistics_components?.length
    ? allocateLogisticsPrices(line.product_logistics_components, Number(line.price || 0))
    : createDefaultWaybillSplit(line);
};
const ensureAllWaybillComponents = () => {
  waybillProductLines.value.forEach(ensureWaybillComponents);
};
const componentPerParentTotal = (component: OrderLogisticsComponent) => (
  normalizePositiveNumber(component.unit_price, 0) * normalizePositiveInteger(component.quantity_per_parent, 1)
);
const lineLogisticsPerParentTotal = (line: WaybillProductLine) => (
  (line.logistics_components || []).reduce((sum, component) => sum + componentPerParentTotal(component), 0)
);
const chooseBalanceComponentIndex = (components: OrderLogisticsComponent[], changedIndex: number | null) => {
  if (!components.length) return -1;
  if (components.length === 1) return 0;
  const changedKind = changedIndex === null ? null : normalizeLogisticsKind(components[changedIndex]?.kind);
  const preferredKind = changedKind === 'outdoor' ? 'indoor' : 'outdoor';
  const preferred = components.findIndex((component, index) => index !== changedIndex && normalizeLogisticsKind(component.kind) === preferredKind);
  if (preferred >= 0) return preferred;
  const outdoor = components.findIndex((component, index) => index !== changedIndex && normalizeLogisticsKind(component.kind) === 'outdoor');
  if (outdoor >= 0) return outdoor;
  return components.findIndex((_, index) => index !== changedIndex);
};
const setComponentTotal = (component: OrderLogisticsComponent, total: number) => {
  const quantityPerParent = normalizePositiveInteger(component.quantity_per_parent, 1);
  component.unit_price = roundMoney(Math.max(0, total) / quantityPerParent);
};
const rebalanceWaybillLine = (line: WaybillProductLine, changedIndex: number | null = null) => {
  const components = line.logistics_components || [];
  if (!components.length) return;
  const targetIndex = chooseBalanceComponentIndex(components, changedIndex);
  if (targetIndex < 0) return;
  const target = components[targetIndex];
  if (!target) return;
  const linePrice = Number(line.price || 0);

  if (changedIndex !== null && components[changedIndex]) {
    const fixedWithoutTargetAndChanged = components.reduce((sum, component, index) => (
      index === targetIndex || index === changedIndex ? sum : sum + componentPerParentTotal(component)
    ), 0);
    const maxChangedTotal = Math.max(0, linePrice - fixedWithoutTargetAndChanged);
    const changed = components[changedIndex]!;
    if (componentPerParentTotal(changed) > maxChangedTotal) {
      setComponentTotal(changed, maxChangedTotal);
    }
  }

  const fixedWithoutTarget = components.reduce((sum, component, index) => (
    index === targetIndex ? sum : sum + componentPerParentTotal(component)
  ), 0);
  setComponentTotal(target, linePrice - fixedWithoutTarget);
};
const handleWaybillUnitPriceInput = (line: WaybillProductLine, componentIndex: number, event: Event) => {
  const component = line.logistics_components?.[componentIndex];
  if (!component) return;
  component.unit_price = normalizePositiveNumber((event.target as HTMLInputElement).value, 0);
  rebalanceWaybillLine(line, componentIndex);
};
const handleWaybillQuantityInput = (line: WaybillProductLine, componentIndex: number, event: Event) => {
  const component = line.logistics_components?.[componentIndex];
  if (!component) return;
  component.quantity_per_parent = normalizePositiveInteger((event.target as HTMLInputElement).value, 1);
  rebalanceWaybillLine(line, componentIndex);
};
const addWaybillComponent = (line: WaybillProductLine) => {
  ensureWaybillComponents(line);
  line.logistics_components = [
    ...(line.logistics_components || []),
    {
      title: '',
      country: line.product_country || 'Китай',
      unit: 'шт.',
      quantity_per_parent: 1,
      unit_price: 0,
      kind: 'other',
    },
  ];
  rebalanceWaybillLine(line, null);
};
const removeWaybillComponent = (line: WaybillProductLine, componentIndex: number) => {
  if (!line.logistics_components) return;
  line.logistics_components.splice(componentIndex, 1);
  if (!line.logistics_components.length) {
    line.logistics_components = null;
    return;
  }
  rebalanceWaybillLine(line, null);
};
const lineLogisticsHasMismatch = (line: WaybillProductLine) => (
  Boolean(line.logistics_components?.length) && Math.abs(lineLogisticsPerParentTotal(line) - Number(line.price || 0)) >= 0.01
);

const getRoleLabel = (value?: string | null) => (
  DOCUMENT_ROLE_OPTIONS.find((option) => option.value === normalizeRoleType(value))?.label || 'Продавец / Покупатель'
);

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
  const base = hasContract.value ? 'договор есть' : (hasOrderInvoice.value ? 'есть счет' : (hasClosingBaseDocument.value ? 'есть основание' : 'без основания'));
  return `${documents.value.length} док. · ${base}`;
});
const hasDocumentSetupWarning = computed(() => isCompanyOrder.value && !selectedCustomerContractId.value && !hasClosingBaseDocument.value);
const suggestedDocumentType = computed(() => {
  if (isCompanyOrder.value && hasClosingBaseDocument.value) return 'act';
  if (isCompanyOrder.value && !hasContract.value) return 'contract';
  if (isCompanyOrder.value && !hasOrderInvoice.value) return 'invoice';
  return 'act';
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
));
const additionalConditionsMode = computed(() => (selectedDocumentType.value === 'contract' ? 'contract' : 'invoice'));
const contractBindingLabel = computed(() => {
  if (selectedDocumentType.value === 'contract') return 'будет создан разовый договор заказа';
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
    { label: 'Договор', value: contractBindingLabel.value },
  ];
  if (showsAdditionalConditions.value) {
    items.push({ label: 'Условия', value: additionalConditions.value.trim() ? 'есть выбранные условия' : 'Оставить по шаблону' });
  }
  if (showsDocumentRoleControl.value) {
    items.push({ label: 'Роли', value: roleChecklistLabel.value });
  }
  return items;
});

const datedDocumentTypes = new Set(['contract', 'act', 'defect_act', 'tn2', 'ttn1']);
const getDocumentDateForType = (type: string) => (
  datedDocumentTypes.has(type) && documentDate.value ? `${documentDate.value}T00:00:00` : undefined
);

const isDocumentTypeLocked = (type: string) => (
  isClosingDocumentType(type) && !hasClosingBaseDocument.value
);
const lockedDocumentTitle = (type: string) => (
  isClosingDocumentType(type) ? 'Сначала создайте договор, счет или оферту' : ''
);

const documentProposalName = (doc: ManagerOrderDocumentItem) => {
  if (!doc.proposal_id) return '';
  const proposal = (props.order.proposals || []).find((item) => item.id === doc.proposal_id);
  return proposal?.name || `вариант #${doc.proposal_id}`;
};

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
  try {
    const res = await ManagerDocsService.getManagerOrderDocuments(props.order.id);
    documents.value = res.items;
    if (!isCreatePanelOpen.value) selectedDocumentType.value = suggestedDocumentType.value;
    syncBaseDocumentSelection();
  } catch (error) {
    console.error('Failed to load documents', error);
  }
};

const loadContractTemplates = async () => {
  try {
    const res = await ManagerDocsService.getDocTemplates('contract', props.order.id);
    contractTemplates.value = res.items.filter((template) => !template.is_open_contract);
    if (contractTemplates.value.length > 0 && contractTemplates.value[0]) {
      selectedContractTemplateId.value = contractTemplates.value[0].id;
    }
  } catch (error) {
    console.warn('Failed to load contract templates', error);
  }
};

const loadCustomerContracts = async () => {
  if (!props.order.customer?.id) {
    customerContracts.value = [];
    selectedCustomerContractId.value = null;
    syncBaseDocumentSelection();
    return;
  }
  try {
    const res = await ManagerContractsService.getManagerCustomerContracts(props.order.customer.id);
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
}, { immediate: true });

watch(selectedDocumentType, () => {
  if (!showsAdditionalConditions.value) showAdvancedSettings.value = false;
  syncBaseDocumentSelection();
});

watch(() => [
  props.order.customer_contract_id,
  props.order.document_role_type,
  props.order.additional_conditions,
], () => {
  resetFromOrder();
});

const saveAdditionalConditions = async (showSuccessToast = true) => {
  if (!hasAdditionalConditionsChanges.value) return true;
  const valueToSave = additionalConditions.value;
  isSavingAdditionalConditions.value = true;
  try {
    await ManagerOrdersService.patchManagerOrder(props.order.id, {
      additional_conditions: valueToSave,
    });
    additionalConditionsSaved.value = valueToSave;
    if (showSuccessToast) notify('Условия сохранены', 'success');
    return true;
  } catch (error) {
    notify(`Ошибка сохранения условий: ${getApiErrorMessage(error)}`, 'error');
    return false;
  } finally {
    isSavingAdditionalConditions.value = false;
  }
};

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
  if (!documents.value.length) {
    notify('Сначала создайте или загрузите документ', 'error');
    return;
  }
  showDocumentSendModal.value = true;
};

const openCreatePanel = () => {
  selectedDocumentType.value = suggestedDocumentType.value;
  showAdvancedSettings.value = false;
  isCreatePanelOpen.value = true;
  syncBaseDocumentSelection();
  if (isWaybillDocument.value) {
    syncWaybillProductLines();
    ensureAllWaybillComponents();
  }
};

const selectDocumentType = (type: string) => {
  selectedDocumentType.value = type;
  syncBaseDocumentSelection();
  if (isWaybillType(type)) {
    syncWaybillProductLines();
    ensureAllWaybillComponents();
  }
};

const activeWaybillProposalId = computed(() => props.activeProposalId ?? selectedOrderProposal.value?.id ?? null);

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

const saveWaybillProductLines = async () => {
  const lines = waybillProductLines.value;
  if (!lines.length) return true;
  const missingProduct = lines.find((line) => !Number(line.product_id || 0));
  if (missingProduct) {
    notify('Для накладной выберите товар из каталога в товарной строке.', 'error');
    return false;
  }

  try {
    await ManagerOrdersService.patchManagerOrder(props.order.id, {
      products: lines.map((line) => ({
        product_id: Number(line.product_id),
        quantity: Math.trunc(Number(line.quantity) || 0),
        price: Math.round(Number(line.price) || 0),
        cost: line.cost == null ? null : Math.round(Number(line.cost) || 0),
        proposal_id: activeWaybillProposalId.value ?? undefined,
        logistics_components: line.logistics_components?.length ? line.logistics_components : null,
      })),
    });
    return true;
  } catch (error) {
    notify(`Ошибка сохранения состава накладной: ${getApiErrorMessage(error)}`, 'error');
    return false;
  }
};

const handleDocumentsSent = () => {
  notify('Письмо отправлено', 'success');
  emit('refresh');
};

const generateDocument = async (type: string) => {
  isGeneratingDoc.value = true;
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
    const beforeResult = await props.beforeGenerate?.(type);
    if (beforeResult === false) return;
    if (isWaybillType(type) && !(await saveWaybillProductLines())) return;
    if (!(await saveAdditionalConditions(false))) return;
    if (type === 'contract' && isCompanyOrder.value) {
      await useOneTimeContractForClosingDocs();
    }
    const template = (type === 'contract' && selectedContractTemplateId.value)
      ? selectedContractTemplate.value
      : undefined;
    const proposalId = (type === 'offer' || isWaybillType(type)) ? (activeWaybillProposalId.value ?? undefined) : undefined;
    const baseDocumentId = getSelectedBaseDocumentId(type);
    const res = await ManagerOrdersService.generateManagerOrderDocument(
      props.order.id,
      type,
      template?.document_template_id ?? undefined,
      template && !template.document_template_id ? template.id : undefined,
      getDocumentDateForType(type),
      proposalId,
      baseDocumentId,
    );
    window.open(res.edit_url, '_blank');
    await loadDocuments();
    emit('refresh');
    notify('Документ создан', 'success');
    isCreatePanelOpen.value = false;
  } catch (error) {
    notify(`Ошибка генерации: ${getApiErrorMessage(error)}`, 'error');
  } finally {
    isGeneratingDoc.value = false;
  }
};

const triggerFileUpload = () => {
  fileInputRef.value?.click();
};

const handleFileUpload = async (event: Event) => {
  const target = event.target as HTMLInputElement;
  const file = target.files?.[0] as File | undefined;
  if (!file) return;

  isUploadingDoc.value = true;
  try {
    await ManagerDocsService.uploadManagerOrderDocument(props.order.id, { file });
    await loadDocuments();
    emit('refresh');
    notify('Документ загружен', 'success');
  } catch (error) {
    notify(`Ошибка загрузки: ${getApiErrorMessage(error)}`, 'error');
  } finally {
    isUploadingDoc.value = false;
    if (fileInputRef.value) fileInputRef.value.value = '';
  }
};

const handleAttachDocumentFile = async (doc: ManagerOrderDocumentItem, event: Event) => {
  const target = event.target as HTMLInputElement;
  const file = target.files?.[0] as File | undefined;
  if (!file) return;

  processingDocId.value = doc.id;
  try {
    await ManagerDocsService.attachManagerDocFile(doc.id, { file });
    await loadDocuments();
    emit('refresh');
    notify('Файл прикреплен', 'success');
  } catch (error) {
    notify(`Ошибка прикрепления: ${getApiErrorMessage(error)}`, 'error');
  } finally {
    processingDocId.value = null;
    target.value = '';
  }
};

const downloadDocument = async (doc: ManagerOrderDocumentItem) => {
  processingDocId.value = doc.id;
  try {
    const { blob, filename } = await downloadManagerDocBlob(doc.id);
    const url = window.URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.setAttribute('download', filename || `${doc.number || doc.doc_type}.pdf`);
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.URL.revokeObjectURL(url);
  } catch (error) {
    notify(`Ошибка скачивания: ${getApiErrorMessage(error)}`, 'error');
  } finally {
    processingDocId.value = null;
  }
};

const deleteDocument = async (docId: number) => {
  if (!confirm('Удалить документ?')) return;
  processingDocId.value = docId;
  try {
    await ManagerDocsService.deleteManagerDoc(docId);
    await loadDocuments();
    emit('refresh');
    notify('Документ удален', 'success');
  } catch (error) {
    notify('Ошибка удаления', 'error');
  } finally {
    processingDocId.value = null;
  }
};

const handleExternalContractFile = (event: Event) => {
  const target = event.target as HTMLInputElement;
  externalContractFile.value = target.files?.[0] || null;
};

const resetExternalContractForm = () => {
  externalContractNumber.value = '';
  externalContractDate.value = new Date().toISOString().slice(0, 10);
  externalContractUrl.value = '';
  externalContractFile.value = null;
};

const registerExternalContract = async () => {
  const number = externalContractNumber.value.trim();
  if (!number) {
    notify('Укажите номер договора', 'error');
    return;
  }
  if (!externalContractDate.value) {
    notify('Укажите дату договора', 'error');
    return;
  }

  isRegisteringExternalContract.value = true;
  try {
    await ManagerDocsService.registerManagerExternalContract(props.order.id, {
      number,
      contract_date: `${externalContractDate.value}T00:00:00`,
      external_url: externalContractUrl.value.trim() || undefined,
      file: externalContractFile.value || undefined,
    });
    await loadDocuments();
    selectedCustomerContractId.value = null;
    externalContractOpen.value = false;
    resetExternalContractForm();
    emit('refresh');
    notify('Внешний договор добавлен', 'success');
  } catch (error) {
    notify(`Ошибка добавления договора: ${getApiErrorMessage(error)}`, 'error');
  } finally {
    isRegisteringExternalContract.value = false;
  }
};
</script>

<template>
  <section class="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-700/60 dark:bg-slate-900/60 sm:p-5">
    <DocumentSendModal
      v-model="showDocumentSendModal"
      :order="order"
      :documents="documents"
      @sent="handleDocumentsSent"
    />

    <div class="mb-4 flex flex-col gap-3 border-b border-slate-100 pb-4 dark:border-slate-800 sm:flex-row sm:items-start sm:justify-between">
      <div>
        <h3 class="font-['Space_Grotesk'] text-lg font-bold text-slate-900 dark:text-white">Документы</h3>
        <p
          class="mt-1 text-xs font-medium"
          :class="hasDocumentSetupWarning ? 'text-amber-600 dark:text-amber-400' : 'text-slate-500 dark:text-slate-400'"
        >
          {{ documentSummary }}
        </p>
      </div>

      <div class="flex flex-wrap items-center gap-2 sm:justify-end">
        <button
          class="inline-flex h-9 items-center gap-1.5 rounded-lg bg-teal-600 px-3 text-sm font-semibold text-white shadow-sm hover:bg-teal-700 focus:outline-none focus:ring-2 focus:ring-teal-500/50 disabled:opacity-50"
          title="Отправить документы"
          :disabled="!documents.length || isUploadingDoc || !!processingDocId || isGeneratingDoc"
          @click="openDocumentSendModal"
        >
          <span class="material-icons-round text-[18px]">send</span>
          Отправить
        </button>

        <button
          class="inline-flex h-9 items-center gap-1.5 rounded-lg bg-[#007f80] px-3 text-sm font-semibold text-white shadow-sm hover:bg-teal-600 focus:outline-none focus:ring-2 focus:ring-teal-500/50 disabled:opacity-50"
          :disabled="isGeneratingDoc || !!processingDocId || isUploadingDoc"
          @click="openCreatePanel"
        >
          <span class="material-icons-round text-[18px]">add_circle</span>
          Создать
        </button>

        <input ref="fileInputRef" type="file" class="hidden" :accept="DOCUMENT_FILE_ACCEPT" @change="handleFileUpload" />
        <button
          class="inline-flex h-9 items-center gap-1.5 rounded-lg bg-slate-700 px-3 text-sm font-semibold text-white shadow-sm hover:bg-slate-600 focus:outline-none focus:ring-2 focus:ring-slate-500/50 disabled:opacity-50"
          title="Загрузить файл"
          :disabled="isUploadingDoc || !!processingDocId || isGeneratingDoc"
          @click="triggerFileUpload"
        >
          <span v-if="isUploadingDoc" class="material-icons-round animate-spin text-[18px]">loop</span>
          <span v-else class="material-icons-round text-[18px]">upload_file</span>
          Загрузить
        </button>
      </div>
    </div>

    <div class="flex flex-col gap-3">
      <div>
        <p class="mb-2 text-[11px] font-bold uppercase tracking-wide text-slate-500 dark:text-slate-400">Документы</p>
        <div v-if="documents.length" class="space-y-2">
          <div
            v-for="doc in documents"
            :key="doc.id"
            class="flex items-center justify-between rounded-xl border border-slate-200 bg-white p-3 text-slate-700 shadow-sm dark:border-slate-700/50 dark:bg-[#1e293b] dark:text-slate-300 dark:shadow-none"
          >
            <div class="flex min-w-0 items-center gap-3">
              <div class="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-slate-100 text-teal-600 dark:bg-slate-800 dark:text-teal-400">
                <span class="material-icons-round text-[19px]">description</span>
              </div>
              <div class="min-w-0">
                <p class="truncate text-sm font-medium text-slate-900 dark:text-white">{{ doc.number || doc.doc_type }}</p>
                <p class="truncate text-xs text-slate-500 dark:text-slate-400">
                  {{ new Date(doc.date).toLocaleDateString('ru-RU') }} · <span class="uppercase">{{ doc.doc_type }}</span>
                  <span v-if="documentProposalName(doc)"> · {{ documentProposalName(doc) }}</span>
                </p>
                <p v-if="doc.base_document_number" class="truncate text-[11px] text-slate-400 dark:text-slate-500">
                  Основание: {{ doc.base_document_type_label || documentTypeLabel(doc.base_document_type) }} · {{ doc.base_document_number }}
                </p>
              </div>
            </div>
            <div class="flex shrink-0 items-center gap-1 sm:gap-2">
              <a
                v-if="doc.edit_url"
                :href="doc.edit_url"
                target="_blank"
                class="flex h-8 w-8 items-center justify-center rounded-lg text-slate-500 hover:bg-slate-100 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-700 dark:hover:text-white"
                title="Открыть"
              >
                <span class="material-icons-round text-[18px]">open_in_new</span>
              </a>
              <button
                v-if="doc.is_downloadable"
                class="flex h-8 w-8 items-center justify-center rounded-lg text-slate-500 hover:bg-slate-100 hover:text-slate-900 disabled:opacity-50 dark:text-slate-400 dark:hover:bg-slate-700 dark:hover:text-white"
                :disabled="processingDocId === doc.id"
                title="Скачать PDF"
                @click="downloadDocument(doc)"
              >
                <span class="material-icons-round text-[18px]">download</span>
              </button>
              <label
                v-else
                class="flex h-8 w-8 cursor-pointer items-center justify-center rounded-lg text-teal-600 hover:bg-teal-50 hover:text-teal-700 dark:text-teal-400 dark:hover:bg-teal-900/30 dark:hover:text-teal-300"
                title="Добавить файл"
              >
                <span class="material-icons-round text-[18px]">attach_file</span>
                <input type="file" class="hidden" :accept="DOCUMENT_FILE_ACCEPT" :disabled="processingDocId === doc.id" @change="handleAttachDocumentFile(doc, $event)" />
              </label>
              <button
                class="flex h-8 w-8 items-center justify-center rounded-lg text-red-400 hover:bg-red-500/10 hover:text-red-500 disabled:opacity-50"
                :disabled="processingDocId === doc.id"
                title="Удалить"
                @click="deleteDocument(doc.id)"
              >
                <span class="material-icons-round text-[18px]">delete</span>
              </button>
            </div>
          </div>
        </div>
        <div v-else class="rounded-xl border border-dashed border-slate-300 py-5 text-center text-sm italic text-slate-500 dark:border-slate-700">
          Нет сформированных документов
        </div>
      </div>

      <div v-if="isCreatePanelOpen" class="order-first rounded-xl border border-teal-200 bg-teal-50/30 p-3 dark:border-teal-800/70 dark:bg-teal-950/20">
        <div class="mb-3 flex items-center justify-between gap-3">
          <div>
            <p class="text-[11px] font-bold uppercase tracking-wide text-teal-700 dark:text-teal-300">Создание документа</p>
            <p class="text-xs text-slate-500 dark:text-slate-400">Проверьте обязательные поля и создайте документ.</p>
          </div>
          <button
            type="button"
            class="rounded-lg px-2 py-1 text-xs font-semibold text-slate-500 hover:bg-white dark:text-slate-400 dark:hover:bg-slate-800"
            @click="isCreatePanelOpen = false"
          >
            Закрыть
          </button>
        </div>

        <div class="space-y-4">
          <div>
            <p class="mb-2 text-xs font-semibold text-slate-700 dark:text-slate-200">Шаг 1: выберите тип документа</p>
            <div class="grid grid-cols-2 gap-2 sm:grid-cols-4">
              <button
                v-for="dtype in DOCUMENT_TYPES"
                :key="dtype.type"
                type="button"
                class="flex min-h-10 items-center justify-between rounded-lg border px-3 py-2 text-left text-sm font-semibold transition-colors disabled:cursor-not-allowed disabled:opacity-50"
                :class="selectedDocumentType === dtype.type ? 'border-teal-500 bg-white text-teal-700 shadow-sm dark:bg-slate-900 dark:text-teal-300' : 'border-slate-200 bg-white/80 text-slate-600 hover:border-teal-300 hover:text-teal-700 dark:border-slate-700 dark:bg-slate-900/60 dark:text-slate-300'"
                :disabled="isDocumentTypeLocked(dtype.type)"
                :title="isDocumentTypeLocked(dtype.type) ? lockedDocumentTitle(dtype.type) : ''"
                @click="selectDocumentType(dtype.type)"
              >
                <span>{{ dtype.label }}</span>
                <span v-if="isDocumentTypeLocked(dtype.type)" class="material-icons-round text-[16px] text-amber-500">lock</span>
              </button>
            </div>
            <p v-if="isDocumentTypeLocked(selectedDocumentType)" class="mt-2 text-xs text-amber-600 dark:text-amber-400">
              {{ lockedDocumentTitle(selectedDocumentType) }}.
            </p>
          </div>

          <div class="grid gap-3 md:grid-cols-2">
            <label class="text-xs font-medium text-slate-600 dark:text-slate-300">Шаг 2: дата документа
              <input
                v-model="documentDate"
                type="date"
                class="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-teal-500/50 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-200"
              />
            </label>
            <label v-if="selectedDocumentType === 'contract'" class="text-xs font-medium text-slate-600 dark:text-slate-300">Шаг 2: шаблон
              <select
                v-model="selectedContractTemplateId"
                class="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-teal-500/50 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-200"
              >
                <option v-for="template in contractTemplates" :key="template.id" :value="template.id">{{ template.name }}</option>
              </select>
            </label>
          </div>

          <div v-if="showsDocumentRoleControl" class="rounded-xl border border-slate-200 bg-slate-50/70 p-3 dark:border-slate-700/50 dark:bg-slate-800/40">
            <label class="mb-1 block text-xs font-semibold text-slate-700 dark:text-slate-200">Шаг 2: роли сторон</label>
            <select
              v-model="selectedDocumentRoleBinding"
              class="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-teal-500/50 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-200"
            >
              <option value="">Оставить по шаблону · {{ getRoleLabel(inheritedDocumentRoleType) }}</option>
              <option v-for="option in DOCUMENT_ROLE_OPTIONS" :key="option.value" :value="option.value">
                {{ option.label }}
              </option>
            </select>
          </div>

      <div v-if="needsContractBinding" class="rounded-xl border border-slate-200 bg-slate-50/70 p-3 dark:border-slate-700/50 dark:bg-slate-800/40">
        <div class="mb-2 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <label class="block text-xs font-semibold text-slate-700 dark:text-slate-200">Шаг 2: документ-основание</label>
          <button
            type="button"
            class="inline-flex w-fit items-center gap-1 rounded-lg border border-slate-300 bg-white px-2.5 py-1 text-xs font-semibold text-slate-600 hover:bg-slate-100 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300 dark:hover:bg-slate-800"
            @click="externalContractOpen = !externalContractOpen"
          >
            <span class="material-icons-round text-[16px]">post_add</span>
            Внешний договор
          </button>
        </div>

        <select
          v-model="selectedBaseDocumentBinding"
          class="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-teal-500/50 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-200"
        >
          <option value="">Выберите основание</option>
          <option v-for="option in baseDocumentOptions" :key="option.value" :value="option.value">
            {{ option.label }}
          </option>
        </select>

        <p v-if="baseDocumentOptions.length > 1" class="mt-2 text-xs text-slate-500 dark:text-slate-400">
          Если в заказе несколько счетов, договоров или оферт, закрывающий документ будет привязан к выбранному основанию.
        </p>

        <form
          v-if="externalContractOpen"
          class="mt-3 space-y-3 rounded-lg border border-dashed border-teal-300 bg-teal-50/40 p-3 dark:border-teal-700/70 dark:bg-teal-950/20"
          @submit.prevent="registerExternalContract"
        >
          <div class="grid gap-3 sm:grid-cols-2">
            <label class="text-xs font-medium text-slate-600 dark:text-slate-300">Номер договора
              <input
                v-model="externalContractNumber"
                type="text"
                class="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-teal-500/50 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100"
                placeholder="Например, 44-ЭА/2026"
              />
            </label>
            <label class="text-xs font-medium text-slate-600 dark:text-slate-300">Дата договора
              <input
                v-model="externalContractDate"
                type="date"
                class="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-teal-500/50 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100"
              />
            </label>
          </div>
          <label class="block text-xs font-medium text-slate-600 dark:text-slate-300">Ссылка на договор
            <input
              v-model="externalContractUrl"
              type="url"
              class="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-teal-500/50 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100"
              placeholder="https://..."
            />
          </label>
          <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <label class="inline-flex cursor-pointer items-center gap-2 text-xs font-semibold text-slate-600 dark:text-slate-300">
              <span class="material-icons-round text-[18px] text-teal-600 dark:text-teal-400">upload_file</span>
              <span>{{ externalContractFile?.name || 'Прикрепить файл вместо ссылки' }}</span>
              <input type="file" class="hidden" :accept="DOCUMENT_FILE_ACCEPT" @change="handleExternalContractFile" />
            </label>
            <div class="flex justify-end gap-2">
              <button
                type="button"
                class="rounded-lg px-3 py-1.5 text-xs font-semibold text-slate-500 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-800"
                @click="externalContractOpen = false"
              >
                Отмена
              </button>
              <button
                type="submit"
                class="inline-flex items-center gap-1 rounded-lg bg-teal-600 px-3 py-1.5 text-xs font-semibold text-white shadow-sm hover:bg-teal-700 disabled:opacity-60"
                :disabled="isRegisteringExternalContract"
              >
                <span v-if="isRegisteringExternalContract" class="material-icons-round animate-spin text-[16px]">loop</span>
                <span v-else class="material-icons-round text-[16px]">check</span>
                Добавить договор
              </button>
            </div>
          </div>
        </form>

        <div
          v-if="customerContracts.length === 0"
          class="mt-3 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-dashed border-slate-300 bg-white p-3 text-xs text-slate-600 dark:border-slate-700 dark:bg-slate-800/50 dark:text-slate-300"
        >
          <span>У клиента нет открытых договоров.</span>
          <button
            type="button"
            class="rounded-lg bg-teal-600 px-3 py-1.5 text-xs font-semibold text-white shadow-sm hover:bg-teal-700 focus:outline-none focus:ring-2 focus:ring-teal-500/50"
            @click="openCustomerProfileForContract"
          >
            Создать открытый договор
          </button>
        </div>
        <p v-else-if="!hasClosingBaseDocument" class="mt-2 text-xs text-amber-600 dark:text-amber-400">
          Для актов и накладных нужен договор, счет или оферта.
        </p>
      </div>

          <div
            v-if="isWaybillDocument"
            class="rounded-xl border border-teal-200 bg-white p-3 dark:border-teal-800/70 dark:bg-slate-900/70"
          >
            <div class="mb-3 flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <p class="text-xs font-semibold text-slate-700 dark:text-slate-200">Шаг 3: состав накладной</p>
                <p class="text-[11px] text-slate-500 dark:text-slate-400">
                  {{ waybillProductLines.length }} товар. поз. в активном предложении
                </p>
              </div>
            </div>

            <div v-if="waybillProductLines.length" class="space-y-3">
              <div
                v-for="(line, lineIndex) in waybillProductLines"
                :key="`waybill-line-${line.product_id}-${lineIndex}`"
                class="rounded-xl border border-slate-200 bg-slate-50/70 p-3 dark:border-slate-700/60 dark:bg-slate-800/40"
              >
                <div class="mb-3 flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
                  <div class="min-w-0">
                    <p class="truncate text-sm font-semibold text-slate-800 dark:text-slate-100">{{ line.product_query || 'Товар' }}</p>
                    <p class="text-xs text-slate-500 dark:text-slate-400">
                      {{ line.logistics_components?.length || 0 }} поз. · {{ formatMoney(line.price) }} за комплект · кол-во {{ line.quantity }}
                    </p>
                  </div>
                  <span
                    class="w-fit rounded-lg px-2 py-1 text-xs font-semibold"
                    :class="lineLogisticsHasMismatch(line) ? 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300' : 'bg-teal-100 text-teal-700 dark:bg-teal-900/30 dark:text-teal-300'"
                  >
                    {{ lineLogisticsHasMismatch(line) ? 'Проверьте сумму' : 'Сумма совпадает' }}
                  </span>
                </div>

                <div class="space-y-2">
                  <div
                    v-for="(component, componentIndex) in line.logistics_components || []"
                    :key="`waybill-component-${line.product_id}-${componentIndex}`"
                    class="grid gap-2 rounded-lg border border-white bg-white p-2 dark:border-slate-700/60 dark:bg-slate-900/80 md:grid-cols-[1.4fr_100px_70px_80px_95px_32px]"
                  >
                    <textarea
                      v-model="component.title"
                      class="field-input min-h-[38px] resize-none text-xs"
                      rows="1"
                      placeholder="Название позиции"
                    />
                    <input v-model="component.country" class="field-input h-9 text-xs" placeholder="Страна" />
                    <input v-model="component.unit" class="field-input h-9 text-xs" placeholder="Ед." />
                    <input
                      :value="component.quantity_per_parent"
                      type="number"
                      min="1"
                      class="field-input h-9 text-xs"
                      title="Количество на комплект"
                      @input="handleWaybillQuantityInput(line, componentIndex, $event)"
                    />
                    <input
                      :value="component.unit_price"
                      type="number"
                      min="0"
                      step="0.01"
                      class="field-input h-9 text-xs"
                      title="Цена за единицу"
                      @input="handleWaybillUnitPriceInput(line, componentIndex, $event)"
                    />
                    <button
                      type="button"
                      class="flex h-9 w-8 items-center justify-center rounded-lg text-red-400 hover:bg-red-50 hover:text-red-600 dark:hover:bg-red-950/30"
                      @click="removeWaybillComponent(line, componentIndex)"
                    >
                      <span class="material-icons-round text-[18px]">delete</span>
                    </button>
                    <select
                      v-model="component.kind"
                      class="field-input h-9 text-xs md:col-span-2"
                      @change="rebalanceWaybillLine(line, null)"
                    >
                      <option value="indoor">внутренний блок</option>
                      <option value="outdoor">наружный блок</option>
                      <option value="accessory">аксессуар</option>
                      <option value="other">прочее</option>
                    </select>
                    <div class="flex items-center text-xs font-semibold text-slate-600 dark:text-slate-300 md:col-span-4">
                      По строке: {{ formatMoney(component.unit_price * component.quantity_per_parent * line.quantity) }}
                    </div>
                  </div>

                  <div class="flex flex-wrap items-center justify-between gap-2">
                    <p
                      v-if="lineLogisticsHasMismatch(line)"
                      class="text-xs font-semibold text-amber-700 dark:text-amber-300"
                    >
                      Состав: {{ formatMoney(lineLogisticsPerParentTotal(line)) }}, товар: {{ formatMoney(line.price) }}.
                    </p>
                    <span v-else class="text-xs text-teal-700 dark:text-teal-300">
                      Состав: {{ formatMoney(lineLogisticsPerParentTotal(line)) }}.
                    </span>
                    <button
                      type="button"
                      class="inline-flex items-center gap-1 rounded-lg border border-slate-300 bg-white px-2.5 py-1 text-xs font-semibold text-slate-600 hover:bg-slate-100 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300 dark:hover:bg-slate-800"
                      @click="addWaybillComponent(line)"
                    >
                      + позиция
                    </button>
                  </div>
                </div>
              </div>
            </div>
            <div v-else class="rounded-lg border border-dashed border-amber-300 bg-amber-50 px-3 py-4 text-center text-xs font-semibold text-amber-700 dark:border-amber-900/70 dark:bg-amber-950/20 dark:text-amber-300">
              В активном предложении нет товаров для накладной.
            </div>
          </div>

          <div v-if="showsAdditionalConditions">
            <button
              type="button"
              class="inline-flex items-center gap-1 rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs font-semibold text-slate-600 hover:bg-slate-100 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300 dark:hover:bg-slate-800"
              @click="showAdvancedSettings = !showAdvancedSettings"
            >
              <span class="material-icons-round text-[16px]">{{ showAdvancedSettings ? 'expand_less' : 'tune' }}</span>
              {{ showAdvancedSettings ? 'Скрыть дополнительные условия' : 'Дополнительные условия' }}
            </button>
          </div>

          <div v-if="showAdvancedSettings && showsAdditionalConditions" class="space-y-3">
            <AdditionalConditionsLibrary
              v-model="additionalConditions"
              :default-mode="additionalConditionsMode"
              :saving="isSavingAdditionalConditions"
            />
          </div>

          <div class="rounded-xl border border-slate-200 bg-white p-3 dark:border-slate-700/50 dark:bg-slate-900/60">
            <p class="mb-2 text-xs font-semibold text-slate-700 dark:text-slate-200">
              {{ isWaybillDocument ? 'Шаг 4: проверьте перед созданием' : 'Шаг 3: проверьте перед созданием' }}
            </p>
            <dl class="grid gap-2 text-xs sm:grid-cols-2">
              <div v-for="item in createChecklist" :key="item.label" class="flex items-center justify-between gap-3 rounded-lg bg-slate-50 px-3 py-2 dark:bg-slate-800/70">
                <dt class="text-slate-500 dark:text-slate-400">{{ item.label }}</dt>
                <dd class="truncate font-semibold text-slate-800 dark:text-slate-100">{{ item.value }}</dd>
              </div>
            </dl>
            <div class="mt-3 flex justify-end gap-2">
              <button
                type="button"
                class="rounded-lg px-3 py-2 text-sm font-semibold text-slate-500 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-800"
                @click="isCreatePanelOpen = false"
              >
                Отмена
              </button>
              <button
                type="button"
                class="inline-flex items-center gap-1 rounded-lg bg-teal-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-teal-700 disabled:opacity-60"
                :disabled="isGeneratingDoc || isDocumentTypeLocked(selectedDocumentType)"
                @click="generateDocument(selectedDocumentType)"
              >
                <span v-if="isGeneratingDoc" class="material-icons-round animate-spin text-[18px]">loop</span>
                <span v-else class="material-icons-round text-[18px]">check</span>
                Создать {{ selectedDocumentTypeItem.label }}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>
