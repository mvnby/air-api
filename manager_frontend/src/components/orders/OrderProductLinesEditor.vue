<script setup lang="ts">
import OrderMoney from './OrderMoney.vue';
import OrderLineEditorActions from './OrderLineEditorActions.vue';
import { Pencil, Trash2 } from 'lucide-vue-next';
import LineFormattedText from './LineFormattedText.vue';
import { computed, nextTick, ref, watch } from 'vue';
import { beginLineEdit, cancelLineEdit, commitLineEdit, focusInvalidLineEditor, focusLineEditor, hasLineEdits, lineErrors, lineKey } from './order-line-drafts';
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
const rows = new Map<number, HTMLElement>();
const touched = ref<Record<number, string[]>>({});
const errorsFor = (line: ProductLine): Record<string, string> => ({ ...lineErrors(line, line.product_query, true),
  ...((line.client_description?.length || 0) > 2000 ? { description: 'Не более 2000 символов' } : {}) });
const touch = (line: ProductLine, field: string) => {
  const key = lineKey(line);
  touched.value[key] = [...(touched.value[key] || []), field];
};
const fieldError = (line: ProductLine, field: string) => touched.value[lineKey(line)]?.includes(field) ? errorsFor(line)[field] : '';
const focusEditor = async (line: ProductLine) => { await nextTick(); await focusLineEditor(rows.get(lineKey(line))); };
const focusInvalidEditor = (line: ProductLine) => focusInvalidLineEditor(rows.get(lineKey(line)));
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
      if (appended && !appended.product_id && !appended.product_query.trim()) {
        appended.editor ||= { original: null };
        editingLine.value = appended;
        void focusEditor(appended);
      }
    }
  },
  { flush: 'sync' },
);

