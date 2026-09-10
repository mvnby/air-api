<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue';
import DealExecutionTab from './DealExecutionTab.vue';
import OrderAttachmentsPanel from '../service-attachments/OrderAttachmentsPanel.vue';
import OrderEquipmentPanel from '../equipment/OrderEquipmentPanel.vue';
import OrderWorkspaceHeader from './OrderWorkspaceHeader.vue';
import OrderSalesInstallationWorkspace from './OrderSalesInstallationWorkspace.vue';
import OrderPaymentsPanel from './OrderPaymentsPanel.vue';
import OrderWebsiteIntakePanel from './OrderWebsiteIntakePanel.vue';
import OrderPlanningPanel from './OrderPlanningPanel.vue';
import OrderRepairPanel from './OrderRepairPanel.vue';
import OrderCustomerContext from './OrderCustomerContext.vue';
import OrderExecutionPanel from './OrderExecutionPanel.vue';
import OrderDocumentsWorkspace from './OrderDocumentsWorkspace.vue';
import OrderManagerLabels from './OrderManagerLabels.vue';
import OrderProposalWorkspace from './OrderProposalWorkspace.vue';
import OrderWorkspaceNav from './OrderWorkspaceNav.vue';
import OrderWorkspaceContext from './OrderWorkspaceContext.vue';
import OrderWorkspaceUsageReport from './OrderWorkspaceUsageReport.vue';
import type { ServiceAttachmentEquipmentOption } from '../service-attachments/types';
import type {
  ManagerOrderDetailResponse,
} from '../../client';
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
import { useOrderDrawerSaving } from '../../composables/useOrderDrawerSaving';
import { useOrderDrawerActions } from '../../composables/useOrderDrawerActions';
import { useDrawerFocusTrap } from '../../composables/useDrawerFocusTrap';
import { useOrderWorkspaceUsage } from '../../composables/useOrderWorkspaceUsage';
import { useOrderWorkspaceUsageControls } from '../../composables/useOrderWorkspaceUsageControls';
import { useOrderCatalogNavigation } from '../../composables/useOrderCatalogNavigation';

const props = defineProps<{
  modelValue: boolean;
  order: ManagerOrderDetailResponse | null;
  serverErrors?: Record<string, string>;
  formError?: string;
}>();

const emit = defineEmits<{
  'update:modelValue': [value: boolean];
  updated: [order: ManagerOrderDetailResponse];
  deleted: [orderId: number];
  reload: [orderId: number];
}>();

const drawerScrollContainer = ref<HTMLElement | null>(null);
const { captureFocus, focusContainer, restoreFocus, trapFocus } = useDrawerFocusTrap(drawerScrollContainer);
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

