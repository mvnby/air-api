<script setup lang="ts">
import LineFormattedText from './LineFormattedText.vue';
import { computed, ref, watch } from 'vue';
import type { ProductLine, ProductOption } from './order-editor-types';
import { formatMoney } from './order-utils';
import { MANAGER_CAPABILITY, hasManagerCapability } from '../../manager-capabilities';
import { managerSession } from '../../services/manager-session';
import { useDemoReadOnly } from '../../services/manager-demo';

type SupplyBadge = { label: string; requestId: number; status: string } | null;

const props = defineProps<{
  productOptions: ProductOption[];
  productLookupById: Record<number, ProductOption>;
  productLookupLoading: boolean;
  activeSuggestionIndex: number | null;
  supplyActionLoadingLineId: number | null;
  productsError?: string;
  catalogAvailable?: boolean;
  catalogOpening?: boolean;
  catalogNeedsSave?: boolean;
  compact?: boolean;
  hideActions?: boolean;
  showCosts?: boolean;
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
  catalog: [];
  fillDescription: [index: number];
  supply: [payload: { line: ProductLine; intent: 'order' | 'reserve' }];
}>();

const lines = defineModel<ProductLine[]>('lines', { required: true });
const searchInStock = defineModel<boolean>('searchInStock', { required: true });
const canManagePlatform = computed(() => hasManagerCapability(
  managerSession.auth.value,
  MANAGER_CAPABILITY.platformManage,
));
const demoReadOnly = useDemoReadOnly();
const editingLine = ref<ProductLine | null>(null);
const visibleCosts = computed(() => Boolean(props.showCosts && !demoReadOnly.value));

watch(
  () => [...lines.value],
  (nextLines, previousLines) => {
    if (editingLine.value && !nextLines.includes(editingLine.value)) {
      editingLine.value = null;
    }
    if (
      props.compact
      && nextLines.length > previousLines.length
      && nextLines.length === previousLines.length + 1
    ) {
      const appended = nextLines[nextLines.length - 1];
      if (appended && !appended.product_id && !appended.product_query.trim()) editingLine.value = appended;
    }
  },
  { flush: 'sync' },
);

const editLine = (line: ProductLine) => { editingLine.value = line; };
const finishEditing = () => { editingLine.value = null; };
const isEditing = (line: ProductLine) => editingLine.value === line;

const suggestionsFor = (index: number) => (
  props.activeSuggestionIndex === index ? props.productOptions.slice(0, 10) : []
);
const catalogPrice = (productId: number) => {
  const option = props.productLookupById[productId];
  if (!option || option.catalog_price_known === false) return null;
  return option.price ?? null;
};
const priceAdjustment = (line: ProductLine) => {
  const catalog = Number(catalogPrice(line.product_id));
  const price = Number(line.price);
  if (!Number.isFinite(catalog) || !Number.isFinite(price) || catalog <= 0 || price <= 0) return null;

  const difference = Number((price - catalog).toFixed(2));
  if (difference === 0) return null;

  const amount = Math.abs(difference);
  const percent = Number((amount / catalog * 100).toFixed(1));
  const direction = difference < 0 ? 'discount' : 'markup';
  const description = direction === 'discount' ? 'Скидка' : 'Наценка';
  const percentLabel = `${percent.toLocaleString('ru-RU', { maximumFractionDigits: 1 })}%`;
  const details = `${description} ${formatMoney(amount)} (${percentLabel}) относительно каталожной цены ${formatMoney(catalog)}`;
  return { direction, description, percentLabel, details };
};
const isPriceDifferent = (line: ProductLine) => {
  const price = catalogPrice(line.product_id);
  return price !== null && Number(line.price) !== Number(price);
};
const productQueryRows = (query: string) => Math.min(5, Math.max(2, Math.ceil(query.length / 36)));
const lineTotal = (line: ProductLine) => Number(line.quantity || 0) * Number(line.price || 0);
</script>

