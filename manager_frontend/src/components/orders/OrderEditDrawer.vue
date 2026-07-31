<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue';
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
import { confirmDialog } from '../../services/ui-feedback';
import type { ServiceAttachmentEquipmentOption } from '../service-attachments/types';
import type {
  ManagerOrderDetailResponse,
  ManagerOrderUpdatePayload,
  ManagerInstallerResponse,
  PaymentResponse,
  PaymentCurrency,
  FxRateResponse,
  OutgoingEmailResponse,
} from '../../client';
import { ManagerOrdersService, ManagerSettingsService, ManagerMailService } from '../../client';
import {
  buildOrderWorkspaceViewModel,
  normalizeOrderWorkflowType,
  type OrderWorkflowType,
  type OrderWorkspaceTarget,
} from './order-workspace';
import { emptyRepairMeta, normalizeRepairMeta, type RepairMeta } from './repair-meta';
import { fromLocalDateTimeInput, toLocalDateTimeInput } from '../../utils/datetime';
import { getApiErrorMessage } from '../../utils/api-errors';
import { useSmartStickyHeader } from '../../composables/useSmartStickyHeader';
import { useOrderCommercialEditor } from '../../composables/useOrderCommercialEditor';
import { useOrderProposalLifecycle } from '../../composables/useOrderProposalLifecycle';
import type {
  OrderDrawerDraft,
  OrderLogisticsComponent,
  ProductLogisticsTemplateComponent,
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
const toast = ref('');
const toastType = ref<'success' | 'error'>('success');
function setToast(message: string, type: 'success' | 'error' = 'success') {
  toast.value = message;
  toastType.value = type;
  window.setTimeout(() => {
    if (toast.value === message) toast.value = '';
  }, 3000);
}

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
const negotiationStatus = ref('awaiting_offer');
const executionStatus = ref('needs_schedule');
const executionWithoutPayment = ref(false);
const executionWithoutPaymentReason = ref('');
const autoExecutionOnPayment = ref(false);
const autoCloseOnPayment = ref(false);

const installersList = ref<ManagerInstallerResponse[]>([]);

const savedLinesSnapshot = ref('');
const savedFormSnapshot = ref('');
const pendingDraftClearOrderId = ref<number | null>(null);
const {
  activeServiceSuggestionIndex,
  activeSuggestionIndex,
  addProductLine,
  addServiceLine,
  applyEstimateToServices,
  applyTariffTemplateToLine,
  buildLinesPayload,
  createSupplyFromProductLine,
  currentLinesSnapshot: buildCurrentLinesSnapshot,
  editingServiceLineIndex,
  estimateImportMode,
  estimateOptions,
  estimateOptionsLoading,
  estimateSearchQuery,
  importingEstimate,
  loadEstimateOptions,
  loadLines,
  loadOrderSupplyRequests,
  margin: marginPreview,
  onProductInputBlur,
  onProductInputFocus,
  onProductQueryInput,
  onServiceTitleBlur,
  onServiceTitleFocus,
  onServiceTitleInput,
  openSelectedProduct,
  productLines,
  productLookupById,
  productLookupLoading,
  productOptions,
  removeProductLine,
  removeServiceLine,
  resetLookupState,
  searchInStock,
  selectProductForLine,
  selectServiceTariffForLine,
  selectedEstimateId,
  serviceDescriptionMode,
  serviceLines,
  serviceTariffLookupLoading,
  serviceTariffOptions,
  setDefaultServiceDescriptionMode,
  setServiceLineDescriptionMode,
  showEstimateImport,
  supplyActionLoadingLineId,
  supplyBadgeForLine,
  syncProductLookupFromLines,
  toggleEstimateImport,
  total: totalPreview,
  validateLines: validateProposalLines,
} = useOrderCommercialEditor({
  order: computed(() => props.order),
  setToast,
  persistDraft: () => persistDraft(),
});
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

const {
  activeProposal,
  activeProposalId,
  activeProposalLineLabel,
  activeProposalLocked,
  activeProposalStatus,
  archiveProposal,
  changeActiveProposalStatus,
  createProposal,
  duplicateProposal,
  loadProposalLines,
  onProposalClick,
  proposalActionLoading,
  proposalStatus,
  proposals: orderProposals,
  renameProposal,
  saveCurrentProposalLines,
  selectProposalForOrder,
  selectedProposal: selectedOrderProposal,
} = useOrderProposalLifecycle({
  order: computed(() => props.order),
  negotiationStatus,
  total: totalPreview,
  localFormError,
  buildLinesPayload,
  validateLines: validateProposalLines,
  loadLines,
  resetLookupState,
  loadSupplyRequests: loadOrderSupplyRequests,
  clearDraft: () => clearDraft(),
  currentLinesSnapshot: buildCurrentLinesSnapshot,
  savedLinesSnapshot,
  setToast,
  onUpdated: (updatedOrder) => emit('updated', updatedOrder),
  onReload: (orderId) => emit('reload', orderId),
});

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

const currentLinesSnapshot = () => buildCurrentLinesSnapshot(activeProposalId.value);
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

function persistDraft() {
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
}

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

function clearDraft() {
  if (!draftKey.value) return;
  try {
    window.sessionStorage.removeItem(draftKey.value);
  } catch (error) {
    console.warn('Failed to clear order drawer draft', error);
  }
}

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

  resetLookupState();
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

const buildProposalLinesPayload = () => buildLinesPayload(activeProposalId.value);

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
