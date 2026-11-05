<script setup lang="ts">
import { computed } from 'vue';
import type { OrderProductLineResponse, OrderServiceLineResponse } from '../../../client';
import { formatByn, moneyToCents } from '../model/installation-two-stages';

const props = defineProps<{
  products: OrderProductLineResponse[];
  services: OrderServiceLineResponse[];
  total: number | null;
}>();
const selection = defineModel<number[] | null>({ required: true });
const selectedIds = computed(() => selection.value || []);
const toggleProduct = (id: number) => {
  selection.value = selectedIds.value.includes(id)
    ? selectedIds.value.filter(item => item !== id)
    : [...selectedIds.value, id];
};
</script>

<template>
  <fieldset class="mt-4 min-w-0 rounded-xl border border-slate-200 p-3 text-sm dark:border-slate-700" data-testid="consumer-work-composition">
    <legend class="px-1 font-bold">Состав заказ-акта</legend>
    <ul v-if="services.length" class="grid gap-1">
      <li v-for="work in services" :key="work.id" class="flex min-w-0 flex-wrap justify-between gap-x-3">
        <span class="min-w-0 break-words [overflow-wrap:anywhere]">{{ work.service_title }}
          <small v-if="work.quantity > 1" class="block text-xs font-normal text-slate-500 dark:text-slate-300">{{ work.quantity }} × {{ formatByn(moneyToCents(work.price)) }}</small>
        </span>
        <span class="whitespace-nowrap tabular-nums">{{ formatByn(moneyToCents(work.line_total)) }}</span>
      </li>
    </ul>
    <div v-if="products.length" class="mt-3 border-t border-slate-200 pt-2 dark:border-slate-700">
      <p class="text-xs text-slate-600 dark:text-slate-300">Оформите только работы или отметьте материалы и запчасти, переданные клиенту.</p>
      <label class="flex min-h-11 cursor-pointer items-center gap-2 font-semibold">
        <input type="checkbox" class="h-4 w-4 shrink-0" data-testid="consumer-work-only"
          :checked="selection?.length === 0" @change="selection = selection?.length === 0 ? null : []">
        Только работы
      </label>
      <label v-for="line in products" :key="line.id" class="material-option min-h-11 min-w-0 cursor-pointer">
        <input type="checkbox" class="h-4 w-4 shrink-0" :data-testid="`consumer-material-${line.id}`"
          :checked="selectedIds.includes(line.id)" @change="toggleProduct(line.id)">
        <span class="min-w-0 break-words [overflow-wrap:anywhere]">{{ line.title_snapshot || line.product_title }}
          <small v-if="line.quantity > 1" class="block text-xs font-normal text-slate-500 dark:text-slate-300">{{ line.quantity }} × {{ formatByn(moneyToCents(line.price)) }}</small>
        </span>
        <span class="whitespace-nowrap tabular-nums">{{ formatByn(moneyToCents(line.line_total)) }}</span>
      </label>
    </div>
    <p v-if="total !== null" class="mt-2 flex flex-wrap justify-between gap-x-2 border-t border-slate-200 pt-2 font-bold dark:border-slate-700">
      <span>Итого по акту</span><span class="tabular-nums" data-testid="consumer-act-total">{{ formatByn(total) }}</span>
    </p>
  </fieldset>
</template>

<style scoped>
.material-option {
  display: grid;
  grid-template-columns: 1rem minmax(0, 1fr) auto;
  gap: .15rem .5rem;
  align-items: center;
}
@media (max-width: 480px) {
  .material-option {
    grid-template-columns: 1rem minmax(0, 1fr);
    align-items: baseline;
    padding-block: .35rem;
  }
  .material-option span:last-child { grid-column: 2; }
}
</style>
