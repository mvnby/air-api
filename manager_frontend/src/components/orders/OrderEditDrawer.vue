<script setup lang="ts">
import { readOrderProposalContext } from '../../services/order-navigation';
import { replaceManagerLocation } from '../../services/manager-navigation-history';
import { computed, defineAsyncComponent, nextTick, onScopeDispose, ref, toRaw, watch } from 'vue';
import OrderResponsiblePanel from './OrderResponsiblePanel.vue';
import { useOrderResponsibility } from '../../composables/useOrderResponsibility';
import type { OrderWithResponsibility } from '../../services/order-responsibility';
import type OrderEquipmentPanel from '../equipment/OrderEquipmentPanel.vue';
import OrderWorkspaceHeader from './OrderWorkspaceHeader.vue';
import TenderWorkflowPanel from './TenderWorkflowPanel.vue';
import OrderCustomerContext from './OrderCustomerContext.vue';
import LeadSourceReviewModal from '../leads/LeadSourceReviewModal.vue';
import OrderRequestSourceCard from './OrderRequestSourceCard.vue';
import OrderSourceEquipmentAction from './OrderSourceEquipmentAction.vue';
import { sourceEquipmentPrefillMessage, type SourceAppliedEvent } from '../../services/order-source-review';
import type OrderDocumentsWorkspace from './OrderDocumentsWorkspace.vue';
import OrderAsyncPanel from './OrderAsyncPanel.vue';
import { loadProposalWorkspace, loadDocumentsWorkspace, loadWorkWorkspace, loadPaymentsWorkspace } from './order-workspace-loaders';
import type { OrderWorkspaceSection } from './OrderWorkspaceNav.vue';
import OrderManagerLabels from './OrderManagerLabels.vue';
import type OrderProposalWorkspace from './OrderProposalWorkspace.vue';
import OrderProposalTotalsBar from './OrderProposalTotalsBar.vue';
import { useDemoReadOnly } from '../../services/manager-demo';
import OrderWorkspaceNav from './OrderWorkspaceNav.vue';
import OrderWorkspaceUsageReport from './OrderWorkspaceUsageReport.vue';
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
import OrderDraftRecovery from './OrderDraftRecovery.vue';
import { useOrderDrawerPersistence } from '../../composables/useOrderDrawerPersistence';
import { useOrderDocumentStatus } from '../../composables/useOrderDocumentStatus';
import { useOrderWorkspaceNavigation } from '../../composables/useOrderWorkspaceNavigation';
import { useOrderDrawerSaving } from '../../composables/useOrderDrawerSaving';
import { useOrderDrawerActions } from '../../composables/useOrderDrawerActions';
import { useDrawerFocusTrap } from '../../composables/useDrawerFocusTrap';
import { useDocumentScrollLock } from '../../composables/useDocumentScrollLock';
import { useOrderWorkspaceUsage } from '../../composables/useOrderWorkspaceUsage';
import { useOrderWorkspaceUsageControls } from '../../composables/useOrderWorkspaceUsageControls';
import { useOrderCatalogNavigation } from '../../composables/useOrderCatalogNavigation';
import { useOrderInstallationAttachment } from '../../composables/useOrderInstallationAttachment';
import { useOrderSourceCommand } from '../../composables/useOrderSourceCommand';

const props = defineProps<{
  modelValue: boolean;
  presentation?: 'page' | 'dialog';
  backLabel?: string;
  order: OrderWithResponsibility | null;
  serverErrors?: Record<string, string>;
  formError?: string;
}>();

const emit = defineEmits<{
  'update:modelValue': [value: boolean];
  back: [];
  updated: [order: ManagerOrderDetailResponse];
  deleted: [orderId: number];
  reload: [orderId: number];
}>();

