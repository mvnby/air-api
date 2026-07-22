<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue';
import { useDebounceFn } from '@vueuse/core';
import { api } from '../../api';
import DateTimeField from '../ui/DateTimeField.vue';
import CustomerSummaryCard from '../customers/CustomerSummaryCard.vue';
import DealExecutionTab from './DealExecutionTab.vue';
import OrderDocumentsPanel from './OrderDocumentsPanel.vue';
import OrderDrawerSection from './OrderDrawerSection.vue';
import ServiceDescriptionModeSwitch from './ServiceDescriptionModeSwitch.vue';
import OrderAttachmentsPanel from '../service-attachments/OrderAttachmentsPanel.vue';
import OrderEquipmentPanel from '../equipment/OrderEquipmentPanel.vue';
import OrderWorkspaceHeader from './OrderWorkspaceHeader.vue';
import OrderCustomerObjectSummary from './OrderCustomerObjectSummary.vue';
import OrderSalesInstallationWorkspace from './OrderSalesInstallationWorkspace.vue';
import OrderProposalToolbar from './OrderProposalToolbar.vue';
import AddressSuggestInput from '../ui/AddressSuggestInput.vue';
import { confirmDialog, promptDialog } from '../../services/ui-feedback';
import type { ServiceAttachmentEquipmentOption } from '../service-attachments/types';
import type {
  ManagerOrderDetailResponse,
  ManagerOrderUpdatePayload,
  ManagerCustomerBranchItemResponse,
  ManagerServiceEstimateResponse,
  OrderProductLineResponse,
  OrderProposalResponse,
  OrderServiceLineResponse,
  ManagerInstallerResponse,
  ManagerQuickTariffResponse,
  PaymentResponse,
  PaymentCurrency,
  BankReceiptResponse,
  FxRateResponse,
  ManagerRepairComplaintPresetResponse,
  EquipmentServiceEventType,
  ManagerEquipmentDetailResponse,
  ManagerEquipmentItemResponse,
  ManagerEquipmentHistoryFromRepairOrderPayload,
  OutgoingEmailResponse,
} from '../../client';
import { ManagerOrdersService, ManagerSettingsService, ManagerMailService, ManagerRepairComplaintsService, ManagerEquipmentService } from '../../client';
import { EXECUTION_STATUS_OPTIONS, NEGOTIATION_STATUS_OPTIONS, formatMoney } from './order-utils';
import {
  buildMeasurementSummary,
  buildOrderWorkspaceViewModel,
  normalizeOrderWorkflowType,
  type OrderWorkflowType,
  type OrderWorkspaceTarget,
} from './order-workspace';
import {
  isProposalRevisionLocked,
  normalizeProposalStatus,
  proposalStatusLabel,
  type ProposalLifecycleStatus,
} from './proposal-lifecycle';
import {
  CUSTOMER_APPROVAL_STATUS_OPTIONS,
  EQUIPMENT_EVENT_OPTIONS,
  PARTS_STATUS_OPTIONS,
  REFRIGERANT_PRICING_MODE_OPTIONS,
  REPAIR_AI_DEFECT_TYPES,
  REPAIR_CHOICE_OPTIONS,
  REPAIR_WORKFLOW_STATUS_OPTIONS,
  emptyRepairMeta,
  labeledOptionsWithCurrent,
  normalizeRepairMeta,
  selectOptionsWithCurrent,
  type RepairMeta,
} from './repair-meta';
import { fromLocalDateTimeInput, toLocalDateTimeInput } from '../../utils/datetime';
import {
  useServiceDescriptionMode,
  type ServiceDescriptionLine,
  type ServiceDescriptionMode,
} from './service-description-mode';

import { getApiErrorMessage } from '../../utils/api-errors';
import { useSmartStickyHeader } from '../../composables/useSmartStickyHeader';

const props = defineProps<{
  modelValue: boolean;
  order: ManagerOrderDetailResponse | null;
  serverErrors?: Record<string, string>;
  formError?: string;
  saving?: boolean;
}>();

const emit = defineEmits<{
  'update:modelValue': [value: boolean];
  save: [payload: { orderId: number; data: ManagerOrderUpdatePayload }];
  updated: [order: ManagerOrderDetailResponse];
  deleted: [orderId: number];
  reload: [orderId: number];
}>();

const drawerScrollContainer = ref<HTMLElement | null>(null);
const { compact: compactWorkspaceHeader, reset: resetWorkspaceHeader } = useSmartStickyHeader(drawerScrollContainer);

type ProductOption = {
  id: number;
  title: string;
  price: number;
  cost?: number;
  is_inverter: boolean;
  power_cooling: number | null;
  availability_status: string;
  vitebsk_qty: number;
  minsk_qty: number;
  specs?: Record<string, any>;
};
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
type ProductLine = {
  link_id?: number | null;
  product_id: number;
  product_query: string;
  quantity: number;
  price: number;
  cost: number;
  product_country?: string | null;
  product_logistics_components?: ProductLogisticsTemplateComponent[];
  logistics_components?: OrderLogisticsComponent[] | null;
};
type ServiceLine = ServiceDescriptionLine;

const serviceKindLabels: Record<string, string> = {
  installation: 'монтаж',
  pre_install: 'закладка трассы',
  dismantling: 'демонтаж',
  maintenance: 'обслуживание',
  repair: 'ремонт',
};

const formatServiceKind = (kind?: string | null) => serviceKindLabels[String(kind || '')] || kind || '';
type OrderDrawerDraft = {
  productLines: ProductLine[];
  serviceLines: ServiceLine[];
};

const productOptions = ref<ProductOption[]>([]);
const productLookupById = ref<Record<number, ProductOption>>({});
const activeSuggestionIndex = ref<number | null>(null);
const productLookupLoading = ref(false);
const toast = ref('');
let productSearchRequestId = 0;

const status = ref('new_lead');
const orderTitle = ref('');
const workflowType = ref<OrderWorkflowType>('sales_installation');
const repairMeta = ref<RepairMeta>(emptyRepairMeta());
const managerLabels = ref<string[]>([]);
const managerLabelDraft = ref('');
const nextFollowupDate = ref('');
const assessmentDate = ref('');
const installationDate = ref('');
const comment = ref('');
const isPaid = ref(false);
const installerId = ref<number | null>(null);

const customerDeliveryAddress = ref('');
const customerBranches = ref<ManagerCustomerBranchItemResponse[]>([]);
const customerBranchId = ref<number | null>(null);
const customerBranchesLoading = ref(false);
const creatingCustomerBranch = ref(false);
const newBranchName = ref('');
const newBranchAddress = ref('');

const targetCurrency = ref<PaymentCurrency | null>(null);
const targetCurrencyAmount = ref<number | null>(null);
const targetCurrencyPayments = ref<number>(0);
const enableCurrency = ref(false);
const currentFxRate = ref<FxRateResponse | null>(null);

const searchInStock = ref(false);

watch(searchInStock, () => {
  if (activeSuggestionIndex.value !== null) {
    onProductQueryInput(activeSuggestionIndex.value);
  }
});

const syncTargetCurrencyAmountFromRate = () => {
  const rate = getActiveFxRate(targetCurrency.value);
  if (!enableCurrency.value || !rate || totalPreview.value <= 0) return;
  targetCurrencyAmount.value = Number((totalPreview.value / rate).toFixed(2));
};

watch(enableCurrency, async (val) => {
  if (!val) {
    targetCurrency.value = null;
    targetCurrencyAmount.value = null;
    targetCurrencyPayments.value = 0;
  } else if (!targetCurrency.value) {
    targetCurrency.value = 'USD';
    try {
       currentFxRate.value = await ManagerSettingsService.getFxRate();
       syncTargetCurrencyAmountFromRate();
    } catch (e) {
       console.warn('Failed to fetch FX rate', e);
       enableCurrency.value = false;
       setToast('Не удалось загрузить курс валют', 'error');
    }
  }
});

watch(targetCurrency, (newCurrency) => {
  if (newCurrency === 'EUR' && !hasManualEurRate.value) {
    targetCurrency.value = 'USD';
    return;
  }
  syncTargetCurrencyAmountFromRate();
});

// Negotiation stage properties
const measurementRequired = ref(false);
const measurerId = ref<number | null>(null);
const measurementResult = ref('');
const additionalConditions = ref('');
const proposalStatus = ref<ProposalLifecycleStatus>('draft');
const negotiationStatus = ref('awaiting_offer');
const executionStatus = ref('needs_schedule');
const executionWithoutPayment = ref(false);
const executionWithoutPaymentReason = ref('');
const autoExecutionOnPayment = ref(false);
const autoCloseOnPayment = ref(false);
const activeProposalId = ref<number | null>(null);
const proposalActionLoading = ref(false);
const executionStatusLabel = computed(() => (
  EXECUTION_STATUS_OPTIONS.find((option) => option.value === executionStatus.value)?.label || 'Назначить работы'
));

const setNegotiationStatus = (value: string) => {
  negotiationStatus.value = value;
};

const setExecutionStatus = (value: string) => {
  executionStatus.value = value;
};

const installersList = ref<ManagerInstallerResponse[]>([]);

const productLines = ref<ProductLine[]>([]);
const supplyRequests = ref<any[]>([]);
const supplyActionLoadingLineId = ref<number | null>(null);
const serviceLines = ref<ServiceLine[]>([]);
const editingServiceLineIndex = ref<number | null>(null);
const savedLinesSnapshot = ref('');
const savedFormSnapshot = ref('');
const pendingDraftClearOrderId = ref<number | null>(null);
const activeServiceSuggestionIndex = ref<number | null>(null);
const serviceTariffOptions = ref<ManagerQuickTariffResponse[]>([]);
const serviceTariffLookupLoading = ref(false);
let serviceTariffSearchRequestId = 0;
let customerBranchesRequestId = 0;
const estimateOptions = ref<ManagerServiceEstimateResponse[]>([]);
const estimateOptionsLoading = ref(false);
const estimateImportMode = ref<'detailed' | 'collapsed'>('detailed');
const {
  preferredMode: serviceDescriptionMode,
  rememberMode: setDefaultServiceDescriptionMode,
  applyTariffTemplate: applyTariffTemplateToLine,
  replaceLineDescription,
} = useServiceDescriptionMode();
const selectedEstimateId = ref<number | null>(null);
const estimateSearchQuery = ref('');
const importingEstimate = ref(false);
const showEstimateImport = ref(false);
const repairComplaintPresets = ref<ManagerRepairComplaintPresetResponse[]>([]);
const repairComplaintSearch = ref('');
const repairComplaintsLoading = ref(false);
const repairAiDefectType = ref(REPAIR_AI_DEFECT_TYPES[0]?.value || '');
const repairAiExtraContext = ref('');
const repairAiAllowAssumptions = ref(false);
const repairAiPolishExisting = ref(true);
const repairAiGenerating = ref(false);
const repairEquipment = ref<ManagerEquipmentItemResponse[]>([]);
const repairEquipmentLoading = ref(false);
const repairEquipmentError = ref('');
const selectedRepairEquipmentId = ref<number | null>(null);
const selectedRepairEquipmentDetail = ref<ManagerEquipmentDetailResponse | null>(null);
const repairEquipmentHistoryLoading = ref(false);
const creatingRepairEquipment = ref(false);
const recordingRepairHistory = ref(false);
const repairHistoryEventType = ref<EquipmentServiceEventType | ''>('');
const repairHistoryNotes = ref('');
const payments = ref<PaymentResponse[]>([]);
const bankReceipts = ref<BankReceiptResponse[]>([]);
const bankReceiptsLoading = ref(false);
const linkedEquipmentOptions = ref<ServiceAttachmentEquipmentOption[]>([]);
const equipmentPanelRef = ref<InstanceType<typeof OrderEquipmentPanel> | null>(null);
const documentsPanelRef = ref<InstanceType<typeof OrderDocumentsPanel> | null>(null);
const proposalToolbarRef = ref<InstanceType<typeof OrderProposalToolbar> | null>(null);
const executionWorkspaceSection = ref<'documents' | 'payments' | null>(null);
const activeWorkspaceTarget = ref<OrderWorkspaceTarget | null>(null);
const orderEmails = ref<OutgoingEmailResponse[]>([]);
const orderEmailsLoaded = ref(false);
let orderEmailsRequestId = 0;

const executorOptions = computed(() => {
  const selectedIds = new Set<number>();
  if (installerId.value !== null) selectedIds.add(installerId.value);
  if (measurerId.value !== null) selectedIds.add(measurerId.value);
  return installersList.value.filter((inst) => inst.is_active || selectedIds.has(inst.id));
});
const attachingReceiptId = ref<number | null>(null);
const localServerErrors = ref<Record<string, string>>({});

const createDefaultDrawerSections = () => ({
  website: false,
  clientDetails: false,
  planningDetails: false,
  repair: true,
  proposals: false,
  documents: false,
  payments: false,
  execution: false,
});
type DrawerSectionsState = ReturnType<typeof createDefaultDrawerSections>;
const expandedDrawerSections = ref(createDefaultDrawerSections());
const initializedOrderId = ref<number | null>(null);

const localFormError = ref('');
const showCustomerModal = ref(false);
const savingCustomerInline = ref(false);
const showManagerLabelInput = ref(false);
const showBranchFields = ref(false);

const showChangeCustomerModal = ref(false);
const customerSearchQuery = ref('');
const customerSearchResults = ref<any[]>([]);
const isCustomerSearchLoading = ref(false);
let customerSearchRequestId = 0;

const debouncedSearchCustomer = useDebounceFn(async (query: string) => {
  const requestId = ++customerSearchRequestId;
  if (!query || query.length < 3) {
    customerSearchResults.value = [];
    isCustomerSearchLoading.value = false;
    return;
  }
  isCustomerSearchLoading.value = true;
  try {
    const res = await api.getManagerCustomers(1, 10, query);
    if (requestId !== customerSearchRequestId || query !== customerSearchQuery.value) return;
    customerSearchResults.value = res.items || [];
  } catch (error) {
    if (requestId !== customerSearchRequestId) return;
    console.error('Customer search error', error);
  } finally {
    if (requestId === customerSearchRequestId) {
      isCustomerSearchLoading.value = false;
    }
  }
}, 400);

const onCustomerSearchInput = () => {
  debouncedSearchCustomer(customerSearchQuery.value);
};

const assignNewCustomer = async (newCustomer: any) => {
  if (!props.order?.id) return;
  try {
    const res = await api.patchManagerOrder(props.order.id, { customer_id: newCustomer.id });
    emit('updated', res);
    await initForm(res);
    showChangeCustomerModal.value = false;
    setToast('Клиент успешно изменен', 'success');
    emit('reload', res.id);
  } catch (error) {
    setToast(`Ошибка смены клиента: ${getApiErrorMessage(error)}`, 'error');
  }
};

const resetCustomerBranches = () => {
  customerBranchesRequestId += 1;
  customerBranches.value = [];
  customerBranchId.value = null;
  customerBranchesLoading.value = false;
  creatingCustomerBranch.value = false;
  newBranchName.value = '';
  newBranchAddress.value = '';
};

const loadCustomerBranches = async (customerId: number, preferredBranchId?: number | null) => {
  const requestId = ++customerBranchesRequestId;
  customerBranchesLoading.value = true;
  try {
    const response = await api.getManagerCustomerBranches(customerId);
    if (requestId !== customerBranchesRequestId) return;
    customerBranches.value = response.items || [];
    if (!customerBranches.value.length) {
      customerBranchId.value = null;
      return;
    }
    // Keep "Без филиала" when order explicitly stores null branch.
    if (preferredBranchId === null) {
      customerBranchId.value = null;
      return;
    }
    const preferredFromOrder = typeof preferredBranchId === 'number'
      ? customerBranches.value.find((branch) => branch.id === preferredBranchId)
      : null;
    const preferred = preferredFromOrder
      || customerBranches.value.find((branch) => branch.is_default)
      || customerBranches.value[0]
      || null;
    customerBranchId.value = preferred?.id || null;
  } catch (error) {
    if (requestId !== customerBranchesRequestId) return;
    console.error('Failed to load customer branches', error);
    resetCustomerBranches();
  } finally {
    if (requestId === customerBranchesRequestId) {
      customerBranchesLoading.value = false;
    }
  }
};

const onCustomerBranchChange = (event: Event) => {
  const value = (event.target as HTMLSelectElement).value;
  customerBranchId.value = value ? Number(value) : null;
  const branch = customerBranches.value.find((item) => item.id === customerBranchId.value) || null;
  if (branch) {
    customerDeliveryAddress.value = branch.delivery_address;
  }
};

const createCustomerBranch = async () => {
  const customerId = customer.value?.id;
  if (!customerId || creatingCustomerBranch.value) return;
  const deliveryAddress = newBranchAddress.value.trim();
  if (!deliveryAddress) {
    setToast('Введите адрес филиала', 'error');
    return;
  }

  creatingCustomerBranch.value = true;
  try {
    const created = await api.createManagerCustomerBranch(customerId, {
      name: newBranchName.value.trim() || undefined,
      delivery_address: deliveryAddress,
      is_default: customerBranches.value.length === 0,
    });
    customerBranches.value = [created, ...customerBranches.value.filter((branch) => branch.id !== created.id)];
    customerBranchId.value = created.id;
    customerDeliveryAddress.value = created.delivery_address;
    newBranchName.value = '';
    newBranchAddress.value = '';
    setToast('Филиал создан', 'success');
  } catch (error) {
    setToast(`Ошибка создания филиала: ${getApiErrorMessage(error)}`, 'error');
  } finally {
    creatingCustomerBranch.value = false;
  }
};

const resetRepairEquipment = () => {
  repairEquipment.value = [];
  selectedRepairEquipmentId.value = null;
  selectedRepairEquipmentDetail.value = null;
  repairEquipmentError.value = '';
  repairHistoryEventType.value = '';
  repairHistoryNotes.value = '';
};

const loadRepairEquipmentDetail = async (equipmentId: number) => {
  repairEquipmentHistoryLoading.value = true;
  repairEquipmentError.value = '';
  try {
    selectedRepairEquipmentDetail.value = await ManagerEquipmentService.getManagerEquipment(equipmentId, 10);
  } catch (error) {
    selectedRepairEquipmentDetail.value = null;
    repairEquipmentError.value = `Не удалось загрузить историю оборудования: ${getApiErrorMessage(error)}`;
  } finally {
    repairEquipmentHistoryLoading.value = false;
  }
};

const selectRepairEquipment = async (equipmentId: number) => {
  selectedRepairEquipmentId.value = equipmentId;
  await loadRepairEquipmentDetail(equipmentId);
};

const loadRepairEquipment = async () => {
  const customerId = customer.value?.id;
  if (!customerId || !isRepairWorkflow.value) {
    resetRepairEquipment();
    return;
  }
  repairEquipmentLoading.value = true;
  repairEquipmentError.value = '';
  try {
    const branchId = customerBranchId.value || null;
    const response = await ManagerEquipmentService.listManagerEquipment(customerId, branchId, 1, 50, false);
    repairEquipment.value = response.items || [];
    if (selectedRepairEquipmentId.value && !repairEquipment.value.some((item) => item.id === selectedRepairEquipmentId.value)) {
      selectedRepairEquipmentId.value = null;
      selectedRepairEquipmentDetail.value = null;
    }
    if (!selectedRepairEquipmentId.value && repairEquipment.value.length) {
      await selectRepairEquipment(repairEquipment.value[0]!.id);
    } else if (selectedRepairEquipmentId.value) {
      await loadRepairEquipmentDetail(selectedRepairEquipmentId.value);
    }
  } catch (error) {
    repairEquipment.value = [];
    selectedRepairEquipmentDetail.value = null;
    repairEquipmentError.value = `Не удалось загрузить оборудование клиента: ${getApiErrorMessage(error)}`;
  } finally {
    repairEquipmentLoading.value = false;
  }
};

const createRepairEquipmentFromMeta = async () => {
  const customerId = customer.value?.id;
  if (!customerId || creatingRepairEquipment.value) return;
  const meta = repairMeta.value;
  const displayName = trimOrNull(meta.equipment_name) || trimOrNull(orderTitle.value) || trimOrNull(props.order?.title || '');
  const hasPassportData = Boolean(
    displayName
    || trimOrNull(meta.equipment_brand)
    || trimOrNull(meta.equipment_model)
    || trimOrNull(meta.equipment_serial_number)
    || trimOrNull(meta.equipment_inventory_number),
  );
  if (!hasPassportData) {
    repairEquipmentError.value = 'Заполните название, бренд, модель, серийный или инвентарный номер';
    return;
  }
  creatingRepairEquipment.value = true;
  repairEquipmentError.value = '';
  try {
    const notes = [
      meta.equipment_power ? `Мощность: ${meta.equipment_power}` : '',
      meta.equipment_commissioning_date ? `Ввод в эксплуатацию: ${meta.equipment_commissioning_date}` : '',
    ].filter(Boolean).join('\n') || null;
    const created = await ManagerEquipmentService.createManagerEquipment({
      customer_id: customerId,
      customer_branch_id: customerBranchId.value || null,
      equipment_type: 'hvac',
      display_name: displayName,
      brand: trimOrNull(meta.equipment_brand),
      model: trimOrNull(meta.equipment_model),
      serial: trimOrNull(meta.equipment_serial_number),
      inventory_number: trimOrNull(meta.equipment_inventory_number),
      location_hint: trimOrNull(compactObjectAddress.value),
      refrigerant_type: trimOrNull(meta.refrigerant_type),
      notes,
    });
    selectedRepairEquipmentId.value = created.id;
    await loadRepairEquipment();
    await loadRepairEquipmentDetail(created.id);
    setToast('Оборудование создано из полей ремонта', 'success');
  } catch (error) {
    repairEquipmentError.value = `Не удалось создать оборудование: ${getApiErrorMessage(error)}`;
  } finally {
    creatingRepairEquipment.value = false;
  }
};

