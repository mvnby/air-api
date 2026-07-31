<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue';
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
import type { ServiceAttachmentEquipmentOption } from '../service-attachments/types';
import type {
  ManagerOrderDetailResponse,
  ManagerOrderUpdatePayload,
} from '../../client';
import { ManagerOrdersService } from '../../client';
import {
  buildOrderWorkspaceViewModel,
} from './order-workspace';
import { useSmartStickyHeader } from '../../composables/useSmartStickyHeader';
import { useOrderCommercialEditor } from '../../composables/useOrderCommercialEditor';
import { useOrderProposalLifecycle } from '../../composables/useOrderProposalLifecycle';
import { useOrderDrawerForm } from '../../composables/useOrderDrawerForm';
import { useOrderDrawerPersistence } from '../../composables/useOrderDrawerPersistence';
import { useOrderDocumentStatus } from '../../composables/useOrderDocumentStatus';
import { useOrderWorkspaceNavigation } from '../../composables/useOrderWorkspaceNavigation';
import { useOrderDrawerActions } from '../../composables/useOrderDrawerActions';

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

const savedLinesSnapshot = ref('');
const savedFormSnapshot = ref('');
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
const {
  addManagerLabel,
  assessmentDate,
  autoCloseOnPayment,
  autoExecutionOnPayment,
  balanceDue: balanceDuePreview,
  buildRepairMetaPayload,
  buildSavePayload,
  calculatedTargetCurrencyPayments,
  comment,
  currentFormSnapshot: buildCurrentFormSnapshot,
  currentFxRate,
  customerBranchId,
  customerDeliveryAddress,
  enableCurrency,
  executionStatus,
  executionWithoutPayment,
  executionWithoutPaymentReason,
  executorOptions,
  hydrateOrder,
  installationDate,
  installerId,
  isB2cCustomer: buildIsB2cCustomer,
  isRepairWorkflow,
  localFormError,
  localServerErrors,
  managerLabelDraft,
  managerLabels,
  measurementRequired,
  measurementResult,
  measurerId,
  negotiationStatus,
  newBranchAddress,
  orderTitle,
  payments,
  removeManagerLabel,
  repairMeta,
  setWorkflowType,
  showProductLinesSection,
  status,
  targetCurrency,
  targetCurrencyAmount,
  targetCurrencyBalanceDue,
  totalPayments: totalPaymentsPreview,
  workflowType,
} = useOrderDrawerForm({
  total: totalPreview,
  productLines,
  serviceLines,
  serviceTariffOptions,
  activeServiceSuggestionIndex,
  applyTariffTemplateToLine,
  buildLinesPayload: () => buildLinesPayload(activeProposalId.value),
  validateLines: validateProposalLines,
  setToast,
});
const linkedEquipmentOptions = ref<ServiceAttachmentEquipmentOption[]>([]);
const equipmentPanelRef = ref<InstanceType<typeof OrderEquipmentPanel> | null>(null);
const documentsWorkspaceRef = ref<InstanceType<typeof OrderDocumentsWorkspace> | null>(null);
const proposalToolbarRef = ref<InstanceType<typeof OrderProposalToolbar> | null>(null);

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

const {
  clearDraft,
  expandedDrawerSections,
  hasUnsavedChanges,
  initializedOrderId,
  pendingDraftClearOrderId,
  persistDraft,
  restoreDraft,
  restoreDrawerSections,
} = useOrderDrawerPersistence({
  order: computed(() => props.order),
  activeProposalId,
  productLines,
  serviceLines,
  savedLinesSnapshot,
  savedFormSnapshot,
  currentLinesSnapshot: () => buildCurrentLinesSnapshot(activeProposalId.value),
  currentFormSnapshot: () => buildCurrentFormSnapshot(proposalStatus.value),
});

const {
  documentEmailStatus,
  loadOrderEmails,
  missingReferencedInvoice,
  orderDocuments,
  resetOrderEmails,
  sentDocumentTypes,
} = useOrderDocumentStatus({
  order: computed(() => props.order),
  payments,
});

const {
  activeWorkspaceTarget,
  executionWorkspaceOpen,
  openDocumentsSend,
  openProposalSend: openProposalDocuments,
  openWorkspaceTarget,
  resetWorkspaceNavigation,
} = useOrderWorkspaceNavigation({
  status,
  workflowType,
  expandedSections: expandedDrawerSections,
  equipmentPanelRef,
  documentsWorkspaceRef,
  setToast,
});
const openProposalSend = () => openProposalDocuments(activeProposal.value, orderDocuments.value);

const customer = computed(() => props.order?.customer ?? null);
const customerDisplayName = computed(() => (
  customer.value?.full_legal_name
  || customer.value?.name
  || ''
));
const isWebsiteOrder = computed(() => props.order?.lead_source === 'site');
const isB2cCustomer = buildIsB2cCustomer(computed(() => props.order));
const displayOrderTitle = computed(() => (
  orderTitle.value.trim()
  || customer.value?.full_legal_name
  || customer.value?.name
  || 'Без названия'
));
const {
  closeDrawer,
  copyText,
  deleteOrder,
  toggleHold,
} = useOrderDrawerActions({
  order: computed(() => props.order),
  displayOrderTitle,
  hasUnsavedChanges,
  localFormError,
  persistDraft,
  clearDraft,
  setToast,
  onBeforeClose: () => {
    pendingDraftClearOrderId.value = null;
  },
  onModelValue: (open) => emit('update:modelValue', open),
  onUpdated: (updatedOrder) => emit('updated', updatedOrder),
  onDeleted: (orderId) => emit('deleted', orderId),
});
const compactObjectAddress = computed(() => (
  customerDeliveryAddress.value.trim()
  || props.order?.customer_branch?.delivery_address
  || ''
));
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

const initForm = async (order: ManagerOrderDetailResponse | null) => {
  if (!order) return;
  localServerErrors.value = {};
  localFormError.value = '';
  if (initializedOrderId.value !== order.id) {
    initializedOrderId.value = order.id;
    expandedDrawerSections.value = restoreDrawerSections();
    linkedEquipmentOptions.value = [];
    resetWorkspaceNavigation();
    resetOrderEmails();
  }
  hydrateOrder(order);

  const selectedProposal = (order.proposals || []).find((proposal) => proposal.is_selected && !proposal.is_archived)
    || (order.proposals || []).find((proposal) => !proposal.is_archived)
    || null;
  loadProposalLines(selectedProposal, order);
  if (pendingDraftClearOrderId.value === order.id) {
    clearDraft();
    pendingDraftClearOrderId.value = null;
  }
  savedLinesSnapshot.value = buildCurrentLinesSnapshot(activeProposalId.value);
  showEstimateImport.value = false;
  await loadEstimateOptions();

  resetLookupState();
  savedFormSnapshot.value = buildCurrentFormSnapshot(proposalStatus.value);
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

const handleSave = () => {
  if (!props.order) return;
  const payload = buildSavePayload(activeProposalLocked.value);
  if (!payload) return;
  pendingDraftClearOrderId.value = props.order.id;
  emit('save', { orderId: props.order.id, data: payload });
};
const getFieldError = (field: string): string => localServerErrors.value[field] || props.serverErrors?.[field] || '';
const displayFormError = computed(() => localFormError.value || props.formError || '');
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
