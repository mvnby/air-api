<script setup lang="ts">
import { computed } from 'vue';
import AdditionalConditionsPanel from './AdditionalConditionsPanel.vue';
import PaymentTermsPanel from './PaymentTermsPanel.vue';
import SupplyWarrantyTermsPanel from './SupplyWarrantyTermsPanel.vue';
import type {
  BusinessDocumentTerms,
} from '../model/business-document-terms';

const props = defineProps<{
  documentType: string;
  terms: BusinessDocumentTerms;
  orderConditions?: string | null;
}>();
const emit = defineEmits<{ updateTerms: [terms: BusinessDocumentTerms] }>();

const isContract = computed(() => props.documentType === 'contract');
const showsPayment = computed(() => ['contract', 'offer', 'invoice'].includes(props.documentType));
const showsSupply = computed(() => ['contract', 'offer', 'invoice'].includes(props.documentType));
const showsWarranty = computed(() => ['contract', 'act'].includes(props.documentType));
const update = (terms: BusinessDocumentTerms) => emit('updateTerms', terms);
</script>

<template>
  <div data-testid="b2b-contract-terms-panel">
    <details v-if="showsPayment" class="terms-details" data-testid="payment-terms-details"><summary>Порядок оплаты</summary><PaymentTermsPanel embedded :terms="terms" @update-terms="update" /></details>
    <details v-if="showsSupply" class="terms-details" data-testid="subject-terms-details"><summary>Предмет и сроки</summary><SupplyWarrantyTermsPanel embedded :terms="terms" :show-supply="true" :show-warranty="false" :show-valid-until="isContract" @update-terms="update" /></details>
    <details v-if="showsWarranty" class="terms-details" data-testid="warranty-terms-details"><summary>Гарантия <span class="font-normal text-slate-500">· оборудование {{ terms.goods_warranty_months ?? 'не указано' }} мес., работы {{ terms.work_warranty_months ?? 'не указано' }}</span></summary><SupplyWarrantyTermsPanel embedded :terms="terms" :show-supply="false" :show-warranty="true" :show-valid-until="false" @update-terms="update" /></details>
    <details class="terms-details" data-testid="additional-terms-details"><summary>Дополнительные условия <span v-if="orderConditions && !terms.additional_conditions_overridden" class="font-normal text-slate-500">· из заказа</span></summary><AdditionalConditionsPanel embedded :terms="terms" :order-conditions="orderConditions" @update-terms="update" /></details>
  </div>
</template>

<style scoped>
.terms-details { @apply mt-3 rounded-xl border border-slate-200 bg-white px-3 py-2 dark:border-slate-700 dark:bg-slate-900/50; }
.terms-details > summary { @apply cursor-pointer py-1 text-sm font-semibold text-slate-800 dark:text-slate-200; }
</style>
