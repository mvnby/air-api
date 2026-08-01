<script setup lang="ts">
import { computed } from 'vue';
import { EXECUTION_STATUS_OPTIONS } from './order-utils';
import type { OrderWorkflowType } from './order-workspace';
import OrderDrawerSection from './OrderDrawerSection.vue';

defineProps<{
  workflowType: OrderWorkflowType;
}>();

const expanded = defineModel<boolean>('expanded', { required: true });
const executionStatus = defineModel<string>('executionStatus', { required: true });
const executionWithoutPayment = defineModel<boolean>('executionWithoutPayment', { required: true });
const executionWithoutPaymentReason = defineModel<string>('executionWithoutPaymentReason', { required: true });
const autoCloseOnPayment = defineModel<boolean>('autoCloseOnPayment', { required: true });

const summary = computed(() => (
  EXECUTION_STATUS_OPTIONS.find((option) => option.value === executionStatus.value)?.label || 'Назначить работы'
));
</script>

<template>
  <OrderDrawerSection
    id="order-workspace-planning"
    v-model:expanded="expanded"
    :title="workflowType === 'sales_installation' ? 'Монтаж' : 'Работы'"
    :summary="summary"
    tone="default"
  >
    <label v-if="workflowType === 'sales_installation'" class="field-label">
      Общий этап заказа
      <select v-model="executionStatus" data-testid="execution-status" class="field-input mt-1">
        <option v-for="option in EXECUTION_STATUS_OPTIONS" :key="option.value" :value="option.value">{{ option.label }}</option>
      </select>
    </label>
    <div v-else class="grid grid-cols-2 gap-2 sm:grid-cols-3">
      <button
        v-for="option in EXECUTION_STATUS_OPTIONS"
        :key="option.value"
        type="button"
        :data-testid="`execution-status-${option.value}`"
        class="inline-flex min-h-10 items-center justify-center gap-1.5 rounded-xl border px-2 py-2 text-xs font-semibold transition"
        :class="executionStatus === option.value
          ? 'border-teal-500 bg-white text-teal-800 shadow-sm'
          : 'border-teal-100 bg-white/70 text-slate-600 hover:border-teal-300 hover:text-teal-800'"
        @click="executionStatus = option.value"
      >
        <span class="material-icons-round text-[15px]">{{ option.icon }}</span>
        <span class="truncate">{{ option.label }}</span>
      </button>
    </div>
    <div class="mt-3 grid gap-2 sm:grid-cols-2">
      <label class="flex items-start gap-2 rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs text-slate-700 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200">
        <input v-model="executionWithoutPayment" data-testid="execution-without-payment" type="checkbox" class="mt-0.5 h-4 w-4 rounded border-gray-300 text-teal-600 focus:ring-teal-600" />
        <span><strong class="block">Разрешить переходы при наличии долга</strong><span class="mt-0.5 block text-slate-500 dark:text-slate-400">Менеджер сможет продолжать работу без полной оплаты.</span></span>
      </label>
      <label class="flex items-start gap-2 rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs text-slate-700 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200">
        <input v-model="autoCloseOnPayment" data-testid="auto-close-on-payment" type="checkbox" class="mt-0.5 h-4 w-4 rounded border-gray-300 text-teal-600 focus:ring-teal-600" />
        <span><strong class="block">Автоматически завершить после полной оплаты</strong><span class="mt-0.5 block text-slate-500 dark:text-slate-400">Сработает, когда долг станет нулевым.</span></span>
      </label>
    </div>
    <label v-if="executionWithoutPayment" class="field-label mt-3">
      Причина работы при наличии долга
      <textarea v-model="executionWithoutPaymentReason" data-testid="execution-without-payment-reason" class="field-input min-h-[60px]" placeholder="Например: постоянный клиент, оплата по факту..." />
    </label>
  </OrderDrawerSection>
</template>