const drawerScrollContainer = ref<HTMLElement | null>(null);
const workspaceScrollContainer = ref<HTMLElement | null>(null);
const proposalClientPreview = ref(false);
const proposalPanelRef = ref<InstanceType<typeof OrderAsyncPanel> | null>(null);
const documentsPanelRef = ref<InstanceType<typeof OrderAsyncPanel> | null>(null);
const workPanelRef = ref<InstanceType<typeof OrderAsyncPanel> | null>(null);
const paymentsPanelRef = ref<InstanceType<typeof OrderAsyncPanel> | null>(null);
const ensureSection = async (section: OrderWorkspaceSection) => {
  await nextTick();
  await ({proposal: proposalPanelRef, documents: documentsPanelRef, work: workPanelRef, payments: paymentsPanelRef}[section].value?.ready());
};
const showProposalCosts = ref(false);
const mobileContextOpen = ref(false);
const demoReadOnly = useDemoReadOnly();
const isPage = computed(() => props.presentation === 'page');
useDocumentScrollLock(() => props.modelValue && !isPage.value);
const { captureFocus, focusContainer, restoreFocus, trapFocus } = useDrawerFocusTrap(drawerScrollContainer);
const { compact: compactWorkspaceHeader, reset: resetWorkspaceHeader } = useSmartStickyHeader(workspaceScrollContainer);
watch(() => [props.order?.id, props.modelValue], () => {
  proposalClientPreview.value = false;
  showProposalCosts.value = false;
  mobileContextOpen.value = false;
});

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
const drawerForm = useOrderDrawerForm({
  total: totalPreview, productLines, serviceLines, serviceTariffOptions, activeServiceSuggestionIndex,
  applyTariffTemplateToLine, buildLinesPayload: () => buildLinesPayload(activeProposalId.value),
  validateLines: validateProposalLines, setToast, loadExecutorsOnHydrate: false,
});
const {
  autoExecutionOnPayment,
  balanceDue: balanceDuePreview,
  buildSavePayload,
  comment,
  currentFormSnapshot: buildCurrentFormSnapshot,
  customerBranchId,
  customerDeliveryAddress,
  executionStatus,
  hydrateOrder,
  installationDate,
  isRepairWorkflow,
  localFormError,
  localServerErrors,
  managerLabels,
  negotiationStatus,
  orderTitle,
  payments,
  setWorkflowType,
  status,
  totalPayments: totalPaymentsPreview,
  workflowType,
} = drawerForm;
const workerAssignmentBusy = ref(false), workerPayBusy = ref(false), workerPayRevision = ref(0);
const setWorkerAssignmentBusy = (value: boolean) => { if (workerAssignmentBusy.value && !value) workerPayRevision.value++; workerAssignmentBusy.value = value; };
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
    if (!initializing.value) {
      orderSaving.resetBaseline();
      restoreDraft();
      syncProductLookupFromLines();
    }
  },
});
const {
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
  draftConflicts, draftBlocked, resolveDraftConflict,
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
  restoreFormDraft: drawerForm.restoreFormDraft,
  ready: computed(() => !initializing.value),
});

const {
  busy: installationAttaching,
  autosavePaused: installationAutosavePaused,
  begin: beginInstallationAttach,
  after: refreshAfterInstallationAttach,
  end: endInstallationAttach,
} = useOrderInstallationAttachment({
  order: computed(() => props.order), open: computed(() => props.modelValue), proposalId: activeProposalId,
  serviceLines, dirty: hasUnsavedChanges,
  flush: () => orderSaving.flush(), clearDraft,
  onUpdated: (updated) => emit('updated', updated),
});

const responsibilityResponses = new WeakSet<object>();
const { busy: responsibilityBusy, paused: responsibilityPaused, error: responsibilityError, canAssign: canAssignResponsible, assign: assignResponsible } = useOrderResponsibility({
  order: computed(() => props.order), open: computed(() => props.modelValue),
  otherBusy: computed(() => installationAttaching.value || sourceApplying.value || proposalActionLoading.value || initializing.value),
  flush: () => orderSaving.flush(),
  onUpdated: fresh => {
    if (!props.order || props.order.id !== fresh.id) return;
    // Assignment returns a full order, but only its own fields may replace local draft state.
    const updated: OrderWithResponsibility = { ...props.order, responsible_person: fresh.responsible_person, responsible_version: fresh.responsible_version, updated_at: fresh.updated_at };
    responsibilityResponses.add(toRaw(updated)); emit('updated', updated);
  },
});