const editLine = (line: ProductLine) => {
  beginLineEdit(line);
  editingLine.value = line;
  void focusEditor(line);
};
const finishEditing = (line: ProductLine) => {
  touched.value[lineKey(line)] = ['title', 'quantity', 'price', 'cost', 'description'];
  if (Object.keys(errorsFor(line)).length) { void focusInvalidEditor(line); return; }
  commitLineEdit(line);
  editingLine.value = null;
};
const cancelEditing = (line: ProductLine) => {
  cancelLineEdit(lines.value, line);
  editingLine.value = null;
};
const isEditing = (line: ProductLine) => Boolean(line.editor) || editingLine.value === line;
const validateDrafts = () => {
  const drafts = lines.value.filter(line => line.editor && (line.editor.original || hasLineEdits([line])));
  for (const line of drafts) touched.value[lineKey(line)] = ['title', 'quantity', 'price', 'cost', 'description'];
  const invalid = drafts.find(line => Object.keys(errorsFor(line)).length);
  if (invalid) void focusInvalidEditor(invalid);
  return !invalid;
};
const commitDrafts = () => {
  for (const line of [...lines.value]) {
    if (!line.editor) continue;
    if (!line.editor.original && !hasLineEdits([line])) cancelLineEdit(lines.value, line);
    else commitLineEdit(line);
  }
  editingLine.value = null;
};
const cancelDrafts = () => {
  for (const line of [...lines.value]) if (line.editor) cancelLineEdit(lines.value, line);
  editingLine.value = null;
};
const focusDraft = () => {
  const invalid = lines.value.find(line => line.editor && touched.value[lineKey(line)]?.length && Object.keys(errorsFor(line)).length);
  const line = invalid || lines.value.find(line => hasLineEdits([line])) || lines.value.find(line => line.editor);
  if (line) void (invalid ? focusInvalidEditor(line) : focusEditor(line));
};
defineExpose({ validateDrafts, commitDrafts, cancelDrafts, focusDraft });

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
  <section class="order-lines" :class="compact ? '' : 'mt-2'" aria-label="Товары">
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
      <div v-for="(line, index) in lines" :key="lineKey(line)" :ref="element => { if (element) rows.set(lineKey(line), element as HTMLElement); else rows.delete(lineKey(line)); }" data-testid="product-line-row" class="relative" :class="compact ? 'bg-white dark:bg-slate-950' : 'rounded-xl border border-gray-200 bg-white p-3 shadow-sm'">
        <template v-if="!compact || isEditing(line)">
        <div class="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 px-3 py-2.5 dark:border-slate-800">
          <span class="text-xs font-semibold text-slate-600 dark:text-slate-300">{{ line.editor?.original === null ? 'Новый товар' : 'Редактирование товара' }}</span>
          <label v-if="hideActions && canManagePlatform" class="flex items-center gap-1 text-xs text-slate-500"><input v-model="searchInStock" type="checkbox" />Искать в наличии</label>
        </div>
        <div class="order-line-form grid grid-cols-6 items-start gap-3" :class="compact ? 'p-3' : ''">
          <label class="relative min-w-0 space-y-1 col-span-full">
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
              placeholder="Найти в каталоге или ввести название"
              :aria-invalid="Boolean(fieldError(line, 'title'))"
              :aria-describedby="fieldError(line, 'title') ? `product-title-error-${lineKey(line)}` : undefined"
              @focus="emit('focus', index)"
              @input="emit('input', index)"
              @blur="touch(line, 'title'); emit('blur', index)"
            />
            <p v-if="fieldError(line, 'title')" :id="`product-title-error-${lineKey(line)}`" class="text-xs text-red-600" role="alert">{{ fieldError(line, 'title') }}</p>
            <div v-if="!line.product_id && line.product_query.trim().length >= 2 && (productLookupLoading || suggestionsFor(index).length)" data-line-suggestions style="max-height:var(--order-line-suggestions-height,20rem)" class="relative mt-2 max-h-80 overflow-auto rounded-[12px] border border-gray-200 bg-white p-1 shadow-xl">
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
                <p class="break-words font-medium text-gray-900 dark:text-slate-100">{{ item.title }}</p>
                <p class="mt-1 flex flex-wrap items-center gap-1 text-[11px] text-gray-500 dark:text-slate-300">
                  <span><OrderMoney :value="item.price" /></span><span>·</span><span>{{ item.is_inverter ? 'Инвертор' : 'On/Off' }}</span><span>·</span>
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
          <label class="col-span-3 min-w-0 space-y-1">
            <span class="flex h-auto items-center px-1 text-xs font-medium text-gray-500 md:h-6">Цена</span>
            <input v-model.number="line.price" type="number" min="0" class="field-input w-full min-w-0 px-2 text-sm" placeholder="0" :aria-invalid="Boolean(fieldError(line, 'price'))" @blur="touch(line, 'price')" />
            <p v-if="fieldError(line, 'price')" class="text-xs text-red-600" role="alert">{{ fieldError(line, 'price') }}</p>
          </label>
          <label class="col-span-3 min-w-0 space-y-1">
            <span class="flex h-auto items-center whitespace-nowrap px-1 text-xs font-medium text-gray-500 md:h-6 md:text-[11px]">Кол-во</span>
            <input v-model.number="line.quantity" type="number" min="1" class="field-input w-full min-w-0 px-2 text-sm" placeholder="1" :aria-invalid="Boolean(fieldError(line, 'quantity'))" @blur="touch(line, 'quantity')" />
            <p v-if="fieldError(line, 'quantity')" class="text-xs text-red-600" role="alert">{{ fieldError(line, 'quantity') }}</p>
          </label>
          <label v-if="compact ? visibleCosts : !demoReadOnly" class="col-span-3 min-w-0 space-y-1">
            <span class="flex h-auto items-center px-1 text-xs font-medium text-gray-500 md:h-6">Себест.</span>
            <input v-model.number="line.cost" type="number" min="0" class="field-input w-full min-w-0 px-2 text-sm" placeholder="0" :aria-invalid="Boolean(fieldError(line, 'cost'))" @blur="touch(line, 'cost')" />
            <p v-if="fieldError(line, 'cost')" class="text-xs text-red-600" role="alert">{{ fieldError(line, 'cost') }}</p>
          </label>
          <div class="col-span-3 min-w-0 space-y-1">
            <span class="flex h-auto items-center px-1 text-xs font-medium text-gray-500 md:h-6">Итого</span>
            <div class="rounded-lg bg-gray-50 px-2 py-1.5 md:px-3 md:py-2"><p class="whitespace-nowrap text-sm font-semibold leading-tight text-gray-900 md:text-base"><OrderMoney :value="lineTotal(line)" /></p></div>
          </div>
          <label class="min-w-0 space-y-1 col-span-full">
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
              :aria-invalid="Boolean(fieldError(line, 'description'))" @blur="touch(line, 'description')"
              data-order-usage="order_product_description"
              class="field-input min-h-[64px] w-full min-w-0 resize-y text-sm leading-snug"
              rows="2"
              maxlength="2000"
              placeholder="Ключевые характеристики и уточнения для клиента"
            />
          </label>
          <p v-if="fieldError(line, 'description')" class="text-xs text-red-600 col-span-full" role="alert">{{ fieldError(line, 'description') }}</p>
          <p v-if="!line.product_id && line.product_query.trim()" role="note" class="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs leading-relaxed text-amber-800 col-span-full">Товар не связан с каталогом; наличие и цена не подтверждены</p>
          <p v-if="isPriceDifferent(line)" class="rounded-md border border-amber-300 bg-amber-50 px-2 py-1 text-xs text-amber-700 col-span-full">
            Цена строки отличается от каталожной (<OrderMoney :value="catalogPrice(line.product_id) || 0" />).
          </p>
          <div v-if="canManagePlatform && line.product_id" class="flex flex-wrap items-center gap-2 border-t border-gray-100 pt-2 col-span-full">
            <span v-if="supplyBadgeForLine(line)" class="inline-flex items-center gap-1 rounded-full bg-brand-50 px-2 py-1 text-xs font-semibold text-brand-700">
              Поставка: {{ supplyBadgeForLine(line)?.label }}
            </span>
            <span v-else-if="line.link_id" class="text-xs text-gray-500">Поставка не создана</span>
            <button type="button" data-order-usage="order_product_supply" class="rounded-lg border border-brand-200 px-3 py-1.5 text-xs font-semibold text-brand-700 hover:bg-brand-50 disabled:opacity-50" :disabled="!line.product_id || supplyActionLoadingLineId === line.link_id" @click="emit('supply', { line, intent: 'order' })">В поставку</button>
            <button type="button" data-order-usage="order_product_reserve" class="rounded-lg border border-indigo-200 px-3 py-1.5 text-xs font-semibold text-indigo-700 hover:bg-indigo-50 disabled:opacity-50" :disabled="!line.product_id || supplyActionLoadingLineId === line.link_id" @click="emit('supply', { line, intent: 'reserve' })">Забронировать</button>
          </div>
        </div>
        <OrderLineEditorActions
          :commit-label="line.editor?.original === null ? 'Добавить товар' : 'Применить'"
          :commit-aria-label="line.editor?.original === null ? `Добавить товар #${index + 1}` : `Применить: товар #${index + 1}`"
          :cancel-aria-label="`Отмена: товар #${index + 1}`"
          :remove-label="line.editor?.original !== null ? `Удалить товар #${index + 1}` : undefined"
          remove-usage="order_product_remove"
          @commit="finishEditing(line)" @cancel="cancelEditing(line)" @remove="emit('remove', index)"
        />
        </template>
        <div v-else class="order-line-row grid items-center gap-2 px-3 py-2.5 text-sm" :class="{ 'has-costs': visibleCosts }">
          <div class="order-line-name min-w-0">
            <p class="break-words text-sm font-semibold text-gray-900 dark:text-slate-100"><LineFormattedText :text="line.product_query || 'Новый товар'" /></p>
            <p v-if="!line.product_id" role="note" class="mt-1 text-xs leading-relaxed text-amber-700 dark:text-amber-300">Товар не связан с каталогом; наличие и цена не подтверждены</p>
            <p v-if="line.client_description" class="mt-0.5 whitespace-pre-wrap break-words text-xs font-normal leading-relaxed text-gray-500 dark:text-slate-400"><LineFormattedText :text="line.client_description" /></p>
          </div>
          <p class="order-line-quantity flex flex-col gap-1"><span class="order-line-mobile-label text-xs text-gray-500">Кол-во</span><span class="font-medium text-gray-700 dark:text-slate-300">{{ line.quantity }}</span></p>
          <p class="flex flex-col gap-1"><span class="order-line-mobile-label text-xs text-gray-500">Цена</span><span class="font-medium text-gray-700 dark:text-slate-300"><OrderMoney :value="line.price" /></span>
            <span
              v-if="priceAdjustment(line)"
              data-testid="product-price-adjustment"
              class="mt-0.5 block text-[11px] leading-tight"
              role="note"
              :class="priceAdjustment(line)?.direction === 'discount' ? 'text-emerald-700 dark:text-emerald-300' : 'text-amber-700 dark:text-amber-300'"
              :aria-label="priceAdjustment(line)?.details"
              :title="priceAdjustment(line)?.details"
            >{{ priceAdjustment(line)?.direction === 'discount' ? '↓' : '↑' }} {{ priceAdjustment(line)?.description }} {{ priceAdjustment(line)?.percentLabel }}</span>
          </p>
          <p class="flex flex-col gap-1"><span class="order-line-mobile-label text-xs text-gray-500">Итого</span><span class="font-semibold text-gray-900 dark:text-slate-100"><OrderMoney :value="lineTotal(line)" /></span></p>
          <p v-if="visibleCosts" class="order-line-cost flex flex-col gap-1"><span class="order-line-mobile-label text-xs text-gray-500">Себест.</span><span class="font-medium text-gray-700 dark:text-slate-300"><OrderMoney :value="line.cost" /></span></p>
          <div class="order-line-actions flex items-center justify-end gap-2">
            <button type="button" data-order-usage="order_product_edit" class="inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-lg border border-brand-200 bg-brand-50 text-brand-700 hover:bg-brand-100 focus-visible:ring-2 focus-visible:ring-brand-500 dark:border-brand-800 dark:bg-brand-950 dark:text-brand-300" :aria-label="`Редактировать товар #${index + 1}`" title="Редактировать" @click="editLine(line)"><Pencil class="h-5 w-5 shrink-0" aria-hidden="true" /></button>
            <button type="button" data-order-usage="order_product_remove" class="inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-lg border border-red-200 bg-red-50 text-red-600 hover:bg-red-100 focus-visible:ring-2 focus-visible:ring-red-500 dark:border-red-900 dark:bg-red-950/30 dark:text-red-400" :aria-label="`Удалить товар #${index + 1}`" title="Удалить" @click="emit('remove', index)"><Trash2 class="h-5 w-5 shrink-0" aria-hidden="true" /></button>
          </div>
        </div>
      </div>
    </div>
    <button v-if="!hideActions" type="button" data-testid="add-product-line" data-order-usage="order_product_add" class="btn-mini mt-3 justify-center" :class="compact ? '' : 'w-full'" @click="emit('add')">+ товар</button>
  </section>
