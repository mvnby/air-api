<script setup lang="ts">
import { computed, ref } from 'vue';
import { X } from 'lucide-vue-next';
import { useDialogA11y } from '../../composables/useDialogA11y';
import type { CatalogDecisionItem } from '../../services/catalog-decision-api';
import CatalogMoney from './CatalogMoney.vue';

type ComparisonRow = {
  key: string;
  label: string;
  values: Array<string | number | null | undefined>;
  money?: boolean;
};

const props = defineProps<{
  open: boolean;
  items: CatalogDecisionItem[];
  loading?: boolean;
  error?: string;
}>();
const emit = defineEmits<{ close: [] }>();

const dialogRef = ref<HTMLElement | null>(null);
const closeButtonRef = ref<HTMLElement | null>(null);
const differencesOnly = ref(false);
const comparisonItems = computed(() => props.items);
const wifiLabels: Record<string, string> = { builtin: 'Встроен', ready: 'Опция', none: 'Нет' };
const formLabels: Record<string, string> = {
  wall: 'Настенный', console: 'Консольный', cassette: 'Кассетный', duct: 'Канальный', floor_ceiling: 'Напольно-потолочный', column: 'Колонный',
};
const wifiLabel = (value: CatalogDecisionItem['wifi']) => wifiLabels[value || ''] || '—';
const formLabel = (value: CatalogDecisionItem['indoor_form_factor']) => formLabels[value || ''] || '—';
const valueOrDash = (value: string | number | null | undefined) => value == null || value === '' ? '—' : value;
const kw = (value: number | null | undefined) => value == null ? '—' : `${value} кВт`;
const temperature = (value: number | null | undefined) => value == null ? '—' : `До ${value} °C`;
const percent = (value: number | null | undefined) => value == null ? '—' : `${(value * 100).toLocaleString('ru-BY', { maximumFractionDigits: 2 })}%`;
const stock = (item: CatalogDecisionItem) => item.availability === 'in_stock'
  ? `В наличии${item.supplier_qty == null ? '' : ` · ${item.supplier_qty} шт.`}`
  : 'Нет в наличии';

const rows = computed<ComparisonRow[]>(() => [
  { key: 'customer-price', label: 'Цена клиенту', values: comparisonItems.value.map(item => item.retail_price_byn), money: true },
  { key: 'purchase-cost', label: 'Закупка', values: comparisonItems.value.map(item => item.purchase_cost_byn), money: true },
  { key: 'rrc', label: 'РРЦ', values: comparisonItems.value.map(item => item.recommended_price_byn), money: true },
  { key: 'margin-abs', label: 'Маржа', values: comparisonItems.value.map(item => item.margin_abs_byn), money: true },
  { key: 'margin-pct', label: 'Маржа, %', values: comparisonItems.value.map(item => percent(item.margin_pct)) },
  { key: 'stock', label: 'Остаток', values: comparisonItems.value.map(stock) },
  { key: 'supplier', label: 'Поставщик', values: comparisonItems.value.map(item => valueOrDash(item.supplier_name)) },
  { key: 'cooling', label: 'Охлаждение', values: comparisonItems.value.map(item => kw(item.cooling_power_kw)) },
  { key: 'heating', label: 'Обогрев', values: comparisonItems.value.map(item => temperature(item.heating_min_c)) },
  { key: 'inverter', label: 'Инвертор', values: comparisonItems.value.map(item => item.is_inverter ? 'Да' : 'Нет') },
  { key: 'wifi', label: 'Wi-Fi', values: comparisonItems.value.map(item => wifiLabel(item.wifi)) },
  { key: 'form-factor', label: 'Внутренний блок', values: comparisonItems.value.map(item => formLabel(item.indoor_form_factor)) },
  { key: 'area', label: 'Площадь', values: comparisonItems.value.map(item => item.area_m2 == null ? '—' : `${item.area_m2} м²`) },
]);
const visibleRows = computed(() => differencesOnly.value
  ? rows.value.filter(row => new Set(row.values.map(value => String(valueOrDash(value)))).size > 1)
  : rows.value);
