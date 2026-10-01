<script setup lang="ts">
import { computed, nextTick, reactive, ref, watch } from 'vue';
import type { useOrderCommercialEditor } from '../../composables/useOrderCommercialEditor';
import type { useOrderProposalLifecycle } from '../../composables/useOrderProposalLifecycle';
import OrderProposalClientPreview from './OrderProposalClientPreview.vue';
import { useDemoReadOnly } from '../../services/manager-demo';
import OrderProductLinesEditor from './OrderProductLinesEditor.vue';
import OrderInstallationEstimatePanel from './OrderInstallationEstimatePanel.vue';
import OrderMultiSplitConfigurator from './OrderMultiSplitConfigurator.vue';
import OrderProposalToolbar from './OrderProposalToolbar.vue';
import OrderServiceLinesEditor from './OrderServiceLinesEditor.vue';
import type { OrderWorkflowType } from './order-workspace';
import type { ManagerOrderDetailResponse } from '../../client';

const props = defineProps<{
  commercial: ReturnType<typeof useOrderCommercialEditor>;
  proposal: ReturnType<typeof useOrderProposalLifecycle>;
  title: string;
  orderTitle?: string;
  customerName?: string;
  objectAddress?: string;
  showProductLines: boolean;
  productsError?: string;
  servicesError?: string;
  catalogAvailable?: boolean;
  catalogOpening?: boolean;
  catalogNeedsSave?: boolean;
  formatServiceKind: (kind?: string | null) => string;
  workflow: OrderWorkflowType;
  customerId?: number | null;
  orderId: number | null;
  beforeInstallationAction: () => Promise<boolean>;
  beginInstallationAttach: (orderId: number, proposalId: number, scopeKey: string, token: string) => Promise<boolean>;
  afterInstallationAttach: (orderId: number, proposalId: number, scopeKey: string, token: string) => Promise<boolean>;
  endInstallationAttach: (token: string) => void;
  beforeMultiSplitSave: () => Promise<boolean>;
}>();

const emit = defineEmits<{ catalog: []; documents: []; multiSplitUpdated: [order: ManagerOrderDetailResponse] }>();
defineModel<boolean>('expanded', { required: true });
const clientPreview = defineModel<boolean>('clientPreview', { default: false });
const showCosts = defineModel<boolean>('showCosts', { default: false });
const demoReadOnly = useDemoReadOnly();
const toolbarRef = ref<InstanceType<typeof OrderProposalToolbar> | null>(null);
const installationPanelRef = ref<InstanceType<typeof OrderInstallationEstimatePanel> | null>(null);
const serviceEditorRef = ref<InstanceType<typeof OrderServiceLinesEditor> | null>(null);
const previewOpenButton = ref<HTMLButtonElement | null>(null);
const previewReturnButton = ref<HTMLButtonElement | null>(null);
watch(clientPreview, async (preview) => {
  await nextTick();
  (preview ? previewReturnButton.value : previewOpenButton.value)?.focus({ preventScroll: true });
});
const commercial = reactive(props.commercial);
const proposal = reactive(props.proposal);
const hasAttachedInstallation = computed(() => commercial.serviceLines.some((line) => Boolean(line.installation_estimate_revision_id)));
const multiSplitOpen = ref(false);
const canAddInstallation = computed(() => Boolean(props.orderId && proposal.activeProposal?.id && (props.workflow === 'sales_installation' || props.workflow === 'service_work')));
const addStandardInstallation = () => {
  if (commercial.productLines.some((line) => line.product_id)) void installationPanelRef.value?.addStandard();
  else serviceEditorRef.value?.openCatalog();
};

defineExpose({
  addProduct: () => commercial.addProductLine(),
  openResponse: () => toolbarRef.value?.openResponse(),
});
</script>

