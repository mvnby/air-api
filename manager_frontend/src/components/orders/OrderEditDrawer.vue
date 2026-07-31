<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue';
import { useDebounceFn } from '@vueuse/core';
import { api } from '../../api';
import DealExecutionTab from './DealExecutionTab.vue';
import OrderDrawerSection from './OrderDrawerSection.vue';
import OrderAttachmentsPanel from '../service-attachments/OrderAttachmentsPanel.vue';
import OrderEquipmentPanel from '../equipment/OrderEquipmentPanel.vue';
import OrderWorkspaceHeader from './OrderWorkspaceHeader.vue';
import OrderSalesInstallationWorkspace from './OrderSalesInstallationWorkspace.vue';
import OrderProposalToolbar from './OrderProposalToolbar.vue';
import OrderPaymentsPanel from './OrderPaymentsPanel.vue';
import OrderWebsiteIntakePanel from './OrderWebsiteIntakePanel.vue';
import OrderPlanningPanel from './OrderPlanningPanel.vue';
import OrderRepairPanel from './OrderRepairPanel.vue';
import OrderProductLinesEditor from './OrderProductLinesEditor.vue';
import OrderServiceLinesEditor from './OrderServiceLinesEditor.vue';
import OrderCustomerContext from './OrderCustomerContext.vue';
import OrderExecutionPanel from './OrderExecutionPanel.vue';
import OrderDocumentsWorkspace from './OrderDocumentsWorkspace.vue';
import { confirmDialog, promptDialog } from '../../services/ui-feedback';
import type { ServiceAttachmentEquipmentOption } from '../service-attachments/types';
import type {
  ManagerOrderDetailResponse,
  ManagerOrderUpdatePayload,
  ManagerServiceEstimateResponse,
  OrderProductLineResponse,
  OrderProposalResponse,
  OrderServiceLineResponse,
  ManagerInstallerResponse,
  ManagerQuickTariffResponse,
  PaymentResponse,
  PaymentCurrency,
  FxRateResponse,
  OutgoingEmailResponse,
} from '../../client';
import { ManagerOrdersService, ManagerSettingsService, ManagerMailService } from '../../client';
import { formatMoney } from './order-utils';
import {
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
import { emptyRepairMeta, normalizeRepairMeta, type RepairMeta } from './repair-meta';
import { fromLocalDateTimeInput, toLocalDateTimeInput } from '../../utils/datetime';
import {
  useServiceDescriptionMode,
  type ServiceDescriptionMode,
} from './service-description-mode';

import { getApiErrorMessage } from '../../utils/api-errors';
import { useSmartStickyHeader } from '../../composables/useSmartStickyHeader';
import type {
  LogisticsComponentKind,
  OrderDrawerDraft,
  OrderLogisticsComponent,
  ProductLine,
  ProductLogisticsTemplateComponent,
  ProductOption,
  ServiceLine,
} from './order-editor-types';

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

const serviceKindLabels: Record<string, string> = {
  installation: 'монтаж',
  pre_install: 'закладка трассы',
  dismantling: 'демонтаж',
  maintenance: 'обслуживание',
  repair: 'ремонт',
};

const formatServiceKind = (kind?: string | null) => serviceKindLabels[String(kind || '')] || kind || '';
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
const customerBranchId = ref<number | null>(null);
const newBranchAddress = ref('');

const targetCurrency = ref<PaymentCurrency | null>(null);
const targetCurrencyAmount = ref<number | null>(null);
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
const payments = ref<PaymentResponse[]>([]);
const linkedEquipmentOptions = ref<ServiceAttachmentEquipmentOption[]>([]);
const equipmentPanelRef = ref<InstanceType<typeof OrderEquipmentPanel> | null>(null);
const documentsWorkspaceRef = ref<InstanceType<typeof OrderDocumentsWorkspace> | null>(null);
const proposalToolbarRef = ref<InstanceType<typeof OrderProposalToolbar> | null>(null);
const executionWorkspaceOpen = ref(false);
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
const showManagerLabelInput = ref(false);

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
const compactObjectAddress = computed(() => (
  customerDeliveryAddress.value.trim()
  || props.order?.customer_branch?.delivery_address
  || ''
));
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
const normalizeDocumentIdentity = (value: unknown) => (
  String(value || '').toUpperCase().replace(/[^A-ZА-ЯЁ0-9]/g, '')
);
const sentDocumentTypes = computed(() => {
  const types = new Set<string>();
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
      for (const [number, docType] of documentsByNumber) {
        if (number && filename.includes(number)) {
          types.add(docType);
          break;
        }
      }
    }
  }
  return [...types];
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
  sentDocumentTypes: sentDocumentTypes.value,
  missingReferencedInvoice: missingReferencedInvoice.value,
  total: totalPreview.value,
  paid: totalPaymentsPreview.value,
  balance: balanceDuePreview.value,
}));
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