const {
  busy: sourceApplying, before: beforeSourceCommand,
  after: refreshAfterSourceCommand, end: endSourceCommand,
} = useOrderSourceCommand({
  order: computed(() => props.order), open: computed(() => props.modelValue),
  proposalId: activeProposalId, otherCommandBusy: computed(() => installationAttaching.value || responsibilityBusy.value),
  flush: () => orderSaving.flush(), clearDraft,
  onUpdated: (updated) => emit('updated', updated),
});
const orderSaving = useOrderDrawerSaving({
  blocked: draftBlocked,
  order: computed(() => props.order),
  ready: computed(() => props.modelValue && !initializing.value && !installationAutosavePaused.value && !sourceApplying.value && !responsibilityPaused.value && Boolean(props.order)),
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
  loadManagedDocuments,
  managedDocuments,
  missingReferencedInvoice,
  orderDocuments,
  resetOrderEmails,
  sentDocumentTypes,
} = useOrderDocumentStatus({
  order: computed(() => props.order),
  payments,
});

const workspaceNavigation = useOrderWorkspaceNavigation({
  status, workflowType, expandedSections: expandedDrawerSections, equipmentPanelRef, documentsWorkspaceRef,
  syncLocation: isPage, orderId: computed(() => props.order?.id),
  ensureSection,
});
const {
  activeWorkspaceSection,
  executionWorkspaceOpen,
  openWorkspaceTarget,
  resetWorkspaceNavigation,
  selectWorkspaceSection,
} = workspaceNavigation;
const proposalMounted = ref(false);
const documentsMounted = ref(false);
const workMounted = ref(false);
const paymentsMounted = ref(false);
const contextMounted = ref(false);
const setEquipmentPanel = (panel: InstanceType<typeof OrderEquipmentPanel> | null) => { equipmentPanelRef.value = panel; };
watch(mobileContextOpen, open => { if (open) contextMounted.value = true; });
const customerContextTarget = ref<'customer' | 'object' | null>(null);
const customerContextRef = ref<InstanceType<typeof OrderCustomerContext> | null>(null);
const sourceReviewOpen = ref(false);
const openSourceReview = async () => {
  const orderId = props.order?.id;
  if (!await orderSaving.flush() || !props.modelValue || props.order?.id !== orderId) return;
  sourceReviewOpen.value = true;
};
const handleSourceApplied = (result: SourceAppliedEvent) => {
  sourceReviewOpen.value = false;
  setToast(sourceEquipmentPrefillMessage(result.equipmentPrefill) || 'Данные из источника применены');
};
watch(activeWorkspaceSection, (section) => {
  if (section !== 'proposal') proposalClientPreview.value = false;
  if (section === 'proposal') proposalMounted.value = true;
  if (section === 'documents') documentsMounted.value = true;
  if (section === 'work') { workMounted.value = true; void drawerForm.loadExecutors(); }
  if (section === 'payments') paymentsMounted.value = true;
}, { immediate: true });
watch(activeProposalId, (proposalId) => {
  proposalClientPreview.value = false;
  if (!isPage.value || !proposalId || readOrderProposalContext(window.location.href).orderId !== props.order?.id) return;
  const url = new URL(window.location.href);
  url.searchParams.set('proposalId', String(proposalId));
  replaceManagerLocation(`${url.pathname}${url.search}`);
}, { flush: 'sync' });
const EnvelopePrintDialog = defineAsyncComponent(() => import('../envelopes/EnvelopePrintDialog.vue'));
const showEnvelope = ref(false);
const customer = computed(() => props.order?.customer ?? null);
const customerDisplayName = computed(() => customer.value?.full_legal_name || customer.value?.name || '');
const compactObjectAddress = computed(() => customerDeliveryAddress.value.trim() || props.order?.customer_branch?.delivery_address || '');
const orderWorkspaceUsage = useOrderWorkspaceUsage({
  open: computed(() => props.modelValue),
  ready: computed(() => props.modelValue && !initializing.value && Boolean(props.order) && initializedOrderId.value === props.order?.id),
  orderKey: computed(() => props.order?.id ?? null),
  workflow: workflowType,
  customer,
});
const usageReportOpen = ref(false);
const { trackControl: trackUsageControl } = useOrderWorkspaceUsageControls(orderWorkspaceUsage.track);
const isWebsiteOrder = computed(() => props.order?.lead_source === 'site');
const displayOrderTitle = computed(() => (
  orderTitle.value.trim()
  || customer.value?.full_legal_name
  || customer.value?.name
  || 'Без названия'
));
const {
  prepareToLeave,
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
  beforeClose: async () => !proposalActionLoading.value && !sourceApplying.value && !responsibilityBusy.value && !workerAssignmentBusy.value && !workerPayBusy.value
    && await (customerContextRef.value?.beforeClose?.() ?? true) && await orderSaving.beforeClose(),
  onBeforeClose: orderSaving.cancelScheduled,
  onModelValue: (open) => emit('update:modelValue', open),
  onUpdated: (updatedOrder) => emit('updated', updatedOrder),
  onDeleted: (orderId) => emit('deleted', orderId),
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
  managedDocuments: managedDocuments.value,
  documentEmailStatus: documentEmailStatus.value,
  sentDocumentTypes: sentDocumentTypes.value,
  missingReferencedInvoice: missingReferencedInvoice.value,
  total: totalPreview.value,
  paid: totalPaymentsPreview.value,
  balance: balanceDuePreview.value,
}));
const beforeDocumentGenerate = orderSaving.beforeDocumentGenerate;