const recordRepairHistoryFromOrder = async () => {
  if (!props.order?.id || !selectedRepairEquipmentId.value || recordingRepairHistory.value) return;
  recordingRepairHistory.value = true;
  repairEquipmentError.value = '';
  try {
    const payload: ManagerEquipmentHistoryFromRepairOrderPayload = {
      order_id: props.order.id,
      event_type: repairHistoryEventType.value || null,
      notes: trimOrNull(repairHistoryNotes.value),
    };
    await ManagerEquipmentService.createManagerEquipmentHistoryFromRepairOrder(selectedRepairEquipmentId.value, payload);
    repairHistoryEventType.value = '';
    repairHistoryNotes.value = '';
    await loadRepairEquipmentDetail(selectedRepairEquipmentId.value);
    setToast('Событие записано в историю оборудования', 'success');
  } catch (error) {
    repairEquipmentError.value = `Не удалось записать историю: ${getApiErrorMessage(error)}`;
  } finally {
    recordingRepairHistory.value = false;
  }
};

const customer = computed(() => props.order?.customer ?? null);
const customerDisplayName = computed(() => (
  customer.value?.full_legal_name
  || customer.value?.name
  || ''
));
const isWebsiteOrder = computed(() => props.order?.lead_source === 'site');
const isB2cCustomer = computed(() => {
  if (!customer.value) return true; // defaults to B2C if unknown
  return customer.value.type !== 'company';
});
const displayOrderTitle = computed(() => (
  orderTitle.value.trim()
  || customer.value?.full_legal_name
  || customer.value?.name
  || 'Без названия'
));
const selectedCustomerBranch = computed(() => (
  customerBranches.value.find((branch) => branch.id === customerBranchId.value)
  || props.order?.customer_branch
  || null
));
const selectedRepairEquipment = computed(() => (
  repairEquipment.value.find((item) => item.id === selectedRepairEquipmentId.value) || null
));
const compactObjectAddress = computed(() => (
  customerDeliveryAddress.value.trim()
  || selectedCustomerBranch.value?.delivery_address
  || ''
));
const customerDetailsSummary = computed(() => {
  if (customerBranchId.value) return 'Филиал и дополнительные данные';
  return 'Адрес и комментарий';
});
const filteredEstimateOptions = computed(() => {
  const query = estimateSearchQuery.value.trim().toLowerCase();
  if (!query) return estimateOptions.value;
  return estimateOptions.value.filter((estimate) => {
    const byTitle = (estimate.title || '').toLowerCase().includes(query);
    const byId = String(estimate.id).includes(query);
    return byTitle || byId;
  });
});
const orderProposals = computed(() => {
  const proposals = props.order?.proposals || [];
  return [...proposals]
    .filter((proposal) => !proposal.is_archived)
    .sort((a, b) => Number(a.sort_order || 0) - Number(b.sort_order || 0) || Number(a.id) - Number(b.id));
});
const selectedOrderProposal = computed(() => (
  orderProposals.value.find((proposal) => proposal.is_selected)
  || orderProposals.value[0]
  || null
));
const activeProposal = computed(() => (
  orderProposals.value.find((proposal) => proposal.id === activeProposalId.value)
  || selectedOrderProposal.value
));
const activeProposalStatus = computed(() => normalizeProposalStatus(activeProposal.value?.status || proposalStatus.value));
const activeProposalLocked = computed(() => isProposalRevisionLocked(activeProposalStatus.value));
const activeProposalLineLabel = computed(() => {
  const proposal = activeProposal.value;
  if (!proposal) return 'Предложение не создано';
  const count = (proposal.product_lines?.length || 0) + (proposal.service_lines?.length || 0);
  const mod100 = count % 100;
  const mod10 = count % 10;
  const noun = mod100 >= 11 && mod100 <= 14 ? 'позиций' : mod10 === 1 ? 'позиция' : mod10 >= 2 && mod10 <= 4 ? 'позиции' : 'позиций';
  return `${proposal.name} · ${proposalStatusLabel(proposal.status)} · ${count} ${noun} · ${formatMoney(proposal.total_amount || 0)}`;
});
const paymentsSectionSummary = computed(() => (
  `оплачено ${formatMoney(totalPaymentsPreview.value)} · остаток ${formatMoney(balanceDuePreview.value)} · итого ${formatMoney(totalPreview.value)} · маржа ${formatMoney(marginPreview.value)}`
));
const documentEmailStatus = computed<'unknown' | 'none' | 'pending' | 'sent' | 'failed'>(() => {
  if (!orderEmailsLoaded.value) return 'unknown';
  const latestDocumentEmail = [...orderEmails.value]
    .filter((email) => Boolean(email.attachments?.length))
    .sort((left, right) => Date.parse(right.created_at) - Date.parse(left.created_at))[0];
  if (!latestDocumentEmail) return 'none';
  if (latestDocumentEmail.status === 'sent') return 'sent';
  if (latestDocumentEmail.status === 'pending') return 'pending';
  if (latestDocumentEmail.status === 'failed') return 'failed';
  return 'none';
});
const normalizeDocumentNumber = (value: string) => value.toUpperCase().replace(/[^A-ZА-ЯЁ0-9]/g, '');
const missingReferencedInvoice = computed(() => {
  const invoiceNumbers = new Set(
    orderDocuments.value
      .filter((document) => document.doc_type === 'invoice')
      .map((document) => normalizeDocumentNumber(document.number || ''))
      .filter(Boolean),
  );
  for (const payment of payments.value) {
    const purpose = payment.bank_receipt?.payment_purpose || payment.comment || '';
    const match = purpose.match(/сч[её]т(?:у|а|ом|е)?\s*(?:№\s*)?([A-ZА-ЯЁ0-9][A-ZА-ЯЁ0-9/-]{2,})/iu);
    const referencedNumber = match?.[1]?.trim();
    if (referencedNumber && !invoiceNumbers.has(normalizeDocumentNumber(referencedNumber))) return referencedNumber;
  }
  return null;
});
const orderWorkspace = computed(() => buildOrderWorkspaceViewModel({
  status: status.value,
  negotiationStatus: negotiationStatus.value,
  executionStatus: executionStatus.value,
  statusChangedAt: props.order?.status_changed_at,
  negotiationStatusChangedAt: props.order?.negotiation_status_changed_at,
  executionStatusChangedAt: props.order?.execution_status_changed_at,
  installationDate: installationDate.value,
  activeProposalId: selectedOrderProposal.value?.id || null,
  activeProposalStatus: selectedOrderProposal.value?.status || proposalStatus.value,
  activeProposalLineCount: (selectedOrderProposal.value?.product_lines?.length || 0) + (selectedOrderProposal.value?.service_lines?.length || 0),
  activeProposalTotal: Number(selectedOrderProposal.value?.total_amount || 0),
  autoExecutionOnPayment: autoExecutionOnPayment.value,
  productCount: productLines.value.length,
  serviceCount: serviceLines.value.length,
  linkedEquipmentCount: props.order?.linked_equipment_count || 0,
  documents: orderDocuments.value,
  documentEmailStatus: documentEmailStatus.value,
  missingReferencedInvoice: missingReferencedInvoice.value,
  total: totalPreview.value,
  paid: totalPaymentsPreview.value,
  balance: balanceDuePreview.value,
}));
const candidateBankReceipts = computed(() => bankReceipts.value.filter((receipt) => receipt.status === 'requires_review'));
const hasDebtForBankReceipts = computed(() => balanceDuePreview.value > 0 && Boolean(props.order?.customer?.inn));
const draftKey = computed(() => (
  props.order ? `manager_order_drawer_draft_${props.order.id}_${activeProposalId.value || 'default'}` : ''
));
const drawerSectionsKey = computed(() => (
  props.order ? `manager_order_drawer_sections_${props.order.id}` : ''
));
const hasManualEurRate = computed(() => Boolean(currentFxRate.value?.eur_byn));

const getActiveFxRate = (currency: PaymentCurrency | null): number | null => {
  if (!currentFxRate.value || !currency) return null;
  if (currency === 'USD') return currentFxRate.value.usd_byn ?? null;
  if (currency === 'EUR') return currentFxRate.value.eur_byn ?? null;
  return null;
};

const toastType = ref<'success' | 'error'>('success');
const setToast = (message: string, type: 'success' | 'error' = 'success') => {
  toast.value = message;
  toastType.value = type;
  window.setTimeout(() => {
    if (toast.value === message) toast.value = '';
  }, 3000);
};

const supplyStatusLabels: Record<string, string> = {
  draft: 'черновик',
  awaiting_reply: 'ждем ответ',
  reserved: 'бронь',
  ordered: 'заказано',
  ready_for_pickup: 'готово к забору',
  picked_up: 'забрано',
  received: 'получено',
  canceled: 'отменено',
};

const loadOrderSupplyRequests = async (orderId: number) => {
  try {
    const response = await api.listSupplyRequests({ orderId, limit: 100 });
    supplyRequests.value = response.items || [];
  } catch (error) {
    console.warn('Failed to load supply requests for order', error);
    supplyRequests.value = [];
  }
};

const loadOrderEmails = async (orderId: number) => {
  const requestId = ++orderEmailsRequestId;
  try {
    const response = await ManagerMailService.listManagerOrderOutgoingEmails(orderId, 20);
    if (requestId !== orderEmailsRequestId || props.order?.id !== orderId) return;
    orderEmails.value = response.items || [];
    orderEmailsLoaded.value = true;
  } catch (error) {
    if (requestId !== orderEmailsRequestId) return;
    console.warn('Failed to load order email summary', error);
    orderEmails.value = [];
    orderEmailsLoaded.value = false;
  }
};

const supplyBadgeForLine = (line: ProductLine) => {
  if (!line.link_id) return null;
  for (const request of supplyRequests.value) {
    const requestLine = (request.lines || []).find((item: any) => Number(item.order_product_link_id) === Number(line.link_id));
    if (requestLine) {
      return {
        label: supplyStatusLabels[requestLine.status] || requestLine.status,
        requestId: request.id,
        status: requestLine.status,
      };
    }
  }
  return null;
};

const createSupplyFromProductLine = async (line: ProductLine, intent: 'order' | 'reserve') => {
  if (!props.order?.id) return;
  if (!line.link_id) {
    setToast('Сначала сохраните заказ, чтобы создать поставку по строке.', 'error');
    return;
  }
  supplyActionLoadingLineId.value = line.link_id;
  try {
    await api.createSupplyRequestFromOrderLines({
      order_product_link_ids: [line.link_id],
      intent,
    });
    setToast(intent === 'reserve' ? 'Строка отправлена в бронирование.' : 'Строка добавлена в поставки.');
    await loadOrderSupplyRequests(props.order.id);
  } catch (error) {
    setToast(`Не удалось создать поставку: ${getApiErrorMessage(error)}`, 'error');
  } finally {
    supplyActionLoadingLineId.value = null;
  }
};

const normalizeManagerLabel = (value: string) => value.trim().replace(/\s+/g, ' ');

const addManagerLabel = () => {
  const label = normalizeManagerLabel(managerLabelDraft.value);
  if (!label) return;
  const exists = managerLabels.value.some((item) => item.toLocaleLowerCase('ru-RU') === label.toLocaleLowerCase('ru-RU'));
  if (!exists) managerLabels.value.push(label);
  managerLabelDraft.value = '';
  showManagerLabelInput.value = false;
};

const removeManagerLabel = (label: string) => {
  managerLabels.value = managerLabels.value.filter((item) => item !== label);
};

const formatDateTime = (value?: string | null) => {
  if (!value) return null;
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return null;
  return parsed.toLocaleString('ru-RU', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
};

const trimOrNull = (value: string) => {
  const normalized = value.trim();
  return normalized || null;
};

const equipmentEventLabel = (value?: EquipmentServiceEventType | null) => (
  EQUIPMENT_EVENT_OPTIONS.find((option) => option.value === value)?.label || 'Другое'
);

const equipmentTitle = (item?: Pick<ManagerEquipmentItemResponse, 'display_name' | 'brand' | 'model' | 'serial' | 'inventory_number'> | null) => {
  if (!item) return 'Оборудование';
  const name = item.display_name?.trim();
  if (name) return name;
  const parts = [item.brand, item.model, item.serial || item.inventory_number].map((value) => value?.trim()).filter(Boolean);
  return parts.join(' ') || 'Оборудование';
};

const equipmentSubtitle = (item: ManagerEquipmentItemResponse | ManagerEquipmentDetailResponse) => {
  const parts = [
    item.brand,
    item.model,
    item.serial ? `SN ${item.serial}` : '',
    item.inventory_number ? `Инв. ${item.inventory_number}` : '',
    item.location_hint,
    item.refrigerant_type,
  ].map((value) => value?.trim()).filter(Boolean);
  return parts.join(' · ') || 'Паспортные данные не заполнены';
};

const repairHistoryLine = (item: NonNullable<ManagerEquipmentDetailResponse['recent_history']>[number]) => {
  const parts = [
    item.complaint_snapshot,
    item.diagnostic_result,
    item.repair_recommendation,
    item.refrigerant_type ? `Хладагент ${item.refrigerant_type}` : '',
    item.refrigerant_amount,
    item.not_repairable ? 'Не ремонтируется' : '',
    item.not_repairable_reason,
    item.notes,
  ].map((value) => value?.trim()).filter(Boolean);
  return parts.join(' · ') || 'Без подробностей';
};

const copyText = async (value: string | null | undefined, label: string) => {
  const normalized = String(value || '').trim();
  if (!normalized) {
    setToast(`${label} отсутствует`, 'error');
    return;
  }

  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(normalized);
    } else {
      const textarea = document.createElement('textarea');
      textarea.value = normalized;
      textarea.setAttribute('readonly', 'true');
      textarea.style.position = 'absolute';
      textarea.style.left = '-9999px';
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand('copy');
      document.body.removeChild(textarea);
    }
    setToast(`${label} скопирован`, 'success');
  } catch (error) {
    setToast(`Не удалось скопировать ${label.toLowerCase()}`, 'error');
  }
};

const websiteProductSummaryLines = computed(() => {
  return (props.order?.product_lines ?? []).map((line) => ({
    id: line.id,
    title: line.product_title || `Товар #${line.product_id}`,
    quantity: line.quantity,
    lineTotal: line.line_total,
    installationIncluded: Boolean(line.is_installation_included),
    installationPrice: Number(line.installation_price || 0),
  }));
});

const websiteServiceSummaryLines = computed(() => {
  return (props.order?.service_lines ?? []).map((line) => ({
    id: line.id,
    title: line.service_title || 'Услуга',
    quantity: line.quantity,
    lineTotal: line.line_total,
  }));
});

const toggleHold = async () => {
    if (!props.order) return;
    const hold = !props.order.is_on_hold;
    try {
        const updatedOrder = await api.patchManagerOrder(
            props.order.id,
            { is_on_hold: hold, on_hold_reason: hold ? 'Переговоры / Ручная пауза' : '' },
        );
        emit('updated', updatedOrder);
        setToast(hold ? 'Сделка поставлена на паузу' : 'Сделка снята с паузы', 'success');
    } catch {
        setToast('Ошибка паузы', 'error');
    }
};

const isCompanyOrder = computed(() => props.order?.customer?.type === 'company' || !!props.order?.customer?.inn);
const orderDocuments = computed(() => props.order?.documents || []);
const hasOrderContract = computed(() => orderDocuments.value.some((doc) => doc.doc_type === 'contract'));
const hasContract = computed(() => (isCompanyOrder.value ? !!props.order?.customer_contract_id : false) || hasOrderContract.value);
const hasOrderInvoice = computed(() => orderDocuments.value.some((doc) => doc.doc_type === 'invoice'));
const hasClosingBaseDocument = computed(() => hasContract.value || hasOrderInvoice.value);
const websiteOrderSummary = computed(() => {
  const lines = websiteProductSummaryLines.value.length + websiteServiceSummaryLines.value.length;
  const parts = [];
  const createdAt = formatDateTime(props.order?.created_at);
  if (createdAt) parts.push(`создан ${createdAt}`);
  parts.push(`${lines} поз.`);
  if (customerDeliveryAddress.value) parts.push(customerDeliveryAddress.value);
  return parts.join(' · ');
});
const planningSummary = computed(() => {
  const parts = [buildMeasurementSummary({
    required: measurementRequired.value,
    date: assessmentDate.value,
    result: measurementResult.value,
    kind: workflowType.value === 'repair' ? 'diagnostic' : 'measurement',
    formatDate: formatDateTime,
  })];
  if (installationDate.value) parts.push(`${workDateLabel.value.toLowerCase()} ${formatDateTime(installationDate.value)}`);
  return parts.join(' · ');
});
const planningDetailsSummary = computed(() => {
  const parts = [];
  if (measurerId.value) parts.push('замерщик назначен');
  if (measurementResult.value.trim()) parts.push('есть результат замера');
  if (customerBranchId.value) parts.push('выбран филиал');
  if (newBranchAddress.value.trim()) parts.push('готовится новый филиал');
  return parts.join(' · ') || 'дополнительные поля не заполнены';
});
const isRepairWorkflow = computed(() => workflowType.value === 'repair');
const showProductLinesSection = computed(() => workflowType.value === 'sales_installation');
const planningTitle = computed(() => {
  if (workflowType.value === 'repair') return 'Диагностика и выезд';
  if (workflowType.value === 'maintenance') return 'Планирование обслуживания';
  if (workflowType.value === 'service_work') return 'Планирование работ';
  return 'Планирование';
});
const workDateLabel = computed(() => {
  if (workflowType.value === 'repair') return 'Дата диагностики / ремонта';
  if (workflowType.value === 'maintenance') return 'Дата обслуживания';
  if (workflowType.value === 'service_work') return 'Дата работ';
  return 'Дата монтажа';
});
const repairWorkflowStatusLabel = computed(() => (
  REPAIR_WORKFLOW_STATUS_OPTIONS.find((item) => item.value === repairMeta.value.repair_status)?.label || ''
));
const repairSectionSummary = computed(() => {
  const parts = [];
  if (repairWorkflowStatusLabel.value) parts.push(repairWorkflowStatusLabel.value);
  if (repairMeta.value.equipment_name.trim()) parts.push(repairMeta.value.equipment_name.trim());
  const serial = repairMeta.value.equipment_serial_number.trim() || repairMeta.value.equipment_inventory_number.trim();
  if (serial) parts.push(serial);
  if (repairMeta.value.customer_complaint.trim()) parts.push('есть жалоба');
  if (repairMeta.value.diagnostic_result.trim()) parts.push('есть диагностика');
  if (repairMeta.value.repair_recommendation.trim() || repairMeta.value.technical_conclusion.trim()) parts.push('есть вывод');
  return parts.join(' · ') || 'данные для диагностики и дефектного акта';
});
const filteredRepairComplaintPresets = computed(() => {
  const q = repairComplaintSearch.value.trim().toLowerCase();
  const items = repairComplaintPresets.value.filter((item) => {
    if (!q) return true;
    return [
      item.customer_phrase,
      item.document_wording,
      item.likely_diagnosis,
      item.complaint_group,
    ].some((value) => String(value || '').toLowerCase().includes(q));
  });
  return items.slice(0, 12);
});
const selectedRepairAiDefect = computed(() => (
  REPAIR_AI_DEFECT_TYPES.find((item) => item.value === repairAiDefectType.value) || REPAIR_AI_DEFECT_TYPES[0]
));
const repairStructuredJson = computed(() => {
  const payload = {
    structured_diagnosis: repairMeta.value.structured_diagnosis || {},
    defect_act_blocks: repairMeta.value.defect_act_blocks || {},
    risks: repairMeta.value.risks || [],
    recommended_actions: repairMeta.value.recommended_actions || [],
  };
  return JSON.stringify(payload, null, 2);
});
const repairPossibleOptions = computed(() => selectOptionsWithCurrent(REPAIR_CHOICE_OPTIONS, repairMeta.value.repair_possible));
const repairNotViableOptions = computed(() => selectOptionsWithCurrent(REPAIR_CHOICE_OPTIONS, repairMeta.value.repair_not_viable));
const customerApprovalStatusOptions = computed(() => labeledOptionsWithCurrent(CUSTOMER_APPROVAL_STATUS_OPTIONS, repairMeta.value.customer_approval_status));
const partsStatusOptions = computed(() => labeledOptionsWithCurrent(PARTS_STATUS_OPTIONS, repairMeta.value.parts_status));
watch(repairAiDefectType, (value) => {
  if (isRepairWorkflow.value) {
    repairMeta.value.fault_type = value;
  }
});
const buildRepairMetaPayload = () => normalizeRepairMeta({
  ...repairMeta.value,
  fault_type: repairMeta.value.fault_type || repairAiDefectType.value,
}, { defaultRepairStatus: isRepairWorkflow.value });
const documentSectionSummary = computed(() => {
  const count = orderDocuments.value.length;
  if (!count) return 'Документов нет';
  const mod100 = count % 100;
  const mod10 = count % 10;
  const noun = mod100 >= 11 && mod100 <= 14 ? 'документов' : mod10 === 1 ? 'документ' : mod10 >= 2 && mod10 <= 4 ? 'документа' : 'документов';
  return `${count} ${noun}${hasContract.value ? '' : ' · договор не создан'}`;
});
const documentSectionHasError = computed(() => isCompanyOrder.value && !props.order?.customer_contract_id && !hasClosingBaseDocument.value);
const beforeDocumentGenerate = async (type: string) => {
  if (!props.order?.id) return false;
  let mutated = false;
  if (type === 'offer' || type === 'tn2' || type === 'ttn1') {
    await saveCurrentProposalLines();
    mutated = true;
  }
  if (type === 'defect_act') {
    repairMeta.value = buildRepairMetaPayload();
    await ManagerOrdersService.patchManagerOrder(props.order.id, {
      repair_meta: buildRepairMetaPayload() as any,
      measurement_result: measurementResult.value,
    });
    mutated = true;
    emit('reload', props.order.id);
  }
  return { mutated };
};

const handleDocumentPanelToast = (payload: { message: string; type?: 'success' | 'error' }) => {
  setToast(payload.message, payload.type || 'success');
  if (props.order?.id) window.setTimeout(() => void loadOrderEmails(props.order!.id), 500);
};

const refreshOrderFromDocumentsPanel = () => {
  if (props.order?.id) {
    emit('reload', props.order.id);
    void loadOrderEmails(props.order.id);
  }
};

const newPaymentAmount = ref<number | null>(null);
const newPaymentType = ref<string>('prepayment');
const isAddingPayment = ref(false);

