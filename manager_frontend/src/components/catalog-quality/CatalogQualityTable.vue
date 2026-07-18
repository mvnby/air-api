<script setup lang="ts">
import { ExternalLink, Image as ImageIcon } from 'lucide-vue-next';
import type { ManagerCatalogQualityReportResponse } from '../../api';

type QualityProduct = ManagerCatalogQualityReportResponse['items'][number];

defineProps<{ items: QualityProduct[] }>();
const emit = defineEmits<{ open: [product: QualityProduct]; selectIssue: [code: string] }>();

const formatNumber = (value?: number | null) => new Intl.NumberFormat('ru-RU').format(Number(value || 0));
const connectionCountLabel = (value?: number | null) => {
  const count = Number(value || 0);
  const lastTwo = count % 100;
  const last = count % 10;
  const noun = last === 1 && lastTwo !== 11
    ? 'связь'
    : last >= 2 && last <= 4 && (lastTwo < 12 || lastTwo > 14) ? 'связи' : 'связей';
  return `${formatNumber(count)} ${noun}`;
};
const scoreTone = (score: number) => score >= 85
  ? 'bg-emerald-50 text-emerald-700'
  : score >= 65 ? 'bg-amber-50 text-amber-800' : 'bg-red-50 text-red-700';
const priorityLabel = (priority?: string) => ({ high: 'Высокий', medium: 'Средний', low: 'Низкий' }[priority ?? ''] ?? 'Низкий');
const priorityTone = (priority?: string) => priority === 'high'
  ? 'text-red-700'
  : priority === 'medium' ? 'text-amber-700' : 'text-gray-500';
const supplierLabel = (product: QualityProduct) => {
  const suppliers = product.suppliers ?? [];
  if (!suppliers.length) return 'Нет маппинга';
  const first = suppliers[0]!;
  return `${first.supplier_name}${suppliers.length > 1 ? ` +${suppliers.length - 1}` : ''}`;
};
</script>

<template>
  <div class="overflow-x-auto border-y border-gray-200 bg-white">
    <table class="min-w-[1120px] w-full text-left text-sm">
      <thead class="bg-gray-50 text-xs font-bold uppercase text-gray-500">
        <tr>
          <th class="w-20 px-3 py-3">Score</th>
          <th class="min-w-72 px-3 py-3">Товар</th>
          <th class="w-40 px-3 py-3">Тип</th>
          <th class="w-36 px-3 py-3">Бренд / серия</th>
          <th class="w-44 px-3 py-3">Поставщик</th>
          <th class="w-24 px-3 py-3">Наличие</th>
          <th class="w-24 px-3 py-3">Фото</th>
          <th class="w-52 px-3 py-3">Проблемы</th>
          <th class="w-12 px-3 py-3"><span class="sr-only">Открыть</span></th>
        </tr>
      </thead>
      <tbody class="divide-y divide-gray-100">
        <tr v-for="product in items" :key="product.product_id" class="group hover:bg-teal-50/40">
          <td class="px-3 py-3 align-top">
            <span class="inline-flex min-w-11 justify-center rounded-lg px-2 py-1 font-bold" :class="scoreTone(product.score)">{{ product.score }}</span>
            <span class="mt-1 block text-xs font-semibold" :class="priorityTone(product.work_priority)">{{ priorityLabel(product.work_priority) }}</span>
          </td>
          <td class="px-3 py-3 align-top">
            <button class="font-semibold leading-5 text-gray-950 hover:text-teal-700" @click="emit('open', product)">{{ product.title }}</button>
            <p class="mt-1 text-xs text-gray-500">#{{ product.product_id }} · {{ product.is_published ? 'на сайте' : 'скрыт' }}</p>
          </td>
          <td class="px-3 py-3 align-top text-gray-700">
            <span class="font-medium">{{ product.equipment_type_label || 'Не определен' }}</span>
            <span v-if="product.equipment_subtype_label" class="mt-1 block text-xs text-gray-500">{{ product.equipment_subtype_label }}</span>
          </td>
          <td class="px-3 py-3 align-top text-gray-700">
            <span class="font-medium">{{ product.brand_title || 'Без бренда' }}</span>
            <span class="mt-1 block text-xs text-gray-500">{{ product.series_title || 'без серии' }}</span>
          </td>
          <td class="px-3 py-3 align-top text-gray-700">
            <span class="font-medium">{{ supplierLabel(product) }}</span>
            <span class="mt-1 block text-xs text-gray-500">{{ connectionCountLabel(product.supplier_mapping_count) }}</span>
          </td>
          <td class="px-3 py-3 align-top font-semibold" :class="product.available_qty ? 'text-emerald-700' : 'text-gray-500'">{{ formatNumber(product.available_qty) }} шт.</td>
          <td class="px-3 py-3 align-top">
            <span class="inline-flex items-center gap-1.5 font-semibold text-gray-700"><ImageIcon class="h-4 w-4" />{{ product.image_count || 0 }}</span>
            <span class="mt-1 block text-xs text-gray-500">{{ product.main_image_width && product.main_image_height ? `${product.main_image_width}x${product.main_image_height}` : 'размер неизвестен' }}</span>
          </td>
          <td class="px-3 py-3 align-top">
            <div class="flex flex-wrap gap-1">
              <button v-for="issue in (product.issues ?? []).slice(0, 3)" :key="issue.code" class="rounded-md bg-gray-100 px-1.5 py-1 text-xs font-semibold text-gray-700 hover:bg-teal-100 hover:text-teal-800" :title="issue.detail || issue.message" @click="emit('selectIssue', issue.code)">{{ issue.label }}</button>
              <span v-if="product.issue_count > 3" class="rounded-md bg-gray-50 px-1.5 py-1 text-xs font-semibold text-gray-500">+{{ product.issue_count - 3 }}</span>
            </div>
          </td>
          <td class="px-3 py-3 align-top">
            <button class="grid h-9 w-9 place-items-center rounded-lg border border-gray-200 text-gray-500 opacity-70 transition hover:border-teal-300 hover:text-teal-700 group-hover:opacity-100" title="Открыть товар" @click="emit('open', product)"><ExternalLink class="h-4 w-4" /></button>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
