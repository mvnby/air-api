<script setup lang="ts">
import { computed, onScopeDispose, ref, toRef, watch } from 'vue';
import type { OrderWithResponsibility } from '../../services/order-responsibility';
import type { useOrderDrawerForm } from '../../composables/useOrderDrawerForm';
import type { useOrderWorkspaceNavigation } from '../../composables/useOrderWorkspaceNavigation';
import type { OrderDrawerSectionsState } from '../../composables/useOrderDrawerPersistence';
import type { ProductLine } from './order-editor-types';
import type { OrderWorkspaceTarget, OrderWorkspaceViewModel } from './order-workspace';
import type { ServiceAttachmentEquipmentOption } from '../service-attachments/types';
import OrderEquipmentPanel from '../equipment/OrderEquipmentPanel.vue';
import OrderAttachmentsPanel from '../service-attachments/OrderAttachmentsPanel.vue';
import EmailContractReviewLauncher from '../leads/EmailContractReviewLauncher.vue';
import MaintenanceObservationsPanel from '../maintenance-observations/MaintenanceObservationsPanel.vue';
import OrderWorkerPayPanel from './OrderWorkerPayPanel.vue';
import OrderWorkerAssignmentsPanel from './OrderWorkerAssignmentsPanel.vue';
import OrderSalesInstallationWorkspace from './OrderSalesInstallationWorkspace.vue';
import OrderIncomingContext from './OrderIncomingContext.vue';
import OrderWebsiteIntakePanel from './OrderWebsiteIntakePanel.vue';
import OrderPlanningPanel from './OrderPlanningPanel.vue';
import OrderRepairPanel from './OrderRepairPanel.vue';
import OrderExecutionPanel from './OrderExecutionPanel.vue';

const props = defineProps<{
  order: OrderWithResponsibility;
  form: ReturnType<typeof useOrderDrawerForm>;
  sections: OrderDrawerSectionsState;
  navigation: ReturnType<typeof useOrderWorkspaceNavigation>;
  viewModel: OrderWorkspaceViewModel;
  products: ProductLine[];
  objectAddress: string;
  disabled: boolean;
  assignmentBusy: boolean;
  payBusy: boolean;
  payRevision: number;
  beforeAction: () => Promise<boolean>;
  equipmentRef: (panel: InstanceType<typeof OrderEquipmentPanel> | null) => void;
  fieldError: (field: string) => string;
}>();
const emit = defineEmits<{
  'assignment-busy': [value: boolean];
  'pay-busy': [value: boolean];
  reload: [orderId: number];
  open: [target: OrderWorkspaceTarget];
  toast: [value: {message: string; type?: 'success' | 'error'}];
  copy: [value: {value: string | null | undefined; label: string}];
}>();
const { status, workflowType, customerBranchId, customerDeliveryAddress, comment, measurementRequired,
  assessmentDate, negotiationStatus, autoExecutionOnPayment, measurerId, measurementResult,
  installationDate, installerId, executorOptions, newBranchAddress, isRepairWorkflow, repairMeta,
  orderTitle, executionStatus, executionWithoutPayment, executionWithoutPaymentReason, autoCloseOnPayment,
  executorsLoading, executorsError, loadExecutors,
} = props.form;
const expandedDrawerSections = toRef(props, 'sections');
const { activeWorkspaceTarget } = props.navigation;
const orderWorkspace = toRef(props, 'viewModel');
const productLines = toRef(props, 'products');
const compactObjectAddress = toRef(props, 'objectAddress');
const workerPayRevision = toRef(props, 'payRevision');
const workerContextVersion = computed(() => JSON.stringify([
  props.order.work_stages, props.order.product_lines, props.order.service_lines,
  props.order.payments, props.order.total_amount, props.order.total_cost, props.order.total_payments,
]));
const workerPayContextVersion = computed(() => `${workerContextVersion.value}:${workerPayRevision.value}`);
const customer = computed(() => props.order.customer);
const isWebsiteOrder = computed(() => props.order.lead_source === 'site');
const equipmentPanelRef = ref<InstanceType<typeof OrderEquipmentPanel> | null>(null);
const linkedEquipmentOptions = ref<ServiceAttachmentEquipmentOption[]>([]);
watch(equipmentPanelRef, panel => props.equipmentRef(panel), {flush: 'sync'});
onScopeDispose(() => props.equipmentRef(null));
const getFieldError = props.fieldError;
</script>