const addPayment = async () => {
  if (!props.order?.id || !newPaymentAmount.value) return;
  if (enableCurrency.value) {
    if (!targetCurrency.value) {
      setToast('Сначала выберите валюту сделки', 'error');
      return;
    }
    if (!getActiveFxRate(targetCurrency.value)) {
      setToast('Для выбранной валюты нет доступного курса', 'error');
      return;
    }
  }
  isAddingPayment.value = true;
  try {
    const res = await ManagerOrdersService.addManagerOrderPayment(props.order.id, {
        amount: newPaymentAmount.value,
        type: newPaymentType.value,
        currency: enableCurrency.value ? (targetCurrency.value || 'USD') : 'BYN',
    });
    payments.value = res;
    newPaymentAmount.value = null;
    setToast('Платеж добавлен', 'success');
  } catch (error) {
    setToast(`Ошибка: ${getApiErrorMessage(error)}`, 'error');
  } finally {
    isAddingPayment.value = false;
  }
};

const loadCandidateBankReceipts = async (order: ManagerOrderDetailResponse | null) => {
  const inn = order?.customer?.inn;
  if (!inn) {
    bankReceipts.value = [];
    return;
  }
  bankReceiptsLoading.value = true;
  try {
    const response = await ManagerMailService.listManagerBankReceipts(1, 20, 'requires_review', inn);
    bankReceipts.value = response.items || [];
  } catch (error) {
    console.error('Failed to load bank receipts', error);
    bankReceipts.value = [];
  } finally {
    bankReceiptsLoading.value = false;
  }
};

const attachBankReceipt = async (receipt: BankReceiptResponse) => {
  if (!props.order?.id || !receipt.id) return;
  attachingReceiptId.value = receipt.id;
  try {
    await ManagerMailService.attachManagerBankReceipt(receipt.id, {
      order_id: props.order.id,
      payment_type: 'postpayment',
    });
    setToast('Поступление прикреплено к заказу', 'success');
    await loadCandidateBankReceipts(props.order);
    emit('reload', props.order.id);
  } catch (error) {
    setToast(`Ошибка привязки: ${getApiErrorMessage(error)}`, 'error');
  } finally {
    attachingReceiptId.value = null;
  }
};

const receiptCandidateHint = (receipt: BankReceiptResponse) => {
  const meta = receipt.match_meta as any;
  const docs = Array.isArray(meta?.document_candidates) ? meta.document_candidates : [];
  if (docs.length) {
    const doc = docs[0];
    return `${doc.doc_type || 'документ'} ${doc.number || ''} · заказ #${doc.order_id}`;
  }
  const ids = Array.isArray(meta?.candidate_order_ids) ? meta.candidate_order_ids : [];
  if (ids.length) return `кандидат: заказ #${ids[0]}`;
  return '';
};

const formatReceiptDate = (value?: string | null) => {
  if (!value) return 'дата не указана';
  return new Date(value).toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });
};

const formatPaymentType = (value?: string | null) => (value === 'prepayment' ? 'Аванс' : 'Доплата');

