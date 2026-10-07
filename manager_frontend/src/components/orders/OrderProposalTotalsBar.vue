<script setup lang="ts">
import OrderMoney from './OrderMoney.vue';
import { computed } from 'vue';
import { ArrowRight } from 'lucide-vue-next';
import type { ProductLine, ServiceLine } from './order-editor-types';

const props = defineProps<{
  products: ProductLine[];
  services: ServiceLine[];
  showCosts?: boolean;
  preview?: boolean;
  busy?: boolean;
  actionLabel: string;
}>();
const emit = defineEmits<{ next: [] }>();
const totals = computed(() => {
  const sum = (lines: Array<ProductLine | ServiceLine>, key: 'price' | 'cost') => lines.reduce((value, line) => value + Number(line.quantity || 0) * Math.round(Number(line[key] || 0) * 100), 0) / 100;
  const equipment = sum(props.products, 'price');
  const services = sum(props.services, 'price');
  const total = equipment + services;
  const cost = sum([...props.products, ...props.services], 'cost');
  return { equipment, services, total, cost, profit: total - cost, margin: total > 0 ? (total - cost) / total * 100 : 0 };
});
</script>

<template>
  <footer class="shrink-0 border-t border-slate-200 bg-white px-3 py-2 dark:border-slate-700 dark:bg-slate-950 sm:px-4" data-testid="proposal-totals-bar">
    <div class="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
      <div v-if="!preview" class="hidden items-center gap-4 text-xs tabular-nums sm:flex">
        <div><span class="block text-slate-500">Товары</span><span class="font-semibold"><OrderMoney :value="totals.equipment" /></span></div>
        <div><span class="block text-slate-500">Услуги</span><span class="font-semibold"><OrderMoney :value="totals.services" /></span></div>
      </div>
      <div v-if="showCosts && !preview" class="order-last flex w-full flex-wrap gap-x-4 gap-y-1 text-xs tabular-nums text-slate-500 xl:order-none xl:w-auto" data-testid="proposal-cost-metrics">
        <span>Себестоимость: <OrderMoney :value="totals.cost" /></span>
        <span>Прибыль: <strong class="font-semibold text-emerald-700 dark:text-emerald-300"><OrderMoney :value="totals.profit" /></strong></span>
        <span>Маржа: {{ totals.margin.toFixed(1) }}%</span>
      </div>
      <div class="ml-auto flex min-w-0 items-center gap-3">
        <div class="text-right tabular-nums"><span class="block text-xs text-slate-500">Итого</span><strong class="whitespace-nowrap text-base sm:text-lg" data-testid="proposal-grand-total"><OrderMoney :value="totals.total" /></strong></div>
        <button v-if="!preview" type="button" class="btn-mini min-h-9 max-w-[55vw] gap-1.5 px-3 text-xs disabled:opacity-50" :disabled="busy" @click="emit('next')"><span>{{ actionLabel }}</span><ArrowRight :size="15" class="shrink-0" aria-hidden="true" /></button>
      </div>
    </div>
  </footer>
</template>
