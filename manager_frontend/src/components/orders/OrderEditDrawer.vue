<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { useDebounceFn } from '@vueuse/core';
import { api } from '../../api';
import DateTimeField from '../ui/DateTimeField.vue';
import CustomerSummaryCard from '../customers/CustomerSummaryCard.vue';
import DealExecutionTab from './DealExecutionTab.vue';
import OrderDocumentsPanel from './OrderDocumentsPanel.vue';
import OrderDrawerSection from './OrderDrawerSection.vue';
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
} from '../../client';
import { ManagerOrdersService, ManagerSettingsService, ManagerMailService, ManagerRepairComplaintsService } from '../../client';
import { formatMoney } from './order-utils';
import { fromLocalDateTimeInput, toLocalDateTimeInput } from '../../utils/datetime';

import { getApiErrorMessage } from '../../utils/api-errors';

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
  deleted: [orderId: number];
  reload: [orderId: number];
}>();

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
};
type ProductLine = { product_id: number; product_query: string; quantity: number; price: number; cost: number };
type ServiceLine = { service_id?: number | null; title: string; quantity: number; price: number; cost: number };
type OrderWorkflowType = 'sales_installation' | 'service_work' | 'maintenance' | 'repair';
type RepairMeta = {
  customer_complaint: string;
  complaint_official: string;
  likely_diagnosis: string;
  equipment_name: string;
  equipment_brand: string;
  equipment_model: string;
  equipment_power: string;
  equipment_serial_number: string;
  equipment_inventory_number: string;
  equipment_commissioning_date: string;
  technical_condition: string;
  startup_check_result: string;
  compressor_check_result: string;
  measurement_result: string;
  further_use_assessment: string;
  operation_restrictions: string;
  technical_conclusion: string;
  repair_feasibility: string;
  recommended_decision: string;
};
type RepairAiDefectType = {
  value: string;
  label: string;
  hint: string;
};

const WORKFLOW_OPTIONS: Array<{ value: OrderWorkflowType; label: string; hint: string; icon: string }> = [
  { value: 'sales_installation', label: 'Продажа + монтаж', hint: 'товары, КП, монтаж', icon: 'shopping_cart' },
  { value: 'service_work', label: 'Работы', hint: 'монтаж, демонтаж, трассы', icon: 'construction' },
  { value: 'maintenance', label: 'Обслуживание', hint: 'ТО и сервисные договоры', icon: 'ac_unit' },
  { value: 'repair', label: 'Ремонт', hint: 'диагностика и дефектный акт', icon: 'build_circle' },
];

const emptyRepairMeta = (): RepairMeta => ({
  customer_complaint: '',
  complaint_official: '',
  likely_diagnosis: '',
  equipment_name: '',
  equipment_brand: '',
  equipment_model: '',
  equipment_power: '',
  equipment_serial_number: '',
  equipment_inventory_number: '',
  equipment_commissioning_date: '',
  technical_condition: '',
  startup_check_result: '',
  compressor_check_result: '',
  measurement_result: '',
  further_use_assessment: '',
  operation_restrictions: '',
  technical_conclusion: '',
  repair_feasibility: '',
  recommended_decision: '',
});

const REPAIR_AI_DEFECT_TYPES: RepairAiDefectType[] = [
  {
    value: 'multiple_heat_exchanger_defects',
    label: 'Множественные дефекты теплообменника',
    hint: 'коррозия, загрязнение, механические повреждения, нарушение теплообмена',
  },
  {
    value: 'compressor_winding_breakdown',
    label: 'Пробой обмотки компрессора',
    hint: 'электрическая неисправность компрессора, срабатывание защиты',
  },
  {
    value: 'refrigerant_leak',
    label: 'Утечка хладагента',
    hint: 'падение производительности, обмерзание, требуется поиск и устранение утечки',
  },
  {
    value: 'control_board_failure',
    label: 'Неисправность платы управления',
    hint: 'ошибки управления, нестабильная работа, отсутствие запуска',
  },
  {
    value: 'fan_motor_failure',
    label: 'Неисправность двигателя вентилятора',
    hint: 'шум, отсутствие вращения, перегрев, ошибка вентилятора',
  },
  {
    value: 'drainage_failure',
    label: 'Нарушение отвода конденсата',
    hint: 'протечка воды, засор или неправильный уклон дренажа',
  },
];

const serviceKindLabels: Record<string, string> = {
  installation: 'монтаж',
  dismantling: 'демонтаж',
  maintenance: 'обслуживание',
  repair: 'ремонт',
};

const formatServiceKind = (kind?: string | null) => serviceKindLabels[String(kind || '')] || kind || '';
const normalizeWorkflowType = (value: unknown): OrderWorkflowType => {
  const raw = String(value || '').trim();
  if (raw === 'service_work' || raw === 'maintenance' || raw === 'repair') return raw;
  return 'sales_installation';
};
const serviceKindForWorkflow = (value: OrderWorkflowType) => {
  if (value === 'repair') return 'repair';
  if (value === 'maintenance') return 'maintenance';
  if (value === 'service_work') return 'installation';
  return null;
};

type OrderDrawerDraft = {
  productLines: ProductLine[];
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
const addressSuggestions = ref<any[]>([]);
const addressSuggestActive = ref(false);
const addressLookupLoading = ref(false);
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
const proposalStatus = ref<'draft' | 'sent' | 'approved' | 'rejected'>('draft');
const activeProposalId = ref<number | null>(null);
const proposalActionLoading = ref(false);

const installersList = ref<ManagerInstallerResponse[]>([]);

const productLines = ref<ProductLine[]>([]);
const serviceLines = ref<ServiceLine[]>([]);
const activeServiceSuggestionIndex = ref<number | null>(null);
const serviceTariffOptions = ref<ManagerQuickTariffResponse[]>([]);
const serviceTariffLookupLoading = ref(false);
let serviceTariffSearchRequestId = 0;
const estimateOptions = ref<ManagerServiceEstimateResponse[]>([]);
const estimateOptionsLoading = ref(false);
const estimateImportMode = ref<'detailed' | 'collapsed'>('detailed');
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
const repairAiGenerating = ref(false);
const payments = ref<PaymentResponse[]>([]);
const bankReceipts = ref<BankReceiptResponse[]>([]);
const bankReceiptsLoading = ref(false);
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
});
const expandedDrawerSections = ref(createDefaultDrawerSections());