const formatBankPaymentDate = (value?: string | null) => {
  if (!value) return 'дата не указана';
  return new Date(value).toLocaleString('ru-RU', {
    day: '2-digit',
    month: '2-digit',
    year: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
};

const openBankReceiptJournal = (payment: PaymentResponse) => {
  if (!props.order?.id || !payment.bank_receipt_id) return;
  window.history.pushState({}, '', `/manager/payments?orderId=${props.order.id}`);
  window.dispatchEvent(new PopStateEvent('popstate'));
};

const deletingPaymentId = ref<number | null>(null);

const confirmDeletePayment = (paymentId: number) => {
  deletingPaymentId.value = paymentId;
};

const cancelDeletePayment = () => {
  deletingPaymentId.value = null;
};

const deletePayment = async (paymentId: number) => {
  if (!props.order?.id) return;
  try {
    const res = await ManagerOrdersService.deleteManagerOrderPayment(props.order.id, paymentId);
    payments.value = res;
    deletingPaymentId.value = null;
    setToast('Платеж удален', 'success');
  } catch (error) {
    setToast(`Ошибка: ${getApiErrorMessage(error)}`, 'error');
  }
};


const totalPreview = computed(() => {
  const pTotal = productLines.value.reduce((sum, line) => sum + line.price * line.quantity, 0);
  const sTotal = serviceLines.value.reduce((sum, line) => sum + line.price * line.quantity, 0);
  return pTotal + sTotal;
});

const totalPaymentsPreview = computed(() => {
  const bynPaid = payments.value.filter((p) => p.currency === 'BYN').reduce((sum, p) => sum + p.amount, 0);
  if (!enableCurrency.value || !currentFxRate.value || !targetCurrency.value) {
    return bynPaid;
  }
  const foreignPaid = payments.value.filter((p) => p.currency === targetCurrency.value).reduce((sum, p) => sum + p.amount, 0);
  const rate = getActiveFxRate(targetCurrency.value);
  if (!rate) return bynPaid;
  return bynPaid + (foreignPaid * rate);
});

const calculatedTargetCurrencyPayments = computed(() => {
  return payments.value.reduce((sum, p) => {
    if (p.currency === targetCurrency.value) {
      return sum + p.amount;
    }
    if (p.currency === 'BYN' && currentFxRate.value && targetCurrency.value) {
      const rate = getActiveFxRate(targetCurrency.value);
      if (rate) {
        return sum + (p.amount / rate);
      }
    }
    return sum;
  }, 0);
});

const balanceDuePreview = computed(() => {
  if (enableCurrency.value && currentFxRate.value && targetCurrency.value) {
    const rate = getActiveFxRate(targetCurrency.value);
    if (!rate) return Math.max(0, totalPreview.value - totalPaymentsPreview.value);
    return targetCurrencyBalanceDue.value * rate;
  }
  return Math.max(0, totalPreview.value - totalPaymentsPreview.value);
});

const targetCurrencyBalanceDue = computed(() => {
  return Math.max(0, (targetCurrencyAmount.value || 0) - calculatedTargetCurrencyPayments.value);
});

const marginPreview = computed(() => {
  const pCost = productLines.value.reduce((sum, line) => sum + line.cost * line.quantity, 0);
  const sCost = serviceLines.value.reduce((sum, line) => sum + line.cost * line.quantity, 0);
  return Math.round(totalPreview.value - (pCost + sCost));
});

const rememberProductOption = (option: ProductOption) => {
  productLookupById.value = {
    ...productLookupById.value,
    [option.id]: option,
  };
};

const rememberProductOptions = (options: ProductOption[]) => {
  if (!options.length) return;
  const merged = { ...productLookupById.value };
  for (const option of options) merged[option.id] = option;
  productLookupById.value = merged;
};

const mapSmartSearchItemToOption = (item: any): ProductOption => ({
  id: Number(item.id),
  title: String(item.title ?? ''),
  price: Number(item.price ?? 0),
  cost: Number(item.min_cost_byn ?? 0),
  is_inverter: Boolean(item.is_inverter),
  power_cooling: item.power_cooling == null ? null : Number(item.power_cooling),
  availability_status: String(item.availability_status ?? 'out_of_stock'),
  vitebsk_qty: Number(item.vitebsk_qty ?? 0),
  minsk_qty: Number(item.minsk_qty ?? 0),
  specs: ((item.specs || {}) as Record<string, any>),
});

const syncProductLookupFromLines = () => {
  for (const line of productLines.value) {
    if (!line.product_id || productLookupById.value[line.product_id]) continue;
    rememberProductOption({
      id: line.product_id,
      title: line.product_query,
      price: line.price,
      cost: line.cost,
      is_inverter: false,
      power_cooling: null,
      availability_status: 'out_of_stock',
      vitebsk_qty: 0,
      minsk_qty: 0,
    });
  }
};

const debouncedLoadProductOptions = useDebounceFn(async (index: number, q: string, requestId: number) => {
  try {
    productLookupLoading.value = true;
    const response = await api.smartSearchProducts(q, 20);
    if (requestId !== productSearchRequestId || activeSuggestionIndex.value !== index) return;
    let options = Array.isArray(response) ? response.map(mapSmartSearchItemToOption) : [];
    if (searchInStock.value) {
      options = options.filter(o => o.vitebsk_qty > 0 || o.minsk_qty > 0 || o.availability_status === 'check_availability');
    }
    productOptions.value = options;
    rememberProductOptions(options);
  } catch (error) {
    setToast(`Ошибка поиска товаров: ${getApiErrorMessage(error)}`);
    if (requestId === productSearchRequestId) {
      productOptions.value = [];
    }
  } finally {
    if (requestId === productSearchRequestId) {
      productLookupLoading.value = false;
    }
  }
}, 400);

const currentLinesSnapshot = () => JSON.stringify({
  activeProposalId: activeProposalId.value,
  products: productLines.value.map((line) => ({
    link_id: line.link_id ?? null,
    product_id: Number(line.product_id || 0),
    product_query: String(line.product_query || '').trim(),
    quantity: Number(line.quantity || 0),
    price: Number(line.price || 0),
    cost: Number(line.cost || 0),
    product_country: line.product_country || null,
    product_logistics_components: line.product_logistics_components || [],
    logistics_components: line.logistics_components || null,
  })),
  services: serviceLines.value.map((line) => ({
    service_id: line.service_id ?? null,
    title: String(line.title || '').trim(),
    quantity: Number(line.quantity || 0),
    price: Number(line.price || 0),
    cost: Number(line.cost || 0),
  })),
});

const currentFormSnapshot = () => JSON.stringify({
  status: status.value,
  title: orderTitle.value.trim(),
  workflowType: workflowType.value,
  repairMeta: buildRepairMetaPayload(),
  managerLabels: [...managerLabels.value],
  nextFollowupDate: nextFollowupDate.value,
  assessmentDate: assessmentDate.value,
  installationDate: installationDate.value,
  comment: comment.value,
  installerId: installerId.value,
  customerDeliveryAddress: customerDeliveryAddress.value.trim(),
  customerBranchId: customerBranchId.value,
  measurementRequired: measurementRequired.value,
  measurerId: measurerId.value,
  measurementResult: measurementResult.value,
  additionalConditions: additionalConditions.value,
  proposalStatus: proposalStatus.value,
  negotiationStatus: negotiationStatus.value,
  executionStatus: executionStatus.value,
  executionWithoutPayment: executionWithoutPayment.value,
  executionWithoutPaymentReason: executionWithoutPaymentReason.value,
  autoExecutionOnPayment: autoExecutionOnPayment.value,
  autoCloseOnPayment: autoCloseOnPayment.value,
  enableCurrency: enableCurrency.value,
  targetCurrency: targetCurrency.value,
  targetCurrencyAmount: targetCurrencyAmount.value,
});

const hasUnsavedChanges = computed(() => (
  Boolean(props.order?.id)
  && (
    (Boolean(savedLinesSnapshot.value) && currentLinesSnapshot() !== savedLinesSnapshot.value)
    || (Boolean(savedFormSnapshot.value) && currentFormSnapshot() !== savedFormSnapshot.value)
  )
));

const persistDraft = () => {
  if (!draftKey.value) return;
  try {
    const payload: OrderDrawerDraft = {
      productLines: productLines.value.map((line) => ({ ...line })),
      serviceLines: serviceLines.value.map((line) => ({ ...line })),
    };
    window.sessionStorage.setItem(draftKey.value, JSON.stringify(payload));
  } catch (error) {
    console.warn('Failed to persist order drawer draft', error);
  }
};

const restoreDraft = () => {
  if (!draftKey.value) return;
  try {
    const raw = window.sessionStorage.getItem(draftKey.value);
    if (!raw) return;
    const payload = JSON.parse(raw) as Partial<OrderDrawerDraft>;
    if (Array.isArray(payload.productLines)) {
      productLines.value = payload.productLines.map((line) => ({
        link_id: Number((line as any).link_id || 0) || null,
        product_id: Number(line.product_id || 0),
        product_query: String(line.product_query || ''),
        quantity: Number(line.quantity || 1),
        price: Number(line.price || 0),
        cost: Number(line.cost || 0),
        product_country: (line as any).product_country || null,
        product_logistics_components: Array.isArray((line as any).product_logistics_components)
          ? [...((line as any).product_logistics_components as ProductLogisticsTemplateComponent[])]
          : [],
        logistics_components: Array.isArray((line as any).logistics_components)
          ? [...((line as any).logistics_components as OrderLogisticsComponent[])]
          : null,
      }));
    }
    if (Array.isArray(payload.serviceLines)) {
      serviceLines.value = payload.serviceLines.map((line) => ({
        service_id: line.service_id ?? null,
        title: String(line.title || ''),
        quantity: Number(line.quantity || 1),
        price: Number(line.price || 0),
        cost: Number(line.cost || 0),
        tariff_id: Number(line.tariff_id || 0) || null,
        template_short_name: line.template_short_name || null,
        template_full_description: line.template_full_description || null,
        template_applied_text: line.template_applied_text || null,
        description_mode: line.description_mode === 'full' ? 'full' : 'short',
      }));
    }
  } catch (error) {
    console.warn('Failed to restore order drawer draft', error);
  }
};

const persistDrawerSections = () => {
  if (!drawerSectionsKey.value) return;
  try {
    window.sessionStorage.setItem(drawerSectionsKey.value, JSON.stringify(expandedDrawerSections.value));
  } catch (error) {
    console.warn('Failed to persist order drawer sections', error);
  }
};

const restoreDrawerSections = (): DrawerSectionsState => {
  if (!drawerSectionsKey.value) return createDefaultDrawerSections();
  try {
    const raw = window.sessionStorage.getItem(drawerSectionsKey.value);
    if (!raw) return createDefaultDrawerSections();
    const stored = JSON.parse(raw) as Partial<DrawerSectionsState>;
    return {
      ...createDefaultDrawerSections(),
      ...Object.fromEntries(
        Object.entries(stored).filter(([, value]) => typeof value === 'boolean'),
      ),
    } as DrawerSectionsState;
  } catch (error) {
    console.warn('Failed to restore order drawer sections', error);
    return createDefaultDrawerSections();
  }
};

const clearDraft = () => {
  if (!draftKey.value) return;
  try {
    window.sessionStorage.removeItem(draftKey.value);
  } catch (error) {
    console.warn('Failed to clear order drawer draft', error);
  }
};

const mapProductLineFromResponse = (line: OrderProductLineResponse): ProductLine => ({
  link_id: line.id,
  product_id: line.product_id || 0,
  product_query: line.product_title || '',
  quantity: line.quantity,
  price: line.price,
  cost: line.cost,
  product_country: (line as any).product_country || null,
  product_logistics_components: Array.isArray((line as any).product_logistics_components)
    ? ((line as any).product_logistics_components as ProductLogisticsTemplateComponent[])
    : [],
  logistics_components: Array.isArray((line as any).logistics_components) && (line as any).logistics_components.length
    ? ((line as any).logistics_components as OrderLogisticsComponent[])
    : null,
});

const mapServiceLineFromResponse = (line: OrderServiceLineResponse): ServiceLine => ({
  service_id: line.service_id,
  title: line.service_title,
  quantity: Math.max(1, Number(line.quantity || 1)),
  price: Number(line.price || 0),
  cost: Number(line.cost || 0),
});

const loadProposalLines = (proposal: OrderProposalResponse | null | undefined, fallbackOrder?: ManagerOrderDetailResponse | null) => {
  editingServiceLineIndex.value = null;
  if (proposal) {
    activeProposalId.value = proposal.id;
    proposalStatus.value = normalizeProposalStatus(proposal.status);
    productLines.value = (proposal.product_lines || []).map(mapProductLineFromResponse);
    serviceLines.value = (proposal.service_lines || []).map(mapServiceLineFromResponse);
    return;
  }
  activeProposalId.value = null;
  productLines.value = (fallbackOrder?.product_lines ?? []).map(mapProductLineFromResponse);
  serviceLines.value = (fallbackOrder?.service_lines ?? []).map(mapServiceLineFromResponse);
};

const initForm = async (order: ManagerOrderDetailResponse | null) => {
  if (!order) return;
  localServerErrors.value = {};
  localFormError.value = '';
  if (initializedOrderId.value !== order.id) {
    initializedOrderId.value = order.id;
    expandedDrawerSections.value = restoreDrawerSections();
    linkedEquipmentOptions.value = [];
    executionWorkspaceSection.value = null;
    activeWorkspaceTarget.value = null;
    orderEmails.value = [];
    orderEmailsLoaded.value = false;
  }
  status.value = order.status;
  orderTitle.value = order.title ?? '';
  workflowType.value = normalizeOrderWorkflowType((order as any).workflow_type);
  repairMeta.value = normalizeRepairMeta(((order as any).repair_meta || {}) as Partial<RepairMeta>, {
    defaultRepairStatus: workflowType.value === 'repair',
  });
  if (workflowType.value === 'repair') {
    const savedFaultType = repairMeta.value.fault_type || (repairMeta.value.structured_diagnosis || {}).fault_type;
    if (savedFaultType && REPAIR_AI_DEFECT_TYPES.some((item) => item.value === savedFaultType)) {
      repairAiDefectType.value = savedFaultType;
    } else {
      repairMeta.value.fault_type = repairAiDefectType.value;
    }
  }
  repairComplaintSearch.value = '';
  if (workflowType.value === 'repair' && !repairComplaintPresets.value.length) {
    void loadRepairComplaintPresets();
  }
  managerLabels.value = [...(order.manager_labels ?? [])];
  managerLabelDraft.value = '';
  nextFollowupDate.value = toLocalDateTimeInput(order.next_followup_date);
  assessmentDate.value = toLocalDateTimeInput(order.measurement_date);
  installationDate.value = toLocalDateTimeInput(order.installation_date);
  comment.value = order.comment ?? '';
  isPaid.value = order.is_paid;
  installerId.value = order.installer_id ?? null;
  customerDeliveryAddress.value = order.delivery_address || '';
  customerBranchId.value = order.customer_branch?.id ?? null;
  measurementRequired.value = order.measurement_required ?? false;
  measurerId.value = order.measurer_id ?? null;
  measurementResult.value = order.measurement_result ?? '';
  additionalConditions.value = order.additional_conditions ?? '';
  proposalStatus.value = normalizeProposalStatus(order.proposal_status);
  negotiationStatus.value = order.negotiation_status || 'awaiting_offer';
  executionStatus.value = order.execution_status || 'needs_schedule';
  executionWithoutPayment.value = Boolean(order.execution_without_payment);
  executionWithoutPaymentReason.value = order.execution_without_payment_reason || '';
  autoExecutionOnPayment.value = Boolean(order.auto_execution_on_payment);
  autoCloseOnPayment.value = Boolean(order.auto_close_on_payment);
  targetCurrency.value = order.target_currency || null;
  targetCurrencyAmount.value = order.target_currency_amount || null;
  targetCurrencyPayments.value = order.target_currency_payments || 0;

  // Set default currency toggle state
  enableCurrency.value = !!order.target_currency;

  if (enableCurrency.value && !currentFxRate.value) {
      ManagerSettingsService.getFxRate().then(res => {
          currentFxRate.value = res;
          if (targetCurrency.value === 'EUR' && !res.eur_byn) {
            targetCurrency.value = 'USD';
          }
      }).catch(e => console.warn('Failed to load fx rate on init', e));
  }

  if (installersList.value.length === 0) {
    api.getManagerInstallers(1, 100).then(res => {
      installersList.value = res.items;
    }).catch(e => console.error("Failed to load installers", e));
  }

  const selectedProposal = (order.proposals || []).find((proposal) => proposal.is_selected && !proposal.is_archived)
    || (order.proposals || []).find((proposal) => !proposal.is_archived)
    || null;
  loadProposalLines(selectedProposal, order);
  if (pendingDraftClearOrderId.value === order.id) {
    clearDraft();
    pendingDraftClearOrderId.value = null;
  }
  savedLinesSnapshot.value = currentLinesSnapshot();
  showEstimateImport.value = false;
  await loadEstimateOptions();

  // Payments
  payments.value = [...(order.payments || [])];
  await loadCandidateBankReceipts(order);

  const customerId = order.customer?.id;
  if (customerId) {
    await loadCustomerBranches(customerId, order.customer_branch?.id ?? null);
  } else {
    resetCustomerBranches();
  }
  if (workflowType.value === 'repair') {
    await loadRepairEquipment();
  } else {
    resetRepairEquipment();
  }

  productLookupById.value = {};

  syncProductLookupFromLines();
  productOptions.value = [];
  activeSuggestionIndex.value = null;
  productLookupLoading.value = false;
  serviceTariffOptions.value = [];
  activeServiceSuggestionIndex.value = null;
  serviceTariffLookupLoading.value = false;
  savedFormSnapshot.value = currentFormSnapshot();
  restoreDraft();
  syncProductLookupFromLines();
  await Promise.all([
    loadOrderSupplyRequests(order.id),
    loadOrderEmails(order.id),
  ]);
};

watch(
  () => props.modelValue,
  async (value) => {
    if (value) {
      await initForm(props.order);
    }
  },
);

watch(
  () => props.order,
  async (order, previousOrder) => {
    if (
      props.modelValue
      && order
      && order !== previousOrder
      && pendingDraftClearOrderId.value === order.id
    ) {
      await initForm(order);
    }
  },
);

watch(() => props.modelValue, (open) => {
  if (open) nextTick(resetWorkspaceHeader);
});

watch(
  () => props.order,
  async (value) => {
    if (props.modelValue) await initForm(value);
  },
);

watch(customerBranchId, () => {
  if (props.modelValue && isRepairWorkflow.value && customer.value?.id) {
    void loadRepairEquipment();
  }
});

const onProductChanged = (index: number, applyCatalogPrice = false) => {
  const row = productLines.value[index];
  if (!row) return;
  const selected = productLookupById.value[row.product_id];
  if (!selected) return;
  row.product_query = selected.title;
  if (applyCatalogPrice) {
    row.price = selected.price;
  }
};

const getProductSuggestions = (index: number) => {
  if (activeSuggestionIndex.value !== index) return [];
  return productOptions.value.slice(0, 10);
};

const onProductQueryInput = (index: number) => {
  const row = productLines.value[index];
  if (!row) return;
  activeSuggestionIndex.value = index;
  const query = row.product_query.trim();
  row.product_id = 0;
  productSearchRequestId += 1;
  if (query.length < 2) {
    productOptions.value = [];
    productLookupLoading.value = false;
    return;
  }
  debouncedLoadProductOptions(index, query, productSearchRequestId);
};

const onProductInputBlur = (index: number) => {
  window.setTimeout(() => {
    if (activeSuggestionIndex.value === index) {
      activeSuggestionIndex.value = null;
    }
  }, 120);
};

const onProductInputFocus = (index: number) => {
  activeSuggestionIndex.value = index;
};

const selectProductForLine = (index: number, option: ProductOption) => {
  const row = productLines.value[index];
  if (!row) return;
  row.product_id = option.id;
  row.product_query = option.title;
  row.price = option.price;
  row.product_country = getProductCountryFromSpecs(option.specs);
  row.product_logistics_components = normalizeProductLogisticsTemplate(option.specs?.logistics_components);
  row.logistics_components = null;
  // Quick selection means the row now follows the selected catalog product.
  if (option.cost && option.cost > 0) {
    row.cost = option.cost;
  }
  rememberProductOption(option);
  activeSuggestionIndex.value = null;
  productOptions.value = [];
  onProductChanged(index, false);
};

const openSelectedProduct = (index: number) => {
  const row = productLines.value[index];
  if (!row?.product_id) return;
  persistDraft();
  const returnTo = `${window.location.pathname}${window.location.search}`;
  const query = new URLSearchParams({
    editProductId: String(row.product_id),
    editProductQuery: row.product_query || '',
    returnTo,
  });
  window.history.pushState({}, '', `/manager/products?${query.toString()}`);
  window.dispatchEvent(new PopStateEvent('popstate'));
};

const addProductLine = () => {
  productLines.value.push({
    link_id: null,
    product_id: 0,
    product_query: '',
    quantity: 1,
    price: 0,
    cost: 0,
    product_country: null,
    product_logistics_components: [],
    logistics_components: null,
  });
};

const addServiceLine = () => {
  serviceLines.value.push({ title: '', quantity: 1, price: 0, cost: 0, service_id: null });
  editingServiceLineIndex.value = serviceLines.value.length - 1;
};

const applyOrderResponse = async (
  order: ManagerOrderDetailResponse,
  preferredProposalId?: number | null,
  emitReload = true,
) => {
  emit('updated', order);
  const nextProposal = preferredProposalId
    ? (order.proposals || []).find((proposal) => proposal.id === preferredProposalId && !proposal.is_archived)
    : ((order.proposals || []).find((proposal) => proposal.is_selected && !proposal.is_archived)
      || (order.proposals || []).find((proposal) => !proposal.is_archived));
  loadProposalLines(nextProposal || null, order);
  syncProductLookupFromLines();
  await loadOrderSupplyRequests(order.id);
  if (emitReload) emit('reload', order.id);
};

const buildProposalLinesPayload = () => ({
  products: productLines.value.map((line) => ({
    product_id: line.product_id || 0,
    quantity: Math.trunc(Number(line.quantity) || 0),
    price: Math.round(Number(line.price) || 0),
    cost: (!line.cost && line.cost !== 0) ? null : toIntegerMoney(line.cost),
    logistics_components: normalizeOrderLogisticsComponents(line.logistics_components),
    link_id: line.link_id ?? null,
    proposal_id: activeProposalId.value,
  })),
  services: serviceLines.value.map((line) => ({
    service_id: line.service_id ?? null,
    title: line.title,
    quantity: Math.trunc(Number(line.quantity) || 0),
    price: Math.round(Number(line.price) || 0),
    cost: (!line.cost && line.cost !== 0) ? null : toIntegerMoney(line.cost),
    link_id: null,
    proposal_id: activeProposalId.value,
  })),
});

const validateProposalLines = () => {
  if (productLines.value.some((line) => line.quantity <= 0)) return 'Количество товара должно быть больше 0';
  if (productLines.value.some((line) => line.price < 0)) return 'Цена товара не может быть отрицательной';
  if (productLines.value.some((line) => !line.product_id)) return 'Выберите товар из выпадающего списка';
  if (serviceLines.value.some((line) => line.quantity <= 0)) return 'Количество услуги должно быть больше 0';
  if (serviceLines.value.some((line) => line.price < 0)) return 'Цена услуги не может быть отрицательной';
  if (serviceLines.value.some((line) => !line.title?.trim())) return 'Для услуги укажите название';
  return '';
};

const saveCurrentProposalLines = async () => {
  if (!props.order?.id) return props.order || null;
  if (activeProposalLocked.value) return props.order;
  const validationError = validateProposalLines();
  if (validationError) {
    localFormError.value = validationError;
    throw new Error(validationError);
  }
  const currentProposalId = activeProposalId.value;
  const order = await ManagerOrdersService.patchManagerOrder(props.order.id, buildProposalLinesPayload());
  clearDraft();
  await applyOrderResponse(order, currentProposalId, false);
  savedLinesSnapshot.value = currentLinesSnapshot();
  return order;
};

const setActiveProposal = async (proposal: OrderProposalResponse) => {
  if (!proposal || activeProposalId.value === proposal.id || proposalActionLoading.value) return;
  proposalActionLoading.value = true;
  try {
    await saveCurrentProposalLines();
  } catch (error) {
    setToast(`Сначала сохраните текущий вариант: ${getApiErrorMessage(error)}`, 'error');
    return;
  } finally {
    proposalActionLoading.value = false;
  }
  loadProposalLines(proposal, props.order);
  productLookupById.value = {};
  syncProductLookupFromLines();
};

const onProposalClick = (proposal: OrderProposalResponse) => {
  void setActiveProposal(proposal);
};

const createProposal = async () => {
  if (!props.order?.id || proposalActionLoading.value) return;
  const name = await promptDialog({
    title: 'Новое предложение',
    inputLabel: 'Название',
    initialValue: `Вариант ${orderProposals.value.length + 1}`,
    required: true,
    confirmText: 'Создать',
  });
  if (name === null) return;
  proposalActionLoading.value = true;
  try {
    await saveCurrentProposalLines();
    const order = await ManagerOrdersService.createManagerOrderProposal(props.order.id, { name });
    const created = order.proposals?.[Math.max(0, (order.proposals?.length || 1) - 1)] || null;
    await applyOrderResponse(order, created?.id || null);
    setToast('Предложение создано', 'success');
  } catch (error) {
    setToast(`Ошибка создания предложения: ${getApiErrorMessage(error)}`, 'error');
  } finally {
    proposalActionLoading.value = false;
  }
};

const duplicateProposal = async () => {
  if (!props.order?.id || !activeProposal.value?.id || proposalActionLoading.value) return;
  const name = await promptDialog({
    title: 'Копия предложения',
    inputLabel: 'Название',
    initialValue: `${activeProposal.value.name} копия`,
    required: true,
    confirmText: 'Создать копию',
  });
  if (name === null) return;
  proposalActionLoading.value = true;
  try {
    const sourceProposalId = activeProposal.value.id;
    await saveCurrentProposalLines();
    const order = await ManagerOrdersService.duplicateManagerOrderProposal(props.order.id, sourceProposalId, { name });
    const created = order.proposals?.[Math.max(0, (order.proposals?.length || 1) - 1)] || null;
    await applyOrderResponse(order, created?.id || null);
    setToast('Предложение скопировано', 'success');
  } catch (error) {
    setToast(`Ошибка копирования предложения: ${getApiErrorMessage(error)}`, 'error');
  } finally {
    proposalActionLoading.value = false;
  }
};

const renameProposal = async () => {
  if (!props.order?.id || !activeProposal.value?.id || proposalActionLoading.value) return;
  const name = await promptDialog({
    title: 'Переименовать предложение',
    inputLabel: 'Название',
    initialValue: activeProposal.value.name,
    required: true,
    confirmText: 'Переименовать',
  });
  if (name === null || !name.trim()) return;
  proposalActionLoading.value = true;
  try {
    const proposalId = activeProposal.value.id;
    await saveCurrentProposalLines();
    const order = await ManagerOrdersService.patchManagerOrderProposal(props.order.id, proposalId, { name });
    await applyOrderResponse(order, proposalId);
    setToast('Название обновлено', 'success');
  } catch (error) {
    setToast(`Ошибка переименования: ${getApiErrorMessage(error)}`, 'error');
  } finally {
    proposalActionLoading.value = false;
  }
};

const archiveProposal = async () => {
  if (!props.order?.id || !activeProposal.value?.id || proposalActionLoading.value) return;
  if (orderProposals.value.length <= 1) {
    setToast('Нельзя удалить единственное предложение', 'error');
    return;
  }
  if (!await confirmDialog({
    title: 'Архивировать предложение?',
    description: activeProposal.value.name,
    confirmText: 'Архивировать',
    variant: 'warning',
  })) return;
  const archivedId = activeProposal.value.id;
  proposalActionLoading.value = true;
  try {
    const order = await ManagerOrdersService.archiveManagerOrderProposal(props.order.id, archivedId);
    const next = (order.proposals || []).find((proposal) => proposal.is_selected && !proposal.is_archived)
      || (order.proposals || []).find((proposal) => proposal.id !== archivedId && !proposal.is_archived)
      || null;
    await applyOrderResponse(order, next?.id || null);
    setToast('Предложение архивировано', 'success');
  } catch (error) {
    setToast(`Ошибка архивации: ${getApiErrorMessage(error)}`, 'error');
  } finally {
    proposalActionLoading.value = false;
  }
};

const selectProposalForOrder = async (proposal?: OrderProposalResponse) => {
  const targetProposal = proposal || activeProposal.value;
  if (!props.order?.id || !targetProposal?.id || targetProposal.is_selected || proposalActionLoading.value) return;
  proposalActionLoading.value = true;
  try {
    await saveCurrentProposalLines();
    const order = await ManagerOrdersService.selectManagerOrderProposal(props.order.id, targetProposal.id);
    await applyOrderResponse(order, targetProposal.id);
    setToast('Предложение выбрано для заказа', 'success');
  } catch (error) {
    setToast(`Ошибка выбора предложения: ${getApiErrorMessage(error)}`, 'error');
  } finally {
    proposalActionLoading.value = false;
  }
};

const changeActiveProposalStatus = async (nextStatus: ProposalLifecycleStatus) => {
  const proposal = activeProposal.value;
  if (!props.order?.id || !proposal?.id || proposalActionLoading.value) return;
  if (nextStatus === activeProposalStatus.value) return;

  if (nextStatus === 'ready_to_send') {
    const validationError = validateProposalLines();
    if (validationError || totalPreview.value <= 0) {
      setToast(validationError || 'Добавьте хотя бы одну позицию с ненулевой суммой', 'error');
      return;
    }
  }
  if (nextStatus === 'sent' && !await confirmDialog({
    title: 'Отметить предложение отправленным?',
    description: 'Используйте это действие, если предложение отправлено не через CRM. Для email используйте основную кнопку отправки.',
    confirmText: 'Отметить отправленным',
    variant: 'warning',
  })) return;
  if (nextStatus === 'draft' && activeProposalLocked.value && !await confirmDialog({
    title: 'Вернуть предложение в черновик?',
    description: 'После этого предложение снова можно будет редактировать.',
    confirmText: 'Вернуть в черновик',
    variant: 'warning',
  })) return;

  proposalActionLoading.value = true;
  try {
    if (nextStatus === 'ready_to_send') await saveCurrentProposalLines();
    const order = await ManagerOrdersService.patchManagerOrderProposal(props.order.id, proposal.id, { status: nextStatus });
    proposalStatus.value = nextStatus;
    negotiationStatus.value = order.negotiation_status || negotiationStatus.value;
    await applyOrderResponse(order, proposal.id);
    const label = proposalStatusLabel(nextStatus);
    setToast(`Статус предложения: ${label}`, 'success');
  } catch (error) {
    setToast(`Не удалось изменить статус: ${getApiErrorMessage(error)}`, 'error');
  } finally {
    proposalActionLoading.value = false;
  }
};

const openProposalSend = async () => {
  const proposal = activeProposal.value;
  if (!proposal) return;
  expandedDrawerSections.value.documents = true;
  activeWorkspaceTarget.value = 'documents';
  await nextTick();
  const offerExists = orderDocuments.value.some((document) => (
    document.doc_type === 'offer'
    && (!document.proposal_id || document.proposal_id === proposal.id)
  ));
  if (offerExists) documentsPanelRef.value?.openSend();
  else {
    documentsPanelRef.value?.openCreate();
    setToast('Сначала создайте коммерческое предложение для активного варианта', 'error');
  }
  document.getElementById('order-workspace-documents')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
};

const handleWorkspaceNextAction = async () => {
  const action = orderWorkspace.value.nextAction;
  if (action.command === 'create_proposal') return createProposal();
  if (action.command === 'finish_proposal') return changeActiveProposalStatus('ready_to_send');
  if (action.command === 'send_proposal') return openProposalSend();
  if (action.command === 'record_proposal_response') {
    openWorkspaceTarget('proposal');
    await nextTick();
    proposalToolbarRef.value?.openResponse();
    return;
  }
  if (action.command === 'create_proposal_variant') return duplicateProposal();
  openWorkspaceTarget(action.target);
};

const toggleEstimateImport = async () => {
  showEstimateImport.value = !showEstimateImport.value;
  if (showEstimateImport.value && !estimateOptions.value.length && !estimateOptionsLoading.value) {
    await loadEstimateOptions();
  }
};

const debouncedLoadServiceTariffOptions = useDebounceFn(async (index: number, q: string, requestId: number) => {
  try {
    serviceTariffLookupLoading.value = true;
    const response = await api.listManagerQuickTariffs(q, null, 10);
    if (requestId !== serviceTariffSearchRequestId || activeServiceSuggestionIndex.value !== index) return;
    serviceTariffOptions.value = response.items || [];
  } catch (error) {
    setToast(`Ошибка поиска тарифов: ${getApiErrorMessage(error)}`, 'error');
    if (requestId === serviceTariffSearchRequestId) {
      serviceTariffOptions.value = [];
    }
  } finally {
    if (requestId === serviceTariffSearchRequestId) {
      serviceTariffLookupLoading.value = false;
    }
  }
}, 300);

const getServiceTariffSuggestions = (index: number) => {
  if (activeServiceSuggestionIndex.value !== index) return [];
  return serviceTariffOptions.value.slice(0, 10);
};

const onServiceTitleInput = (index: number) => {
  const row = serviceLines.value[index];
  if (!row) return;
  activeServiceSuggestionIndex.value = index;
  row.service_id = null;
  const query = row.title.trim();
  serviceTariffSearchRequestId += 1;
  if (query.length < 2) {
    serviceTariffOptions.value = [];
    serviceTariffLookupLoading.value = false;
    return;
  }
  debouncedLoadServiceTariffOptions(index, query, serviceTariffSearchRequestId);
};

const onServiceTitleFocus = (index: number) => {
  activeServiceSuggestionIndex.value = index;
  const row = serviceLines.value[index];
  if (row?.title.trim() && row.title.trim().length >= 2) {
    onServiceTitleInput(index);
  }
};

const onServiceTitleBlur = (index: number) => {
  window.setTimeout(() => {
    if (activeServiceSuggestionIndex.value === index) {
      activeServiceSuggestionIndex.value = null;
    }
  }, 120);
};

const selectServiceTariffForLine = (index: number, option: ManagerQuickTariffResponse) => {
  const row = serviceLines.value[index];
  if (!row) return;
  applyTariffTemplateToLine(row, option);
  activeServiceSuggestionIndex.value = null;
  serviceTariffOptions.value = [];
};

const setServiceLineDescriptionMode = async (index: number, mode: ServiceDescriptionMode) => {
  const row = serviceLines.value[index];
  if (!row) return;
  await replaceLineDescription(
    row,
    mode,
    () => confirmDialog({
      title: 'Заменить изменённое название?',
      description: 'Текст был отредактирован вручную. При замене эти изменения будут потеряны.',
      confirmText: mode === 'full' ? 'Заменить на подробное' : 'Заменить на краткое',
      variant: 'warning',
    }),
  );
};

const hasDiagnosticServiceLine = () => serviceLines.value.some((line) => /диагност/i.test(line.title || ''));

let workflowChangeRequestId = 0;

const addDefaultRepairDiagnostic = async (requestId: number) => {
  if (hasDiagnosticServiceLine()) return;
  try {
    const response = await api.listManagerQuickTariffs('диагностика', 'repair' as any, 5);
    if (requestId !== workflowChangeRequestId || workflowType.value !== 'repair') return;
    const option = (response.items || [])[0];
    const diagnosticLine: ServiceLine = {
      service_id: null,
      title: 'Диагностика кондиционера на объекте',
      quantity: 1,
      price: 0,
      cost: 0,
    };
    if (option) applyTariffTemplateToLine(diagnosticLine, option);
    serviceLines.value = [
      diagnosticLine,
      ...serviceLines.value,
    ];
    setToast('Добавили базовую диагностику для ремонта');
  } catch (error) {
    if (requestId !== workflowChangeRequestId || workflowType.value !== 'repair') return;
    serviceLines.value = [
      {
        service_id: null,
        title: 'Диагностика кондиционера на объекте',
        quantity: 1,
        price: 0,
        cost: 0,
      },
      ...serviceLines.value,
    ];
    setToast(`Не нашли тариф диагностики: ${getApiErrorMessage(error)}`, 'error');
  }
};

const setWorkflowType = async (next: OrderWorkflowType) => {
  if (workflowType.value === next) return;
  const hasScenarioData = productLines.value.length > 0
    || serviceLines.value.length > 0
    || Boolean(comment.value.trim())
    || Boolean(installationDate.value)
    || Boolean(measurementResult.value.trim());
  if (hasScenarioData) {
    const confirmed = await confirmDialog({
      title: 'Сменить сценарий заказа?',
      description: 'В заказе уже есть данные. Скрытые разделы сохранятся и останутся доступны после возврата к сценарию.',
      confirmText: 'Сменить сценарий',
      variant: 'warning',
    });
    if (!confirmed) return;
  }
  const requestId = ++workflowChangeRequestId;
  workflowType.value = next;
  serviceTariffOptions.value = [];
  activeServiceSuggestionIndex.value = null;
  if (next === 'repair') {
    repairMeta.value = normalizeRepairMeta(repairMeta.value, { defaultRepairStatus: true });
    void loadRepairComplaintPresets();
    void loadRepairEquipment();
    await addDefaultRepairDiagnostic(requestId);
  } else {
    resetRepairEquipment();
  }
};

const loadRepairComplaintPresets = async () => {
  if (repairComplaintsLoading.value) return;
  repairComplaintsLoading.value = true;
  try {
    const response = await ManagerRepairComplaintsService.listManagerRepairComplaintPresets('', null, false, false, 100);
    repairComplaintPresets.value = response.items || [];
  } catch (error) {
    console.warn('Failed to load repair complaint presets', error);
  } finally {
    repairComplaintsLoading.value = false;
  }
};

const applyRepairComplaintPreset = (preset: ManagerRepairComplaintPresetResponse) => {
  repairMeta.value.customer_complaint = preset.customer_phrase || repairMeta.value.customer_complaint;
  repairMeta.value.complaint_official = preset.document_wording || repairMeta.value.complaint_official;
  repairMeta.value.likely_diagnosis = preset.likely_diagnosis || repairMeta.value.likely_diagnosis;
};

const generateRepairAiDraft = async () => {
  const defect = selectedRepairAiDefect.value;
  if (!defect || repairAiGenerating.value) return;
  repairAiGenerating.value = true;
  try {
    const response = await ManagerRepairComplaintsService.generateManagerRepairActAiDraft({
      defect_type: defect.value,
      defect_label: defect.label,
      allow_assumptions: repairAiAllowAssumptions.value,
      polish_existing: repairAiPolishExisting.value,
      equipment_name: repairMeta.value.equipment_name || orderTitle.value || props.order?.title || '',
      equipment_brand: repairMeta.value.equipment_brand,
      equipment_model: repairMeta.value.equipment_model,
      equipment_power: repairMeta.value.equipment_power,
      customer_complaint: repairMeta.value.customer_complaint,
      complaint_official: repairMeta.value.complaint_official,
      likely_diagnosis: repairMeta.value.likely_diagnosis,
      diagnostic_notes: repairMeta.value.diagnostic_notes,
      refrigerant_type: repairMeta.value.refrigerant_type,
      refrigerant_amount: repairMeta.value.refrigerant_amount,
      extra_context: repairMeta.value.diagnostic_notes || repairAiExtraContext.value || defect.hint,
      current_meta: repairMeta.value as any,
    });
    repairMeta.value = normalizeRepairMeta({ ...repairMeta.value, ...((response.repair_meta || {}) as Partial<RepairMeta>) });
    if (props.order?.id) {
      await ManagerOrdersService.patchManagerOrder(props.order.id, {
        repair_meta: buildRepairMetaPayload() as any,
        measurement_result: measurementResult.value,
      });
      emit('reload', props.order.id);
    }
    setToast('Черновик дефектного акта заполнен и сохранен', 'success');
  } catch (error) {
    setToast(`AI не смог подготовить черновик: ${getApiErrorMessage(error)}`, 'error');
  } finally {
    repairAiGenerating.value = false;
  }
};

const loadEstimateOptions = async () => {
  estimateOptionsLoading.value = true;
  try {
    const response = await api.listManagerServiceEstimates(1, 10);
    estimateOptions.value = response.items;
    if (!response.items.length) {
      selectedEstimateId.value = null;
      return;
    }
    if (!selectedEstimateId.value || !response.items.some((item) => item.id === selectedEstimateId.value)) {
      selectedEstimateId.value = response.items[0]!.id;
    }
  } catch (error) {
    console.warn('Failed to load service estimates', error);
    estimateOptions.value = [];
    selectedEstimateId.value = null;
  } finally {
    estimateOptionsLoading.value = false;
  }
};

const applyEstimateToServices = async () => {
  const estimateId = Number(selectedEstimateId.value);
  if (!Number.isFinite(estimateId) || estimateId <= 0) {
    setToast('Выберите смету для добавления', 'error');
    return;
  }
  importingEstimate.value = true;
  try {
    const response = await api.getManagerServiceEstimateOrderLines(
      estimateId,
      estimateImportMode.value,
      serviceDescriptionMode.value,
    );
    if (!response.services.length) {
      setToast('В выбранной смете нет строк', 'error');
      return;
    }

    const mappedLines: ServiceLine[] = response.services.map((line) => ({
      service_id: line.service_id ?? null,
      title: line.title || 'Услуга',
      quantity: Math.max(1, Number(line.quantity || 1)),
      price: Number(line.price || 0),
      cost: Number(line.cost || 0),
    }));
    serviceLines.value = [...serviceLines.value, ...mappedLines];
    showEstimateImport.value = false;
    setToast(
      response.mode === 'collapsed'
        ? `Смета #${response.estimate_id} добавлена одной строкой`
        : `Смета #${response.estimate_id} добавлена: ${mappedLines.length} строк`
    );
  } catch (error) {
    setToast(`Ошибка импорта сметы: ${getApiErrorMessage(error)}`, 'error');
  } finally {
    importingEstimate.value = false;
  }
};

const removeProductLine = async (index: number) => {
  if (!await confirmDialog({ title: 'Удалить товар из заказа?', confirmText: 'Удалить', variant: 'danger' })) return;
  productLines.value.splice(index, 1);
  if (activeSuggestionIndex.value === index) {
    activeSuggestionIndex.value = null;
    productOptions.value = [];
  }
};

const removeServiceLine = async (index: number) => {
  if (!await confirmDialog({ title: 'Удалить услугу из заказа?', confirmText: 'Удалить', variant: 'danger' })) return;
  serviceLines.value.splice(index, 1);
  editingServiceLineIndex.value = null;
  if (activeServiceSuggestionIndex.value === index) {
    activeServiceSuggestionIndex.value = null;
    serviceTariffOptions.value = [];
  }
};

const currentCatalogPrice = (productId: number) => productLookupById.value[productId]?.price ?? null;
const isPriceDifferentFromCatalog = (line: { product_id: number; price: number }) => {
  const catalog = currentCatalogPrice(line.product_id);
  return catalog !== null && Number(catalog) !== Number(line.price || 0);
};
const lineTotal = (line: { quantity: number; price: number }) => Number(line.quantity || 0) * Number(line.price || 0);
const toIntegerMoney = (value: number | null | undefined): number | null => {
  if (value == null || Number.isNaN(Number(value))) return null;
  return Math.round(Number(value));
};
const LOGISTICS_COMPONENT_KINDS = new Set(['indoor', 'outdoor', 'accessory', 'other']);
const normalizeLogisticsKind = (value: unknown): LogisticsComponentKind => {
  const raw = String(value || '').trim();
  return LOGISTICS_COMPONENT_KINDS.has(raw) ? (raw as LogisticsComponentKind) : 'other';
};
const getProductCountryFromSpecs = (specs?: Record<string, any> | null) => {
  if (!specs) return null;
  return String(specs.country || specs.country_of_origin || specs['Страна производства'] || specs['Страна-производитель'] || '').trim() || null;
};
const normalizePositiveInteger = (value: unknown, fallback = 1) => {
  const parsed = Math.trunc(Number(value));
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
};
const normalizePositiveNumber = (value: unknown, fallback = 0) => {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : fallback;
};
const normalizeProductLogisticsTemplate = (raw: unknown): ProductLogisticsTemplateComponent[] => {
  if (!Array.isArray(raw)) return [];
  return raw
    .map((item): ProductLogisticsTemplateComponent | null => {
      const source = (item || {}) as Record<string, any>;
      const title = String(source.title || '').trim();
      if (!title) return null;
      return {
        title,
        country: String(source.country || '').trim() || null,
        unit: String(source.unit || '').trim() || 'шт.',
        quantity_per_parent: normalizePositiveInteger(source.quantity_per_parent, 1),
        price_weight: normalizePositiveNumber(source.price_weight, 1),
        kind: normalizeLogisticsKind(source.kind),
      };
    })
    .filter((item): item is ProductLogisticsTemplateComponent => Boolean(item));
};
const normalizeOrderLogisticsComponents = (
  components?: OrderLogisticsComponent[] | null,
): OrderLogisticsComponent[] | null => {
  if (!components?.length) return null;
  const normalized = components
    .map((component) => ({
      title: String(component.title || '').trim(),
      country: String(component.country || '').trim() || 'Китай',
      unit: String(component.unit || '').trim() || 'шт.',
      quantity_per_parent: normalizePositiveInteger(component.quantity_per_parent, 1),
      unit_price: normalizePositiveNumber(component.unit_price, 0),
      kind: normalizeLogisticsKind(component.kind),
    }))
    .filter((component) => Boolean(component.title));
  return normalized.length ? normalized : null;
};

const handleSave = () => {
  if (!props.order) return;
  localServerErrors.value = {};
  localFormError.value = '';

  const errors: Record<string, string> = {};
  if (!status.value) {
    errors.status = 'Укажите статус';
  }

  if (assessmentDate.value && installationDate.value && installationDate.value < assessmentDate.value) {
    errors.installation_date = 'Дата монтажа не может быть раньше даты замера';
  }

  if (productLines.value.some((line) => line.quantity <= 0)) {
    errors.products = 'Количество товара должно быть больше 0';
  } else if (productLines.value.some((line) => line.price < 0)) {
    errors.products = 'Цена товара не может быть отрицательной';
  } else if (productLines.value.some((line) => !line.product_id)) {
    errors.products = 'Выберите товар из выпадающего списка';
  }

  if (serviceLines.value.some((line) => line.quantity <= 0)) {
    errors.services = 'Количество услуги должно быть больше 0';
  } else if (serviceLines.value.some((line) => line.price < 0)) {
    errors.services = 'Цена услуги не может быть отрицательной';
  } else if (serviceLines.value.some((line) => !line.title?.trim())) {
    errors.services = 'Для услуги укажите название';
  }

  if (Object.keys(errors).length) {
    localServerErrors.value = errors;
    localFormError.value = 'Исправьте ошибки в форме';
    return;
  }

  // Cross-field validation for Negotiation
  if (status.value === 'execution') {
    if (totalPreview.value <= 0) {
      localFormError.value = 'Нельзя перевести в монтаж с пустой сметой';
      return;
    }
    if (measurementRequired.value && !measurementResult.value?.trim()) {
      localFormError.value = 'Требуется замер: заполните результат замера';
      return;
    }
  }

  if (enableCurrency.value) {
    if (!targetCurrency.value) {
      localFormError.value = 'Выберите валюту сделки';
      return;
    }
    const activeRate = getActiveFxRate(targetCurrency.value);
    if (!activeRate) {
      localFormError.value = 'Для выбранной валюты сейчас нет доступного курса';
      return;
    }
    if (!targetCurrencyAmount.value || targetCurrencyAmount.value <= 0) {
      localFormError.value = 'Укажите зафиксированную сумму в валюте';
      return;
    }
  } else if (payments.value.some((payment) => payment.currency !== 'BYN')) {
    localFormError.value = 'Нельзя отключить валютный режим, пока в заказе есть валютные платежи';
    return;
  }

  pendingDraftClearOrderId.value = props.order.id;
  const linePayload = buildProposalLinesPayload();
  repairMeta.value = buildRepairMetaPayload();
  const payload: ManagerOrderUpdatePayload = {
    status: status.value,
    title: orderTitle.value,
    workflow_type: workflowType.value as any,
    repair_meta: buildRepairMetaPayload() as any,
    manager_labels: managerLabels.value,
    next_followup_date: fromLocalDateTimeInput(nextFollowupDate.value),
    measurement_date: fromLocalDateTimeInput(assessmentDate.value),
    installation_date: fromLocalDateTimeInput(installationDate.value),
    comment: comment.value,
    is_paid: isPaid.value,
    installer_id: installerId.value,
    customer_branch_id: customerBranchId.value,
    customer_delivery_address: customerDeliveryAddress.value,
    products: activeProposalLocked.value ? undefined : linePayload.products,
    services: activeProposalLocked.value ? undefined : linePayload.services,
    measurement_required: measurementRequired.value,
    measurer_id: measurerId.value,
    measurement_result: measurementResult.value,
    additional_conditions: additionalConditions.value,
    negotiation_status: status.value === 'negotiation' ? negotiationStatus.value : undefined,
    execution_status: status.value === 'execution' ? executionStatus.value : undefined,
    execution_without_payment: status.value === 'execution' ? executionWithoutPayment.value : false,
    execution_without_payment_reason: status.value === 'execution' && executionWithoutPayment.value ? executionWithoutPaymentReason.value : null,
    auto_execution_on_payment: autoExecutionOnPayment.value,
    auto_close_on_payment: status.value === 'execution' ? autoCloseOnPayment.value : false,
    target_currency: enableCurrency.value ? (targetCurrency.value || null) : null,
    target_currency_amount: enableCurrency.value && targetCurrencyAmount.value ? Number(String(targetCurrencyAmount.value).replace(',', '.')) : null,
  };
  emit('save', { orderId: props.order.id, data: payload });
};

const closeDrawer = async (options?: { force?: boolean } | Event) => {
  const isDomEvent = typeof Event !== 'undefined' && options instanceof Event;
  const force = Boolean(options && !isDomEvent && (options as { force?: boolean }).force);
  if (!force && hasUnsavedChanges.value) {
    persistDraft();
    const discard = await confirmDialog({
      title: 'Закрыть без сохранения?',
      description: 'В карточке есть несохранённые изменения. Они будут потеряны.',
      confirmText: 'Закрыть без сохранения',
      variant: 'warning',
    });
    if (!discard) return;
  }
  pendingDraftClearOrderId.value = null;
  clearDraft();
  emit('update:modelValue', false);
};

const isDeleting = ref(false);
const deleteOrder = async () => {
  if (!props.order?.id) return;
  const orderLabel = `Заказ №${props.order.id}${displayOrderTitle.value ? ` «${displayOrderTitle.value}»` : ''}`;
  const proceed = await confirmDialog({
    title: `Удалить ${orderLabel}?`,
    description: 'Заказ будет безвозвратно удалён вместе со связанными документами, выездами и платежами.',
    confirmText: 'Удалить заказ',
    variant: 'danger',
  });
  if (!proceed) return;

  isDeleting.value = true;
  try {
    await ManagerOrdersService.deleteManagerOrder(props.order.id);
    toast.value = 'Заказ успешно удален';
    setTimeout(() => {
      toast.value = '';
      emit('deleted', props.order!.id);
      void closeDrawer({ force: true });
    }, 1500);
  } catch (err: any) {
    localFormError.value = getApiErrorMessage(err) || 'Ошибка при удалении заказа';
  } finally {
    isDeleting.value = false;
  }
};
const getFieldError = (field: string): string => localServerErrors.value[field] || props.serverErrors?.[field] || '';
const displayFormError = computed(() => localFormError.value || props.formError || '');
const closeCustomerModal = () => {
  showCustomerModal.value = false;
};

const openCustomerProfile = () => {
  const customerId = props.order?.customer?.id;
  if (!customerId) return;
  showCustomerModal.value = false;
  const returnTo = `${window.location.pathname}${window.location.search}`;
  const query = new URLSearchParams({
    customerId: String(customerId),
    returnTo,
  });
  window.history.pushState({}, '', `/manager/customers/profile?${query.toString()}`);
  window.dispatchEvent(new PopStateEvent('popstate'));
};

const saveCustomerInline = async (payload: { name: string; phone: string; email: string }) => {
  const customerId = customer.value?.id;
  if (!customerId || savingCustomerInline.value) return;
  savingCustomerInline.value = true;
  try {
    await api.patchManagerCustomer(customerId, {
      name: payload.name,
      full_legal_name: customer.value?.type === 'company' ? payload.name : undefined,
      phone: payload.phone || null,
      email: payload.email || null,
    });
    setToast('Контакты клиента обновлены', 'success');
    if (props.order?.id) emit('reload', props.order.id);
  } catch (error) {
    setToast('Не удалось обновить клиента: ' + getApiErrorMessage(error), 'error');
  } finally {
    savingCustomerInline.value = false;
  }
};

const openWorkspaceTarget = async (target: OrderWorkspaceTarget, allowToggle = false) => {
  const shouldClose = allowToggle && activeWorkspaceTarget.value === target;
  if (activeWorkspaceTarget.value === 'equipment') equipmentPanelRef.value?.collapse();
  if (workflowType.value === 'sales_installation' && target !== 'object') {
    expandedDrawerSections.value.proposals = false;
    expandedDrawerSections.value.documents = false;
    expandedDrawerSections.value.payments = false;
    expandedDrawerSections.value.execution = false;
    executionWorkspaceSection.value = null;
  }
  if (shouldClose) {
    activeWorkspaceTarget.value = null;
    return;
  }
  if (target !== 'object') activeWorkspaceTarget.value = target;
  if (target === 'object') expandedDrawerSections.value.clientDetails = true;
  if (target === 'planning') {
    if (workflowType.value === 'sales_installation') expandedDrawerSections.value.proposals = true;
    if (status.value === 'execution') expandedDrawerSections.value.execution = true;
    else expandedDrawerSections.value.planningDetails = true;
  }
  if (target === 'proposal') expandedDrawerSections.value.proposals = true;
  if (target === 'documents') {
    if (status.value === 'execution') executionWorkspaceSection.value = 'documents';
    else expandedDrawerSections.value.documents = true;
  }
  if (target === 'payments') {
    if (status.value === 'execution') executionWorkspaceSection.value = 'payments';
    else expandedDrawerSections.value.payments = true;
  }
  await nextTick();
  if (target === 'equipment') {
    expandedDrawerSections.value.proposals = true;
    await equipmentPanelRef.value?.expand();
    await nextTick();
  }
  const elementId = status.value === 'execution' && (target === 'documents' || target === 'payments')
    ? 'order-workspace-execution-details'
    : 'order-workspace-' + target;
  document.getElementById(elementId)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
};

const discardUnsavedChanges = async () => {
  if (!props.order) return;
  clearDraft();
  await initForm(props.order);
  setToast('Изменения отменены', 'success');
};

watch(
  () => productLines.value,
  () => {
    persistDraft();
  },
  { deep: true },
);

watch(
  () => serviceLines.value,
  () => {
    persistDraft();
  },
  { deep: true },
);

watch(
  () => expandedDrawerSections.value,
  () => {
    persistDrawerSections();
  },
  { deep: true },
);
</script>

<template>
  <div v-if="modelValue" class="fixed inset-0 z-50 flex">
    <Transition name="fade">
      <div v-if="toast" class="fixed top-6 right-6 z-[100] bg-teal-600 text-white px-6 py-3 rounded-xl shadow-2xl font-medium">
        {{ toast }}
      </div>
    </Transition>
    <div class="flex-1 bg-black/60" @click="closeDrawer" />
    <aside ref="drawerScrollContainer" class="h-full w-full min-w-0 max-w-3xl overflow-y-auto bg-white text-gray-900 shadow-2xl dark:bg-slate-950 dark:text-slate-100 md:border-l md:border-gray-200 dark:md:border-slate-700">
      <OrderWorkspaceHeader
        :order-id="order?.id"
        :title="displayOrderTitle"
        :customer-name="customerDisplayName"
        :workflow="workflowType"
        :view-model="orderWorkspace"
        :total="totalPreview"
        :paid="totalPaymentsPreview"
        :balance="balanceDuePreview"
        :is-website-order="isWebsiteOrder"
        :is-on-hold="order?.is_on_hold"
        :dirty="hasUnsavedChanges"
        :saving="saving"
        :compact="compactWorkspaceHeader"
        @update:title="orderTitle = $event"
        @change-workflow="setWorkflowType"
        @next="handleWorkspaceNextAction"
        @payments="openWorkspaceTarget('payments')"
        @hold="toggleHold"
        @delete="deleteOrder"
        @discard="discardUnsavedChanges"
        @save="handleSave"
        @close="closeDrawer"
      />

      <div class="p-4 sm:p-6">
      <div v-if="managerLabels.length || showManagerLabelInput" class="mt-3 flex flex-wrap items-center gap-1.5">
        <span
          v-for="label in managerLabels"
          :key="label"
          class="inline-flex items-center gap-1 rounded-full border border-teal-200 bg-teal-50 px-2 py-1 text-xs font-medium text-teal-800 dark:border-teal-500/30 dark:bg-teal-500/10 dark:text-teal-200"
        >
          {{ label }}
          <button type="button" class="rounded-full p-0.5 hover:bg-teal-100 dark:hover:bg-teal-800" :aria-label="'Удалить метку ' + label" @click="removeManagerLabel(label)">
            <span class="material-icons-round block text-[13px]">close</span>
          </button>
        </span>
        <button v-if="!showManagerLabelInput" type="button" class="inline-flex items-center gap-1 rounded-full border border-dashed border-slate-300 px-2 py-1 text-xs font-medium text-slate-500 hover:border-teal-300 hover:text-teal-700 dark:border-slate-700 dark:text-slate-400" @click="showManagerLabelInput = true">
          <span class="material-icons-round text-[13px]">add</span> Добавить метку
        </button>
        <div v-if="showManagerLabelInput" class="flex min-w-[190px] gap-1.5">
          <input v-model="managerLabelDraft" class="field-input h-8 text-xs" placeholder="Новая метка" @keydown.enter.prevent="addManagerLabel" @keydown.esc.prevent="showManagerLabelInput = false" />
          <button type="button" class="btn-mini h-8 px-2 text-xs" @click="addManagerLabel">Добавить</button>
        </div>
      </div>
      <button v-else type="button" class="mt-2 inline-flex items-center gap-1 text-xs font-medium text-slate-500 hover:text-teal-700 dark:text-slate-400 dark:hover:text-teal-300" @click="showManagerLabelInput = true">
        <span class="material-icons-round text-[14px]">add</span> Добавить метку
      </button>

      <OrderCustomerObjectSummary
        :customer="customer"
        :branch="selectedCustomerBranch"
        :address="compactObjectAddress"
        :has-comment="Boolean(comment.trim())"
        :saving-customer="savingCustomerInline"
        @copy="copyText"
        @save-customer="saveCustomerInline"
        @update:address="customerDeliveryAddress = $event"
        @open-customer="openCustomerProfile"
        @change-customer="showChangeCustomerModal = true"
        @toggle-branch="showBranchFields = !showBranchFields"
      />

      <div v-if="showBranchFields && customer?.id" class="mt-2 grid gap-2 rounded-xl border border-slate-200 bg-slate-50 p-3 dark:border-slate-700 dark:bg-slate-900 sm:grid-cols-2">
        <label class="field-label sm:col-span-2">
          Филиал клиента
          <select :value="customerBranchId ?? ''" class="field-input mt-1" :disabled="customerBranchesLoading" @change="onCustomerBranchChange">
            <option value="">Без филиала</option>
            <option v-for="branch in customerBranches" :key="'compact-branch-' + branch.id" :value="branch.id">
              {{ branch.name || 'Филиал #' + branch.id }} — {{ branch.delivery_address }}
            </option>
          </select>
        </label>
        <input v-model="newBranchName" class="field-input" placeholder="Название нового филиала" />
        <AddressSuggestInput v-model="newBranchAddress" placeholder="Адрес нового филиала" />
        <div class="sm:col-span-2 flex justify-end">
          <button type="button" class="btn-mini-outline text-xs" :disabled="creatingCustomerBranch" @click="createCustomerBranch">
            {{ creatingCustomerBranch ? 'Создаём...' : 'Создать и выбрать' }}
          </button>
        </div>
      </div>

      <OrderSalesInstallationWorkspace
        v-if="workflowType === 'sales_installation'"
        :lanes="orderWorkspace.lanes"
        :active-target="activeWorkspaceTarget"
        @open="openWorkspaceTarget($event, true)"
      />

      <p v-if="displayFormError" class="mb-4 rounded-xl border border-red-500/40 bg-red-50 px-3 py-2 text-sm text-red-700">
        {{ displayFormError }}
      </p>

      <OrderDrawerSection
        id="order-workspace-object"
        v-model:expanded="expandedDrawerSections.clientDetails"
        title="Подробнее об объекте"
        :summary="customerDetailsSummary"
        tone="default"
        :has-error="Boolean(getFieldError('customer_delivery_address') || getFieldError('comment'))"
      >
        <div class="grid gap-3 md:grid-cols-2">
          <AddressSuggestInput
            v-model="customerDeliveryAddress"
            class="md:col-span-2"
            label="Адрес объекта / доставки"
            placeholder="Введите адрес..."
            :error="getFieldError('customer_delivery_address')"
          />

          <label class="field-label md:col-span-2">
            Комментарий
            <textarea
              v-model="comment"
              class="field-input min-h-[90px]"
              :class="getFieldError('comment') ? 'border-red-500 focus:outline-red-400' : ''"
            />
            <span v-if="getFieldError('comment')" class="text-xs text-red-300">{{ getFieldError('comment') }}</span>
          </label>
        </div>
      </OrderDrawerSection>

      <OrderEquipmentPanel
        v-if="order"
        ref="equipmentPanelRef"
        id="order-workspace-equipment"
        :key="`order-equipment-${order.id}`"
        class="mt-4"
        :order-id="order.id"
        :customer-id="customer?.id"
        :customer-branch-id="customerBranchId"
        :initial-count="order.linked_equipment_count"
        :has-catalog-products="productLines.some((line) => Boolean(line.product_id))"
        @options-change="linkedEquipmentOptions = $event"
        @reload="emit('reload', order.id)"
        @error="setToast($event, 'error')"
      />

      <OrderAttachmentsPanel
        v-if="order"
        :key="`order-attachments-${order.id}`"
        class="mt-4"
        :order-id="order.id"
        :initial-count="order.attachment_count"
        :equipment-options="linkedEquipmentOptions"
        @error="setToast($event, 'error')"
      />

      <OrderDrawerSection
        v-if="isWebsiteOrder"
        v-model:expanded="expandedDrawerSections.website"
        title="Входящий заказ с сайта"
        :summary="websiteOrderSummary"
        tone="emerald"
      >
        <div class="mb-4 flex flex-wrap items-start justify-between gap-3">
          <div>
            <p class="text-[11px] font-semibold uppercase tracking-[0.14em] text-emerald-700">Входящий заказ с сайта</p>
            <p class="mt-1 text-sm text-gray-500">
              <span v-if="formatDateTime(order?.created_at)">Создан: {{ formatDateTime(order?.created_at) }}</span>
              <span v-if="order?.status" class="ml-2 inline-flex items-center rounded-full bg-white px-2 py-0.5 text-[11px] font-medium text-gray-600 ring-1 ring-gray-200">
                {{ order.status }}
              </span>
            </p>
          </div>
          <div class="flex flex-wrap gap-2">
            <button
              type="button"
              class="inline-flex items-center gap-1 rounded-lg bg-white px-3 py-2 text-xs font-medium text-gray-700 shadow-sm ring-1 ring-gray-200 transition hover:bg-gray-50"
              @click="copyText(customer?.phone, 'Телефон')"
            >
              <span class="material-icons-round text-[16px]">content_copy</span>
              Телефон
            </button>
            <button
              type="button"
              class="inline-flex items-center gap-1 rounded-lg bg-white px-3 py-2 text-xs font-medium text-gray-700 shadow-sm ring-1 ring-gray-200 transition hover:bg-gray-50"
              @click="copyText(customerDeliveryAddress, 'Адрес')"
            >
              <span class="material-icons-round text-[16px]">content_copy</span>
              Адрес
            </button>
          </div>
        </div>

        <div class="grid gap-3 md:grid-cols-2">
          <div class="rounded-xl bg-white/90 p-3 ring-1 ring-emerald-100">
            <p class="text-[11px] font-semibold uppercase tracking-[0.12em] text-gray-500">Клиент</p>
            <p class="mt-2 text-sm font-semibold text-gray-900">{{ customer?.full_legal_name || customer?.name || 'Без имени' }}</p>
            <p v-if="customer?.phone" class="mt-1 text-sm text-gray-700">{{ customer.phone }}</p>
            <p v-if="customer?.email" class="mt-1 text-sm text-gray-500">{{ customer.email }}</p>
          </div>

          <div class="rounded-xl bg-white/90 p-3 ring-1 ring-emerald-100">
            <p class="text-[11px] font-semibold uppercase tracking-[0.12em] text-gray-500">Адрес доставки</p>
            <p class="mt-2 text-sm font-medium text-gray-900">{{ customerDeliveryAddress || 'Адрес не указан' }}</p>
          </div>

          <div class="rounded-xl bg-white/90 p-3 ring-1 ring-emerald-100 md:col-span-2">
            <div class="flex items-center justify-between gap-3">
              <p class="text-[11px] font-semibold uppercase tracking-[0.12em] text-gray-500">Состав заказа</p>
              <span class="text-xs font-medium text-emerald-700">
                {{ websiteProductSummaryLines.length + websiteServiceSummaryLines.length }} поз.
              </span>
            </div>
            <div class="mt-3 space-y-2">
              <div
                v-for="line in websiteProductSummaryLines"
                :key="`website-product-${line.id}`"
                class="rounded-xl border border-gray-100 bg-gray-50 px-3 py-2"
              >
                <div class="flex items-start justify-between gap-3">
                  <div>
                    <p class="text-sm font-medium text-gray-900">{{ line.title }}</p>
                    <div class="mt-1 flex flex-wrap gap-2 text-xs text-gray-500">
                      <span>Кол-во: {{ line.quantity }}</span>
                      <span v-if="line.installationIncluded" class="inline-flex items-center gap-1 rounded-full bg-blue-50 px-2 py-0.5 text-blue-700">
                        <span class="material-icons-round text-[14px]">construction</span>
                        Монтаж включен
                        <span v-if="line.installationPrice > 0">+ {{ formatMoney(line.installationPrice) }}</span>
                      </span>
                    </div>
                  </div>
                  <span class="whitespace-nowrap text-sm font-semibold text-gray-800">{{ formatMoney(line.lineTotal) }}</span>
                </div>
              </div>

              <div
                v-for="line in websiteServiceSummaryLines"
                :key="`website-service-${line.id}`"
                class="flex items-start justify-between gap-3 rounded-xl border border-gray-100 bg-gray-50 px-3 py-2"
              >
                <div>
                  <p class="text-sm font-medium text-gray-900">{{ line.title }}</p>
                  <p class="mt-1 text-xs text-gray-500">Кол-во: {{ line.quantity }}</p>
                </div>
                <span class="whitespace-nowrap text-sm font-semibold text-gray-800">{{ formatMoney(line.lineTotal) }}</span>
              </div>

              <p
                v-if="!websiteProductSummaryLines.length && !websiteServiceSummaryLines.length"
                class="rounded-xl border border-dashed border-gray-200 px-3 py-4 text-sm text-gray-500"
              >
                Позиции заказа отсутствуют.
              </p>
            </div>
          </div>

          <div v-if="comment?.trim()" class="rounded-xl bg-white/90 p-3 ring-1 ring-emerald-100 md:col-span-2">
            <p class="text-[11px] font-semibold uppercase tracking-[0.12em] text-gray-500">Комментарий клиента</p>
            <p class="mt-2 whitespace-pre-line text-sm text-gray-800">{{ comment }}</p>
          </div>
        </div>
      </OrderDrawerSection>



      <!-- Планирование (Measurement & Logistics) -->
      <section v-if="status === 'negotiation'" id="order-workspace-planning" class="mt-4 rounded-2xl border border-blue-100 bg-blue-50/30 p-3 dark:border-blue-500/30 dark:bg-blue-500/10">
        <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div class="min-w-0">
            <h3 class="text-sm font-semibold text-blue-900 dark:text-blue-100">{{ planningTitle }}</h3>
            <p class="mt-0.5 truncate text-xs text-blue-700/70 dark:text-blue-200/70">{{ planningSummary }}</p>
          </div>
          <button
            v-if="!measurementRequired"
            type="button"
            class="btn-mini-outline justify-center whitespace-nowrap text-xs"
            @click="measurementRequired = true"
          >
            <span class="material-icons-round text-[15px]">add_location_alt</span>
            {{ isRepairWorkflow ? 'Назначить диагностику' : 'Назначить замер' }}
          </button>
          <label v-else class="inline-flex items-center gap-2 rounded-xl bg-white px-3 py-2 text-xs font-medium text-blue-900 ring-1 ring-blue-100 dark:bg-slate-900 dark:text-blue-100 dark:ring-blue-500/30">
            <input type="checkbox" v-model="measurementRequired" class="h-4 w-4 rounded border-gray-300 text-teal-600 focus:ring-teal-600" />
            {{ isRepairWorkflow ? 'Диагностика нужна' : 'Замер нужен' }}
          </label>
        </div>

        <div class="mt-3 rounded-xl border border-blue-100 bg-white p-3 shadow-sm dark:border-blue-500/30 dark:bg-slate-900">
          <label class="block">
            <span class="text-xs font-semibold uppercase tracking-[0.12em] text-blue-900/70 dark:text-blue-200/80">Состояние переговоров</span>
            <select :value="negotiationStatus" class="field-input mt-2 bg-white dark:bg-slate-950" @change="setNegotiationStatus(($event.target as HTMLSelectElement).value)">
              <option v-for="option in NEGOTIATION_STATUS_OPTIONS" :key="option.value" :value="option.value">{{ option.label }}</option>
            </select>
          </label>
          <label class="mt-3 flex items-start gap-2 rounded-xl border border-emerald-100 bg-emerald-50/70 px-3 py-2 text-xs text-emerald-900 dark:border-emerald-500/30 dark:bg-emerald-500/10 dark:text-emerald-100">
            <input v-model="autoExecutionOnPayment" type="checkbox" class="mt-0.5 h-4 w-4 rounded border-gray-300 text-teal-600 focus:ring-teal-600" />
            <span>
              <span class="block font-semibold">После полной оплаты автоматически перевести заказ в этап «Работы»</span>
              <span class="mt-0.5 block text-emerald-700/80 dark:text-emerald-200/70">Сработает автоматически, когда долг по заказу станет нулевым.</span>
            </span>
          </label>
        </div>

        <div v-if="measurementRequired" class="mt-3 rounded-xl border border-blue-100 bg-white p-3 shadow-sm dark:border-blue-500/30 dark:bg-slate-900">
          <DateTimeField v-model="assessmentDate" :label="isRepairWorkflow ? 'Дата и время диагностики' : 'Дата и время замера'" :error="getFieldError('measurement_date')" />
        </div>

        <OrderDrawerSection
          v-model:expanded="expandedDrawerSections.planningDetails"
          :title="isRepairWorkflow ? 'Детали диагностики и ремонта' : 'Детали выезда и монтажа'"
          :summary="planningDetailsSummary"
          tone="blue"
          :has-error="Boolean(getFieldError('measurement_date') || getFieldError('installation_date'))"
        >
          <div class="grid gap-3 md:grid-cols-2">
            <template v-if="measurementRequired">
              <label class="field-label">
                {{ isRepairWorkflow ? 'Специалист' : 'Замерщик' }}
                <select v-model="measurerId" class="field-input">
                  <option :value="null">Не назначен</option>
                  <option v-for="inst in executorOptions" :key="inst.id" :value="inst.id">
                    {{ inst.name }} {{ !inst.is_active ? '(в архиве)' : '' }}
                  </option>
                </select>
              </label>
              <label class="field-label md:col-span-2">
                Результат замера
                <textarea
                  v-model="measurementResult"
                  class="field-input min-h-[60px]"
                  :placeholder="isRepairWorkflow ? 'Краткий результат диагностики...' : 'Резюме после выезда (длины трасс, доп. работы)...'"
                />
              </label>
            </template>
            <DateTimeField v-model="installationDate" :label="workDateLabel" :error="getFieldError('installation_date')" />
            <label class="field-label">
              {{ isRepairWorkflow ? 'Исполнитель ремонта' : 'Монтажник' }}
              <select v-model="installerId" class="field-input">
                <option :value="null">Не назначен</option>
                <option v-for="inst in executorOptions" :key="inst.id" :value="inst.id">
                  {{ inst.name }} {{ !inst.is_active ? '(в архиве)' : '' }}
                </option>
              </select>
            </label>
          </div>
        </OrderDrawerSection>
      </section>


      <OrderDrawerSection
        v-if="isRepairWorkflow"
        v-model:expanded="expandedDrawerSections.repair"
        title="Ремонт / диагностика"
        :summary="repairSectionSummary"
        tone="default"
      >
        <div class="grid gap-3 md:grid-cols-2">
          <div class="md:col-span-2 rounded-xl border border-teal-100 bg-teal-50/50 p-3">
            <div class="mb-2 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <p class="text-sm font-semibold text-teal-900">Библиотека жалоб</p>
                <p class="text-xs text-teal-700/80">Выберите типовую жалобу, чтобы заполнить формулировку и вероятный диагноз.</p>
              </div>
              <button
                type="button"
                class="btn-mini-outline justify-center whitespace-nowrap text-xs"
                :disabled="repairComplaintsLoading"
                @click="loadRepairComplaintPresets"
              >
                <span class="material-icons-round text-[15px]" :class="{ 'animate-spin': repairComplaintsLoading }">refresh</span>
                Обновить
              </button>
            </div>
            <input
              v-model="repairComplaintSearch"
              type="search"
              class="field-input mb-2"
              placeholder="Найти: не холодит, капает, шумит..."
            />
            <div v-if="filteredRepairComplaintPresets.length" class="flex max-h-44 flex-wrap gap-2 overflow-auto pr-1">
              <button
                v-for="preset in filteredRepairComplaintPresets"
                :key="preset.id"
                type="button"
                class="rounded-lg border bg-white px-3 py-2 text-left text-xs shadow-sm transition hover:border-teal-300 hover:text-teal-800"
                :class="preset.is_favorite ? 'border-teal-200 text-teal-900' : 'border-slate-200 text-slate-700'"
                @click="applyRepairComplaintPreset(preset)"
              >
                <span class="flex items-center gap-1 font-semibold">
                  <span v-if="preset.is_favorite" class="material-icons-round text-[14px] text-amber-500">star</span>
                  {{ preset.customer_phrase }}
                </span>
                <span v-if="preset.document_wording" class="mt-1 line-clamp-2 block max-w-[260px] opacity-75">{{ preset.document_wording }}</span>
              </button>
            </div>
            <p v-else class="rounded-lg border border-dashed border-teal-200 bg-white/70 px-3 py-3 text-xs text-teal-700">
              {{ repairComplaintsLoading ? 'Загружаем пресеты...' : 'Подходящих пресетов пока нет.' }}
            </p>
          </div>
          <div class="md:col-span-2 rounded-xl border border-violet-100 bg-violet-50/60 p-3">
            <div class="mb-2 flex flex-col gap-2 lg:flex-row lg:items-end">
              <div class="min-w-0 flex-1">
                <p class="text-sm font-semibold text-violet-950">AI-черновик по выбранной неисправности</p>
                <p class="mt-1 truncate text-xs text-violet-700/80">
                  {{ selectedRepairAiDefect?.label || 'Базовая неисправность не выбрана' }}
                </p>
              </div>
              <button
                type="button"
                class="btn-mini h-[42px] justify-center whitespace-nowrap bg-violet-600 hover:bg-violet-700"
                :disabled="repairAiGenerating"
                @click="generateRepairAiDraft"
              >
                <span v-if="repairAiGenerating" class="material-icons-round animate-spin text-[16px]">loop</span>
                <span v-else class="material-icons-round text-[16px]">auto_awesome</span>
                AI-черновик
              </button>
            </div>
            <div class="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
              <p class="text-xs text-violet-700/80">{{ selectedRepairAiDefect?.hint }}</p>
              <div class="flex flex-col gap-2 sm:flex-row sm:items-center">
                <label class="inline-flex items-center gap-2 rounded-lg bg-white/70 px-2.5 py-1.5 text-xs font-semibold text-violet-800">
                  <input v-model="repairAiPolishExisting" type="checkbox" class="h-4 w-4 rounded border-violet-300 text-violet-600 focus:ring-violet-500" />
                  Причесать заполненное
                </label>
                <label class="inline-flex items-center gap-2 rounded-lg bg-white/70 px-2.5 py-1.5 text-xs font-semibold text-violet-800">
                  <input v-model="repairAiAllowAssumptions" type="checkbox" class="h-4 w-4 rounded border-violet-300 text-violet-600 focus:ring-violet-500" />
                  Заполнить на усмотрение
                </label>
              </div>
            </div>
          </div>
          <details class="md:col-span-2 rounded-xl border border-slate-200 bg-slate-50 p-3">
            <summary class="cursor-pointer select-none text-sm font-semibold text-slate-900">
              Статусы, согласование и запчасти
              <span class="ml-2 text-xs font-normal text-slate-500">{{ repairWorkflowStatusLabel || 'не указано' }}</span>
            </summary>
            <div class="mt-3 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
              <label class="field-label">
                Этап ремонта
                <select v-model="repairMeta.repair_status" class="field-input bg-white">
                  <option v-for="option in REPAIR_WORKFLOW_STATUS_OPTIONS" :key="option.value" :value="option.value">
                    {{ option.label }}
                  </option>
                </select>
              </label>
              <label class="field-label">
                Согласование клиента
                <select v-model="repairMeta.customer_approval_status" class="field-input bg-white">
                  <option v-for="option in customerApprovalStatusOptions" :key="`approval-${option.value || 'empty'}`" :value="option.value">
                    {{ option.label }}
                  </option>
                </select>
              </label>
              <label class="field-label">
                Запчасти
                <select v-model="repairMeta.parts_status" class="field-input bg-white">
                  <option v-for="option in partsStatusOptions" :key="`parts-${option.value || 'empty'}`" :value="option.value">
                    {{ option.label }}
                  </option>
                </select>
              </label>
              <label class="field-label">
                Комментарий согласования
                <textarea
                  v-model="repairMeta.customer_approval_note"
                  class="field-input min-h-[64px] bg-white"
                  placeholder="Кто согласовал, когда, условия"
                />
              </label>
              <label class="field-label">
                Комментарий по запчастям
                <textarea
                  v-model="repairMeta.parts_note"
                  class="field-input min-h-[64px] bg-white"
                  placeholder="Что нужно, сроки, поставщик"
                />
              </label>
              <label class="field-label">
                Итог ремонта
                <textarea
                  v-model="repairMeta.repair_completion_note"
                  class="field-input min-h-[64px] bg-white"
                  placeholder="Что выполнено или почему закрыто"
                />
              </label>
            </div>
          </details>
          <label class="field-label md:col-span-2">
            Жалоба клиента
            <textarea
              v-model="repairMeta.customer_complaint"
              class="field-input min-h-[72px]"
              placeholder="Например: не охлаждает, шумит, течет вода..."
            />
          </label>
          <label class="field-label">
            Базовая неисправность
            <select v-model="repairAiDefectType" class="field-input">
              <option v-for="item in REPAIR_AI_DEFECT_TYPES" :key="`main-${item.value}`" :value="item.value">
                {{ item.label }}
              </option>
            </select>
          </label>
          <label class="field-label md:col-span-2">
            Детали диагностики / заметки инженера
            <textarea
              v-model="repairMeta.diagnostic_notes"
              class="field-input min-h-[72px]"
              placeholder="Что увидел инженер: симптомы, проверки, ограничения, важные нюансы"
            />
          </label>
          <label class="field-label">
            Результат диагностики
            <textarea
              v-model="repairMeta.diagnostic_result"
              class="field-input min-h-[88px]"
              placeholder="Что выявлено при диагностике, без лишних чисел и предположений"
            />
          </label>
          <label class="field-label">
            Рекомендация по ремонту
            <textarea
              v-model="repairMeta.repair_recommendation"
              class="field-input min-h-[88px]"
              placeholder="Что сделать: устранить утечку, заменить узел, дозаправить..."
            />
          </label>
          <label class="field-label md:col-span-2">
            Формулировка для сметы ремонта
            <textarea
              v-model="repairMeta.repair_estimate_text"
              class="field-input min-h-[72px]"
              placeholder="Короткая строка работ для сметы"
            />
          </label>
          <label class="field-label">
            Возможен ремонт
            <select v-model="repairMeta.repair_possible" class="field-input">
              <option v-for="option in repairPossibleOptions" :key="`repair-possible-${option || 'empty'}`" :value="option">
                {{ option || 'Не указано' }}
              </option>
            </select>
          </label>
          <label class="field-label">
            Ремонт невозможен / нецелесообразен
            <select v-model="repairMeta.repair_not_viable" class="field-input">
              <option v-for="option in repairNotViableOptions" :key="`repair-not-viable-${option || 'empty'}`" :value="option">
                {{ option || 'Не указано' }}
              </option>
            </select>
          </label>
          <label class="field-label">
            Хладагент
            <input v-model="repairMeta.refrigerant_type" class="field-input" placeholder="R32, R410A..." />
          </label>
          <label class="field-label">
            Количество хладагента
            <input v-model="repairMeta.refrigerant_amount" class="field-input" placeholder="0,45 кг или по факту" />
          </label>
          <label class="field-label md:col-span-2">
            Расчет хладагента
            <input
              v-model="repairMeta.refrigerant_pricing_mode"
              list="refrigerant-pricing-mode-options"
              class="field-input"
              placeholder="по фактической массе, включен в стоимость..."
            />
            <datalist id="refrigerant-pricing-mode-options">
              <option v-for="option in REFRIGERANT_PRICING_MODE_OPTIONS" :key="option" :value="option" />
            </datalist>
          </label>
          <label class="field-label md:col-span-2">
            Причина неремонтопригодности
            <textarea
              v-model="repairMeta.repair_not_viable_reason"
              class="field-input min-h-[72px]"
              placeholder="Заполняйте, если ремонт невозможен или экономически нецелесообразен"
            />
          </label>

          <details class="md:col-span-2 rounded-xl border border-slate-200 bg-slate-50 p-3">
            <summary class="cursor-pointer select-none text-sm font-semibold text-slate-900">
              Оборудование и паспортные данные
              <span class="ml-2 text-xs font-normal text-slate-500">{{ repairMeta.equipment_model || repairMeta.equipment_name || 'не заполнено' }}</span>
            </summary>
            <div class="mt-3 grid gap-3 md:grid-cols-2">
          <label class="field-label">
            Оборудование
            <input v-model="repairMeta.equipment_name" class="field-input" placeholder="Кондиционер настенный" />
          </label>
          <label class="field-label">
            Бренд
            <input v-model="repairMeta.equipment_brand" class="field-input" placeholder="LG, Gree, Mitsubishi..." />
          </label>
          <label class="field-label">
            Модель
            <input v-model="repairMeta.equipment_model" class="field-input" placeholder="Модель внутреннего/наружного блока" />
          </label>
          <label class="field-label">
            Мощность
            <input v-model="repairMeta.equipment_power" class="field-input" placeholder="2,5 кВт" />
          </label>
          <label class="field-label">
            Серийный номер
            <input v-model="repairMeta.equipment_serial_number" class="field-input" placeholder="SN..." />
          </label>
          <label class="field-label">
            Инвентарный номер
            <input v-model="repairMeta.equipment_inventory_number" class="field-input" placeholder="Инв. номер заказчика" />
          </label>
          <label class="field-label md:col-span-2">
            Дата ввода в эксплуатацию
            <input v-model="repairMeta.equipment_commissioning_date" class="field-input" placeholder="Например: 2021 г. или 12.05.2021" />
          </label>

          <div class="md:col-span-2 rounded-xl border border-slate-200 bg-slate-50 p-3">
            <div class="mb-3 flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
              <div class="min-w-0">
                <p class="text-sm font-semibold text-slate-900">Карточка оборудования и история</p>
                <p class="mt-1 text-xs text-slate-600">
                  История оборудования записывается отдельным действием и не меняет CRM/Kanban статус заказа.
                </p>
              </div>
              <div class="flex flex-wrap gap-2">
                <button
                  type="button"
                  class="btn-mini-outline justify-center whitespace-nowrap text-xs"
                  :disabled="repairEquipmentLoading"
                  @click="loadRepairEquipment"
                >
                  Обновить
                </button>
                <button
                  type="button"
                  class="btn-mini justify-center whitespace-nowrap text-xs"
                  :disabled="creatingRepairEquipment || !customer?.id"
                  @click="createRepairEquipmentFromMeta"
                >
                  {{ creatingRepairEquipment ? 'Создаем...' : 'Создать из полей' }}
                </button>
              </div>
            </div>

            <p v-if="repairEquipmentError" class="mb-3 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
              {{ repairEquipmentError }}
            </p>

            <div v-if="!customer?.id" class="rounded-lg border border-dashed border-slate-200 bg-white px-3 py-4 text-center text-xs text-slate-500">
              Выберите клиента, чтобы вести оборудование.
            </div>
            <div v-else-if="repairEquipmentLoading" class="rounded-lg border border-dashed border-slate-200 bg-white px-3 py-4 text-xs text-slate-500">
              Загружаем оборудование клиента...
            </div>
            <div v-else class="grid gap-3 lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
              <div class="space-y-2">
                <button
                  v-for="item in repairEquipment"
                  :key="item.id"
                  type="button"
                  class="w-full rounded-lg border px-3 py-2 text-left text-xs transition"
                  :class="selectedRepairEquipmentId === item.id
                    ? 'border-teal-400 bg-white text-teal-900 shadow-sm'
                    : 'border-slate-200 bg-white text-slate-700 hover:border-teal-200'"
                  @click="selectRepairEquipment(item.id)"
                >
                  <span class="block break-words font-semibold">{{ equipmentTitle(item) }}</span>
                  <span class="mt-1 block break-words text-slate-500">{{ equipmentSubtitle(item) }}</span>
                </button>
                <div v-if="!repairEquipment.length" class="rounded-lg border border-dashed border-slate-200 bg-white px-3 py-4 text-center text-xs text-slate-500">
                  {{ customerBranchId ? 'Для выбранного филиала оборудование не найдено.' : 'Оборудование клиента пока не заведено.' }}
                </div>
              </div>

              <div class="rounded-lg border border-slate-200 bg-white p-3">
                <div v-if="repairEquipmentHistoryLoading" class="text-xs text-slate-500">Загружаем историю...</div>
                <template v-else-if="selectedRepairEquipment">
                  <div class="mb-3">
                    <p class="break-words text-sm font-semibold text-slate-900">{{ equipmentTitle(selectedRepairEquipment) }}</p>
                    <p class="mt-1 break-words text-xs text-slate-500">{{ equipmentSubtitle(selectedRepairEquipment) }}</p>
                  </div>
                  <div class="grid gap-2 sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
                    <label class="field-label !mb-0">
                      Тип записи из заказа
                      <select v-model="repairHistoryEventType" class="field-input bg-white">
                        <option value="">Определить автоматически</option>
                        <option v-for="option in EQUIPMENT_EVENT_OPTIONS" :key="option.value" :value="option.value">{{ option.label }}</option>
                      </select>
                    </label>
                    <label class="field-label !mb-0">
                      Заметка
                      <input v-model="repairHistoryNotes" class="field-input bg-white" placeholder="Например: закрыто после согласования" />
                    </label>
                  </div>
                  <button
                    type="button"
                    class="btn-mini mt-2 w-full justify-center text-xs"
                    :disabled="recordingRepairHistory || !selectedRepairEquipmentId || !order?.id"
                    @click="recordRepairHistoryFromOrder"
                  >
                    {{ recordingRepairHistory ? 'Записываем...' : 'Записать историю из этого ремонта' }}
                  </button>
                  <p class="mt-2 text-[11px] text-slate-500">
                    Действие создаст запись истории оборудования из repair meta текущего заказа. Статус заказа и этап ремонта останутся отдельными.
                  </p>

                  <div class="mt-3 max-h-56 space-y-2 overflow-y-auto pr-1">
                    <div
                      v-for="entry in selectedRepairEquipmentDetail?.recent_history || []"
                      :key="entry.id"
                      class="rounded-lg border border-slate-100 bg-slate-50 px-3 py-2 text-xs"
                    >
                      <div class="flex flex-wrap items-center gap-2">
                        <span class="rounded-full bg-teal-50 px-2 py-0.5 font-semibold text-teal-700">{{ equipmentEventLabel(entry.event_type) }}</span>
                        <span class="text-slate-500">{{ formatDateTime(entry.event_date) || 'Без даты' }}</span>
                        <span v-if="entry.order_id" class="text-slate-500">Заказ #{{ entry.order_id }}</span>
                      </div>
                      <p class="mt-1 break-words text-slate-600">{{ repairHistoryLine(entry) }}</p>
                    </div>
                    <div v-if="!(selectedRepairEquipmentDetail?.recent_history || []).length" class="rounded-lg border border-dashed border-slate-200 px-3 py-3 text-center text-xs text-slate-500">
                      История пока пустая
                    </div>
                  </div>
                </template>
                <div v-else class="text-xs text-slate-500">Выберите оборудование слева или создайте карточку из полей ремонта.</div>
              </div>
            </div>
          </div>
            </div>
          </details>

          <details class="md:col-span-2 rounded-xl border border-amber-200 bg-amber-50/60 p-3">
            <summary class="cursor-pointer select-none text-sm font-semibold text-amber-900">
              Экспертный режим: JSON и ручные override-поля
            </summary>
            <div class="mt-3 grid gap-3 md:grid-cols-2">
              <label class="field-label md:col-span-2">
                Структурированные выводы AI
                <textarea :value="repairStructuredJson" readonly class="field-input min-h-[180px] font-mono text-xs" />
              </label>
              <label class="field-label">
                Формулировка для акта
                <textarea
                  v-model="repairMeta.complaint_official"
                  class="field-input min-h-[72px]"
                  placeholder="Override официальной формулировки жалобы"
                />
              </label>
              <label class="field-label">
                Вероятный диагноз
                <textarea
                  v-model="repairMeta.likely_diagnosis"
                  class="field-input min-h-[72px]"
                  placeholder="Override предварительной причины"
                />
              </label>
          <label class="field-label">
            Техническое состояние
            <textarea v-model="repairMeta.technical_condition" class="field-input min-h-[80px]" placeholder="Общее состояние, износ, загрязнение, следы вмешательства..." />
          </label>
          <label class="field-label">
            Проверка запуска
            <textarea v-model="repairMeta.startup_check_result" class="field-input min-h-[80px]" placeholder="Запускается / не запускается, ошибки, симптомы..." />
          </label>
          <label class="field-label">
            Проверка компрессора
            <textarea v-model="repairMeta.compressor_check_result" class="field-input min-h-[80px]" placeholder="Токи, сопротивления, срабатывание защиты..." />
          </label>
          <label class="field-label">
            Замеры / диагностика
            <textarea v-model="repairMeta.measurement_result" class="field-input min-h-[80px]" placeholder="Давление, температура, утечки, электрические замеры..." />
          </label>
          <label class="field-label">
            Возможность дальнейшей эксплуатации
            <textarea v-model="repairMeta.further_use_assessment" class="field-input min-h-[80px]" placeholder="Допускается / не допускается / с ограничениями..." />
          </label>
          <label class="field-label">
            Ограничения эксплуатации
            <textarea v-model="repairMeta.operation_restrictions" class="field-input min-h-[80px]" placeholder="Что нельзя делать до ремонта или замены" />
          </label>
          <label class="field-label">
            Целесообразность ремонта
            <textarea v-model="repairMeta.repair_feasibility" class="field-input min-h-[80px]" placeholder="Ремонт целесообразен / нецелесообразен..." />
          </label>
          <label class="field-label">
            Рекомендованное решение
            <textarea v-model="repairMeta.recommended_decision" class="field-input min-h-[80px]" placeholder="Ремонт, замена узла, списание, замена оборудования..." />
          </label>
          <label class="field-label md:col-span-2">
            Техническое заключение
            <textarea v-model="repairMeta.technical_conclusion" class="field-input min-h-[96px]" placeholder="Итоговый вывод для дефектного акта" />
          </label>
            </div>
          </details>
        </div>
      </OrderDrawerSection>



      <!-- Смета -->
      <OrderDrawerSection
        id="order-workspace-proposal"
        v-model:expanded="expandedDrawerSections.proposals"
        :title="isRepairWorkflow ? 'Смета ремонта' : 'Предложения'"
        :summary="activeProposalLineLabel"
        tone="default"
        :has-error="Boolean(getFieldError('products') || getFieldError('services'))"
      >
        <div class="min-w-0">
        <OrderProposalToolbar
          ref="proposalToolbarRef"
          class="mb-4"
          :proposals="orderProposals"
          :active-proposal-id="activeProposal?.id"
          :loading="proposalActionLoading"
          @open="onProposalClick"
          @select="selectProposalForOrder"
          @create="createProposal"
          @duplicate="duplicateProposal"
          @rename="renameProposal"
          @archive="archiveProposal"
          @change-status="changeActiveProposalStatus"
          @send="openProposalSend"
        />

        <div v-if="activeProposalLocked" class="mb-3 flex flex-col gap-2 rounded-xl border border-amber-200 bg-amber-50 p-3 text-xs text-amber-900 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-100 sm:flex-row sm:items-center sm:justify-between">
          <span>Эта редакция уже {{ activeProposalStatus === 'approved' ? 'принята клиентом' : 'отправлена' }}. Чтобы изменить состав или стоимость, создайте копию либо верните её в черновик.</span>
          <div class="flex shrink-0 gap-2">
            <button type="button" class="btn-mini-outline h-8 px-2 text-xs" @click="duplicateProposal">Создать копию</button>
            <button type="button" class="btn-mini-outline h-8 px-2 text-xs" @click="changeActiveProposalStatus('draft')">В черновик</button>
          </div>
        </div>

        <fieldset :disabled="activeProposalLocked" :class="activeProposalLocked ? 'opacity-60' : ''">

        <section v-if="showProductLinesSection" class="mt-2">
          <div class="mb-2 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
            <div class="flex flex-wrap items-center gap-3">
              <h4 class="text-md font-semibold text-gray-800">Товары</h4>
              <div class="flex items-center gap-2">
                <label class="flex items-center gap-1 text-xs text-gray-600 bg-white border border-gray-200 px-2 py-1 rounded shadow-sm cursor-pointer hover:bg-gray-50 transition-colors">
                  <input type="checkbox" v-model="searchInStock" class="rounded text-teal-600 focus:ring-teal-500 w-3 h-3 border-gray-300" />
                  В наличии
                </label>
              </div>
            </div>
        </div>
        <p v-if="getFieldError('products')" class="mb-2 text-xs text-red-300">{{ getFieldError('products') }}</p>
        <div class="space-y-2">
          <div
            v-for="(line, index) in productLines"
            :key="`product-${index}`"
            class="relative rounded-xl border border-gray-200 bg-white p-3 shadow-sm"
          >
            <button
              type="button"
              class="absolute -right-2 -top-2 z-10 inline-flex h-8 w-8 items-center justify-center rounded-full border border-red-200 bg-red-50 text-lg font-bold text-red-600 shadow-sm transition-colors hover:bg-red-100"
              :aria-label="`Удалить товар #${index + 1}`"
              title="Удалить товар"
              @click="removeProductLine(index)"
            >
              ×
            </button>
            <div class="grid grid-cols-6 gap-2 md:grid-cols-12 md:items-start">
              <label class="relative col-span-6 space-y-1 md:col-span-5">
                <span class="flex items-center justify-between gap-2 px-1 text-xs font-medium text-gray-500 md:h-6">
                  <span>Название</span>
                  <button
                    v-if="line.product_id"
                    class="text-xs font-semibold text-teal-700 hover:text-teal-900"
                    type="button"
                    @click="openSelectedProduct(index)"
                  >
                    Открыть ↗
                  </button>
                </span>
                <textarea
                  v-model="line.product_query"
                  class="field-input min-h-[44px] resize-none overflow-hidden text-sm leading-snug focus:min-h-[120px] focus:resize-y focus:overflow-auto sm:text-base"
                  rows="1"
                  placeholder="Поиск и выбор товара"
                  @focus="onProductInputFocus(index)"
                  @input="onProductQueryInput(index)"
                  @blur="onProductInputBlur(index)"
                />
                <div
                  v-if="!line.product_id && line.product_query.trim().length >= 2 && (productLookupLoading || getProductSuggestions(index).length)"
                  class="absolute left-0 right-0 top-full z-20 mt-1 max-h-56 overflow-auto rounded-[12px] border border-gray-200 bg-white p-1 shadow-xl"
                >
                  <div v-if="productLookupLoading" class="px-3 py-2 text-xs text-gray-500">Поиск товаров...</div>
                  <button
                    v-for="item in getProductSuggestions(index)"
                    :key="`product-suggest-${index}-${item.id}`"
                    type="button"
                    class="mb-1 block w-full rounded-[12px] px-3 py-2 text-left text-xs text-gray-700 hover:bg-slate-100 dark:hover:bg-slate-800 last:mb-0"
                    @mousedown.prevent
                    @click="selectProductForLine(index, item)"
                  >
                    <p class="truncate font-medium text-gray-900 dark:text-slate-100">{{ item.title }}</p>
                    <p class="mt-1 flex flex-wrap items-center gap-1 text-[11px] text-gray-500 dark:text-slate-300">
                      <span>{{ formatMoney(item.price) }}</span>
                      <span>·</span>
                      <span>{{ item.is_inverter ? 'Инвертор' : 'On/Off' }}</span>
                      <span>·</span>
                      <template v-if="item.vitebsk_qty > 0 || item.minsk_qty > 0">
                        <span v-if="item.vitebsk_qty > 0" class="font-medium text-emerald-600 bg-emerald-50 px-1 rounded">Вит: {{item.vitebsk_qty}}</span>
                        <span v-if="item.minsk_qty > 0" class="font-medium text-blue-500 bg-blue-50 px-1 rounded">Минск: {{item.minsk_qty}}</span>
                      </template>
                      <template v-else>
                        <span v-if="item.availability_status === 'check_availability'" class="font-medium text-amber-500">Уточнять</span>
                        <span v-else class="text-gray-400">Нет в наличии</span>
                      </template>
                    </p>
                  </button>
                </div>
              </label>
              <label class="col-span-4 space-y-1 md:col-span-2">
                <span class="flex h-auto items-center px-1 text-xs font-medium text-gray-500 md:h-6">Цена</span>
                <input v-model.number="line.price" type="number" min="0" class="field-input" placeholder="0" />
              </label>
              <label class="col-span-2 space-y-1 md:col-span-1">
                <span class="flex h-auto items-center whitespace-nowrap px-1 text-xs font-medium text-gray-500 md:h-6 md:text-[11px]">Кол-во</span>
                <input v-model.number="line.quantity" type="number" min="1" class="field-input" placeholder="1" />
              </label>
              <label class="col-span-3 space-y-1 md:col-span-2">
                <span class="flex h-auto items-center px-1 text-xs font-medium text-gray-500 md:h-6">Себест.</span>
                <input v-model.number="line.cost" type="number" min="0" class="field-input" placeholder="0" />
              </label>
              <div class="col-span-3 space-y-1 md:col-span-2">
                <span class="flex h-auto items-center px-1 text-xs font-medium text-gray-500 md:h-6">Итого</span>
                <div class="rounded-lg bg-gray-50 px-3 py-2">
                  <p class="whitespace-nowrap text-base font-semibold leading-tight text-gray-900">{{ formatMoney(lineTotal(line)) }}</p>
                </div>
              </div>
              <p
                v-if="isPriceDifferentFromCatalog(line)"
                class="col-span-6 rounded-md border border-amber-300 bg-amber-50 px-2 py-1 text-xs text-amber-700 md:col-span-12"
              >
                Цена строки отличается от каталожной ({{ formatMoney(currentCatalogPrice(line.product_id) || 0) }}).
              </p>
              <div class="col-span-6 flex flex-wrap items-center gap-2 border-t border-gray-100 pt-2 md:col-span-12">
                <span
                  v-if="supplyBadgeForLine(line)"
                  class="inline-flex items-center gap-1 rounded-full bg-teal-50 px-2 py-1 text-xs font-semibold text-teal-700"
                >
                  Поставка: {{ supplyBadgeForLine(line)?.label }}
                </span>
                <span v-else-if="line.link_id" class="text-xs text-gray-500">Поставка не создана</span>
                <button
                  type="button"
                  class="rounded-lg border border-teal-200 px-3 py-1.5 text-xs font-semibold text-teal-700 hover:bg-teal-50 disabled:opacity-50"
                  :disabled="!line.product_id || supplyActionLoadingLineId === line.link_id"
                  @click="createSupplyFromProductLine(line, 'order')"
                >
                  В поставку
                </button>
                <button
                  type="button"
                  class="rounded-lg border border-indigo-200 px-3 py-1.5 text-xs font-semibold text-indigo-700 hover:bg-indigo-50 disabled:opacity-50"
                  :disabled="!line.product_id || supplyActionLoadingLineId === line.link_id"
                  @click="createSupplyFromProductLine(line, 'reserve')"
                >
                  Забронировать
                </button>
              </div>
            </div>
          </div>
        </div>
        <button type="button" class="btn-mini mt-3 w-full justify-center" @click="addProductLine">+ товар</button>
      </section>

        <section class="mt-6">
          <div class="mb-2">
            <h4 class="text-md font-semibold text-gray-800">Услуги</h4>
          </div>
          <p v-if="getFieldError('services')" class="mb-2 text-xs text-red-300">{{ getFieldError('services') }}</p>
          <div class="space-y-2">
            <div
              v-for="(line, index) in serviceLines"
              :key="`service-${index}`"
              class="relative rounded-xl border border-gray-200 bg-white p-3 shadow-sm"
            >
              <button
                v-if="editingServiceLineIndex === index"
                type="button"
                class="absolute -right-2 -top-2 z-10 inline-flex h-8 w-8 items-center justify-center rounded-full border border-red-200 bg-red-50 text-lg font-bold text-red-600 shadow-sm transition-colors hover:bg-red-100"
                :aria-label="`Удалить услугу #${index + 1}`"
                title="Удалить услугу"
                @click="removeServiceLine(index)"
              >
                ×
              </button>
              <div v-if="editingServiceLineIndex !== index" class="flex min-w-0 items-start gap-3">
                <div class="min-w-0 flex-1">
                  <p class="break-words text-sm font-semibold leading-snug text-slate-900 dark:text-slate-100">{{ line.title || 'Новая услуга' }}</p>
                  <div class="mt-1 flex flex-wrap items-center justify-between gap-x-3 gap-y-1 text-xs text-slate-500 dark:text-slate-400">
                    <span>{{ line.quantity }} × {{ formatMoney(line.price) }}</span>
                    <span class="font-semibold text-slate-800 dark:text-slate-200">{{ formatMoney(lineTotal(line)) }}</span>
                  </div>
                </div>
                <button
                  type="button"
                  class="btn-mini-outline h-9 w-9 shrink-0 justify-center p-0"
                  :aria-label="`Редактировать услугу #${index + 1}`"
                  title="Редактировать"
                  @click="editingServiceLineIndex = index"
                >
                  <span class="material-icons-round text-[17px]">edit</span>
                </button>
              </div>
              <div v-else class="grid grid-cols-6 gap-2 md:grid-cols-12 md:items-start">
                <div class="relative col-span-6 space-y-1 md:col-span-5">
                  <span class="flex min-h-6 items-center justify-between gap-2 px-1 text-xs font-medium text-gray-500">
                    <span>Название</span>
                    <ServiceDescriptionModeSwitch
                      v-if="line.template_full_description"
                      :model-value="line.description_mode || 'short'"
                      @update:model-value="setServiceLineDescriptionMode(index, $event)"
                    />
                  </span>
                  <textarea
                    v-model="line.title"
                    class="field-input min-h-[64px] resize-none overflow-hidden text-sm leading-snug focus:min-h-[120px] focus:resize-y focus:overflow-auto sm:text-base"
                    rows="2"
                    placeholder="Название услуги"
                    @focus="onServiceTitleFocus(index)"
                    @input="onServiceTitleInput(index)"
                    @blur="onServiceTitleBlur(index)"
                  />
                  <div
                    v-if="line.title.trim().length >= 2 && activeServiceSuggestionIndex === index && (serviceTariffLookupLoading || getServiceTariffSuggestions(index).length)"
                    class="absolute left-0 right-0 top-full z-20 mt-1 max-h-64 overflow-auto rounded-[12px] border border-gray-200 bg-white p-1 shadow-xl"
                  >
                    <div v-if="serviceTariffLookupLoading" class="px-3 py-2 text-xs text-gray-500">Ищем тарифы...</div>
                    <button
                      v-for="item in getServiceTariffSuggestions(index)"
                      :key="`service-tariff-suggest-${index}-${item.tariff_id}`"
                      type="button"
                      class="mb-1 block w-full rounded-[12px] px-3 py-2 text-left text-xs text-gray-700 hover:bg-slate-100 last:mb-0"
                      @mousedown.prevent
                      @click="selectServiceTariffForLine(index, item)"
                    >
                      <p class="line-clamp-2 font-medium text-gray-900">{{ item.short_name || item.title }}</p>
                      <p
                        v-if="item.full_description && item.full_description !== item.short_name"
                        class="mt-0.5 line-clamp-2 text-[11px] leading-snug text-gray-500"
                      >
                        {{ item.full_description }}
                      </p>
                      <p class="mt-1 flex flex-wrap items-center gap-1 text-[11px] text-gray-500">
                        <span>{{ formatMoney(item.price) }}</span>
                        <span v-if="item.service_kind">· {{ formatServiceKind(item.service_kind) }}</span>
                        <span v-if="item.category">· {{ item.category }}</span>
                        <span v-if="item.included_route_meters">· трасса до {{ item.included_route_meters }} м</span>
                      </p>
                    </button>
                  </div>
                </div>
                <label class="col-span-4 space-y-1 md:col-span-2">
                  <span class="flex h-auto items-center px-1 text-xs font-medium text-gray-500 md:h-6">Цена</span>
                  <input v-model.number="line.price" type="number" min="0" class="field-input" placeholder="0" />
                </label>
                <label class="col-span-2 space-y-1 md:col-span-1">
                  <span class="flex h-auto items-center whitespace-nowrap px-1 text-xs font-medium text-gray-500 md:h-6 md:text-[11px]">Кол-во</span>
                  <input v-model.number="line.quantity" type="number" min="1" class="field-input" placeholder="1" />
                </label>
                <label class="col-span-3 space-y-1 md:col-span-2">
                  <span class="flex h-auto items-center px-1 text-xs font-medium text-gray-500 md:h-6">Себест.</span>
                  <input v-model.number="line.cost" type="number" min="0" class="field-input" placeholder="0" />
                </label>
                <div class="col-span-3 space-y-1 md:col-span-2">
                  <span class="flex h-auto items-center px-1 text-xs font-medium text-gray-500 md:h-6">Итого</span>
                  <div class="rounded-lg bg-gray-50 px-3 py-2">
                    <p class="whitespace-nowrap text-base font-semibold leading-tight text-gray-900">{{ formatMoney(lineTotal(line)) }}</p>
                  </div>
                </div>
                <div class="col-span-6 flex justify-end md:col-span-12">
                  <button type="button" class="btn-mini-outline h-8 px-3 text-xs" @click="editingServiceLineIndex = null">Готово</button>
                </div>
              </div>
            </div>
          </div>
          <div class="mt-3 grid grid-cols-2 gap-2">
            <button type="button" class="btn-mini justify-center" @click="addServiceLine">+ услуга</button>
            <button
              type="button"
              class="btn-mini-outline justify-center"
              :class="showEstimateImport ? 'border-teal-200 bg-teal-50 text-teal-700' : ''"
              @click="toggleEstimateImport"
            >
              Из сметы
            </button>
          </div>
          <div v-if="showEstimateImport" class="mt-3 grid gap-2 rounded-xl border border-gray-200 bg-gray-50 p-3">
            <div class="grid gap-2 md:grid-cols-3">
              <label class="space-y-1 md:col-span-3">
                <span class="px-1 text-xs font-medium text-gray-500">Смета</span>
                <select
                  v-model="selectedEstimateId"
                  class="field-input min-w-0"
                  :disabled="estimateOptionsLoading"
                >
                  <option :value="null">Выберите смету</option>
                  <option v-for="estimate in filteredEstimateOptions" :key="estimate.id" :value="estimate.id">
                    #{{ estimate.id }} · {{ estimate.title }} · {{ formatMoney(estimate.total) }} {{ estimate.currency }}
                  </option>
                </select>
              </label>
              <label class="space-y-1">
                <span class="px-1 text-xs font-medium text-gray-500">Поиск</span>
                <input
                  v-model="estimateSearchQuery"
                  class="field-input"
                  placeholder="ID или название"
                />
              </label>
              <label class="space-y-1">
                <span class="px-1 text-xs font-medium text-gray-500">Структура</span>
                <select v-model="estimateImportMode" class="field-input">
                  <option value="detailed">По строкам</option>
                  <option value="collapsed">Одной строкой</option>
                </select>
              </label>
              <div class="space-y-1">
                <span class="block px-1 text-xs font-medium text-gray-500">Текст позиции</span>
                <ServiceDescriptionModeSwitch
                  :model-value="serviceDescriptionMode"
                  @update:model-value="setDefaultServiceDescriptionMode"
                />
              </div>
            </div>
            <div class="flex flex-col gap-2 sm:flex-row">
              <button
                type="button"
                class="btn-mini justify-center whitespace-nowrap"
                :disabled="importingEstimate || !selectedEstimateId"
                @click="applyEstimateToServices"
              >
                {{ importingEstimate ? 'Добавляю...' : 'Добавить из сметы' }}
              </button>
              <button
                type="button"
                class="btn-mini-outline justify-center whitespace-nowrap"
                :disabled="estimateOptionsLoading"
                @click="loadEstimateOptions"
                title="Обновить список смет"
              >
                Обновить
              </button>
            </div>
            <p class="text-xs text-gray-500">
              Показываем 10 последних смет. Структура определяет количество строк, а формат текста — краткую или подробную формулировку.
            </p>
          </div>
        </section>
        </fieldset>
      </div>
      </OrderDrawerSection>

      <!-- Экшн-зона (Proposal & Docs) -->
      <OrderDrawerSection
        v-if="status !== 'execution'"
        id="order-workspace-documents"
        v-model:expanded="expandedDrawerSections.documents"
        title="Документы"
        :summary="documentSectionSummary"
        tone="amber"
        :has-error="documentSectionHasError"
      >
        <div v-if="status === 'negotiation'" class="mb-6">
          <div class="flex flex-wrap gap-2">
            <!-- B2C Action -->
            <a
              v-if="customer?.type === 'individual'"
              :href="`https://wa.me/${(customer?.phone || '').replace(/\D/g, '')}?text=${encodeURIComponent(`Здравствуйте, ${customer?.name}! Расчет по вашему заказу: Итого к оплате ${formatMoney(totalPreview)}. Подтверждаем?`)}`"
              target="_blank"
              class="flex items-center gap-1 rounded-xl bg-[#25D366] px-4 py-2 text-sm font-medium text-white shadow hover:bg-[#20BE5A]"
            >
              <span class="material-icons-round text-[18px]">chat</span> Отправить в WhatsApp
            </a>
            <a
              v-if="customer?.type === 'individual'"
              :href="`viber://chat?number=%2B${(customer?.phone || '').replace(/\D/g, '')}`"
              target="_blank"
              class="flex items-center gap-1 rounded-xl bg-[#7360f2] px-4 py-2 text-sm font-medium text-white shadow hover:bg-[#5e4cd1]"
            >
              <span class="material-icons-round text-[18px]">chat</span> Viber
            </a>
          </div>
        </div>

        <OrderDocumentsPanel
          v-if="order"
          ref="documentsPanelRef"
          :order="order"
          :active-proposal-id="activeProposalId"
          :product-lines="productLines"
          :before-generate="beforeDocumentGenerate"
          @refresh="refreshOrderFromDocumentsPanel"
          @toast="handleDocumentPanelToast"
        />
      </OrderDrawerSection>


      <OrderDrawerSection
        v-if="status === 'execution'"
        id="order-workspace-planning"
        v-model:expanded="expandedDrawerSections.execution"
        :title="workflowType === 'sales_installation' ? 'Монтаж' : 'Работы'"
        :summary="executionStatusLabel"
        tone="default"
      >
        <label v-if="workflowType === 'sales_installation'" class="field-label">
          Общий этап заказа
          <select v-model="executionStatus" class="field-input mt-1">
            <option v-for="option in EXECUTION_STATUS_OPTIONS" :key="option.value" :value="option.value">{{ option.label }}</option>
          </select>
        </label>
        <div v-else class="grid grid-cols-2 gap-2 sm:grid-cols-3">
          <button
            v-for="option in EXECUTION_STATUS_OPTIONS"
            :key="option.value"
            type="button"
            class="inline-flex min-h-10 items-center justify-center gap-1.5 rounded-xl border px-2 py-2 text-xs font-semibold transition"
            :class="executionStatus === option.value
              ? 'border-teal-500 bg-white text-teal-800 shadow-sm'
              : 'border-teal-100 bg-white/70 text-slate-600 hover:border-teal-300 hover:text-teal-800'"
            @click="setExecutionStatus(option.value)"
          >
            <span class="material-icons-round text-[15px]">{{ option.icon }}</span>
            <span class="truncate">{{ option.label }}</span>
          </button>
        </div>
        <div class="mt-3 grid gap-2 sm:grid-cols-2">
          <label class="flex items-start gap-2 rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs text-slate-700 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200">
            <input v-model="executionWithoutPayment" type="checkbox" class="mt-0.5 h-4 w-4 rounded border-gray-300 text-teal-600 focus:ring-teal-600" />
            <span><strong class="block">Разрешить переходы при наличии долга</strong><span class="mt-0.5 block text-slate-500 dark:text-slate-400">Менеджер сможет продолжать работу без полной оплаты.</span></span>
          </label>
          <label class="flex items-start gap-2 rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs text-slate-700 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200">
            <input v-model="autoCloseOnPayment" type="checkbox" class="mt-0.5 h-4 w-4 rounded border-gray-300 text-teal-600 focus:ring-teal-600" />
            <span><strong class="block">Автоматически завершить после полной оплаты</strong><span class="mt-0.5 block text-slate-500 dark:text-slate-400">Сработает, когда долг станет нулевым.</span></span>
          </label>
        </div>
        <label v-if="executionWithoutPayment" class="field-label mt-3">
          Причина работы при наличии долга
          <textarea v-model="executionWithoutPaymentReason" class="field-input min-h-[60px]" placeholder="Например: постоянный клиент, оплата по факту..." />
        </label>
      </OrderDrawerSection>

      <DealExecutionTab
        v-if="status === 'execution' && order && executionWorkspaceSection"
        id="order-workspace-execution-details"
        :order="order"
        :section="executionWorkspaceSection"
        @refresh="emit('reload', order.id) /* triggering parent reload without closing drawer */"
        @close="closeDrawer"
        class="mt-4"
      />

      <!-- Оплаты и Валюта (Объединенный блок) -->
      <OrderDrawerSection
        v-if="order && status !== 'execution'"
        id="order-workspace-payments"
        v-model:expanded="expandedDrawerSections.payments"
        title="Оплаты"
        :summary="paymentsSectionSummary"
        icon="account_balance_wallet"
        tone="default"
      >
      <section class="rounded-2xl border border-slate-200 bg-slate-50 p-3 shadow-sm sm:p-5">
        <div v-if="isB2cCustomer" class="mb-4 flex justify-end">
            <label v-if="isB2cCustomer" class="flex items-center gap-2 cursor-pointer text-sm font-medium text-slate-600 bg-white border border-slate-200 px-3 py-1.5 rounded-lg shadow-sm hover:bg-slate-50 transition-colors">
                <input type="checkbox" v-model="enableCurrency" class="rounded text-blue-600 focus:ring-blue-500 border-slate-300 w-4 h-4" />
                Считать в валюте
            </label>
        </div>

        <!-- Поля валюты (показываются если включен чекбокс) -->
        <div v-if="enableCurrency" class="mb-5 rounded-xl border border-blue-100 bg-blue-50/30 p-3 sm:p-4">
            <div class="mb-4 flex flex-col gap-3 sm:flex-row sm:items-end sm:gap-4">
                <label class="field-label !mb-0 text-xs sm:w-1/3">Валюта
                    <select v-model="targetCurrency" class="field-input mt-1">
                        <option value="USD">USD ($)</option>
                        <option value="EUR" :disabled="!hasManualEurRate">EUR (€)</option>
                    </select>
                </label>
                <label class="field-label !mb-0 text-xs flex-1">Зафиксировать сумму
                    <div class="relative">
                        <input v-model.number="targetCurrencyAmount" type="number" step="0.01" min="0" class="field-input mt-1 w-full" placeholder="Итоговая сумма в валюте" />
                        <span v-if="currentFxRate?.usd_byn && targetCurrency === 'USD'" class="absolute right-3 top-[50%] -translate-y-[50%] text-[10px] text-blue-400 font-medium bg-blue-50/80 px-1 rounded" title="Текущий курс NBRB">Курс: {{ currentFxRate.usd_byn }}</span>
                        <span v-else-if="currentFxRate?.eur_byn && targetCurrency === 'EUR'" class="absolute right-3 top-[50%] -translate-y-[50%] text-[10px] text-blue-400 font-medium bg-blue-50/80 px-1 rounded" title="Текущий курс NBRB">Курс: {{ currentFxRate.eur_byn }}</span>
                    </div>
                </label>
            </div>
            <p v-if="targetCurrency === 'EUR' && !hasManualEurRate" class="text-xs text-amber-700">
                EUR недоступен при ручном источнике курса. Переключите источник курса на NBRB.
            </p>

            <div class="flex flex-col gap-3 border-t border-blue-100 pt-3 sm:flex-row sm:items-center sm:justify-between">
                 <div class="sm:w-1/2">
                    <p class="text-xs text-slate-500 uppercase tracking-wide mb-1">Внесено оплат ({{ targetCurrency || 'USD' }})</p>
                    <p class="text-xl font-bold text-gray-800">{{ calculatedTargetCurrencyPayments.toFixed(2) }}</p>
                 </div>
                 <div class="sm:text-right">
                    <p class="text-xs text-slate-500 uppercase tracking-wide mb-1">Остаток долга ({{ targetCurrency || 'USD' }})</p>
                    <p class="text-2xl font-bold" :class="targetCurrencyBalanceDue > 0 ? 'text-red-500' : 'text-blue-600'">
                        {{ targetCurrencyBalanceDue.toFixed(2) }}
                    </p>
                 </div>
            </div>
        </div>

        <div class="mt-3 flex flex-col gap-2 rounded-xl border border-slate-200 bg-white p-3 shadow-sm sm:flex-row sm:items-end">
            <label class="flex-1 field-label !mb-0 text-xs">Внести платеж ({{ enableCurrency ? (targetCurrency || 'USD') : 'BYN' }})
                <input v-model.number="newPaymentAmount" type="number" step="0.01" min="0" class="field-input mt-1 shadow-sm" placeholder="0.00" />
            </label>
            <label class="field-label !mb-0 text-xs sm:w-1/3">Тип
                <select v-model="newPaymentType" class="field-input mt-1 shadow-sm">
                    <option value="prepayment">Аванс</option>
                    <option value="postpayment">Доплата</option>
                </select>
            </label>
            <button class="btn-mini h-[38px] w-full sm:w-[100px]" :disabled="!newPaymentAmount || isAddingPayment" @click="addPayment">Внести</button>
        </div>

        <div v-if="hasDebtForBankReceipts" class="mt-4 rounded-xl border border-amber-200 bg-amber-50/60 p-3">
          <div class="mb-3 flex items-center justify-between gap-3">
            <div>
              <p class="text-sm font-semibold text-amber-900">Банковские поступления по УНП</p>
              <p class="text-xs text-amber-700">Можно прикрепить поступление, которое требует ручной проверки.</p>
            </div>
            <span v-if="bankReceiptsLoading" class="material-icons-round animate-spin text-amber-600">refresh</span>
          </div>
          <div v-if="candidateBankReceipts.length" class="space-y-2">
            <div
              v-for="receipt in candidateBankReceipts"
              :key="receipt.id"
              class="rounded-lg border border-amber-100 bg-white p-3 text-xs shadow-sm"
            >
              <div class="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                <div class="min-w-0">
                  <div class="flex flex-wrap items-center gap-2">
                    <span class="font-bold text-slate-900">{{ formatMoney(receipt.amount) }}</span>
                    <span class="text-slate-500">{{ formatReceiptDate(receipt.received_at) }}</span>
                    <span v-if="receipt.payment_document_number" class="rounded bg-slate-100 px-1.5 py-0.5 font-medium text-slate-500">№ {{ receipt.payment_document_number }}</span>
                  </div>
                  <p v-if="receiptCandidateHint(receipt)" class="mt-1 text-amber-700">{{ receiptCandidateHint(receipt) }}</p>
                  <p class="mt-1 line-clamp-2 text-slate-500">{{ receipt.payment_purpose || 'Назначение не указано' }}</p>
                </div>
                <button
                  class="btn-mini h-8 shrink-0"
                  :disabled="attachingReceiptId === receipt.id"
                  @click="attachBankReceipt(receipt)"
                >
                  {{ attachingReceiptId === receipt.id ? '...' : 'Прикрепить' }}
                </button>
              </div>
            </div>
          </div>
          <div v-else-if="!bankReceiptsLoading" class="rounded-lg border border-dashed border-amber-200 bg-white/70 p-3 text-center text-xs text-amber-700">
            Нет неподтвержденных поступлений по УНП {{ order?.customer?.inn }}
          </div>
        </div>

        <div class="mt-4 space-y-2 max-h-56 overflow-y-auto pr-1">
            <div v-for="p in payments" :key="p.id" class="rounded-lg border border-slate-100 bg-white px-3 py-2 text-xs shadow-sm">
                <div class="flex flex-wrap items-center justify-between gap-2">
                    <div class="flex flex-wrap items-center gap-2">
                        <span class="text-slate-500">{{ new Date(p.date).toLocaleDateString() }}</span>
                        <span
                          v-if="p.bank_receipt"
                          class="inline-flex items-center gap-1 rounded-full border border-emerald-200 bg-emerald-50 px-2 py-0.5 font-semibold text-emerald-700"
                        >
                          <span class="material-icons-round text-[13px]">account_balance</span>
                          Банк
                        </span>
                    </div>
                    <span class="font-bold text-slate-800" :class="p.currency !== 'BYN' ? 'text-blue-600' : ''">
                        <template v-if="p.currency !== 'BYN'">{{ p.amount.toFixed(2) }} {{ p.currency }}</template>
                        <template v-else>{{ formatMoney(p.amount) }}</template>
                    </span>
                    <span class="text-slate-400 w-16 text-right">{{ formatPaymentType(p.type) }}</span>
                    <div v-if="deletingPaymentId === p.id" class="flex gap-2 ml-2 items-center">
                        <button class="text-slate-500 hover:text-slate-800 font-medium" @click="cancelDeletePayment()">Отмена</button>
                        <button class="text-red-500 hover:text-red-700 font-bold" @click="deletePayment(p.id)">Да, удалить</button>
                    </div>
                    <button v-else class="flex h-6 w-6 ml-2 items-center justify-center rounded text-red-400 hover:bg-red-50 hover:text-red-600 transition-colors" @click="confirmDeletePayment(p.id)" title="Удалить платеж">
                        <span class="material-icons-round text-[14px]">delete</span>
                    </button>
                </div>
                <div v-if="p.bank_receipt" class="mt-2 rounded-lg border border-emerald-100 bg-emerald-50/40 p-2 text-[11px] text-slate-600">
                    <div class="flex flex-wrap items-center gap-2">
                        <span class="font-semibold text-emerald-800">ПП № {{ p.bank_receipt.payment_document_number || p.bank_receipt.payment_document_raw || p.bank_receipt.id }}</span>
                        <span>{{ formatBankPaymentDate(p.bank_receipt.received_at || p.date) }}</span>
                        <span v-if="p.bank_receipt.payer_unp">УНП {{ p.bank_receipt.payer_unp }}</span>
                    </div>
                    <p v-if="p.bank_receipt.payer_name" class="mt-1 truncate font-medium text-slate-700">{{ p.bank_receipt.payer_name }}</p>
                    <p v-if="p.bank_receipt.payment_purpose" class="mt-1 line-clamp-2 text-slate-500">{{ p.bank_receipt.payment_purpose }}</p>
                    <button class="mt-1 inline-flex items-center gap-1 font-semibold text-emerald-700 hover:text-emerald-900" @click="openBankReceiptJournal(p)">
                        <span class="material-icons-round text-[13px]">receipt_long</span>
                        Открыть в журнале
                    </button>
                </div>
                <p v-else-if="p.comment" class="mt-1 text-[11px] text-slate-500">{{ p.comment }}</p>
            </div>
            <div v-if="!payments.length" class="text-sm text-gray-500 italic py-3 text-center rounded-xl border border-dashed border-gray-200">
                Нет оплат
            </div>
        </div>
      </section>
      </OrderDrawerSection>

      </div>
    </aside>

    <div
      v-if="showCustomerModal"
      class="fixed inset-0 z-[60] flex items-center justify-center bg-black/70 px-4"
      @click.self="closeCustomerModal"
    >
      <div class="w-full max-w-3xl rounded-2xl border border-gray-200 bg-white p-5 text-gray-900 shadow-2xl">
        <div class="mb-4 flex items-center justify-between gap-3">
          <h3 class="text-lg font-semibold font-['Space_Grotesk']">Карточка клиента</h3>
          <button class="btn-mini-outline" @click="closeCustomerModal">Закрыть</button>
        </div>
        <CustomerSummaryCard :customer="customer" mode="expanded" :show-open-button="false" />
        <div class="mt-4 flex justify-end gap-2">
          <button class="btn-mini-outline" @click="showChangeCustomerModal = true">Сменить</button>
          <button class="btn-mini" :disabled="!customer?.id" @click="openCustomerProfile">Редактировать в карточке клиента</button>
        </div>
      </div>
    </div>

    <!-- Modal for changing order customer -->
    <Transition name="fade">
      <div
        v-if="showChangeCustomerModal"
        class="fixed inset-0 z-[60] flex items-center justify-center bg-black/60 backdrop-blur-sm p-4"
        @click.self="showChangeCustomerModal = false"
      >
        <div class="w-full max-w-lg rounded-2xl bg-white shadow-2xl overflow-hidden flex flex-col max-h-[85vh]">
          <div class="px-6 py-4 border-b border-gray-100 flex items-center justify-between shadow-sm bg-slate-50/50">
            <h3 class="text-lg font-bold text-slate-800 flex items-center gap-2">
              <span class="material-icons-round text-slate-500">swap_horiz</span>
              Сменить клиента для заказа
            </h3>
            <button class="bg-slate-100 hover:bg-slate-200 text-slate-500 w-8 h-8 flex items-center justify-center rounded-full transition-colors" @click="showChangeCustomerModal = false">
              <span class="material-icons-round text-[18px]">close</span>
            </button>
          </div>
          
          <div class="p-6 overflow-y-auto">
            <div class="relative mb-4">
              <span class="material-icons-round absolute left-4 top-1/2 -translate-y-1/2 text-slate-400">search</span>
              <input 
                v-model="customerSearchQuery" 
                @input="onCustomerSearchInput"
                type="text" 
                class="w-full bg-slate-50 border-none rounded-xl pl-11 pr-4 py-3 text-sm focus:ring-2 focus:ring-teal-500 transition-shadow" 
                placeholder="Поиск по телефону, УНП, имени..." 
                autofocus
              />
              <span v-if="isCustomerSearchLoading" class="material-icons-round absolute right-4 top-1/2 -translate-y-1/2 text-teal-500 animate-spin">refresh</span>
            </div>

            <div v-if="customerSearchQuery.length >= 3 && customerSearchResults.length === 0 && !isCustomerSearchLoading" class="text-center py-6 text-slate-500 text-sm bg-slate-50 rounded-xl border border-slate-100 border-dashed">
              Клиенты не найдены
            </div>

            <div v-if="customerSearchQuery.length < 3" class="text-center py-6 text-slate-400 text-xs uppercase tracking-wider font-semibold">
              Введите минимум 3 символа
            </div>

            <div class="space-y-2 mt-2">
              <button
                v-for="res in customerSearchResults"
                :key="`csearch-${res.id}`"
                class="w-full text-left p-4 rounded-xl border border-slate-100 bg-white hover:border-teal-200 hover:shadow-md hover:-translate-y-0.5 transition-all outline-none focus:ring-2 focus:ring-teal-500 flex flex-col gap-1 group"
                @click="assignNewCustomer(res)"
              >
                <div class="font-bold text-slate-800 text-sm group-hover:text-teal-700 transition-colors">
                  {{ res.full_legal_name || res.name || `Клиент #${res.id}` }}
                </div>
                <div class="flex flex-wrap gap-x-3 gap-y-1 text-xs text-slate-500">
                  <span v-if="res.phone" class="flex items-center gap-1"><span class="material-icons-round text-[12px]">phone</span> {{ res.phone }}</span>
                  <span v-if="res.inn" class="flex items-center gap-1"><span class="font-medium">УНП:</span> {{ res.inn }}</span>
                </div>
              </button>
            </div>
          </div>
          <div class="px-6 py-4 border-t border-gray-100 bg-slate-50/50 flex justify-end">
            <button class="px-5 py-2 rounded-xl text-slate-600 font-medium hover:bg-slate-200 hover:text-slate-800 transition-colors" @click="showChangeCustomerModal = false">
              Отмена
            </button>
          </div>
        </div>
      </div>
    </Transition>
  </div>
</template>