let documentRefreshGeneration = 0;
const documentRefreshTimers = new Set<number>();
const invalidateDocumentRefresh = () => {
  documentRefreshGeneration += 1;
  for (const timer of documentRefreshTimers) window.clearTimeout(timer);
  documentRefreshTimers.clear();
};
watch(() => [props.order?.id, props.modelValue], invalidateDocumentRefresh, { flush: 'sync' });
onScopeDispose(invalidateDocumentRefresh);

const handleDocumentPanelToast = (payload: { message: string; type?: 'success' | 'error' }) => {
  setToast(payload.message, payload.type || 'success');
  const orderId = props.order?.id;
  if (!orderId || !props.modelValue) return;
  const generation = documentRefreshGeneration;
  const timer = window.setTimeout(() => {
    documentRefreshTimers.delete(timer);
    if (generation !== documentRefreshGeneration || !props.modelValue || props.order?.id !== orderId) return;
    void loadOrderEmails(orderId);
    void loadManagedDocuments(orderId);
  }, 500);
  documentRefreshTimers.add(timer);
};

const refreshOrderFromDocumentsPanel = () => {
  if (props.order?.id) {
    emit('reload', props.order.id);
    void loadOrderEmails(props.order.id);
    void loadManagedDocuments(props.order.id);
  }
};

const initForm = async (order: ManagerOrderDetailResponse | null) => {
  if (!order) return;
  initializing.value = true;
  localServerErrors.value = {};
  localFormError.value = '';
  const newOrder = initializedOrderId.value !== order.id;
  if (newOrder) {
    showEnvelope.value = false;
    customerContextTarget.value = null;
    initializedOrderId.value = order.id;
    expandedDrawerSections.value = restoreDrawerSections();
    proposalMounted.value = false; documentsMounted.value = false; workMounted.value = false; paymentsMounted.value = false; contextMounted.value = false;
    resetOrderEmails();
  }
  hydrateOrder(order);
  if (newOrder) {
    resetWorkspaceNavigation();
    if (activeWorkspaceSection.value === 'proposal') proposalMounted.value = true;
    if (activeWorkspaceSection.value === 'documents') documentsMounted.value = true;
    if (activeWorkspaceSection.value === 'work') { workMounted.value = true; void drawerForm.loadExecutors(); }
    if (activeWorkspaceSection.value === 'payments') paymentsMounted.value = true;
  }

  const context = readOrderProposalContext(window.location.href);
  const returnProposalId = context.orderId === order.id ? context.proposalId : null;
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
    loadManagedDocuments(order.id),
  ]);
};

