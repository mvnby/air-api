<script setup lang="ts">
import { reactive, ref } from 'vue';
import type { useOrderCommercialEditor } from '../../composables/useOrderCommercialEditor';
import type { useOrderProposalLifecycle } from '../../composables/useOrderProposalLifecycle';
import OrderDrawerSection from './OrderDrawerSection.vue';
import OrderProductLinesEditor from './OrderProductLinesEditor.vue';
import OrderProposalToolbar from './OrderProposalToolbar.vue';
import OrderServiceLinesEditor from './OrderServiceLinesEditor.vue';

const props = defineProps<{
  commercial: ReturnType<typeof useOrderCommercialEditor>;
  proposal: ReturnType<typeof useOrderProposalLifecycle>;
  title: string;
  showProductLines: boolean;
  productsError?: string;
  servicesError?: string;
  formatServiceKind: (kind?: string | null) => string;
}>();

const emit = defineEmits<{ send: [] }>();
const expanded = defineModel<boolean>('expanded', { required: true });
const toolbarRef = ref<InstanceType<typeof OrderProposalToolbar> | null>(null);
const commercial = reactive(props.commercial);
const proposal = reactive(props.proposal);

defineExpose({ openResponse: () => toolbarRef.value?.openResponse() });
</script>

<template>
  <OrderDrawerSection
    id="order-workspace-proposal"
    v-model:expanded="expanded"
    :title="title"
    :summary="proposal.activeProposalLineLabel"
    tone="default"
    :has-error="Boolean(productsError || servicesError)"
  >
    <div class="min-w-0">
      <OrderProposalToolbar
        ref="toolbarRef"
        class="mb-4"
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
        @send="emit('send')"
      />

      <div v-if="proposal.activeProposalLocked" class="mb-3 flex flex-col gap-2 rounded-xl border border-amber-200 bg-amber-50 p-3 text-xs text-amber-900 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-100 sm:flex-row sm:items-center sm:justify-between">
        <span>Эта редакция уже {{ proposal.activeProposalStatus === 'approved' ? 'принята клиентом' : 'отправлена' }}. Чтобы изменить состав или стоимость, создайте копию либо верните её в черновик.</span>
        <div class="flex shrink-0 gap-2">
          <button type="button" class="btn-mini-outline h-8 px-2 text-xs" @click="proposal.duplicateProposal">Создать копию</button>
          <button type="button" class="btn-mini-outline h-8 px-2 text-xs" @click="proposal.changeActiveProposalStatus('draft')">В черновик</button>
        </div>
      </div>

      <fieldset :disabled="proposal.activeProposalLocked" :class="proposal.activeProposalLocked ? 'opacity-60' : ''">
        <OrderProductLinesEditor
          v-if="showProductLines"
          v-model:lines="commercial.productLines"
          v-model:search-in-stock="commercial.searchInStock"
          :product-options="commercial.productOptions"
          :product-lookup-by-id="commercial.productLookupById"
          :product-lookup-loading="commercial.productLookupLoading"
          :active-suggestion-index="commercial.activeSuggestionIndex"
          :supply-action-loading-line-id="commercial.supplyActionLoadingLineId"
          :products-error="productsError"
          :supply-badge-for-line="commercial.supplyBadgeForLine"
          @focus="commercial.onProductInputFocus"
          @input="commercial.onProductQueryInput"
          @blur="commercial.onProductInputBlur"
          @select="commercial.selectProductForLine($event.index, $event.option)"
          @open="commercial.openSelectedProduct"
          @remove="commercial.removeProductLine"
          @add="commercial.addProductLine"
          @supply="commercial.createSupplyFromProductLine($event.line, $event.intent)"
        />

        <OrderServiceLinesEditor
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
          @focus="commercial.onServiceTitleFocus"
          @input="commercial.onServiceTitleInput"
          @blur="commercial.onServiceTitleBlur"
          @select="commercial.selectServiceTariffForLine($event.index, $event.option)"
          @description-mode="commercial.setServiceLineDescriptionMode($event.index, $event.mode)"
          @remove="commercial.removeServiceLine"
          @add="commercial.addServiceLine"
          @toggle-estimate="commercial.toggleEstimateImport"
          @import-estimate="commercial.applyEstimateToServices"
          @load-estimates="commercial.loadEstimateOptions"
          @remember-description-mode="commercial.setDefaultServiceDescriptionMode"
        />
      </fieldset>
    </div>
  </OrderDrawerSection>
</template>