const localFormError = ref('');
const showCustomerModal = ref(false);
const isEditingOrderTitle = ref(false);
const showManagerLabelInput = ref(false);
const showBranchFields = ref(false);

const showChangeCustomerModal = ref(false);
const customerSearchQuery = ref('');
const customerSearchResults = ref<any[]>([]);
const isCustomerSearchLoading = ref(false);

const debouncedSearchCustomer = useDebounceFn(async (query: string) => {
  if (!query || query.length < 3) {
    customerSearchResults.value = [];
    return;
  }
  isCustomerSearchLoading.value = true;
  try {
    const res = await api.getManagerCustomers(1, 10, query);
    customerSearchResults.value = res.items || [];
  } catch (error) {
    console.error('Customer search error', error);
  } finally {
    isCustomerSearchLoading.value = false;
  }
}, 400);

const onCustomerSearchInput = () => {
  debouncedSearchCustomer(customerSearchQuery.value);
};

const assignNewCustomer = async (newCustomer: any) => {
  if (!props.order?.id) return;
  try {
    const res = await api.patchManagerOrder(props.order.id, { customer_id: newCustomer.id });
    Object.assign(props.order, res);
    await initForm(props.order);
    showChangeCustomerModal.value = false;
    setToast('Клиент успешно изменен', 'success');
    emit('reload', props.order.id); // Reload parent list if necessary
  } catch (error) {
    setToast(`Ошибка смены клиента: ${getApiErrorMessage(error)}`, 'error');
  }
};

const resetCustomerBranches = () => {
  customerBranches.value = [];
  customerBranchId.value = null;
  customerBranchesLoading.value = false;
  creatingCustomerBranch.value = false;
  newBranchName.value = '';
  newBranchAddress.value = '';
};