<template>
  <section :class="compact ? '' : 'mt-2'" aria-label="Товары">
    <div v-if="!hideActions" class="mb-2 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
      <div class="flex flex-wrap items-center gap-3">
        <h4 class="text-md font-semibold text-gray-800" :class="compact ? 'text-sm' : ''">Товары</h4>
        <button v-if="catalogAvailable" type="button" class="rounded-lg border border-brand-200 bg-brand-50 px-3 py-2 text-xs font-semibold text-brand-800 disabled:opacity-50" :disabled="catalogOpening" @click="emit('catalog')">{{ catalogOpening ? 'Открываем подбор…' : catalogNeedsSave ? 'Сохранить и подобрать' : 'Подобрать по параметрам' }}</button>
        <label v-if="canManagePlatform" class="flex cursor-pointer items-center gap-1 rounded border border-gray-200 bg-white px-2 py-1 text-xs text-gray-600 shadow-sm transition-colors hover:bg-gray-50">
          <input v-model="searchInStock" type="checkbox" class="h-3 w-3 rounded border-gray-300 text-brand-600 focus:ring-brand-500" />
          В наличии
        </label>
      </div>
    </div>
    <slot v-if="!hideActions" name="source-equipment" />
    <p v-if="productsError" class="mb-2 text-xs text-red-300">{{ productsError }}</p>
    <div :class="compact ? 'divide-y divide-slate-100 dark:divide-slate-800' : 'space-y-2'">
      <div v-for="(line, index) in lines" :key="`product-${index}`" data-testid="product-line-row" class="relative" :class="compact ? 'bg-white dark:bg-slate-950' : 'rounded-xl border border-gray-200 bg-white p-3 shadow-sm'">
        <template v-if="!compact || isEditing(line)">
        <button v-if="!compact" type="button" data-order-usage="order_product_remove" class="absolute -right-2 -top-2 z-10 inline-flex h-8 w-8 items-center justify-center rounded-full border border-red-200 bg-red-50 text-lg font-bold text-red-600 shadow-sm transition-colors hover:bg-red-100" :aria-label="`Удалить товар #${index + 1}`" title="Удалить товар" @click="emit('remove', index)">
          ×
        </button>
        <div v-if="compact" class="mb-2 flex items-center justify-between gap-2 px-3 pt-3">
          <span class="text-xs font-semibold text-gray-500">Редактирование товара</span>
          <label v-if="hideActions && canManagePlatform" class="ml-auto flex items-center gap-1 text-xs text-slate-500"><input v-model="searchInStock" type="checkbox" />Искать в наличии</label>
          <button type="button" class="rounded-lg bg-brand-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-brand-700" :aria-label="`Готово: товар #${index + 1}`" @click="finishEditing">Готово</button>
        </div>
        <div class="grid grid-cols-6 gap-2 md:grid-cols-12 md:items-start" :class="compact ? 'px-3 pb-3' : ''">
          <label class="relative col-span-6 min-w-0 space-y-1 md:col-span-5">
            <span class="flex items-center justify-between gap-2 px-1 text-xs font-medium text-gray-500 md:h-6">
              <span>Название</span>
              <button v-if="line.product_id && canManagePlatform" type="button" data-order-usage="order_product_open_catalog" class="text-xs font-semibold text-brand-700 hover:text-brand-900" @click="emit('open', index)">
                Открыть ↗
              </button>
            </span>
            <textarea
              v-model="line.product_query"
              class="field-input min-h-[56px] w-full min-w-0 resize-y overflow-y-auto text-sm leading-snug sm:text-base"
              :rows="productQueryRows(line.product_query)"
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
                data-order-usage="order_product_select"
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
          <label class="col-span-4 min-w-0 space-y-1 md:col-span-2">
            <span class="flex h-auto items-center px-1 text-xs font-medium text-gray-500 md:h-6">Цена</span>
            <input v-model.number="line.price" type="number" min="0" class="field-input w-full min-w-0 px-2 text-sm" placeholder="0" />
          </label>
          <label class="col-span-2 min-w-0 space-y-1 md:col-span-1">
            <span class="flex h-auto items-center whitespace-nowrap px-1 text-xs font-medium text-gray-500 md:h-6 md:text-[11px]">Кол-во</span>
            <input v-model.number="line.quantity" type="number" min="1" class="field-input w-full min-w-0 px-2 text-sm" placeholder="1" />
          </label>
          <label v-if="compact ? visibleCosts : !demoReadOnly" class="col-span-3 min-w-0 space-y-1 md:col-span-2">
            <span class="flex h-auto items-center px-1 text-xs font-medium text-gray-500 md:h-6">Себест.</span>
            <input v-model.number="line.cost" type="number" min="0" class="field-input w-full min-w-0 px-2 text-sm" placeholder="0" />
          </label>
          <div class="col-span-3 space-y-1 md:col-span-2">
            <span class="flex h-auto items-center px-1 text-xs font-medium text-gray-500 md:h-6">Итого</span>
            <div class="rounded-lg bg-gray-50 px-2 py-1.5 md:px-3 md:py-2"><p class="whitespace-nowrap text-sm font-semibold leading-tight text-gray-900 md:text-base">{{ formatMoney(lineTotal(line)) }}</p></div>
          </div>
          <label class="col-span-6 min-w-0 space-y-1 md:col-span-12">
            <span class="flex items-center justify-between gap-2 px-1 text-xs font-medium text-gray-500">
              <span>Описание для клиента</span>
              <button
                v-if="line.product_id"
                type="button"
                data-order-usage="order_product_fill_description"
                class="text-xs font-semibold text-brand-700 hover:text-brand-900"
                @click="emit('fillDescription', index)"
              >
                Заполнить из каталога
              </button>
            </span>
            <textarea
              v-model="line.client_description"
              data-order-usage="order_product_description"
              class="field-input min-h-[64px] w-full min-w-0 resize-y text-sm leading-snug"
              rows="2"
              maxlength="2000"
              placeholder="Ключевые характеристики и уточнения для клиента"
            />
          </label>
          <p v-if="isPriceDifferent(line)" class="col-span-6 rounded-md border border-amber-300 bg-amber-50 px-2 py-1 text-xs text-amber-700 md:col-span-12">
            Цена строки отличается от каталожной ({{ formatMoney(catalogPrice(line.product_id) || 0) }}).
          </p>
          <div v-if="canManagePlatform" class="col-span-6 flex flex-wrap items-center gap-2 border-t border-gray-100 pt-2 md:col-span-12">
            <span v-if="supplyBadgeForLine(line)" class="inline-flex items-center gap-1 rounded-full bg-brand-50 px-2 py-1 text-xs font-semibold text-brand-700">
              Поставка: {{ supplyBadgeForLine(line)?.label }}
            </span>
            <span v-else-if="line.link_id" class="text-xs text-gray-500">Поставка не создана</span>
            <button type="button" data-order-usage="order_product_supply" class="rounded-lg border border-brand-200 px-3 py-1.5 text-xs font-semibold text-brand-700 hover:bg-brand-50 disabled:opacity-50" :disabled="!line.product_id || supplyActionLoadingLineId === line.link_id" @click="emit('supply', { line, intent: 'order' })">В поставку</button>
            <button type="button" data-order-usage="order_product_reserve" class="rounded-lg border border-indigo-200 px-3 py-1.5 text-xs font-semibold text-indigo-700 hover:bg-indigo-50 disabled:opacity-50" :disabled="!line.product_id || supplyActionLoadingLineId === line.link_id" @click="emit('supply', { line, intent: 'reserve' })">Забронировать</button>
          </div>
        </div>
        </template>
        <div v-else class="grid grid-cols-3 gap-3 px-3 py-2.5 text-sm md:items-center md:gap-2" :class="visibleCosts ? 'md:grid-cols-[minmax(0,1fr)_3.5rem_6rem_6.5rem_6rem_4.5rem]' : 'md:grid-cols-[minmax(0,1fr)_3.5rem_6rem_6.5rem_4.5rem]'">
          <div class="col-span-3 min-w-0 md:col-auto">
            <p class="break-words text-sm font-semibold text-gray-900 dark:text-slate-100"><LineFormattedText :text="line.product_query || 'Новый товар'" /></p>
            <p v-if="line.client_description" class="mt-0.5 whitespace-pre-wrap break-words text-xs font-normal leading-relaxed text-gray-500 dark:text-slate-400"><LineFormattedText :text="line.client_description" /></p>
          </div>
          <p class="flex flex-col gap-1 md:block md:text-center"><span class="text-xs text-gray-500 md:hidden">Кол-во</span><span class="font-medium text-gray-700 dark:text-slate-300">{{ line.quantity }}</span></p>
          <p class="flex flex-col gap-1 md:block md:text-right"><span class="text-xs text-gray-500 md:hidden">Цена</span><span class="font-medium text-gray-700 dark:text-slate-300">{{ formatMoney(line.price) }}</span>
            <span
              v-if="priceAdjustment(line)"
              data-testid="product-price-adjustment"
              class="mt-0.5 block text-[11px] leading-tight md:whitespace-nowrap"
              role="note"
              :class="priceAdjustment(line)?.direction === 'discount' ? 'text-emerald-700 dark:text-emerald-300' : 'text-amber-700 dark:text-amber-300'"
              :aria-label="priceAdjustment(line)?.details"
              :title="priceAdjustment(line)?.details"
            >{{ priceAdjustment(line)?.direction === 'discount' ? '↓' : '↑' }} {{ priceAdjustment(line)?.description }} {{ priceAdjustment(line)?.percentLabel }}</span>
          </p>
          <p class="flex flex-col gap-1 md:block md:text-right"><span class="text-xs text-gray-500 md:hidden">Итого</span><span class="font-semibold text-gray-900 dark:text-slate-100">{{ formatMoney(lineTotal(line)) }}</span></p>
          <p v-if="visibleCosts" class="col-span-2 flex flex-col gap-1 md:col-auto md:block md:text-right"><span class="text-xs text-gray-500 md:hidden">Себест.</span><span class="font-medium text-gray-700 dark:text-slate-300">{{ formatMoney(line.cost) }}</span></p>
          <div class="flex justify-end gap-1 md:justify-center" :class="visibleCosts ? 'md:col-auto' : 'col-span-3 md:col-auto'">
            <button type="button" data-order-usage="order_product_edit" class="inline-flex h-8 w-8 items-center justify-center rounded-lg text-brand-700 hover:bg-brand-50" :aria-label="`Редактировать товар #${index + 1}`" title="Редактировать" @click="editLine(line)">✎</button>
            <button type="button" data-order-usage="order_product_remove" class="inline-flex h-8 w-8 items-center justify-center rounded-lg text-red-600 hover:bg-red-50" :aria-label="`Удалить товар #${index + 1}`" title="Удалить" @click="emit('remove', index)">×</button>
          </div>
        </div>
      </div>
    </div>
    <button v-if="!hideActions" type="button" data-testid="add-product-line" data-order-usage="order_product_add" class="btn-mini mt-3 justify-center" :class="compact ? '' : 'w-full'" @click="emit('add')">+ товар</button>
  </section>
</template>