<template>
  <section id="order-workspace-proposal" class="min-w-0" :aria-label="title">
    <div v-if="clientPreview" class="mb-3 flex justify-end">
      <button ref="previewReturnButton" type="button" class="btn-mini-outline min-h-8 text-xs" aria-pressed="true" @click="clientPreview = false">Вернуться в редактор</button>
    </div>
    <OrderProposalClientPreview v-if="clientPreview" :product-lines="commercial.productLines" :service-lines="commercial.serviceLines" :title="orderTitle" :customer-name="customerName" :address="objectAddress" />
    <div v-show="!clientPreview" class="min-w-0">
      <OrderProposalToolbar
        ref="toolbarRef"
        class="my-2"
        compact
        hide-primary
        :proposals="proposal.proposals"
        :active-proposal-id="proposal.activeProposal?.id"
        :loading="proposal.proposalActionLoading"
        @open="proposal.onProposalClick"
        @select="proposal.selectProposalForOrder"
        @create="proposal.createProposal"
        @duplicate="proposal.duplicateProposal"
        @rename="proposal.renameProposal"
        @archive="proposal.archiveProposal"
        @change-status="proposal.changeActiveProposalStatus"
        @send="emit('documents')"
      >
        <template #controls>
          <label v-if="!demoReadOnly" class="inline-flex min-h-8 cursor-pointer items-center gap-1.5 text-xs text-slate-600 dark:text-slate-300"><input v-model="showCosts" type="checkbox" class="rounded border-slate-300 text-brand-600" />Себестоимость</label>
          <button ref="previewOpenButton" type="button" class="btn-mini-outline min-h-8 text-xs" aria-pressed="false" @click="clientPreview = true">Предпросмотр для клиента</button>
        </template>
      </OrderProposalToolbar>

      <template v-if="orderId && workflow === 'sales_installation'">
        <OrderMultiSplitConfigurator
          v-if="multiSplitOpen"
          :order-id="orderId"
          :proposals="proposal.proposals"
          :before-save="beforeMultiSplitSave"
          @updated="emit('multiSplitUpdated', $event)"
        />
      </template>

      <div v-if="proposal.activeProposalLocked" class="mb-3 flex flex-col gap-2 rounded-xl border border-amber-200 bg-amber-50 p-3 text-xs text-amber-900 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-100 sm:flex-row sm:items-center sm:justify-between">
        <span v-if="hasAttachedInstallation">Эта редакция уже {{ proposal.activeProposalStatus === 'approved' ? 'принята клиентом' : 'отправлена' }}. Для замены монтажа создайте новый пустой черновик предложения.</span>
        <span v-else>Эта редакция уже {{ proposal.activeProposalStatus === 'approved' ? 'принята клиентом' : 'отправлена' }}. Чтобы изменить состав или стоимость, создайте копию либо верните её в черновик.</span>
        <div class="flex shrink-0 gap-2">
          <button v-if="hasAttachedInstallation" type="button" class="btn-mini-outline h-8 px-2 text-xs" @click="proposal.createProposal">Новый черновик</button>
          <template v-else><button type="button" class="btn-mini-outline h-8 px-2 text-xs" @click="proposal.duplicateProposal">Создать копию</button>
          <button type="button" class="btn-mini-outline h-8 px-2 text-xs" @click="proposal.changeActiveProposalStatus('draft')">В черновик</button></template>
        </div>
      </div>

      <fieldset :disabled="proposal.activeProposalLocked" :class="proposal.activeProposalLocked ? 'opacity-60' : ''">
        <div class="mb-2 flex flex-wrap items-center gap-2" aria-label="Добавить в предложение">
          <button v-if="showProductLines" type="button" class="btn-mini-outline h-8 text-xs" data-testid="add-product-line" data-order-usage="order_product_add" @click="commercial.addProductLine">+ Товар</button>
          <button type="button" class="btn-mini-outline h-8 text-xs" data-testid="add-service-line" data-order-usage="order_service_add" @click="serviceEditorRef?.openCatalog()">+ Услуга</button>
          <button v-if="canAddInstallation" type="button" class="btn-mini h-8 text-xs" data-testid="installation-standard-add" :disabled="installationPanelRef?.actionBusy" @click="addStandardInstallation">{{ installationPanelRef?.actionBusy ? 'Рассчитываем монтаж…' : 'Стандартный монтаж' }}</button>
          <button v-if="catalogAvailable && showProductLines" type="button" class="btn-mini-outline h-8 text-xs" :disabled="catalogOpening" @click="emit('catalog')">{{ catalogOpening ? 'Открываем подбор…' : catalogNeedsSave ? 'Сохранить и подобрать' : 'Подобрать по параметрам' }}</button>
          <slot name="source-equipment" />
          <button type="button" class="h-8 px-1 text-xs text-slate-500 hover:text-brand-700" :aria-expanded="commercial.showEstimateImport" @click="commercial.toggleEstimateImport">Из сметы</button>
        </div>
        <OrderInstallationEstimatePanel
          v-if="canAddInstallation && orderId && proposal.activeProposal?.id"
          ref="installationPanelRef"
          compact
          hide-actions
          :order-id="orderId"
          :proposal-id="proposal.activeProposal.id"
          :before-action="beforeInstallationAction"
          :begin-attach="beginInstallationAttach"
          :after-attach="afterInstallationAttach"
          :end-attach="endInstallationAttach"
        />
        <div class="hidden gap-2 rounded-t-lg border-b border-slate-200 bg-slate-50 px-3 py-2 text-xs font-semibold text-slate-500 dark:border-slate-700 dark:bg-slate-900 md:grid" :class="showCosts && !demoReadOnly ? 'grid-cols-[minmax(0,1fr)_3.5rem_6rem_6.5rem_6rem_4.5rem]' : 'grid-cols-[minmax(0,1fr)_3.5rem_6rem_6.5rem_4.5rem]'" aria-hidden="true">
          <span>Наименование и состав</span><span class="text-center">Кол-во</span><span class="text-right">Цена</span><span class="text-right">Сумма</span><span v-if="showCosts && !demoReadOnly" class="text-right">Себест.</span><span class="text-center">Действия</span>
        </div>
        <OrderProductLinesEditor
          v-if="showProductLines"
          compact
          hide-actions
          :show-costs="showCosts"
          v-model:lines="commercial.productLines"
          v-model:search-in-stock="commercial.searchInStock"
          :product-options="commercial.productOptions"
          :product-lookup-by-id="commercial.productLookupById"
          :product-lookup-loading="commercial.productLookupLoading"
          :active-suggestion-index="commercial.activeSuggestionIndex"
          :supply-action-loading-line-id="commercial.supplyActionLoadingLineId"
          :products-error="productsError"
          :supply-badge-for-line="commercial.supplyBadgeForLine"
          :catalog-available="catalogAvailable"
          :catalog-opening="catalogOpening"
          :catalog-needs-save="catalogNeedsSave"
          @catalog="emit('catalog')"
          @focus="commercial.onProductInputFocus"
          @input="commercial.onProductQueryInput"
          @blur="commercial.onProductInputBlur"
          @select="commercial.selectProductForLine($event.index, $event.option)"
          @open="commercial.openSelectedProduct"
          @remove="commercial.removeProductLine"
          @add="commercial.addProductLine"
          @fill-description="commercial.fillProductClientDescription"
          @supply="commercial.createSupplyFromProductLine($event.line, $event.intent)"
        />

        <OrderServiceLinesEditor
          ref="serviceEditorRef"
          compact
          hide-actions
          :show-costs="showCosts"
          v-model:lines="commercial.serviceLines"
          v-model:editing-index="commercial.editingServiceLineIndex"
          v-model:show-estimate-import="commercial.showEstimateImport"
          v-model:selected-estimate-id="commercial.selectedEstimateId"
          v-model:estimate-search-query="commercial.estimateSearchQuery"
          v-model:estimate-import-mode="commercial.estimateImportMode"
          v-model:description-mode="commercial.serviceDescriptionMode"
          :service-options="commercial.serviceTariffOptions"
          :service-lookup-loading="commercial.serviceTariffLookupLoading"
          :active-suggestion-index="commercial.activeServiceSuggestionIndex"
          :services-error="servicesError"
          :estimate-options="commercial.estimateOptions"
          :estimate-options-loading="commercial.estimateOptionsLoading"
          :importing-estimate="commercial.importingEstimate"
          :format-service-kind="formatServiceKind"
          :workflow="workflow"
          :customer-id="customerId"
          :can-open-installation-estimate="Boolean(orderId && proposal.activeProposal?.id && (workflow === 'sales_installation' || workflow === 'service_work'))"
          @focus="commercial.onServiceTitleFocus"
          @input="commercial.onServiceTitleInput"
          @blur="commercial.onServiceTitleBlur"
          @select="commercial.selectServiceTariffForLine($event.index, $event.option)"
          @description-mode="commercial.setServiceLineDescriptionMode($event.index, $event.mode)"
          @remove="commercial.removeServiceLine"
          @add="commercial.addServiceLine"
          @add-tariff="commercial.addServiceTariff"
          @append-estimate="commercial.addCreatedEstimate($event.id, $event.lines)"
          @toggle-estimate="commercial.toggleEstimateImport"
          @import-estimate="commercial.applyEstimateToServices"
          @load-estimates="commercial.loadEstimateOptions"
          @remember-description-mode="commercial.setDefaultServiceDescriptionMode"
          @open-installation-estimate="installationPanelRef?.openPanel()"
          @standard-installation="(tariff, edit) => installationPanelRef?.selectStandardTariff(tariff, edit)"
        />
        <div class="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-slate-500">
          <button v-if="canAddInstallation" type="button" class="min-h-8 hover:text-brand-700" data-testid="installation-open" @click="installationPanelRef?.openPanel()">Настроить монтаж</button>
          <button v-if="orderId && workflow === 'sales_installation'" type="button" class="min-h-8 hover:text-brand-700" :aria-expanded="multiSplitOpen" @click="multiSplitOpen = !multiSplitOpen">{{ multiSplitOpen ? 'Скрыть мультисплит' : 'Собрать мультисплит' }}</button>
          <span v-if="hasAttachedInstallation">Монтаж зафиксирован; для замены — новый пустой черновик.</span>
        </div>
      </fieldset>
      <button v-if="commercial.total > 0" type="button" class="mt-2 min-h-8 text-xs text-brand-700 hover:underline" data-testid="proposal-to-documents" @click="emit('documents')">Перейти к документам →</button>
    </div>
  </section>
</template>