watch(
  [() => props.modelValue, () => props.order],
  async ([open, order], [wasOpen, previousOrder]) => {
    if (!open) {
      usageReportOpen.value = false;
      if (wasOpen && !isPage.value) {
        await nextTick();
        restoreFocus();
      }
      return;
    }
    if (!order) return;
    if (wasOpen && previousOrder?.id === order.id && responsibilityResponses.has(toRaw(order))) return;
    if (!wasOpen || order.id !== previousOrder?.id) {
      if (!isPage.value) captureFocus();
      await initForm(order);
      await nextTick();
      resetWorkspaceHeader();
      focusContainer();
    } else if (!orderSaving.isOwnResponse(order) && !saving.value && (!hasUnsavedChanges.value || draftBlocked.value)) {
      await initForm(order);
    } else {
      payments.value = [...(order.payments || [])];
    }
  },
);

const openProposalForProduct = async () => {
  selectWorkspaceSection('proposal');
  await ensureSection('proposal');
  proposalWorkspaceRef.value?.addProduct();
  document.getElementById('order-workspace-proposal')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
};

const handleWorkspaceNextAction = async () => {
  const action = orderWorkspace.value.nextAction;
  if (action.command === 'create_proposal') return createProposal();
  if (action.command === 'finish_proposal') return changeActiveProposalStatus('ready_to_send');
  if (action.command === 'record_proposal_response') {
    await openWorkspaceTarget('proposal');
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
  if (updatedOrder.id !== props.order?.id) return;
  emit('updated', updatedOrder);
};
const saveContextObject = async (draft: { address: string; branchId: number | null; comment: string }) => {
  const orderId = props.order?.id;
  const customerId = props.order?.customer?.id;
  if (!await orderSaving.flush() || props.order?.id !== orderId || props.order?.customer?.id !== customerId) return false;
  const previous = { address: customerDeliveryAddress.value, branchId: customerBranchId.value, comment: comment.value };
  orderSaving.cancelScheduled();
  customerDeliveryAddress.value = draft.address;
  customerBranchId.value = draft.branchId;
  comment.value = draft.comment;
  await nextTick();
  const saved = await orderSaving.flush();
  if (!saved && props.order?.id === orderId && props.order?.customer?.id === customerId) {
    // Keep a failed object edit inside its editor; other order edits stay intact.
    if (customerDeliveryAddress.value === draft.address) customerDeliveryAddress.value = previous.address;
    if (customerBranchId.value === draft.branchId) customerBranchId.value = previous.branchId;
    if (comment.value === draft.comment) comment.value = previous.comment;
    await nextTick();
  }
  return saved;
};

defineExpose({ prepareToLeave });
</script>

<template>
  <div v-if="modelValue" :class="isPage ? 'order-page-workspace flex w-full min-w-0 overflow-hidden' : 'fixed inset-0 z-50 flex h-dvh w-screen overflow-hidden'">
    <Transition name="fade">
      <div v-if="toast" class="fixed top-6 right-6 z-[100] bg-brand-600 text-white px-6 py-3 rounded-xl shadow-2xl font-medium">
        {{ toast }}
      </div>
    </Transition>
    <div v-if="!isPage" class="flex-1 bg-black/60" aria-hidden="true" @click="closeDrawer" />
    <aside ref="drawerScrollContainer" tabindex="-1" :role="isPage ? 'region' : 'dialog'" :aria-modal="isPage ? undefined : true" aria-label="Рабочая область заказа" :inert="installationAttaching || sourceApplying || responsibilityBusy || workerAssignmentBusy || workerPayBusy ? true : undefined" :aria-busy="installationAttaching || sourceApplying || responsibilityBusy || workerAssignmentBusy || workerPayBusy" class="relative flex h-full w-full min-w-0 flex-col overflow-hidden bg-white text-gray-900 outline-none dark:bg-slate-950 dark:text-slate-100" :class="isPage ? '' : 'shadow-2xl md:my-4 md:h-[calc(100%-2rem)] md:w-[calc(100%-2rem)] md:rounded-2xl xl:max-w-[1680px] xl:border xl:border-gray-200 dark:xl:border-slate-700'" @keydown="!isPage && trapFocus($event)" @keydown.esc="!isPage && closeDrawer()" @click="trackUsageControl" @change="trackUsageControl">
      <OrderWorkspaceHeader
        v-show="!proposalClientPreview"
        class="shrink-0"
        :workspace="true"
        :inert="draftBlocked ? true : undefined"
        :order-id="order?.id"
        :back-label="isPage ? backLabel : undefined"
        :title="displayOrderTitle"
        :customer-name="customerDisplayName"
        :object-label="compactObjectAddress && compactObjectAddress !== displayOrderTitle ? compactObjectAddress : undefined"
        :workflow="workflowType"
        :view-model="orderWorkspace"
        :total="totalPreview"
        :paid="totalPaymentsPreview"
        :balance="balanceDuePreview"
        :is-website-order="isWebsiteOrder"
        :is-on-hold="order?.is_on_hold"
        :can-print-envelope="Boolean(customer?.id)"
        @envelope="showEnvelope = true"
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
        @close="isPage ? emit('back') : closeDrawer()"
      />
      <div v-show="!proposalClientPreview" class="shrink-0 border-b border-slate-200 bg-white px-3 py-2 dark:border-slate-700 dark:bg-slate-950" data-testid="order-section-navigation">
          <OrderWorkspaceNav
            v-show="!proposalClientPreview"
            :active="activeWorkspaceSection"
            :workflow="workflowType"
            @select="selectWorkspaceSection"
            @add-product="openProposalForProduct"
          />
        <button type="button" class="mt-1 flex min-h-9 w-full items-center justify-between rounded-lg px-1 text-left text-xs font-semibold text-slate-600 focus-visible:ring-2 focus-visible:ring-brand-500 dark:text-slate-300" :aria-expanded="mobileContextOpen" aria-controls="order-context-details" @click="mobileContextOpen = !mobileContextOpen"><span>Ответственный, клиент и объект</span><span aria-hidden="true">{{ mobileContextOpen ? '−' : '+' }}</span></button>
      </div>

      <OrderWorkspaceUsageReport :open="usageReportOpen" @close="usageReportOpen = false" />
      <EnvelopePrintDialog v-if="showEnvelope && customer?.id" :key="customer.id" :customer-id="customer.id" :order-address="compactObjectAddress" @close="showEnvelope = false" />

      <div ref="workspaceScrollContainer" class="grid min-h-0 min-w-0 flex-1 grid-cols-1 content-start gap-3 overflow-y-auto p-3" :class="!proposalClientPreview && mobileContextOpen ? 'lg:grid-cols-[minmax(0,1fr)_18rem]' : ''">
        <div class="min-w-0">

          <p v-if="displayFormError && !proposalClientPreview" class="mt-4 rounded-xl border border-red-500/40 bg-red-50 px-3 py-2 text-sm text-red-700">
            {{ displayFormError }}
          </p>
          <OrderDraftRecovery v-if="draftBlocked" :conflicts="draftConflicts" @resolve="resolveDraftConflict" />
          <fieldset :disabled="draftBlocked || proposalActionLoading || installationAttaching || sourceApplying" class="min-w-0">
            <TenderWorkflowPanel v-if="order && !proposalClientPreview && (order.lead_source === 'email' || order.lead_source === 'belzakupki')" :order-id="order.id" />
            <section v-if="proposalMounted" v-show="activeWorkspaceSection === 'proposal'" :key="`proposal-${order?.id}`" class="min-w-0" data-order-usage="workspace-proposal-panel">
              <OrderManagerLabels v-show="!proposalClientPreview" v-model="managerLabels" />
              <OrderAsyncPanel ref="proposalPanelRef" :load="loadProposalWorkspace" label="Предложение">
                <template #default="{ component }">
              <component :is="component"
                ref="proposalWorkspaceRef"
                v-model:expanded="expandedDrawerSections.proposals"
                v-model:client-preview="proposalClientPreview"
                v-model:show-costs="showProposalCosts"
                :order-title="displayOrderTitle"
                :customer-name="customerDisplayName"
                :object-address="compactObjectAddress"
                :commercial="commercialEditor"
                :proposal="proposalLifecycle"
                :title="isRepairWorkflow ? 'Смета ремонта' : 'Предложения'"
                :show-product-lines="true"
                :products-error="getFieldError('products')"
                :services-error="getFieldError('services')"
                :format-service-kind="formatServiceKind"
                :workflow="workflowType"
                :customer-id="order?.customer?.id"
                :order-id="order?.id ?? null"
                :before-installation-action="orderSaving.flush"
                :before-multi-split-save="orderSaving.flush"
                :begin-installation-attach="beginInstallationAttach"
                :after-installation-attach="refreshAfterInstallationAttach"
                :end-installation-attach="endInstallationAttach"
                :catalog-available="catalogNavigation.available.value"
                :catalog-opening="catalogNavigation.opening.value"
                :catalog-needs-save="hasUnsavedChanges"
                @catalog="catalogNavigation.open"
                @multi-split-updated="emit('updated', $event)"
                @documents="openWorkspaceTarget('documents')"
              >
                <template #source-equipment>
                  <OrderSourceEquipmentAction
                    v-if="order?.lead_source === 'belzakupki' && workflowType === 'sales_installation'"
                    compact
                    :order-id="order.id"
                    :proposal-id="activeProposalId"
                    :before-action="beforeSourceCommand"
                    :after-action="refreshAfterSourceCommand"
                    :end-action="endSourceCommand"
                    @toast="setToast($event.message, $event.type)"
                  />
                </template>
              </component>
                </template>
              </OrderAsyncPanel>
            </section>

            <section v-if="documentsMounted" v-show="activeWorkspaceSection === 'documents'" :key="`documents-${order?.id}`" class="min-w-0" data-order-usage="workspace-documents-panel">
              <OrderAsyncPanel ref="documentsPanelRef" :load="loadDocumentsWorkspace" label="Документы">
                <template #default="{ component }">
              <component :is="component"
                v-if="order"
                ref="documentsWorkspaceRef"
                v-model:expanded="expandedDrawerSections.documents"
                :order="order"
                :managed-documents="managedDocuments"
                :workflow-type="workflowType"
                :active-proposal-id="activeProposalId"
                :product-lines="productLines"
                :total="totalPreview"
                :before-generate="beforeDocumentGenerate"
                @refresh="refreshOrderFromDocumentsPanel"
                @toast="handleDocumentPanelToast"
              />
                </template>
              </OrderAsyncPanel>
            </section>

            <section v-if="workMounted && order" v-show="activeWorkspaceSection === 'work'" :key="`work-${order.id}`" class="min-w-0" data-order-usage="workspace-work-panel">
              <OrderAsyncPanel ref="workPanelRef" :load="loadWorkWorkspace" label="Работы">
                <template #default="{ component }">
                  <component :is="component" :order="order" :form="drawerForm" :sections="expandedDrawerSections" :navigation="workspaceNavigation" :view-model="orderWorkspace" :products="productLines" :object-address="compactObjectAddress"
                    :disabled="demoReadOnly || initializing || installationAttaching || sourceApplying || proposalActionLoading || responsibilityBusy" :assignment-busy="workerAssignmentBusy" :pay-busy="workerPayBusy" :pay-revision="workerPayRevision"
                    :before-action="orderSaving.flush" :equipment-ref="setEquipmentPanel" :field-error="getFieldError"
                    @assignment-busy="setWorkerAssignmentBusy" @pay-busy="workerPayBusy = $event" @reload="emit('reload', $event)" @open="openWorkspaceTarget($event, true)" @toast="setToast($event.message, $event.type)" @copy="copyText($event.value, $event.label)" />
                </template>
              </OrderAsyncPanel>
            </section>

            <section v-if="paymentsMounted && order" v-show="activeWorkspaceSection === 'payments'" :key="`payments-${order.id}`" class="min-w-0" data-order-usage="workspace-payments-panel">
              <OrderAsyncPanel ref="paymentsPanelRef" :load="loadPaymentsWorkspace" label="Оплаты">
                <template #default="{ component }">
                  <component :is="component" :order="order" :form="drawerForm" :sections="expandedDrawerSections" :execution-open="executionWorkspaceOpen" :total="totalPreview" :margin="marginPreview"
                    @toast="setToast($event.message, $event.type)" @reload="emit('reload', $event)" @close="isPage ? emit('back') : closeDrawer()" />
                </template>
              </OrderAsyncPanel>
            </section>
          </fieldset>
        </div>
        <div v-if="contextMounted" v-show="!proposalClientPreview && mobileContextOpen" id="order-context-details" class="order-first min-w-0 lg:order-none lg:self-start">
          <div class="space-y-3">
          <OrderResponsiblePanel v-if="order" :order="order" :can-assign="canAssignResponsible" :busy="responsibilityBusy" :disabled="initializing || installationAttaching || sourceApplying || proposalActionLoading || workerAssignmentBusy || workerPayBusy" :error="responsibilityError" :assign="assignResponsible" />
          <OrderCustomerContext
            v-if="order"
            ref="customerContextRef"
            v-model:delivery-address="customerDeliveryAddress"
            v-model:customer-branch-id="customerBranchId"
            v-model:comment="comment"
            v-model:edit-target="customerContextTarget"
            :order="order"
            :total="totalPreview"
            :paid="totalPaymentsPreview"
            :balance="balanceDuePreview"
            :disabled="demoReadOnly"
            :address-error="getFieldError('customer_delivery_address')"
            :comment-error="getFieldError('comment')"
            :save-error="displayFormError"
            :before-navigate="isPage ? undefined : closeDrawer"
            :before-save="orderSaving.flush"
            :inert="draftBlocked ? true : undefined"
            :persist-object="saveContextObject"
            @toast="setToast($event.message, $event.type)"
            @updated="handleCustomerUpdated"
            @reload="emit('reload', $event)"
            @payments="openWorkspaceTarget('payments')"
          />
          <OrderRequestSourceCard
            v-if="order?.lead_source === 'belzakupki'"
            :key="`order-source-${order.id}`"
            :order-id="order.id"
            :source-enrichment="order.source_enrichment"
            @review="openSourceReview"
            @toast="setToast($event.message, $event.type)"
          />
          </div>
        </div>
      </div>
      <OrderProposalTotalsBar
        v-if="activeWorkspaceSection === 'proposal'"
        :products="productLines"
        :services="serviceLines"
        :show-costs="showProposalCosts && !demoReadOnly"
        :preview="proposalClientPreview"
        :busy="saving || proposalActionLoading || installationAttaching || sourceApplying"
        :action-label="orderWorkspace.nextAction.command === 'finish_proposal' ? 'Подготовить КП' : orderWorkspace.nextAction.label"
        @next="handleWorkspaceNextAction"
      />
      <LeadSourceReviewModal
        v-if="order"
        :open="sourceReviewOpen"
        :order-id="order.id"
        :lead-status="status"
        :before-apply="beforeSourceCommand"
        :after-apply="refreshAfterSourceCommand"
        :end-apply="endSourceCommand"
        @close="sourceReviewOpen = false"
        @applied="handleSourceApplied"
      />
    </aside>
    <div v-if="installationAttaching" role="status" class="fixed inset-0 z-[60] flex items-center justify-center bg-black/30 px-4 text-center text-sm font-semibold text-slate-900">
      <span class="rounded-xl bg-white px-5 py-3 shadow-lg">Прикрепляем монтаж к предложению…</span>
    </div>
    <div v-if="sourceApplying" role="status" class="fixed inset-0 z-[60] flex items-center justify-center bg-black/30 px-4 text-center text-sm font-semibold text-slate-900">
      <span class="rounded-xl bg-white px-5 py-3 shadow-lg">Применяем данные заявки…</span>
    </div>

  </div>
</template>

<style scoped>
.order-page-workspace { height: 100%; min-height: 0; }
</style>
