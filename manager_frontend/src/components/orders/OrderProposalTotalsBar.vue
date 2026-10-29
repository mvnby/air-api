<script setup lang="ts">
import { committedLines } from './order-line-drafts';
import OrderMoney from './OrderMoney.vue';
import MoneyText from '../money/MoneyText.vue';
import { computed } from 'vue';
import { ArrowRight, PackagePlus, Wrench } from 'lucide-vue-next';
import type { ProductLine, ServiceLine } from './order-editor-types';

const props = defineProps<{
  products: ProductLine[];
  services: ServiceLine[];
  showCosts?: boolean;
  preview?: boolean;
  busy?: boolean;
  editable?: boolean;
  keyboardOpen?: boolean;
  showProductLines?: boolean;
  actionLabel: string;
}>();
const emit = defineEmits<{ next: []; addProduct: []; addService: [] }>();
const totals = computed(() => {
  const sum = (lines: Array<ProductLine | ServiceLine>, key: 'price' | 'cost') => lines.reduce((value, line) => value + Number(line.quantity || 0) * Math.round(Number(line[key] || 0) * 100), 0) / 100;
  const equipment = sum(committedLines(props.products), 'price');
  const services = sum(committedLines(props.services), 'price');
  const total = equipment + services;
  const cost = sum([...committedLines(props.products), ...committedLines(props.services)], 'cost');
  return { equipment, services, total, cost, profit: total - cost, margin: total > 0 ? (total - cost) / total * 100 : 0 };
});
</script>

<template>
  <footer class="proposal-footer pb-[max(0.5rem,env(safe-area-inset-bottom))] shrink-0 border-t border-slate-200 bg-white px-3 py-2 dark:border-slate-700 dark:bg-slate-950 sm:px-4" data-testid="proposal-totals-bar">
    <div class="flex flex-wrap items-center justify-between gap-x-2 gap-y-2">
      <div v-if="editable && !preview" class="grid shrink-0 grid-cols-2 gap-2 sm:flex" aria-label="Добавить в предложение">
        <button v-if="showProductLines" type="button" class="inline-flex min-h-11 min-w-14 flex-col items-center justify-center gap-0.5 rounded-xl border border-brand-600 bg-brand-600 px-2 text-xs font-semibold text-white shadow-sm min-[400px]:flex-row min-[400px]:gap-2 min-[400px]:px-3 min-[400px]:text-sm transition hover:bg-brand-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-600 disabled:opacity-50 sm:min-w-32" data-testid="add-product-line" data-order-usage="order_product_add" :disabled="busy" @click="emit('addProduct')"><PackagePlus :size="19" class="shrink-0" aria-hidden="true" />Товар</button>
        <button type="button" class="inline-flex min-h-11 min-w-14 flex-col items-center justify-center gap-0.5 rounded-xl border border-brand-300 bg-brand-50 px-2 text-xs font-semibold text-brand-800 transition min-[400px]:flex-row min-[400px]:gap-2 min-[400px]:px-3 min-[400px]:text-sm hover:bg-brand-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-600 disabled:opacity-50 dark:border-brand-600 dark:bg-brand-950 dark:text-brand-100 sm:min-w-32" data-testid="add-service-line" data-order-usage="order_service_add" :disabled="busy" @click="emit('addService')"><Wrench :size="19" class="shrink-0" aria-hidden="true" />Услуга</button>
      </div>
      <div v-if="!preview && !keyboardOpen" class="hidden items-center gap-4 text-xs tabular-nums xl:flex">
        <div><span class="block text-slate-500">Товары</span><span class="font-semibold"><OrderMoney :value="totals.equipment" /></span></div>
        <div><span class="block text-slate-500">Услуги</span><span class="font-semibold"><OrderMoney :value="totals.services" /></span></div>
      </div>
      <div v-if="showCosts && !preview && !keyboardOpen" class="order-last flex w-full flex-wrap gap-x-4 gap-y-1 text-xs tabular-nums text-slate-500 xl:order-none xl:w-auto" data-testid="proposal-cost-metrics">
        <span>Себестоимость: <OrderMoney :value="totals.cost" /></span>
        <span>Прибыль: <strong class="font-semibold text-emerald-700 dark:text-emerald-300"><OrderMoney :value="totals.profit" /></strong></span>
        <span>Маржа: {{ totals.margin.toFixed(1) }}%</span>
      </div>
      <div class="ml-auto flex min-w-0 items-center gap-2">
        <div class="text-right tabular-nums"><span class="block text-xs text-slate-500">Итого</span><strong class="whitespace-nowrap text-base sm:text-lg" data-testid="proposal-grand-total"><OrderMoney :value="totals.total" /></strong></div>
        <button v-if="!preview && !keyboardOpen" type="button" class="btn-mini min-h-11 min-w-11 gap-1.5 px-2 text-xs disabled:opacity-50 sm:px-3" :aria-label="actionLabel" :title="actionLabel" :disabled="busy" @click="emit('next')"><span class="proposal-next-label sr-only"><MoneyText :text="actionLabel" /></span><ArrowRight :size="15" class="shrink-0" aria-hidden="true" /></button>
      </div>
    </div>
  </footer>
</template>

<style scoped>
.proposal-footer { container-type: inline-size; }
@container (min-width: 640px) {
  .proposal-next-label { position: static; width: auto; height: auto; margin: 0; overflow: visible; clip: auto; white-space: normal; }
}
</style>
