<script setup lang="ts">
import OrderMoney from './OrderMoney.vue';
import LineFormattedText from './LineFormattedText.vue';
import { computed } from 'vue';
import type { ProductLine, ServiceLine } from './order-editor-types';

const props = defineProps<{
  productLines: ProductLine[];
  serviceLines: ServiceLine[];
  title?: string;
  customerName?: string;
  address?: string;
}>();
const rows = computed(() => [
  ...props.productLines.filter(line => line.product_id || line.product_query.trim()).map(line => ({
    title: line.product_query, description: line.client_description,
    quantity: line.quantity, price: line.price, unit: 'шт.',
  })),
  ...props.serviceLines.flatMap(line => (line.installation_display_lines?.length
    ? line.installation_display_lines : [line]).map(display => ({
    title: display.title, description: display.description,
    quantity: display.quantity, price: display.price, unit: 'усл.',
  }))),
]);
</script>

<template>
  <article class="rounded-xl border border-slate-200 bg-white p-4 text-slate-900 sm:p-5" aria-label="Предложение для клиента" data-testid="proposal-client-preview">
    <header class="mb-4 border-b border-slate-200 pb-3">
      <p class="text-xs font-medium uppercase tracking-wide text-slate-500">Коммерческое предложение</p>
      <h2 class="mt-1 break-words text-lg font-semibold">{{ title || 'Состав и стоимость' }}</h2>
      <p v-if="customerName" class="mt-2 text-sm">{{ customerName }}</p>
      <p v-if="address" class="mt-1 break-words text-sm text-slate-500">{{ address }}</p>
    </header>
    <div class="hidden grid-cols-[minmax(0,1fr)_3.5rem_6rem_6.5rem] gap-3 border-b border-slate-200 pb-2 text-xs font-semibold text-slate-500 md:grid" aria-hidden="true">
      <span>Наименование и состав</span><span class="text-right">Кол-во</span><span class="text-right">Цена</span><span class="text-right">Сумма</span>
    </div>
    <div v-for="(row, index) in rows" :key="index" class="grid gap-3 border-b border-slate-100 py-3 md:grid-cols-[minmax(0,1fr)_3.5rem_6rem_6.5rem] md:items-center">
      <div class="min-w-0"><h3 class="break-words text-sm font-semibold"><LineFormattedText :text="row.title" /></h3><p v-if="row.description" class="mt-1 whitespace-pre-line break-words text-xs leading-relaxed text-slate-500"><LineFormattedText :text="row.description" /></p></div>
      <span class="text-sm tabular-nums md:text-right"><span class="md:hidden">Количество: </span>{{ row.quantity }} <span class="text-xs text-slate-500">{{ row.unit }}</span></span>
      <span class="whitespace-nowrap text-sm tabular-nums md:text-right"><span class="md:hidden">Цена: </span><OrderMoney :value="row.price" /></span>
      <span class="whitespace-nowrap text-sm font-semibold tabular-nums md:text-right"><span class="md:hidden">Сумма: </span><OrderMoney :value="row.quantity * row.price" /></span>
    </div>
    <p v-if="!rows.length" class="py-6 text-sm text-slate-500">В предложении пока нет позиций.</p>
    <p class="mt-4 text-xs leading-relaxed text-slate-500">В стоимость входят перечисленные товары и работы в указанном составе. Дополнительные работы и материалы, не указанные в предложении, рассчитываются отдельно после уточнения условий монтажа.</p>
  </article>
</template>
