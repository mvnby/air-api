<script setup lang="ts">
import { computed } from 'vue';
import type { ProductLine, ProductOption } from './order-editor-types';
import { formatMoney } from './order-utils';
import { MANAGER_CAPABILITY, hasManagerCapability } from '../../manager-capabilities';
import { managerSession } from '../../services/manager-session';

type SupplyBadge = { label: string; requestId: number; status: string } | null;

const props = defineProps<{
  productOptions: ProductOption[];
  productLookupById: Record<number, ProductOption>;
  productLookupLoading: boolean;
  activeSuggestionIndex: number | null;
  supplyActionLoadingLineId: number | null;
  productsError?: string;
  supplyBadgeForLine: (line: ProductLine) => SupplyBadge;
}>();

const emit = defineEmits<{
  focus: [index: number];
  input: [index: number];
  blur: [index: number];
  select: [payload: { index: number; option: ProductOption }];
  open: [index: number];
  remove: [index: number];
  add: [];
  supply: [payload: { line: ProductLine; intent: 'order' | 'reserve' }];
}>();

const lines = defineModel<ProductLine[]>('lines', { required: true });
const searchInStock = defineModel<boolean>('searchInStock', { required: true });
const canManagePlatform = computed(() => hasManagerCapability(
  managerSession.auth.value,
  MANAGER_CAPABILITY.platformManage,
));

const suggestionsFor = (index: number) => (
  props.activeSuggestionIndex === index ? props.productOptions.slice(0, 10) : []
);
const catalogPrice = (productId: number) => props.productLookupById[productId]?.price ?? null;
const isPriceDifferent = (line: ProductLine) => {
  const price = catalogPrice(line.product_id);
  return price !== null && Number(line.price) !== Number(price);
};
const lineTotal = (line: ProductLine) => Number(line.quantity || 0) * Number(line.price || 0);
</script>

