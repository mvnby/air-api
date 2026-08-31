<script setup lang="ts">
import { computed } from 'vue';
import AdditionalConditionsPanel from './AdditionalConditionsPanel.vue';
import ContractScenarioChooser from './ContractScenarioChooser.vue';
import PaymentTermsPanel from './PaymentTermsPanel.vue';
import SupplyWarrantyTermsPanel from './SupplyWarrantyTermsPanel.vue';
import type {
  BusinessDocumentTerms,
  ContractScenario,
  PaymentDueEvent,
} from '../model/business-document-terms';

const props = defineProps<{
  documentType: string;
  terms: BusinessDocumentTerms;
  defaultGoodsWarrantyMonths: number;
}>();
const emit = defineEmits<{ updateTerms: [terms: BusinessDocumentTerms] }>();

const isContract = computed(() => props.documentType === 'contract');
const showsPayment = computed(() => ['contract', 'offer', 'invoice'].includes(props.documentType));
const showsSupply = computed(() => ['contract', 'offer', 'invoice'].includes(props.documentType));
const showsWarranty = computed(() => ['contract', 'act'].includes(props.documentType));
const update = (terms: BusinessDocumentTerms) => emit('updateTerms', terms);
const updateScenario = (contractScenario: ContractScenario) => {
  const schedule = props.terms.payment_schedule;
  const isUntouchedFullPrepayment = schedule.length === 1
    && schedule[0]?.share_percent === 100
    && schedule[0].due_days === null
    && schedule[0].due_event.startsWith('before_');
  const dueEvent: PaymentDueEvent = ['supply', 'supply_installation'].includes(contractScenario)
    ? 'before_supply'
    : 'before_work';
  const usesSuppliedEquipment = ['supply', 'supply_installation'].includes(contractScenario);
  const carriedWarranty = props.terms.goods_warranty_months;
  const goodsWarrantyMonths = usesSuppliedEquipment
    ? carriedWarranty ?? props.defaultGoodsWarrantyMonths
    : (
      carriedWarranty === props.defaultGoodsWarrantyMonths
      && !props.terms.goods_warranty_terms
        ? null
        : carriedWarranty
    );
  update({
    ...props.terms,
    contract_scenario: contractScenario,
    goods_warranty_months: goodsWarrantyMonths,
    payment_schedule: isUntouchedFullPrepayment
      ? [{ ...schedule[0]!, due_event: dueEvent }]
      : schedule,
  });
};
</script>

<template>
  <div data-testid="b2b-contract-terms-panel">
    <ContractScenarioChooser v-if="isContract" :model-value="terms.contract_scenario" @update:model-value="updateScenario" />
    <PaymentTermsPanel v-if="showsPayment" :terms="terms" @update-terms="update" />
    <SupplyWarrantyTermsPanel v-if="showsSupply || showsWarranty" :terms="terms" :show-supply="showsSupply" :show-warranty="showsWarranty" :show-valid-until="isContract" @update-terms="update" />
    <AdditionalConditionsPanel :terms="terms" @update-terms="update" />
  </div>
</template>