</template>

<style scoped>
.order-lines { container-type: inline-size; }
.order-line-row { grid-template-columns: var(--line-columns, repeat(3, minmax(0, 1fr))); }
.order-line-row > * { text-align: var(--line-align, left); }
.order-line-row > .order-line-name { grid-column: var(--line-name-column, span 3 / span 3); text-align: left; }
.order-line-row > .order-line-quantity { text-align: var(--line-quantity-align, left); }
.order-line-cost { grid-column: var(--line-cost-column, span 2 / span 2); }
.order-line-mobile-label { display: var(--line-label-display, block); }
.order-line-actions { grid-column: var(--line-actions-column, span 3 / span 3); flex-direction: var(--line-actions-direction, row); }
.has-costs .order-line-actions { grid-column: var(--line-actions-column, auto); }
@container (min-width: 650px) {
  .order-line-form { grid-template-columns: repeat(12, minmax(0, 1fr)); }
  .order-line-row:not(.has-costs) {
    --line-columns: minmax(0, 1fr) 3.5rem 6rem 6.5rem 3rem;
    --line-name-column: auto;
    --line-actions-column: auto;
    --line-label-display: none;
    --line-align: right;
    --line-quantity-align: center;
    --line-actions-direction: column;
  }
}
@container (min-width: 750px) {
  .order-line-row.has-costs {
    --line-columns: minmax(0, 1fr) 3.5rem 6rem 6.5rem 6rem 3rem;
    --line-name-column: auto;
    --line-actions-column: auto;
    --line-cost-column: auto;
    --line-label-display: none;
    --line-align: right;
    --line-quantity-align: center;
    --line-actions-direction: column;
  }
}
</style>