<template>
  <section class="mt-2">
    <div class="mb-2 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
      <div class="flex flex-wrap items-center gap-3">
        <h4 class="text-md font-semibold text-gray-800">Товары</h4>
        <label v-if="canManagePlatform" class="flex cursor-pointer items-center gap-1 rounded border border-gray-200 bg-white px-2 py-1 text-xs text-gray-600 shadow-sm transition-colors hover:bg-gray-50">
          <input v-model="searchInStock" type="checkbox" class="h-3 w-3 rounded border-gray-300 text-teal-600 focus:ring-teal-500" />
          В наличии
        </label>
      </div>
    </div>
    <p v-if="productsError" class="mb-2 text-xs text-red-300">{{ productsError }}</p>
    <div class="space-y-2">
      <div v-for="(line, index) in lines" :key="`product-${index}`" class="relative rounded-xl border border-gray-200 bg-white p-3 shadow-sm">
        <button type="button" class="absolute -right-2 -top-2 z-10 inline-flex h-8 w-8 items-center justify-center rounded-full border border-red-200 bg-red-50 text-lg font-bold text-red-600 shadow-sm transition-colors hover:bg-red-100" :aria-label="`Удалить товар #${index + 1}`" title="Удалить товар" @click="emit('remove', index)">
          ×
        </button>
        <div class="grid grid-cols-6 gap-2 md:grid-cols-12 md:items-start">
          <label class="relative col-span-6 space-y-1 md:col-span-5">
            <span class="flex items-center justify-between gap-2 px-1 text-xs font-medium text-gray-500 md:h-6">
              <span>Название</span>
              <button v-if="line.product_id && canManagePlatform" class="text-xs font-semibold text-teal-700 hover:text-teal-900" type="button" @click="emit('open', index)">
                Открыть ↗
              </button>
            </span>
            <textarea
              v-model="line.product_query"
              class="field-input min-h-[44px] resize-none overflow-hidden text-sm leading-snug focus:min-h-[120px] focus:resize-y focus:overflow-auto sm:text-base"
              rows="1"
              placeholder="Поиск и выбор товара"
              @focus="emit('focus', index)"
              @input="emit('input', index)"
              @blur="emit('blur', index)"
            />
            <div v-if="!line.product_id && line.product_query.trim().length >= 2 && (productLookupLoading || suggestionsFor(index).length)" class="absolute left-0 right-0 top-full z-20 mt-1 max-h-56 overflow-auto rounded-[12px] border border-gray-200 bg-white p-1 shadow-xl">
              <div v-if="productLookupLoading" class="px-3 py-2 text-xs text-gray-500">Поиск товаров...</div>
              <button
                v-for="item in suggestionsFor(index)"
                :key="`product-suggest-${index}-${item.id}`"
                type="button"
                :data-testid="`select-product-${item.id}`"
                class="mb-1 block w-full rounded-[12px] px-3 py-2 text-left text-xs text-gray-700 hover:bg-slate-100 dark:hover:bg-slate-800 last:mb-0"
                @mousedown.prevent
                @click="emit('select', { index, option: item })"
              >
                <p class="truncate font-medium text-gray-900 dark:text-slate-100">{{ item.title }}</p>
                <p class="mt-1 flex flex-wrap items-center gap-1 text-[11px] text-gray-500 dark:text-slate-300">
                  <span>{{ formatMoney(item.price) }}</span><span>·</span><span>{{ item.is_inverter ? 'Инвертор' : 'On/Off' }}</span><span>·</span>
                  <template v-if="item.vitebsk_qty > 0 || item.minsk_qty > 0">
                    <span v-if="item.vitebsk_qty > 0" class="rounded bg-emerald-50 px-1 font-medium text-emerald-600">Вит: {{ item.vitebsk_qty }}</span>
                    <span v-if="item.minsk_qty > 0" class="rounded bg-blue-50 px-1 font-medium text-blue-500">Минск: {{ item.minsk_qty }}</span>
                  </template>
                  <template v-else>
                    <span v-if="item.availability_status === 'check_availability'" class="font-medium text-amber-500">Уточнять</span>
                    <span v-else class="text-gray-400">Нет в наличии</span>
                  </template>
                </p>
              </button>
            </div>
          </label>
          <label class="col-span-4 space-y-1 md:col-span-2">
            <span class="flex h-auto items-center px-1 text-xs font-medium text-gray-500 md:h-6">Цена</span>
            <input v-model.number="line.price" type="number" min="0" class="field-input" placeholder="0" />
          </label>
          <label class="col-span-2 space-y-1 md:col-span-1">
            <span class="flex h-auto items-center whitespace-nowrap px-1 text-xs font-medium text-gray-500 md:h-6 md:text-[11px]">Кол-во</span>
            <input v-model.number="line.quantity" type="number" min="1" class="field-input" placeholder="1" />
          </label>
          <label class="col-span-3 space-y-1 md:col-span-2">
            <span class="flex h-auto items-center px-1 text-xs font-medium text-gray-500 md:h-6">Себест.</span>
            <input v-model.number="line.cost" type="number" min="0" class="field-input" placeholder="0" />
          </label>
          <div class="col-span-3 space-y-1 md:col-span-2">
            <span class="flex h-auto items-center px-1 text-xs font-medium text-gray-500 md:h-6">Итого</span>
            <div class="rounded-lg bg-gray-50 px-3 py-2"><p class="whitespace-nowrap text-base font-semibold leading-tight text-gray-900">{{ formatMoney(lineTotal(line)) }}</p></div>
          </div>
          <p v-if="isPriceDifferent(line)" class="col-span-6 rounded-md border border-amber-300 bg-amber-50 px-2 py-1 text-xs text-amber-700 md:col-span-12">
            Цена строки отличается от каталожной ({{ formatMoney(catalogPrice(line.product_id) || 0) }}).
          </p>
          <div v-if="canManagePlatform" class="col-span-6 flex flex-wrap items-center gap-2 border-t border-gray-100 pt-2 md:col-span-12">
            <span v-if="supplyBadgeForLine(line)" class="inline-flex items-center gap-1 rounded-full bg-teal-50 px-2 py-1 text-xs font-semibold text-teal-700">
              Поставка: {{ supplyBadgeForLine(line)?.label }}
            </span>
            <span v-else-if="line.link_id" class="text-xs text-gray-500">Поставка не создана</span>
            <button type="button" class="rounded-lg border border-teal-200 px-3 py-1.5 text-xs font-semibold text-teal-700 hover:bg-teal-50 disabled:opacity-50" :disabled="!line.product_id || supplyActionLoadingLineId === line.link_id" @click="emit('supply', { line, intent: 'order' })">В поставку</button>
            <button type="button" class="rounded-lg border border-indigo-200 px-3 py-1.5 text-xs font-semibold text-indigo-700 hover:bg-indigo-50 disabled:opacity-50" :disabled="!line.product_id || supplyActionLoadingLineId === line.link_id" @click="emit('supply', { line, intent: 'reserve' })">Забронировать</button>
          </div>
        </div>
      </div>
    </div>
    <button type="button" data-testid="add-product-line" class="btn-mini mt-3 w-full justify-center" @click="emit('add')">+ товар</button>
  </section>
</template>
