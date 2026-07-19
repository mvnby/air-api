<script setup lang="ts">
import { ExternalLink, MoreHorizontal, Store } from 'lucide-vue-next';
import type { SupplierOfferResponse } from '../../client/models/SupplierOfferResponse';

defineProps<{
  offers: SupplierOfferResponse[];
  vitebskQty: number;
  stockSaving: boolean;
  unlinkingMappingId: number | null;
}>();

const emit = defineEmits<{
  (event: 'update:vitebskQty', value: number): void;
  (event: 'save-stock'): void;
  (event: 'unlink', offer: SupplierOfferResponse): void;
}>();

const money = (value: number | null | undefined, currency = '') => (
  value == null ? '—' : `${new Intl.NumberFormat('ru-BY', { maximumFractionDigits: 2 }).format(value)}${currency ? ` ${currency}` : ''}`
);

const updatedLabel = (value: string): string => {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '—';
  return new Intl.DateTimeFormat('ru-BY', { day: '2-digit', month: '2-digit', year: '2-digit' }).format(date);
};
</script>

<template>
  <section class="space-y-5">
    <header class="border-b border-gray-100 pb-4 dark:border-slate-800">
      <p class="text-xs font-bold uppercase tracking-[0.16em] text-teal-700 dark:text-teal-300">Поставщики</p>
      <h2 class="mt-1 text-xl font-bold text-gray-950 dark:text-white">Остатки и коммерческие связи</h2>
      <p class="mt-1 text-sm text-gray-500 dark:text-slate-400">Проверяйте источник цены и наличие, не раскрывая технические детали маппинга.</p>
    </header>

    <div class="rounded-lg border border-gray-200 bg-gray-50 p-4 dark:border-slate-700 dark:bg-slate-950/30">
      <div class="flex flex-col gap-3 sm:flex-row sm:items-end">
        <label class="flex-1 text-sm font-semibold text-gray-700 dark:text-slate-200">
          Остаток на складе в Витебске
          <input :value="vitebskQty" type="number" min="0" class="mt-1 w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-900" @input="emit('update:vitebskQty', Number(($event.target as HTMLInputElement).value || 0))" />
        </label>
        <button type="button" class="h-10 rounded-lg bg-teal-600 px-4 text-sm font-semibold text-white hover:bg-teal-700 disabled:opacity-50" :disabled="stockSaving" @click="emit('save-stock')">{{ stockSaving ? 'Применяем…' : 'Применить остаток' }}</button>
      </div>
      <p class="mt-2 text-xs text-gray-500 dark:text-slate-400">Это отдельная складская операция. Остальные данные сохраняются общей кнопкой страницы.</p>
    </div>

    <div v-if="offers.length" class="overflow-x-auto rounded-lg border border-gray-200 dark:border-slate-700">
      <table class="min-w-[760px] w-full text-left text-sm">
        <thead class="bg-gray-50 text-xs uppercase tracking-wide text-gray-500 dark:bg-slate-950/50 dark:text-slate-400">
          <tr><th class="px-4 py-3">Поставщик</th><th class="px-4 py-3">Позиция</th><th class="px-4 py-3 text-right">Остаток</th><th class="px-4 py-3 text-right">Закупка</th><th class="px-4 py-3 text-right">РРЦ</th><th class="px-4 py-3">Обновлено</th><th class="w-12 px-2 py-3" /></tr>
        </thead>
        <tbody class="divide-y divide-gray-100 dark:divide-slate-800">
          <tr v-for="offer in offers" :key="`${offer.supplier_id}-${offer.external_id}`" class="bg-white dark:bg-slate-900">
            <td class="px-4 py-3 font-semibold text-gray-900 dark:text-white">
              {{ offer.supplier_name || `#${offer.supplier_id}` }}
              <span class="mt-1 block w-fit rounded-full px-2 py-0.5 text-[10px]" :class="offer.is_active ? 'bg-emerald-50 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300' : 'bg-gray-100 text-gray-500 dark:bg-slate-800 dark:text-slate-400'">{{ offer.is_active ? 'Активно' : 'Неактивно' }}</span>
            </td>
            <td class="max-w-[280px] px-4 py-3">
              <p class="truncate font-medium text-gray-700 dark:text-slate-200" :title="offer.title_raw || offer.external_id">{{ offer.title_raw || offer.external_id }}</p>
              <a v-if="offer.source_url" :href="offer.source_url" target="_blank" rel="noopener noreferrer" class="mt-0.5 inline-flex items-center gap-1 text-xs text-teal-700 hover:underline dark:text-teal-300"><ExternalLink class="h-3 w-3" />Открыть позицию</a>
            </td>
            <td class="px-4 py-3 text-right font-semibold">{{ offer.qty }}</td>
            <td class="px-4 py-3 text-right">{{ money(offer.wholesale_value, offer.wholesale_currency || '') }}</td>
            <td class="px-4 py-3 text-right">{{ money(offer.rrc_byn, 'BYN') }}</td>
            <td class="px-4 py-3 text-gray-500 dark:text-slate-400">{{ updatedLabel(offer.updated_at) }}</td>
            <td class="relative px-2 py-3 text-right">
              <details class="relative">
                <summary class="flex h-8 w-8 cursor-pointer list-none items-center justify-center rounded-md text-gray-500 hover:bg-gray-100 dark:hover:bg-slate-800" title="Действия"><MoreHorizontal class="h-4 w-4" /></summary>
                <div class="absolute right-0 top-9 z-20 w-44 rounded-lg border border-gray-200 bg-white p-1 shadow-xl dark:border-slate-700 dark:bg-slate-900">
                  <button v-if="offer.mapping_id" type="button" class="w-full rounded-md px-3 py-2 text-left text-sm font-semibold text-red-600 hover:bg-red-50 dark:hover:bg-red-950/30" :disabled="unlinkingMappingId === offer.mapping_id" @click="emit('unlink', offer)">{{ unlinkingMappingId === offer.mapping_id ? 'Отвязываем…' : 'Отвязать от товара' }}</button>
                </div>
              </details>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <div v-else class="flex min-h-56 flex-col items-center justify-center rounded-lg border border-dashed border-gray-300 bg-gray-50 px-6 text-center dark:border-slate-700 dark:bg-slate-950/30">
      <Store class="h-8 w-8 text-gray-300" />
      <p class="mt-3 font-semibold text-gray-800 dark:text-slate-100">Нет предложений поставщиков</p>
      <p class="mt-1 max-w-md text-sm text-gray-500 dark:text-slate-400">Свяжите товар с позицией прайса через раздел «Маппинг прайсов».</p>
    </div>
  </section>
</template>