const initializing = ref(false);
const savedLinesSnapshot = ref('');
const savedFormSnapshot = ref('');
const commercialEditor = useOrderCommercialEditor({
  order: computed(() => props.order),
  setToast,
  persistDraft: () => persistDraft(),
});
const {
  activeServiceSuggestionIndex,
  applyTariffTemplateToLine,
  buildLinesPayload,
  currentLinesSnapshot: buildCurrentLinesSnapshot,
  loadLines,
  loadOrderSupplyRequests,
  margin: marginPreview,
  productLines,
  resetLookupState,
  serviceLines,
  serviceTariffOptions,
  showEstimateImport,
  syncProductLookupFromLines,
  total: totalPreview,
  validateLines: validateProposalLines,
} = commercialEditor;
const {
  assessmentDate,
  autoCloseOnPayment,
  autoExecutionOnPayment,
  balanceDue: balanceDuePreview,
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
  managerLabels,
  measurementRequired,
  measurementResult,
  measurerId,
  negotiationStatus,
  newBranchAddress,
  orderTitle,
  payments,
  repairMeta,
  setWorkflowType,
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
const proposalWorkspaceRef = ref<InstanceType<typeof OrderProposalWorkspace> | null>(null);

const proposalLifecycle = useOrderProposalLifecycle({
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
  saveOrder: async () => {
    if (!await orderSaving.flush()) throw new Error(localFormError.value || 'Заказ не сохранён');
    return props.order;
  },
  onLoaded: () => {
    savedLinesSnapshot.value = buildCurrentLinesSnapshot(activeProposalId.value);
  },
});
const {
  activeProposal,
  activeProposalId,
  activeProposalLocked,
  changeActiveProposalStatus,
  createProposal,
  duplicateProposal,
  loadProposalLines,
  proposalActionLoading,
  proposalStatus,
  selectedProposal: selectedOrderProposal,
} = proposalLifecycle;

const {
  clearDraft,
  expandedDrawerSections,
  hasUnsavedChanges,
  initializedOrderId,
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

const orderSaving = useOrderDrawerSaving({
  order: computed(() => props.order),
  ready: computed(() => props.modelValue && !initializing.value && Boolean(props.order)),
  activeProposalId,
  activeProposalLocked,
  productLines,
  currentFormSnapshot: () => buildCurrentFormSnapshot(),
  currentLinesSnapshot: () => buildCurrentLinesSnapshot(activeProposalId.value),
  savedFormSnapshot,
  savedLinesSnapshot,
  hasUnsavedChanges,
  buildSavePayload,
  hydrateOrder,
  localFormError,
  localServerErrors,
  clearDraft,
  onUpdated: (order) => emit('updated', order),
});
const { enabled: autosaveEnabled, saving, failed: saveFailed, statusText: saveStatusText } = orderSaving;
const catalogNavigation = useOrderCatalogNavigation({
  orderId: computed(() => props.order?.id), proposalId: activeProposalId, status,
  locked: activeProposalLocked,
  busy: computed(() => initializing.value || proposalActionLoading.value),
  flush: orderSaving.flush,
  close: () => emit('update:modelValue', false),
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
  activeWorkspaceSection,
  executionWorkspaceOpen,
  openDocumentsSend,
  openProposalSend: openProposalDocuments,
  openWorkspaceTarget,
  resetWorkspaceNavigation,
  selectWorkspaceSection,
} = useOrderWorkspaceNavigation({
  status,
  workflowType,
  expandedSections: expandedDrawerSections,
  equipmentPanelRef,
  documentsWorkspaceRef,
  setToast,
});
const documentsMounted = ref(false);
watch(activeWorkspaceSection, (section) => {
  if (section === 'documents') documentsMounted.value = true;
}, { immediate: true });
const openProposalSend = async () => {
  if (await orderSaving.beforeDocumentGenerate()) openProposalDocuments(activeProposal.value, orderDocuments.value);
};

const customer = computed(() => props.order?.customer ?? null);
const orderWorkspaceUsage = useOrderWorkspaceUsage({
  open: computed(() => props.modelValue),
  ready: computed(() => props.modelValue && !initializing.value && Boolean(props.order) && initializedOrderId.value === props.order?.id),
  orderKey: computed(() => props.order?.id ?? null),
  workflow: workflowType,
  customer,
});
const usageReportOpen = ref(false);
const { trackControl: trackUsageControl } = useOrderWorkspaceUsageControls(orderWorkspaceUsage.track);
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
  beforeClose: async () => !proposalActionLoading.value && await orderSaving.beforeClose(),
  onBeforeClose: orderSaving.cancelScheduled,
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
const beforeDocumentGenerate = orderSaving.beforeDocumentGenerate;

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
  initializing.value = true;
  localServerErrors.value = {};
  localFormError.value = '';
  if (initializedOrderId.value !== order.id) {
    initializedOrderId.value = order.id;
    expandedDrawerSections.value = restoreDrawerSections();
    selectWorkspaceSection('proposal');
    linkedEquipmentOptions.value = [];
    resetWorkspaceNavigation();
    resetOrderEmails();
  }
  hydrateOrder(order);

  const params = new URLSearchParams(window.location.search);
  const returnProposalId = Number(params.get('orderId')) === order.id ? Number(params.get('proposalId')) : null;
  const selectedProposal = (order.proposals || []).find((proposal) => proposal.id === (activeProposalId.value || returnProposalId) && !proposal.is_archived)
    || (order.proposals || []).find((proposal) => proposal.is_selected && !proposal.is_archived)
    || (order.proposals || []).find((proposal) => !proposal.is_archived)
    || null;
  loadProposalLines(selectedProposal, order);
  orderSaving.resetBaseline();
  showEstimateImport.value = false;
  resetLookupState();
  restoreDraft();
  syncProductLookupFromLines();
  await nextTick();
  initializing.value = false;
  await Promise.all([
    loadOrderSupplyRequests(order.id),
    loadOrderEmails(order.id),
  ]);
};

watch(
  [() => props.modelValue, () => props.order],
  async ([open, order], [wasOpen, previousOrder]) => {
    if (!open) {
      usageReportOpen.value = false;
      if (wasOpen) {
        await nextTick();
        restoreFocus();
      }
      return;
    }
    if (!order) return;
    if (!wasOpen || order.id !== previousOrder?.id) {
      captureFocus();
      await initForm(order);
      await nextTick();
      resetWorkspaceHeader();
      focusContainer();
    } else if (!orderSaving.isOwnResponse(order) && !saving.value && !hasUnsavedChanges.value) {
      await initForm(order);
    } else {
      payments.value = [...(order.payments || [])];
    }
  },
);

const openProposalForProduct = async () => {
  selectWorkspaceSection('proposal');
  await nextTick();
  proposalWorkspaceRef.value?.addProduct();
  document.getElementById('order-workspace-proposal')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
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
    proposalWorkspaceRef.value?.openResponse();
    return;
  }
  if (action.command === 'create_proposal_variant') return duplicateProposal();
  openWorkspaceTarget(action.target);
};

const handleSave = () => orderSaving.flush();
const getFieldError = (field: string): string => localServerErrors.value[field] || props.serverErrors?.[field] || '';
const displayFormError = computed(() => localFormError.value || props.formError || '');
const discardUnsavedChanges = async () => {
  if (!props.order) return;
  orderSaving.cancelScheduled();
  clearDraft();
  await initForm(props.order);
  setToast('Изменения отменены', 'success');
};

const handleCustomerUpdated = async (updatedOrder: ManagerOrderDetailResponse) => {
  emit('updated', updatedOrder);
};

</script>

<template>
  <div v-if="modelValue" class="fixed inset-0 z-50 flex">
    <Transition name="fade">
      <div v-if="toast" class="fixed top-6 right-6 z-[100] bg-teal-600 text-white px-6 py-3 rounded-xl shadow-2xl font-medium">
        {{ toast }}
      </div>
    </Transition>
    <div class="flex-1 bg-black/60" aria-hidden="true" @click="closeDrawer" />
    <aside ref="drawerScrollContainer" tabindex="-1" role="dialog" aria-modal="true" aria-label="Рабочая область заказа" class="relative h-full w-full min-w-0 overflow-y-auto bg-white text-gray-900 shadow-2xl outline-none dark:bg-slate-950 dark:text-slate-100 md:my-4 md:h-[calc(100%-2rem)] md:w-[calc(100%-2rem)] md:rounded-2xl xl:max-w-[1680px] xl:border xl:border-gray-200 dark:xl:border-slate-700" @keydown="trapFocus" @keydown.esc.stop="closeDrawer" @click="trackUsageControl" @change="trackUsageControl">
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
        :autosave-enabled="autosaveEnabled"
        :save-failed="saveFailed"
        :save-status-text="saveStatusText"
        @toggle-autosave="orderSaving.toggle"
        :compact="compactWorkspaceHeader"
        @update:title="orderTitle = $event"
        @change-workflow="setWorkflowType"
        @next="handleWorkspaceNextAction"
        @payments="openWorkspaceTarget('payments')"
        @hold="toggleHold"
        @delete="deleteOrder"
        @discard="discardUnsavedChanges"
        @save="handleSave"
        :usage-enabled="orderWorkspaceUsage.enabled.value"
        :can-view-usage-report="orderWorkspaceUsage.canViewReport.value"
        @usage-toggle="orderWorkspaceUsage.toggle"
        @usage-report="usageReportOpen = true"
        @close="closeDrawer"
      />

      <OrderWorkspaceUsageReport :open="usageReportOpen" @close="usageReportOpen = false" />

      <div class="grid gap-4 p-4 sm:p-6 lg:grid-cols-[minmax(0,1fr)_18rem] lg:gap-6">
        <div class="min-w-0">
          <OrderWorkspaceNav
            :active="activeWorkspaceSection"
            :workflow="workflowType"
            @select="selectWorkspaceSection"
            @add-product="openProposalForProduct"
          />
          <p v-if="displayFormError" class="mt-4 rounded-xl border border-red-500/40 bg-red-50 px-3 py-2 text-sm text-red-700">
            {{ displayFormError }}
          </p>
          <fieldset :disabled="proposalActionLoading" class="min-w-0">
            <section v-show="activeWorkspaceSection === 'proposal'" class="min-w-0" data-order-usage="workspace-proposal-panel">
              <OrderManagerLabels v-model="managerLabels" />
              <OrderProposalWorkspace
                ref="proposalWorkspaceRef"
                v-model:expanded="expandedDrawerSections.proposals"
                :commercial="commercialEditor"
                :proposal="proposalLifecycle"
                :title="isRepairWorkflow ? 'Смета ремонта' : 'Предложения'"
                :show-product-lines="true"
                :products-error="getFieldError('products')"
                :services-error="getFieldError('services')"
                :format-service-kind="formatServiceKind"
                :catalog-available="catalogNavigation.available.value"
                :catalog-opening="catalogNavigation.opening.value"
                :catalog-needs-save="hasUnsavedChanges"
                @catalog="catalogNavigation.open"
                @send="openProposalSend"
              />
            </section>

            <section v-if="documentsMounted" v-show="activeWorkspaceSection === 'documents'" class="min-w-0" data-order-usage="workspace-documents-panel">
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
            </section>

            <section v-show="activeWorkspaceSection === 'work'" class="min-w-0" data-order-usage="workspace-work-panel">
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
                :before-navigate="closeDrawer"
                @toast="setToast($event.message, $event.type)"
                @updated="handleCustomerUpdated"
                @reload="emit('reload', $event)"
              />
              <OrderSalesInstallationWorkspace
                v-if="workflowType === 'sales_installation'"
                class="mt-4"
                :lanes="orderWorkspace.lanes"
                :active-target="activeWorkspaceTarget"
                @open="openWorkspaceTarget($event, true)"
              />
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
              <OrderAttachmentsPanel v-if="order" :key="`order-attachments-${order.id}`" class="mt-4" :order-id="order.id" :initial-count="order.attachment_count" :equipment-options="linkedEquipmentOptions" @need-equipment-options="equipmentPanelRef?.ensureLoaded()" @error="setToast($event, 'error')" />
              <OrderWebsiteIntakePanel v-if="isWebsiteOrder" v-model:expanded="expandedDrawerSections.website" :order="order!" :delivery-address="customerDeliveryAddress" :comment="comment" @copy="copyText($event.value, $event.label)" />
              <OrderPlanningPanel
                v-if="status === 'negotiation'"
                v-model:measurement-required="measurementRequired" v-model:assessment-date="assessmentDate" v-model:negotiation-status="negotiationStatus" v-model:auto-execution-on-payment="autoExecutionOnPayment" v-model:details-expanded="expandedDrawerSections.planningDetails" v-model:measurer-id="measurerId" v-model:measurement-result="measurementResult" v-model:installation-date="installationDate" v-model:installer-id="installerId"
                :workflow-type="workflowType" :executor-options="executorOptions" :customer-branch-id="customerBranchId" :new-branch-address="newBranchAddress" :measurement-error="getFieldError('measurement_date')" :installation-error="getFieldError('installation_date')"
              />
              <OrderRepairPanel v-if="isRepairWorkflow && order" v-model:expanded="expandedDrawerSections.repair" v-model:repair-meta="repairMeta" :order="order" :order-title="orderTitle" :measurement-result="measurementResult" :customer-branch-id="customerBranchId" :object-address="compactObjectAddress" @toast="setToast($event.message, $event.type)" @reload="emit('reload', $event)" />
              <OrderExecutionPanel v-if="status === 'execution'" v-model:expanded="expandedDrawerSections.execution" v-model:execution-status="executionStatus" v-model:execution-without-payment="executionWithoutPayment" v-model:execution-without-payment-reason="executionWithoutPaymentReason" v-model:auto-close-on-payment="autoCloseOnPayment" :workflow-type="workflowType" />
            </section>

            <section v-show="activeWorkspaceSection === 'payments'" class="min-w-0" data-order-usage="workspace-payments-panel">
              <OrderPaymentsPanel
                v-if="order && status !== 'execution'"
                v-model:expanded="expandedDrawerSections.payments" v-model:payments="payments" v-model:enable-currency="enableCurrency" v-model:target-currency="targetCurrency" v-model:target-currency-amount="targetCurrencyAmount"
                :order="order" :current-fx-rate="currentFxRate" :is-b2c-customer="isB2cCustomer" :total="totalPreview" :total-payments="totalPaymentsPreview" :balance-due="balanceDuePreview" :margin="marginPreview" :calculated-target-currency-payments="calculatedTargetCurrencyPayments" :target-currency-balance-due="targetCurrencyBalanceDue"
                @toast="setToast($event.message, $event.type)" @reload="emit('reload', $event)"
              />
              <DealExecutionTab v-if="status === 'execution' && order && executionWorkspaceOpen" id="order-workspace-execution-details" :order="order" class="mt-4" @refresh="emit('reload', order.id)" @close="closeDrawer" />
            </section>
          </fieldset>
        </div>
        <OrderWorkspaceContext class="order-first lg:order-none" :customer-name="customerDisplayName" :address="compactObjectAddress" :total="totalPreview" :paid="totalPaymentsPreview" :balance="balanceDuePreview" @object="openWorkspaceTarget('object')" @payments="openWorkspaceTarget('payments')" />
      </div>
    </aside>

  </div>
</template>