const orderDocuments = computed(() => props.order?.documents || []);
const isRepairWorkflow = computed(() => workflowType.value === 'repair');
const showProductLinesSection = computed(() => workflowType.value === 'sales_installation');
const buildRepairMetaPayload = () => normalizeRepairMeta(
  repairMeta.value,
  { defaultRepairStatus: isRepairWorkflow.value },
);
const beforeDocumentGenerate = async (type: string) => {
  if (!props.order?.id) return false;
  let mutated = false;
  if (['offer', 'invoice', 'retail_receipt', 'service_act', 'maintenance_service_act', 'warranty_certificate', 'act', 'defect_act', 'tn2', 'ttn1'].includes(type)) {
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
    executionWorkspaceOpen.value = false;
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
  if (offerExists) documentsWorkspaceRef.value?.openSend();
  else {
    documentsWorkspaceRef.value?.openCreate();
    setToast('Сначала создайте коммерческое предложение для активного варианта', 'error');
  }
  document.getElementById('order-workspace-documents')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
};

const openDocumentsSend = async () => {
  expandedDrawerSections.value.documents = true;
  activeWorkspaceTarget.value = 'documents';
  await nextTick();
  documentsWorkspaceRef.value?.openSend();
  document.getElementById('order-workspace-documents')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
};

const handleWorkspaceNextAction = async () => {
  const action = orderWorkspace.value.nextAction;
  if (action.command === 'create_proposal') return createProposal();
  if (action.command === 'finish_proposal') return changeActiveProposalStatus('ready_to_send');
  if (action.command === 'send_proposal') return openProposalSend();
  if (action.command === 'send_documents') return openDocumentsSend();
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
    await addDefaultRepairDiagnostic(requestId);
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
const openWorkspaceTarget = async (target: OrderWorkspaceTarget, allowToggle = false) => {
  const shouldClose = allowToggle && activeWorkspaceTarget.value === target;
  if (activeWorkspaceTarget.value === 'equipment') equipmentPanelRef.value?.collapse();
  if (workflowType.value === 'sales_installation' && target !== 'object') {
    expandedDrawerSections.value.proposals = false;
    expandedDrawerSections.value.documents = false;
    expandedDrawerSections.value.payments = false;
    expandedDrawerSections.value.execution = false;
    executionWorkspaceOpen.value = false;
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
    expandedDrawerSections.value.documents = true;
  }
  if (target === 'payments') {
    if (status.value === 'execution') executionWorkspaceOpen.value = true;
    else expandedDrawerSections.value.payments = true;
  }
  await nextTick();
  if (target === 'equipment') {
    expandedDrawerSections.value.proposals = true;
    await equipmentPanelRef.value?.expand();
    await nextTick();
  }
  const elementId = status.value === 'execution' && target === 'payments'
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

const handleCustomerUpdated = async (updatedOrder: ManagerOrderDetailResponse) => {
  emit('updated', updatedOrder);
  await initForm(updatedOrder);
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

      <OrderCustomerContext
        v-if="order"
        v-model:delivery-address="customerDeliveryAddress"
        v-model:customer-branch-id="customerBranchId"
        v-model:comment="comment"
        v-model:expanded="expandedDrawerSections.clientDetails"
        v-model:new-branch-address="newBranchAddress"
        :order="order"
        :address-error="getFieldError('customer_delivery_address')"
        :comment-error="getFieldError('comment')"
        @toast="setToast($event.message, $event.type)"
        @updated="handleCustomerUpdated"
        @reload="emit('reload', $event)"
      >
        <OrderSalesInstallationWorkspace
          v-if="workflowType === 'sales_installation'"
          :lanes="orderWorkspace.lanes"
          :active-target="activeWorkspaceTarget"
          @open="openWorkspaceTarget($event, true)"
        />

        <p v-if="displayFormError" class="mb-4 rounded-xl border border-red-500/40 bg-red-50 px-3 py-2 text-sm text-red-700">
          {{ displayFormError }}
        </p>
      </OrderCustomerContext>

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

      <OrderWebsiteIntakePanel
        v-if="isWebsiteOrder"
        v-model:expanded="expandedDrawerSections.website"
        :order="order!"
        :delivery-address="customerDeliveryAddress"
        :comment="comment"
        @copy="copyText($event.value, $event.label)"
      />



      <OrderPlanningPanel
        v-if="status === 'negotiation'"
        v-model:measurement-required="measurementRequired"
        v-model:assessment-date="assessmentDate"
        v-model:negotiation-status="negotiationStatus"
        v-model:auto-execution-on-payment="autoExecutionOnPayment"
        v-model:details-expanded="expandedDrawerSections.planningDetails"
        v-model:measurer-id="measurerId"
        v-model:measurement-result="measurementResult"
        v-model:installation-date="installationDate"
        v-model:installer-id="installerId"
        :workflow-type="workflowType"
        :executor-options="executorOptions"
        :customer-branch-id="customerBranchId"
        :new-branch-address="newBranchAddress"
        :measurement-error="getFieldError('measurement_date')"
        :installation-error="getFieldError('installation_date')"
      />


      <OrderRepairPanel
        v-if="isRepairWorkflow && order"
        v-model:expanded="expandedDrawerSections.repair"
        v-model:repair-meta="repairMeta"
        :order="order"
        :order-title="orderTitle"
        :measurement-result="measurementResult"
        :customer-branch-id="customerBranchId"
        :object-address="compactObjectAddress"
        @toast="setToast($event.message, $event.type)"
        @reload="emit('reload', $event)"
      />



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

        <OrderProductLinesEditor
          v-if="showProductLinesSection"
          v-model:lines="productLines"
          v-model:search-in-stock="searchInStock"
          :product-options="productOptions"
          :product-lookup-by-id="productLookupById"
          :product-lookup-loading="productLookupLoading"
          :active-suggestion-index="activeSuggestionIndex"
          :supply-action-loading-line-id="supplyActionLoadingLineId"
          :products-error="getFieldError('products')"
          :supply-badge-for-line="supplyBadgeForLine"
          @focus="onProductInputFocus"
          @input="onProductQueryInput"
          @blur="onProductInputBlur"
          @select="selectProductForLine($event.index, $event.option)"
          @open="openSelectedProduct"
          @remove="removeProductLine"
          @add="addProductLine"
          @supply="createSupplyFromProductLine($event.line, $event.intent)"
        />

        <OrderServiceLinesEditor
          v-model:lines="serviceLines"
          v-model:editing-index="editingServiceLineIndex"
          v-model:show-estimate-import="showEstimateImport"
          v-model:selected-estimate-id="selectedEstimateId"
          v-model:estimate-search-query="estimateSearchQuery"
          v-model:estimate-import-mode="estimateImportMode"
          v-model:description-mode="serviceDescriptionMode"
          :service-options="serviceTariffOptions"
          :service-lookup-loading="serviceTariffLookupLoading"
          :active-suggestion-index="activeServiceSuggestionIndex"
          :services-error="getFieldError('services')"
          :estimate-options="estimateOptions"
          :estimate-options-loading="estimateOptionsLoading"
          :importing-estimate="importingEstimate"
          :format-service-kind="formatServiceKind"
          @focus="onServiceTitleFocus"
          @input="onServiceTitleInput"
          @blur="onServiceTitleBlur"
          @select="selectServiceTariffForLine($event.index, $event.option)"
          @description-mode="setServiceLineDescriptionMode($event.index, $event.mode)"
          @remove="removeServiceLine"
          @add="addServiceLine"
          @toggle-estimate="toggleEstimateImport"
          @import-estimate="applyEstimateToServices"
          @load-estimates="loadEstimateOptions"
          @remember-description-mode="setDefaultServiceDescriptionMode"
        />
        </fieldset>
      </div>
      </OrderDrawerSection>

      <OrderDocumentsWorkspace
        v-if="order"
        ref="documentsWorkspaceRef"
        v-model:expanded="expandedDrawerSections.documents"
        :order="order"
        :active-proposal-id="activeProposalId"
        :product-lines="productLines"
        :total="totalPreview"
        :before-generate="beforeDocumentGenerate"
        @refresh="refreshOrderFromDocumentsPanel"
        @toast="handleDocumentPanelToast"
      />


      <OrderExecutionPanel
        v-if="status === 'execution'"
        v-model:expanded="expandedDrawerSections.execution"
        v-model:execution-status="executionStatus"
        v-model:execution-without-payment="executionWithoutPayment"
        v-model:execution-without-payment-reason="executionWithoutPaymentReason"
        v-model:auto-close-on-payment="autoCloseOnPayment"
        :workflow-type="workflowType"
      />

      <DealExecutionTab
        v-if="status === 'execution' && order && executionWorkspaceOpen"
        id="order-workspace-execution-details"
        :order="order"
        @refresh="emit('reload', order.id) /* triggering parent reload without closing drawer */"
        @close="closeDrawer"
        class="mt-4"
      />

      <OrderPaymentsPanel
        v-if="order && status !== 'execution'"
        v-model:expanded="expandedDrawerSections.payments"
        v-model:payments="payments"
        v-model:enable-currency="enableCurrency"
        v-model:target-currency="targetCurrency"
        v-model:target-currency-amount="targetCurrencyAmount"
        :order="order"
        :current-fx-rate="currentFxRate"
        :is-b2c-customer="isB2cCustomer"
        :total="totalPreview"
        :total-payments="totalPaymentsPreview"
        :balance-due="balanceDuePreview"
        :margin="marginPreview"
        :calculated-target-currency-payments="calculatedTargetCurrencyPayments"
        :target-currency-balance-due="targetCurrencyBalanceDue"
        @toast="setToast($event.message, $event.type)"
        @reload="emit('reload', $event)"
      />

      </div>
    </aside>

  </div>
</template>
