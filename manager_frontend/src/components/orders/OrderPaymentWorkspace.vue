<script setup lang="ts">
import { computed, toRef } from 'vue';
import type { ManagerOrderDetailResponse } from '../../client';
import type { useOrderDrawerForm } from '../../composables/useOrderDrawerForm';
import type { OrderDrawerSectionsState } from '../../composables/useOrderDrawerPersistence';
import { isB2cCustomer as isConsumer } from '../../utils/customer-party';
import OrderPaymentsPanel from './OrderPaymentsPanel.vue';
import DealExecutionTab from './DealExecutionTab.vue';
const props = defineProps<{
  order: ManagerOrderDetailResponse;
  form: ReturnType<typeof useOrderDrawerForm>;
  sections: OrderDrawerSectionsState;
  executionOpen: boolean;
  total: number;
  margin: number;
}>();
const emit = defineEmits<{ reload: [id: number]; close: []; toast: [value: { message: string; type?: 'success' | 'error' }] }>();
const { status, payments, enableCurrency, targetCurrency, targetCurrencyAmount, currentFxRate,
  totalPayments, balanceDue, calculatedTargetCurrencyPayments, targetCurrencyBalanceDue } = props.form;
const expanded = toRef(props, 'sections');
const isB2cCustomer = computed(() => isConsumer(props.order.customer));
</script>
<template>
  <OrderPaymentsPanel v-if="status !== 'execution'" v-model:expanded="expanded.payments" v-model:payments="payments" v-model:enable-currency="enableCurrency" v-model:target-currency="targetCurrency" v-model:target-currency-amount="targetCurrencyAmount"
    :order="order" :current-fx-rate="currentFxRate" :is-b2c-customer="isB2cCustomer" :total="total" :total-payments="totalPayments" :balance-due="balanceDue" :margin="margin" :calculated-target-currency-payments="calculatedTargetCurrencyPayments" :target-currency-balance-due="targetCurrencyBalanceDue"
    @toast="emit('toast', $event)" @reload="emit('reload', $event)" />
  <DealExecutionTab v-else-if="executionOpen" id="order-workspace-execution-details" :order="order" @refresh="emit('reload', order.id)" @close="emit('close')" />
</template>