const loadCustomerBranches = async (customerId: number, preferredBranchId?: number | null) => {
  customerBranchesLoading.value = true;
  try {
    const response = await api.getManagerCustomerBranches(customerId);
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
    console.error('Failed to load customer branches', error);
    resetCustomerBranches();
  } finally {
    customerBranchesLoading.value = false;
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

const customer = computed(() => props.order?.customer ?? null);
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
const clientDisplayName = computed(() => (
  customer.value?.full_legal_name
  || customer.value?.name
  || 'Клиент не выбран'
));
const selectedCustomerBranch = computed(() => (
  customerBranches.value.find((branch) => branch.id === customerBranchId.value)
  || props.order?.customer_branch
  || null
));
const compactObjectAddress = computed(() => (
  customerDeliveryAddress.value.trim()
  || selectedCustomerBranch.value?.delivery_address
  || ''
));
const clientSummaryContacts = computed(() => {
  const rows: Array<{ key: string; icon?: string; label: string; value: string; href?: string; copyLabel: string }> = [];
  const phone = customer.value?.phone?.trim();
  const email = customer.value?.email?.trim();
  const inn = customer.value?.inn?.trim();
  const address = compactObjectAddress.value.trim();

  if (phone) rows.push({ key: 'phone', icon: 'phone', label: 'Телефон', value: phone, href: `tel:${phone.replace(/\s+/g, '')}`, copyLabel: 'Телефон' });
  if (email) rows.push({ key: 'email', icon: 'email', label: 'Email', value: email, href: `mailto:${email}`, copyLabel: 'Email' });
  if (inn) rows.push({ key: 'inn', label: 'УНП', value: inn, copyLabel: 'УНП' });
  if (address) rows.push({ key: 'address', icon: 'location_on', label: 'Адрес', value: address, href: `https://yandex.by/maps/?text=${encodeURIComponent(address)}`, copyLabel: 'Адрес' });

  return rows;
});
const customerDetailsSummary = computed(() => {
  const parts = [];
  if (compactObjectAddress.value) parts.push(compactObjectAddress.value);
  if (comment.value.trim()) parts.push('есть комментарий');
  return parts.join(' · ') || 'адрес и комментарий';
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
const activeProposalLineLabel = computed(() => {
  const proposal = activeProposal.value;
  if (!proposal) return 'основной расчет';
  const count = (proposal.product_lines?.length || 0) + (proposal.service_lines?.length || 0);
  return `${proposal.name} · ${count} поз. · ${formatMoney(proposal.total_amount || 0)}`;
});
const paymentsSectionSummary = computed(() => (
  `оплачено ${formatMoney(totalPaymentsPreview.value)} · остаток ${formatMoney(balanceDuePreview.value)} · итого ${formatMoney(totalPreview.value)} · маржа ${formatMoney(marginPreview.value)}`
));
const candidateBankReceipts = computed(() => bankReceipts.value.filter((receipt) => receipt.status === 'requires_review'));
const hasDebtForBankReceipts = computed(() => balanceDuePreview.value > 0 && Boolean(props.order?.customer?.inn));
const draftKey = computed(() => (
  props.order ? `manager_order_drawer_draft_${props.order.id}_${activeProposalId.value || 'default'}` : ''
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
        await api.patchManagerOrder(props.order.id, { is_on_hold: hold, on_hold_reason: hold ? 'Переговоры / Ручная пауза' : '' });
        props.order.is_on_hold = hold;
        props.order.on_hold_reason = hold ? 'Переговоры / Ручная пауза' : '';
        emit('save', { orderId: props.order.id, data: { status: props.order.status } });
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
  const parts = [];
  const visitLabel = workflowType.value === 'repair' ? 'диагностика' : 'замер';
  parts.push(measurementRequired.value ? `${visitLabel} нужна` : `без ${visitLabel}`);
  if (assessmentDate.value) parts.push(`${visitLabel} ${formatDateTime(assessmentDate.value)}`);
  if (installationDate.value) parts.push(`${workDateLabel.value.toLowerCase()} ${formatDateTime(installationDate.value)}`);
  if (customerDeliveryAddress.value) parts.push(customerDeliveryAddress.value);
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
const selectedWorkflowOption = computed(() => WORKFLOW_OPTIONS.find((item) => item.value === workflowType.value) || WORKFLOW_OPTIONS[0]!);
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
const repairSectionSummary = computed(() => {
  const parts = [];
  if (repairMeta.value.equipment_name.trim()) parts.push(repairMeta.value.equipment_name.trim());
  const serial = repairMeta.value.equipment_serial_number.trim() || repairMeta.value.equipment_inventory_number.trim();
  if (serial) parts.push(serial);
  if (repairMeta.value.customer_complaint.trim()) parts.push('есть жалоба');
  if (repairMeta.value.technical_conclusion.trim()) parts.push('есть вывод');
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
const documentSectionSummary = computed(() => {
  const contractText = hasContract.value ? 'договор есть' : (hasOrderInvoice.value ? 'есть счет' : 'без договора');
  return `${orderDocuments.value.length} док. · ${contractText}`;
});
const documentSectionHasError = computed(() => isCompanyOrder.value && !props.order?.customer_contract_id && !hasClosingBaseDocument.value);

const beforeDocumentGenerate = async (type: string) => {
  if (!props.order?.id) return false;
  if (type === 'offer') {
    await saveCurrentProposalLines();
  }
  if (type === 'defect_act') {
    await ManagerOrdersService.patchManagerOrder(props.order.id, {
      repair_meta: repairMeta.value as any,
      measurement_result: measurementResult.value,
    });
    emit('reload', props.order.id);
  }
  return true;
};

const handleDocumentPanelToast = (payload: { message: string; type?: 'success' | 'error' }) => {
  setToast(payload.message, payload.type || 'success');
};

const refreshOrderFromDocumentsPanel = () => {
  if (props.order?.id) emit('reload', props.order.id);
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

const persistDraft = () => {
  if (!draftKey.value) return;
  try {
    const payload: OrderDrawerDraft = {
      productLines: productLines.value.map((line) => ({ ...line })),
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
    if (Array.isArray(payload.productLines) && payload.productLines.length) {
      productLines.value = payload.productLines.map((line) => ({
        product_id: Number(line.product_id || 0),
        product_query: String(line.product_query || ''),
        quantity: Number(line.quantity || 1),
        price: Number(line.price || 0),
        cost: Number(line.cost || 0),
      }));
    }
  } catch (error) {
    console.warn('Failed to restore order drawer draft', error);
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
  product_id: line.product_id || 0,
  product_query: line.product_title || '',
  quantity: line.quantity,
  price: line.price,
  cost: line.cost,
});

const mapServiceLineFromResponse = (line: OrderServiceLineResponse): ServiceLine => ({
  service_id: line.service_id,
  title: line.service_title,
  quantity: line.quantity,
  price: line.price,
  cost: line.cost,
});

const loadProposalLines = (proposal: OrderProposalResponse | null | undefined, fallbackOrder?: ManagerOrderDetailResponse | null) => {
  if (proposal) {
    activeProposalId.value = proposal.id;
    proposalStatus.value = (proposal.status as any) || proposalStatus.value || 'draft';
    productLines.value = (proposal.product_lines || []).map(mapProductLineFromResponse);
    serviceLines.value = (proposal.service_lines || []).map(mapServiceLineFromResponse);
    return;
  }
  productLines.value = (fallbackOrder?.product_lines ?? []).map(mapProductLineFromResponse);
  serviceLines.value = (fallbackOrder?.service_lines ?? []).map(mapServiceLineFromResponse);
};

const initForm = async (order: ManagerOrderDetailResponse | null) => {
  if (!order) return;
  localServerErrors.value = {};
  localFormError.value = '';
  expandedDrawerSections.value = createDefaultDrawerSections();
  status.value = order.status;
  orderTitle.value = order.title ?? '';
  workflowType.value = normalizeWorkflowType((order as any).workflow_type);
  repairMeta.value = { ...emptyRepairMeta(), ...(((order as any).repair_meta || {}) as Partial<RepairMeta>) };
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
  proposalStatus.value = (order.proposal_status as any) || 'draft';
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
      installersList.value = res.items.filter(i => i.is_active || i.id === installerId.value);
    }).catch(e => console.error("Failed to load installers", e));
  }

  const selectedProposal = (order.proposals || []).find((proposal) => proposal.is_selected && !proposal.is_archived)
    || (order.proposals || []).find((proposal) => !proposal.is_archived)
    || null;
  loadProposalLines(selectedProposal, order);
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

  productLookupById.value = {};

  syncProductLookupFromLines();
  productOptions.value = [];
  activeSuggestionIndex.value = null;
  productLookupLoading.value = false;
  serviceTariffOptions.value = [];
  activeServiceSuggestionIndex.value = null;
  serviceTariffLookupLoading.value = false;
  restoreDraft();
  syncProductLookupFromLines();
};

watch(
  () => props.modelValue,
  async (value) => {
    if (value) {
      await initForm(props.order);
    }
  },
);

const fetchAddressSuggestions = async (query: string) => {
  if (!query || query.length < 3) {
    addressSuggestions.value = [];
    return;
  }
  addressLookupLoading.value = true;
  try {
    const res = await ManagerSettingsService.suggestAddress(query);
    addressSuggestions.value = res.results || [];
  } catch (err) {
    console.warn('Failed to fetch address suggestions', err);
  } finally {
    addressLookupLoading.value = false;
  }
};

const debouncedFetchAddressSuggestions = useDebounceFn(fetchAddressSuggestions, 400);

const onAddressInput = () => {
  addressSuggestActive.value = true;
  debouncedFetchAddressSuggestions(customerDeliveryAddress.value);
};

const selectAddressSuggestion = (item: any) => {
  customerDeliveryAddress.value = item.title?.text || '';
  if (item.subtitle?.text) customerDeliveryAddress.value += `, ${item.subtitle.text}`;
  addressSuggestActive.value = false;
  addressSuggestions.value = [];
};

const hideAddressSuggestions = () => {
  setTimeout(() => {
    addressSuggestActive.value = false;
  }, 200);
};

watch(
  () => props.order,
  async (value) => {
    if (props.modelValue) await initForm(value);
  },
);

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
  productLines.value.push({ product_id: 0, product_query: '', quantity: 1, price: 0, cost: 0 });
};

const addServiceLine = () => {
  serviceLines.value.push({ title: '', quantity: 1, price: 0, cost: 0, service_id: null });
};

const applyOrderResponse = async (
  order: ManagerOrderDetailResponse,
  preferredProposalId?: number | null,
  emitReload = true,
) => {
  if (props.order) {
    Object.assign(props.order, order);
  }
  const nextProposal = preferredProposalId
    ? (order.proposals || []).find((proposal) => proposal.id === preferredProposalId && !proposal.is_archived)
    : ((order.proposals || []).find((proposal) => proposal.is_selected && !proposal.is_archived)
      || (order.proposals || []).find((proposal) => !proposal.is_archived));
  loadProposalLines(nextProposal || null, order);
  syncProductLookupFromLines();
  if (emitReload) emit('reload', order.id);
};

const buildProposalLinesPayload = () => ({
  products: productLines.value.map((line) => ({
    product_id: line.product_id || 0,
    quantity: Math.trunc(Number(line.quantity) || 0),
    price: Math.round(Number(line.price) || 0),
    cost: (!line.cost && line.cost !== 0) ? null : toIntegerMoney(line.cost),
    link_id: null,
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
  if (!props.order?.id || !activeProposalId.value) return props.order || null;
  const validationError = validateProposalLines();
  if (validationError) {
    localFormError.value = validationError;
    throw new Error(validationError);
  }
  const currentProposalId = activeProposalId.value;
  const order = await ManagerOrdersService.patchManagerOrder(props.order.id, buildProposalLinesPayload());
  clearDraft();
  await applyOrderResponse(order, currentProposalId, false);
  return order;
};

const setActiveProposal = async (proposal: OrderProposalResponse) => {
  if (!proposal || activeProposalId.value === proposal.id) return;
  try {
    await saveCurrentProposalLines();
  } catch (error) {
    setToast(`Сначала сохраните текущий вариант: ${getApiErrorMessage(error)}`, 'error');
    return;
  }
  loadProposalLines(proposal, props.order);
  productLookupById.value = {};
  syncProductLookupFromLines();
};

const onProposalClick = (proposal: OrderProposalResponse, event: MouseEvent) => {
  if (event.detail > 1) {
    void selectProposalForOrder(proposal);
    return;
  }
  void setActiveProposal(proposal);
};

const createProposal = async () => {
  if (!props.order?.id || proposalActionLoading.value) return;
  const name = window.prompt('Название нового предложения', `Вариант ${orderProposals.value.length + 1}`);
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
  const name = window.prompt('Название копии', `${activeProposal.value.name} копия`);
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
  const name = window.prompt('Новое название предложения', activeProposal.value.name);
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
  if (!window.confirm(`Убрать предложение «${activeProposal.value.name}» в архив?`)) return;
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

const toggleEstimateImport = async () => {
  showEstimateImport.value = !showEstimateImport.value;
  if (showEstimateImport.value && !estimateOptions.value.length && !estimateOptionsLoading.value) {
    await loadEstimateOptions();
  }
};

const debouncedLoadServiceTariffOptions = useDebounceFn(async (index: number, q: string, requestId: number) => {
  try {
    serviceTariffLookupLoading.value = true;
    const response = await api.listManagerQuickTariffs(q, serviceKindForWorkflow(workflowType.value) as any, 10);
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
  row.service_id = null;
  row.title = option.title;
  row.quantity = Math.max(1, Number(row.quantity || 1));
  row.price = Math.round(Number(option.price || 0));
  row.cost = 0;
  activeServiceSuggestionIndex.value = null;
  serviceTariffOptions.value = [];
};

const hasDiagnosticServiceLine = () => serviceLines.value.some((line) => /диагност/i.test(line.title || ''));

const addDefaultRepairDiagnostic = async () => {
  if (hasDiagnosticServiceLine()) return;
  try {
    const response = await api.listManagerQuickTariffs('диагностика', 'repair' as any, 5);
    const option = (response.items || [])[0];
    serviceLines.value = [
      {
        service_id: null,
        title: option?.title || 'Диагностика кондиционера на объекте',
        quantity: 1,
        price: Math.round(Number(option?.price || 0)),
        cost: 0,
      },
      ...serviceLines.value,
    ];
    setToast('Добавили базовую диагностику для ремонта');
  } catch (error) {
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
  workflowType.value = next;
  serviceTariffOptions.value = [];
  activeServiceSuggestionIndex.value = null;
  if (next === 'repair') {
    void loadRepairComplaintPresets();
    await addDefaultRepairDiagnostic();
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
      equipment_name: repairMeta.value.equipment_name || orderTitle.value || props.order?.title || '',
      equipment_brand: repairMeta.value.equipment_brand,
      equipment_model: repairMeta.value.equipment_model,
      equipment_power: repairMeta.value.equipment_power,
      customer_complaint: repairMeta.value.customer_complaint,
      complaint_official: repairMeta.value.complaint_official,
      likely_diagnosis: repairMeta.value.likely_diagnosis,
      extra_context: repairAiExtraContext.value || defect.hint,
      current_meta: repairMeta.value as any,
    });
    repairMeta.value = { ...repairMeta.value, ...((response.repair_meta || {}) as Partial<RepairMeta>) };
    if (props.order?.id) {
      await ManagerOrdersService.patchManagerOrder(props.order.id, {
        repair_meta: repairMeta.value as any,
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
    const response = await api.getManagerServiceEstimateOrderLines(estimateId, estimateImportMode.value);
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

const removeProductLine = (index: number) => {
  if (!window.confirm('Удалить этот товар из заказа?')) return;
  productLines.value.splice(index, 1);
  if (activeSuggestionIndex.value === index) {
    activeSuggestionIndex.value = null;
    productOptions.value = [];
  }
};

const removeServiceLine = (index: number) => {
  if (!window.confirm('Удалить эту услугу из заказа?')) return;
  serviceLines.value.splice(index, 1);
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

  clearDraft();
  const linePayload = buildProposalLinesPayload();
  const payload: ManagerOrderUpdatePayload = {
    status: status.value,
    title: orderTitle.value,
    workflow_type: workflowType.value as any,
    repair_meta: repairMeta.value as any,
    manager_labels: managerLabels.value,
    next_followup_date: fromLocalDateTimeInput(nextFollowupDate.value),
    measurement_date: fromLocalDateTimeInput(assessmentDate.value),
    installation_date: fromLocalDateTimeInput(installationDate.value),
    comment: comment.value,
    is_paid: isPaid.value,
    installer_id: installerId.value,
    customer_branch_id: customerBranchId.value,
    customer_delivery_address: customerDeliveryAddress.value,
    products: linePayload.products,
    services: linePayload.services,
    measurement_required: measurementRequired.value,
    measurer_id: measurerId.value,
    measurement_result: measurementResult.value,
    additional_conditions: additionalConditions.value,
    proposal_status: status.value === 'execution' ? 'approved' : proposalStatus.value,
    target_currency: enableCurrency.value ? (targetCurrency.value || null) : null,
    target_currency_amount: enableCurrency.value && targetCurrencyAmount.value ? Number(String(targetCurrencyAmount.value).replace(',', '.')) : null,
  };
  emit('save', { orderId: props.order.id, data: payload });
};

const closeDrawer = () => {
  clearDraft();
  emit('update:modelValue', false);
};

const isDeleting = ref(false);
const deleteOrder = async () => {
  if (!props.order?.id) return;
  const proceed = window.confirm("Вы уверены? Это безвозвратно удалит заказ и все связанные с ним документы, выезды и платежи.");
  if (!proceed) return;

  isDeleting.value = true;
  try {
    await ManagerOrdersService.deleteManagerOrder(props.order.id);
    toast.value = 'Заказ успешно удален';
    setTimeout(() => {
      toast.value = '';
      emit('deleted', props.order!.id);
      closeDrawer();
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

watch(
  () => productLines.value,
  () => {
    persistDraft();
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
    <aside class="h-full w-full min-w-0 max-w-3xl overflow-y-auto bg-white p-4 text-gray-900 shadow-2xl sm:p-6 md:border-l md:border-gray-200">
      <header class="mb-4 border-b border-gray-100 pb-4">
        <div class="mb-3 flex items-start justify-between gap-3">
          <div class="min-w-0 flex-1">
            <div class="mb-1 flex flex-wrap items-center gap-2">
              <span class="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-semibold text-slate-600">Заказ №{{ order?.id }}</span>
              <span
                v-if="isWebsiteOrder"
                class="inline-flex items-center gap-1 rounded-full border border-emerald-200 bg-emerald-50 px-2.5 py-1 text-[11px] font-semibold uppercase tracking-[0.12em] text-emerald-700"
              >
                <span class="material-icons-round text-[14px]">language</span>
                Сайт
              </span>
            </div>

            <div v-if="isEditingOrderTitle" class="mt-2 flex flex-col gap-2 sm:flex-row sm:items-start">
              <label class="min-w-0 flex-1">
                <span class="sr-only">Рабочее название заказа</span>
                <input
                  v-model="orderTitle"
                  class="field-input text-base font-semibold sm:text-lg"
                  placeholder="Например: Монтаж магазина в Дубровно"
                  maxlength="160"
                  @keydown.enter.prevent="isEditingOrderTitle = false"
                  @keydown.esc.prevent="isEditingOrderTitle = false"
                />
                <span v-if="getFieldError('title')" class="text-xs text-red-300">{{ getFieldError('title') }}</span>
              </label>
              <button type="button" class="btn-mini-outline whitespace-nowrap" @click="isEditingOrderTitle = false">Готово</button>
            </div>
            <div v-else class="mt-1 flex min-w-0 items-start gap-2">
              <h2 class="min-w-0 break-words text-lg font-semibold text-gray-900 sm:text-xl font-['Space_Grotesk']">{{ displayOrderTitle }}</h2>
              <button
                type="button"
                class="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-slate-400 transition-colors hover:bg-slate-100 hover:text-teal-700"
                title="Редактировать название"
                @click="isEditingOrderTitle = true"
              >
                <span class="material-icons-round text-[16px]">edit</span>
              </button>
            </div>

            <div class="mt-3 flex flex-wrap items-center gap-2">
              <span
                v-for="label in managerLabels"
                :key="label"
                class="inline-flex max-w-full items-center gap-1 rounded-full border border-teal-200 bg-teal-50 px-2.5 py-1 text-xs font-medium text-teal-800"
              >
                <span class="truncate">{{ label }}</span>
                <button
                  type="button"
                  class="flex h-4 w-4 items-center justify-center rounded-full text-teal-500 hover:bg-teal-100 hover:text-teal-800"
                  :aria-label="`Удалить метку ${label}`"
                  @click="removeManagerLabel(label)"
                >
                  <span class="material-icons-round text-[14px]">close</span>
                </button>
              </span>
              <button
                v-if="!showManagerLabelInput"
                type="button"
                class="inline-flex items-center gap-1 rounded-full border border-dashed border-slate-300 px-2.5 py-1 text-xs font-medium text-slate-600 transition hover:border-teal-300 hover:text-teal-700"
                @click="showManagerLabelInput = true"
              >
                <span class="material-icons-round text-[14px]">add</span>
                метка
              </button>
              <div v-else class="flex min-w-[220px] max-w-full flex-1 gap-2 sm:flex-none">
                <input
                  v-model="managerLabelDraft"
                  class="field-input h-8 text-xs"
                  placeholder="срочно, ждём оплату"
                  @keydown.enter.prevent="addManagerLabel"
                  @keydown.esc.prevent="showManagerLabelInput = false"
                />
                <button type="button" class="btn-mini h-8 whitespace-nowrap text-xs" @click="addManagerLabel">Добавить</button>
              </div>
              <span v-if="getFieldError('manager_labels')" class="text-xs text-red-300">{{ getFieldError('manager_labels') }}</span>
            </div>
          </div>

          <button class="flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-gray-400 transition-colors hover:bg-gray-100 hover:text-gray-600" type="button" @click="closeDrawer" title="Закрыть">
            <span class="material-icons-round">close</span>
          </button>
        </div>

        <div class="mb-4 rounded-2xl border border-slate-200 bg-slate-50 p-2">
          <div class="mb-2 flex items-center gap-2 px-1 text-[11px] font-semibold uppercase tracking-[0.12em] text-slate-500">
            <span class="material-icons-round text-[15px]">{{ selectedWorkflowOption.icon }}</span>
            Сценарий заказа
          </div>
          <div class="grid gap-2 sm:grid-cols-2">
            <button
              v-for="option in WORKFLOW_OPTIONS"
              :key="option.value"
              type="button"
              class="rounded-xl border px-3 py-2 text-left transition"
              :class="workflowType === option.value
                ? 'border-teal-500 bg-white text-teal-900 shadow-sm ring-1 ring-teal-100'
                : 'border-transparent bg-transparent text-slate-600 hover:border-slate-200 hover:bg-white'"
              @click="setWorkflowType(option.value)"
            >
              <span class="flex items-center gap-2 text-sm font-semibold">
                <span class="material-icons-round text-[18px]">{{ option.icon }}</span>
                {{ option.label }}
              </span>
              <span class="mt-0.5 block text-xs opacity-75">{{ option.hint }}</span>
            </button>
          </div>
        </div>

        <div class="grid gap-3 lg:grid-cols-[1fr_auto]">
          <div class="min-w-0 rounded-2xl border border-slate-200 bg-slate-50 p-3">
            <div class="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
              <div class="min-w-0">
                <div class="flex flex-wrap items-center gap-2">
                  <p class="text-[11px] font-semibold uppercase tracking-[0.12em] text-slate-500">Клиент</p>
                  <button @click="showCustomerModal = true" class="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-xs font-medium text-teal-700 transition hover:bg-white" :disabled="!customer?.id">
                    <span class="material-icons-round text-[15px]">open_in_new</span>
                    Открыть клиента
                  </button>
                </div>
                <p class="mt-1 break-words text-sm font-semibold text-slate-900">{{ clientDisplayName }}</p>
              </div>
              <div class="flex shrink-0 flex-wrap gap-2">
                <button @click="showChangeCustomerModal = true" class="btn-mini-outline whitespace-nowrap text-xs">
                  <span class="material-icons-round text-[15px]">swap_horiz</span>
                  Сменить клиента
                </button>
                <button v-if="customer?.id" @click="showBranchFields = !showBranchFields" class="btn-mini-outline whitespace-nowrap text-xs" :class="showBranchFields ? 'border-teal-200 bg-teal-50 text-teal-700' : ''">
                  <span class="material-icons-round text-[15px]">account_tree</span>
                  Филиал
                </button>
              </div>
            </div>

            <div v-if="clientSummaryContacts.length" class="mt-3 flex flex-wrap gap-2">
              <div
                v-for="item in clientSummaryContacts"
                :key="item.key"
                class="group inline-flex min-w-0 max-w-full items-center rounded-full border border-white bg-white px-2.5 py-1 text-xs text-slate-700 shadow-sm"
              >
                <span v-if="item.icon" class="material-icons-round mr-1 text-[14px] text-slate-400">{{ item.icon }}</span>
                <span v-else class="mr-1 text-[10px] font-semibold uppercase text-slate-400">{{ item.label }}</span>
                <a
                  v-if="item.href"
                  :href="item.href"
                  target="_blank"
                  class="min-w-0 truncate font-medium hover:text-teal-700"
                >
                  {{ item.value }}
                </a>
                <span v-else class="min-w-0 truncate font-medium">{{ item.value }}</span>
                <button
                  type="button"
                  class="ml-1 flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-slate-400 transition hover:bg-slate-100 hover:text-teal-700"
                  :title="`Скопировать ${item.label.toLowerCase()}`"
                  @click="copyText(item.value, item.copyLabel)"
                >
                  <span class="material-icons-round text-[13px]">content_copy</span>
                </button>
              </div>
            </div>

            <div v-if="showBranchFields && customer?.id" class="mt-3 grid gap-2 rounded-xl border border-slate-200 bg-white p-3 md:grid-cols-2">
              <label class="field-label md:col-span-2">
                Филиал клиента
                <select
                  :value="customerBranchId ?? ''"
                  class="field-input"
                  :disabled="customerBranchesLoading"
                  @change="onCustomerBranchChange"
                >
                  <option value="">Без филиала</option>
                  <option
                    v-for="branch in customerBranches"
                    :key="`order-branch-${branch.id}`"
                    :value="branch.id"
                  >
                    {{ branch.name || `Филиал #${branch.id}` }} — {{ branch.delivery_address }}
                  </option>
                </select>
                <span v-if="customerBranchesLoading" class="text-xs text-gray-500">Загрузка филиалов...</span>
                <span v-else-if="!customerBranches.length" class="text-xs text-gray-500">У клиента нет филиалов</span>
              </label>

              <input
                v-model="newBranchName"
                class="field-input"
                placeholder="Новый филиал (название)"
              />
              <input
                v-model="newBranchAddress"
                class="field-input"
                placeholder="Новый филиал (адрес)"
              />
              <div class="md:col-span-2">
                <button
                  type="button"
                  class="btn-mini-outline text-xs"
                  :disabled="creatingCustomerBranch"
                  @click="createCustomerBranch"
                >
                  {{ creatingCustomerBranch ? 'Создаем филиал...' : 'Создать филиал и выбрать' }}
                </button>
              </div>
            </div>
          </div>

          <div class="flex flex-wrap items-start gap-2 lg:justify-end">
            <button v-if="status === 'negotiation' && !measurementRequired" type="button" class="btn-mini-outline whitespace-nowrap text-xs" @click="measurementRequired = true">
              <span class="material-icons-round text-[15px]">add_location_alt</span>
              Выезд на замер
            </button>
            <button v-if="order" type="button" @click="toggleHold" class="text-xs px-3 py-1.5 rounded-lg border font-medium transition-colors" :class="order.is_on_hold ? 'bg-amber-50 border-amber-200 text-amber-700' : 'bg-white border-gray-200 text-gray-600 hover:bg-gray-50'">
              {{ order.is_on_hold ? 'Вернуть в работу' : 'Отложить' }}
            </button>
          </div>
        </div>
      </header>

      <p v-if="displayFormError" class="mb-4 rounded-xl border border-red-500/40 bg-red-50 px-3 py-2 text-sm text-red-700">
        {{ displayFormError }}
      </p>

      <OrderDrawerSection
        v-model:expanded="expandedDrawerSections.clientDetails"
        title="Объект"
        :summary="customerDetailsSummary"
        tone="default"
        :has-error="Boolean(getFieldError('customer_delivery_address') || getFieldError('comment'))"
      >
        <div class="grid gap-3 md:grid-cols-2">
          <label class="field-label md:col-span-2 relative">
            Адрес объекта / доставки
            <input
              v-model="customerDeliveryAddress"
              @input="onAddressInput"
              @blur="hideAddressSuggestions"
              @focus="addressSuggestActive = true"
              class="field-input"
              placeholder="Введите адрес..."
              autocomplete="off"
            />
            <div v-if="addressLookupLoading" class="absolute right-3 top-9">
              <span class="material-icons-round animate-spin text-gray-400 text-[18px]">refresh</span>
            </div>
            <span v-if="getFieldError('customer_delivery_address')" class="text-xs text-red-300">{{ getFieldError('customer_delivery_address') }}</span>

            <ul v-if="addressSuggestActive && addressSuggestions.length > 0" class="absolute top-full left-0 z-50 mt-1 max-h-60 w-full overflow-auto rounded-xl bg-white flex flex-col p-1 shadow-2xl border border-gray-100 ring-1 ring-black/5">
              <li
                v-for="(item, i) in addressSuggestions"
                :key="i"
                class="flex cursor-pointer flex-col px-3 py-2 text-sm hover:bg-gray-50 rounded-lg transition-colors border-b border-gray-50 last:border-0"
                @mousedown.prevent="selectAddressSuggestion(item)"
              >
                <div class="font-medium text-gray-900">{{ item.title?.text }}</div>
                <div v-if="item.subtitle?.text" class="text-xs text-gray-500 mt-0.5 truncate">{{ item.subtitle?.text }}</div>
              </li>
            </ul>
          </label>

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
      <section v-if="status === 'negotiation'" class="mt-4 rounded-2xl border border-blue-100 bg-blue-50/30 p-3">
        <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div class="min-w-0">
            <h3 class="text-sm font-semibold text-blue-900">{{ planningTitle }}</h3>
            <p class="mt-0.5 truncate text-xs text-blue-700/70">{{ planningSummary }}</p>
          </div>
          <button
            v-if="!measurementRequired"
            type="button"
            class="btn-mini-outline justify-center whitespace-nowrap text-xs"
            @click="measurementRequired = true"
          >
            <span class="material-icons-round text-[15px]">add_location_alt</span>
            {{ isRepairWorkflow ? 'Выезд на диагностику' : 'Выезд на замер' }}
          </button>
          <label v-else class="inline-flex items-center gap-2 rounded-xl bg-white px-3 py-2 text-xs font-medium text-blue-900 ring-1 ring-blue-100">
            <input type="checkbox" v-model="measurementRequired" class="h-4 w-4 rounded border-gray-300 text-teal-600 focus:ring-teal-600" />
            {{ isRepairWorkflow ? 'Диагностика нужна' : 'Замер нужен' }}
          </label>
        </div>

        <div v-if="measurementRequired" class="mt-3 rounded-xl border border-blue-100 bg-white p-3 shadow-sm">
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
                  <option v-for="inst in installersList" :key="inst.id" :value="inst.id">
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
                <option v-for="inst in installersList" :key="inst.id" :value="inst.id">
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
              <label class="field-label flex-1">
                Базовая неисправность
                <select v-model="repairAiDefectType" class="field-input bg-white">
                  <option v-for="item in REPAIR_AI_DEFECT_TYPES" :key="item.value" :value="item.value">
                    {{ item.label }}
                  </option>
                </select>
              </label>
              <label class="field-label flex-[1.2]">
                Детали диагностики
                <input
                  v-model="repairAiExtraContext"
                  class="field-input bg-white"
                  placeholder="Например: наружный блок не стартует, запах гари, сильная коррозия..."
                />
              </label>
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
              <label class="inline-flex items-center gap-2 rounded-lg bg-white/70 px-2.5 py-1.5 text-xs font-semibold text-violet-800">
                <input v-model="repairAiAllowAssumptions" type="checkbox" class="h-4 w-4 rounded border-violet-300 text-violet-600 focus:ring-violet-500" />
                Заполнить на усмотрение
              </label>
            </div>
          </div>
          <label class="field-label md:col-span-2">
            Жалоба клиента
            <textarea
              v-model="repairMeta.customer_complaint"
              class="field-input min-h-[72px]"
              placeholder="Например: не охлаждает, шумит, течет вода..."
            />
          </label>
          <label class="field-label">
            Формулировка для акта
            <textarea
              v-model="repairMeta.complaint_official"
              class="field-input min-h-[72px]"
              placeholder="Официальная формулировка жалобы"
            />
          </label>
          <label class="field-label">
            Вероятный диагноз
            <textarea
              v-model="repairMeta.likely_diagnosis"
              class="field-input min-h-[72px]"
              placeholder="Предварительная причина неисправности"
            />
          </label>

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
      </OrderDrawerSection>



      <!-- Смета -->
      <OrderDrawerSection
        v-model:expanded="expandedDrawerSections.proposals"
        :title="isRepairWorkflow ? 'Смета ремонта' : 'Предложения'"
        :summary="activeProposalLineLabel"
        tone="default"
        :has-error="Boolean(getFieldError('products') || getFieldError('services'))"
      >
      <div class="rounded-2xl border border-gray-200 bg-gray-50/50 p-3 sm:p-4">
        <div class="mb-4 border-b border-gray-200 pb-3">
          <div class="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
            <div>
              <h3 class="text-lg font-bold text-gray-900 sm:text-xl font-['Space_Grotesk']">{{ isRepairWorkflow ? 'Смета ремонта' : 'Предложения' }}</h3>
              <p class="mt-1 text-xs text-gray-500">{{ activeProposalLineLabel }}</p>
            </div>
          </div>

          <div v-if="orderProposals.length" class="mt-3 flex gap-2 overflow-x-auto pb-1">
            <button
              v-for="proposal in orderProposals"
              :key="proposal.id"
              type="button"
              class="shrink-0 rounded-xl border px-3 py-2 text-left text-xs transition"
              :class="proposal.id === activeProposal?.id
                ? 'border-teal-500 bg-teal-50 text-teal-900 shadow-sm'
                : 'border-gray-200 bg-white text-gray-600 hover:border-teal-200 hover:text-teal-800'"
              @click="onProposalClick(proposal, $event)"
            >
              <span class="flex items-center gap-1 font-semibold">
                {{ proposal.name }}
                <span v-if="proposal.is_selected" class="material-icons-round text-[14px] text-teal-600">check_circle</span>
              </span>
              <span class="mt-0.5 block whitespace-nowrap text-[11px] opacity-75">{{ formatMoney(proposal.total_amount || 0) }}</span>
            </button>
            <button
              type="button"
              class="flex min-h-[58px] w-12 shrink-0 items-center justify-center rounded-xl border border-dashed border-slate-300 bg-white text-slate-500 transition hover:border-teal-300 hover:text-teal-700"
              :disabled="proposalActionLoading"
              title="Добавить предложение"
              @click="createProposal"
            >
              <span class="material-icons-round text-[20px]">add</span>
            </button>
          </div>

          <div v-if="activeProposal" class="mt-3 flex flex-wrap items-center gap-2">
            <button
              type="button"
              class="btn-mini whitespace-nowrap text-xs"
              :disabled="proposalActionLoading || activeProposal.is_selected"
              @click="selectProposalForOrder()"
            >
              <span class="material-icons-round text-[15px]">check_circle</span>
              Выбрать
            </button>
            <button
              type="button"
              class="btn-mini-outline whitespace-nowrap text-xs"
              :disabled="proposalActionLoading || !activeProposal"
              @click="duplicateProposal"
            >
              <span class="material-icons-round text-[15px]">content_copy</span>
              Копия
            </button>
            <button
              type="button"
              class="btn-mini-outline whitespace-nowrap text-xs"
              :disabled="proposalActionLoading || !activeProposal"
              @click="renameProposal"
            >
              <span class="material-icons-round text-[15px]">edit</span>
              Название
            </button>
            <button
              type="button"
              class="flex h-9 w-9 items-center justify-center rounded-xl border border-red-200 bg-white text-red-600 hover:bg-red-50 disabled:opacity-50"
              :disabled="proposalActionLoading || orderProposals.length <= 1"
              @click="archiveProposal"
              title="В архив"
            >
              <span class="material-icons-round text-[18px]">delete</span>
            </button>
          </div>
        </div>

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
                type="button"
                class="absolute -right-2 -top-2 z-10 inline-flex h-8 w-8 items-center justify-center rounded-full border border-red-200 bg-red-50 text-lg font-bold text-red-600 shadow-sm transition-colors hover:bg-red-100"
                :aria-label="`Удалить услугу #${index + 1}`"
                title="Удалить услугу"
                @click="removeServiceLine(index)"
              >
                ×
              </button>
              <div class="grid grid-cols-6 gap-2 md:grid-cols-12 md:items-start">
                <label class="relative col-span-6 space-y-1 md:col-span-5">
                  <span class="flex h-auto items-center px-1 text-xs font-medium text-gray-500 md:h-6">Название</span>
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
                      <p class="line-clamp-2 font-medium text-gray-900">{{ item.title }}</p>
                      <p class="mt-1 flex flex-wrap items-center gap-1 text-[11px] text-gray-500">
                        <span>{{ formatMoney(item.price) }}</span>
                        <span v-if="item.service_kind">· {{ formatServiceKind(item.service_kind) }}</span>
                        <span v-if="item.category">· {{ item.category }}</span>
                        <span v-if="item.included_route_meters">· трасса до {{ item.included_route_meters }} м</span>
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
            <div class="grid gap-2 md:grid-cols-2">
              <label class="space-y-1 md:col-span-2">
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
                <span class="px-1 text-xs font-medium text-gray-500">Режим</span>
                <select v-model="estimateImportMode" class="field-input">
                  <option value="detailed">Подробно (по строкам)</option>
                  <option value="collapsed">Схлопнуто (одной строкой)</option>
                </select>
              </label>
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
              Показываем 10 последних смет как типовые шаблоны. «Подробно» добавляет отдельные строки, «Схлопнуто» — одну строку с общим итогом.
            </p>
          </div>
        </section>
      </div>
      </OrderDrawerSection>

      <!-- Экшн-зона (Proposal & Docs) -->
      <OrderDrawerSection
        v-if="status !== 'execution'"
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
          :order="order"
          :active-proposal-id="activeProposalId"
          :before-generate="beforeDocumentGenerate"
          @refresh="refreshOrderFromDocumentsPanel"
          @toast="handleDocumentPanelToast"
        />
      </OrderDrawerSection>


      <DealExecutionTab
        v-if="status === 'execution' && order"
        :order="order"
        @refresh="emit('reload', order.id) /* triggering parent reload without closing drawer */"
        @close="closeDrawer"
        class="mt-8"
      />

      <!-- Оплаты и Валюта (Объединенный блок) -->
      <OrderDrawerSection
        v-if="order && status !== 'execution'"
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

      <footer class="mt-6 flex flex-col gap-3 border-t border-gray-100 pt-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <button class="inline-flex items-center gap-2 rounded-xl border border-red-200 bg-red-50 px-4 py-2 text-sm font-semibold text-red-700 transition-colors hover:bg-red-100 disabled:opacity-50" :disabled="saving || isDeleting" @click="deleteOrder" title="Безвозвратное удаление">
            <span class="material-icons-round text-[18px]">delete</span>
            {{ isDeleting ? 'Удаление...' : 'Удалить заказ' }}
          </button>
        </div>
        <div class="flex flex-row gap-2">
          <button class="btn-mini-outline flex-1 sm:flex-none" :disabled="saving || isDeleting" @click="closeDrawer">Закрыть</button>
          <button class="btn-mini flex-1 sm:flex-none" :disabled="saving || isDeleting" @click="handleSave">
            {{ saving ? 'Сохраняем...' : 'Сохранить' }}
          </button>
        </div>
      </footer>
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