const setDifferencesOnly = (event: Event) => {
  differencesOnly.value = (event.target as HTMLInputElement).checked;
};
const close = () => emit('close');

useDialogA11y({
  open: computed(() => props.open),
  dialogRef,
  initialFocusRef: closeButtonRef,
  close,
});
</script>

<template>
  <Teleport to="body">
    <div v-if="open" class="fixed inset-0 z-[130] flex items-end justify-center bg-slate-950/55 p-0 sm:items-center sm:p-4" @mousedown.self="close">
      <section ref="dialogRef" role="dialog" aria-modal="true" tabindex="-1" aria-labelledby="catalog-decision-compare-title" class="flex max-h-[94vh] w-full max-w-6xl flex-col rounded-t-lg border border-slate-200 bg-white shadow-2xl outline-none sm:rounded-lg">
        <header class="flex items-start justify-between gap-4 border-b border-slate-200 px-4 py-3 sm:px-5">
          <div>
            <h2 id="catalog-decision-compare-title" class="text-base font-semibold text-slate-950">Сравнение моделей</h2>
            <p class="mt-1 text-sm text-slate-600">Выберите «Только различия», чтобы быстрее увидеть отличия.</p>
          </div>
          <button ref="closeButtonRef" type="button" class="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-slate-500 hover:bg-slate-100" aria-label="Закрыть" @click="close"><X class="h-5 w-5" /></button>
        </header>
        <div class="overflow-auto p-4 sm:p-5">
          <p v-if="loading" class="py-8 text-center text-sm text-slate-500">Загружаем модели для сравнения…</p>
          <p v-else-if="error" role="alert" class="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{{ error }}</p>
          <p v-else-if="comparisonItems.length < 2 || comparisonItems.length > 4" class="rounded-lg bg-slate-50 px-3 py-2 text-sm text-slate-600">Выберите от двух до четырёх моделей для сравнения.</p>
          <template v-else>
            <label class="mb-3 inline-flex cursor-pointer items-center gap-2 text-sm font-medium text-slate-700">
              <input :checked="differencesOnly" type="checkbox" class="h-4 w-4 rounded border-slate-300 text-brand-600 focus:ring-brand-500" @change="setDifferencesOnly">
              Только различия
            </label>
            <div class="overflow-x-auto rounded-lg border border-slate-200">
              <table class="min-w-full text-left text-sm">
                <thead class="bg-slate-50 text-slate-700">
                  <tr>
                    <th scope="col" class="sticky left-0 z-10 min-w-36 bg-slate-50 px-3 py-3 text-xs font-semibold uppercase tracking-wide">Характеристика</th>
                    <th v-for="item in comparisonItems" :key="item.id" scope="col" class="min-w-48 px-3 py-3 align-top font-semibold text-slate-950">
                      <img v-if="item.main_image" :src="item.main_image" alt="" class="mb-2 h-16 w-full rounded-md bg-white object-contain">
                      {{ item.title }}
                    </th>
                  </tr>
                </thead>
                <tbody class="divide-y divide-slate-100">
                  <tr v-for="row in visibleRows" :key="row.key">
                    <th scope="row" class="sticky left-0 z-10 bg-white px-3 py-2.5 font-medium text-slate-600">{{ row.label }}</th>
                    <td v-for="(value, index) in row.values" :key="comparisonItems[index]!.id" class="px-3 py-2.5 text-slate-900">
                      <CatalogMoney v-if="row.money" :value="typeof value === 'number' ? value : null" />
                      <template v-else>{{ valueOrDash(value) }}</template>
                    </td>
                  </tr>
                  <tr v-if="!visibleRows.length"><td :colspan="comparisonItems.length + 1" class="px-3 py-6 text-center text-sm text-slate-500">У выбранных моделей нет различий по этим характеристикам.</td></tr>
                </tbody>
              </table>
            </div>
          </template>
        </div>
      </section>
    </div>
  </Teleport>
</template>