<template>
  <div class="min-w-0" data-testid="order-work-section">
    <p v-if="executorsLoading" role="status" class="mb-3 text-sm text-slate-500">Загружаем исполнителей…</p>
    <div v-if="executorsError" role="alert" class="mb-3 rounded-lg border border-amber-300 p-3 text-sm">
      {{ executorsError }}
      <button type="button" class="ml-2 underline focus-visible:ring-2 focus-visible:ring-brand-500" @click="loadExecutors(true)">Повторить загрузку исполнителей</button>
    </div>

    <OrderWorkerAssignmentsPanel v-if="order" :key="`worker-assignments-${order.id}`" :order-id="order.id" :work-stages="order.work_stages" :context-version="workerContextVersion" :disabled="disabled || payBusy" :before-action="beforeAction" @busy="emit('assignment-busy', $event)" />
    <OrderWorkerPayPanel v-if="order" :key="`worker-pay-${order.id}`" :order-id="order.id" :context-version="workerPayContextVersion" :disabled="disabled || assignmentBusy" :before-action="beforeAction" @busy="emit('pay-busy', $event)" @changed="emit('reload', order.id)" />
    <OrderIncomingContext v-if="order?.incoming_context" :context="order.incoming_context" />
    <OrderSalesInstallationWorkspace
      v-if="workflowType === 'sales_installation'"
      class="mt-4"
      :lanes="orderWorkspace.lanes"
      :active-target="activeWorkspaceTarget"
      @open="emit('open', $event)"
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
      @error="emit('toast', {message: $event, type: 'error'})"
    />
    <a v-if="order?.maintenance_source_order_id" :href="`/manager/orders/kanban?orderId=${order.maintenance_source_order_id}`" class="block mt-4 text-sm text-blue-600" target="_blank" rel="noopener">Исходное ТО #{{ order.maintenance_source_order_id }} · предложения, согласование и устранение ↗</a>
    <MaintenanceObservationsPanel v-if="order?.workflow_type === 'maintenance'" :key="`observations-${order.id}`" class="mt-4" :order-id="order.id" :customer-id="order.customer?.id" :customer-branch-id="order.customer_branch?.id" />
    <EmailContractReviewLauncher v-if="order && order.attachment_count" :order-id="order.id" />
    <OrderAttachmentsPanel v-if="order" :key="`order-attachments-${order.id}`" class="mt-4" :order-id="order.id" :initial-count="order.attachment_count" :equipment-options="linkedEquipmentOptions" @need-equipment-options="equipmentPanelRef?.ensureLoaded()" @error="emit('toast', {message: $event, type: 'error'})" />
    <OrderWebsiteIntakePanel v-if="isWebsiteOrder" v-model:expanded="expandedDrawerSections.website" :order="order!" :delivery-address="customerDeliveryAddress" :comment="comment" @copy="emit('copy', $event)" />
    <OrderPlanningPanel
      v-if="status === 'negotiation'"
      v-model:measurement-required="measurementRequired" v-model:assessment-date="assessmentDate" v-model:negotiation-status="negotiationStatus" v-model:auto-execution-on-payment="autoExecutionOnPayment" v-model:details-expanded="expandedDrawerSections.planningDetails" v-model:measurer-id="measurerId" v-model:measurement-result="measurementResult" v-model:installation-date="installationDate" v-model:installer-id="installerId"
      :workflow-type="workflowType" :executor-options="executorOptions" :customer-branch-id="customerBranchId" :new-branch-address="newBranchAddress" :measurement-error="getFieldError('measurement_date')" :installation-error="getFieldError('installation_date')"
    />
    <OrderRepairPanel v-if="isRepairWorkflow && order" v-model:expanded="expandedDrawerSections.repair" v-model:repair-meta="repairMeta" :order="order" :order-title="orderTitle" :measurement-result="measurementResult" :customer-branch-id="customerBranchId" :object-address="compactObjectAddress" @toast="emit('toast', $event)" @reload="emit('reload', $event)" />
    <OrderExecutionPanel v-if="status === 'execution'" v-model:expanded="expandedDrawerSections.execution" v-model:execution-status="executionStatus" v-model:execution-without-payment="executionWithoutPayment" v-model:execution-without-payment-reason="executionWithoutPaymentReason" v-model:auto-close-on-payment="autoCloseOnPayment" :workflow-type="workflowType" />
    </div>
</template>
