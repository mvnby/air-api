<script setup lang="ts">
import { computed, nextTick, reactive, ref, watch } from 'vue';
import { watchDebounced } from '@vueuse/core';
import { LoaderCircle, Search, ShieldCheck, X } from 'lucide-vue-next';
import {
  ManagerBrandsService,
  ManagerService,
  type ManagerBrandResponse,
  type ManagerBrandSeriesResponse,
  type ManagerCatalogProductItemResponse,
  type ManagerWarrantyPolicyPayload,
  type ManagerWarrantyPolicyResponse,
  type SupplierResponse,
} from '../../client';
import { getApiErrorMessage } from '../../utils/api-errors';
import { useDialogA11y } from './useDialogA11y';

type ScopeType = 'supplier' | 'brand' | 'series' | 'product';

const props = defineProps<{
  open: boolean;
  policy: ManagerWarrantyPolicyResponse | null;
  suppliers: SupplierResponse[];
  brands: ManagerBrandResponse[];
  saving: boolean;
  error?: string;
}>();

const emit = defineEmits<{
  close: [];
  save: [payload: ManagerWarrantyPolicyPayload];
}>();

const form = reactive({
  name: '',
  coverageType: 'supplier',
  scopeType: 'supplier' as ScopeType,
  supplierId: null as number | null,
  brandId: null as number | null,
  seriesId: null as number | null,
  productId: null as number | null,
  productLabel: '',
  durationMonths: '' as string | number,
  startEvent: 'commissioning',
  maintenanceRequired: false,
  maintenanceIntervalMonths: '' as string | number,
  gracePeriodDays: 0 as string | number,
  allowedMaintenanceProvider: 'any',
  terms: '',
  isActive: true,
});

const series = ref<ManagerBrandSeriesResponse[]>([]);
const seriesLoading = ref(false);
const seriesError = ref('');
const productQuery = ref('');
const productResults = ref<ManagerCatalogProductItemResponse[]>([]);
const productLoading = ref(false);
const productError = ref('');
const productSearchCompleted = ref(false);
const activeProductIndex = ref(-1);
const dialogRef = ref<HTMLElement | null>(null);
const closeButtonRef = ref<HTMLElement | null>(null);
let seriesRequestId = 0;
let productRequestId = 0;
let resettingForm = false;

const inferScope = (policy: ManagerWarrantyPolicyResponse | null): ScopeType => {
  if (policy?.product_id) return 'product';
  if (policy?.series_id) return 'series';
  if (policy?.brand_id) return 'brand';
  return 'supplier';
};

const loadSeries = async (brandId: number | null, selectedSeriesId?: number | null) => {
  const requestId = ++seriesRequestId;
  series.value = [];
  seriesError.value = '';
  seriesLoading.value = Boolean(brandId);
  if (!brandId) return;
  try {
    const response = await ManagerBrandsService.listManagerBrandSeries(brandId);
    if (requestId !== seriesRequestId) return;
    series.value = response.items || [];
    if (selectedSeriesId && series.value.some((item) => item.id === selectedSeriesId)) {
      form.seriesId = selectedSeriesId;
    }
  } catch (cause) {
    if (requestId !== seriesRequestId) return;
    seriesError.value = getApiErrorMessage(cause) || 'Не удалось загрузить серии';
  } finally {
    if (requestId === seriesRequestId) seriesLoading.value = false;
  }
};

const resetFromPolicy = async (policy: ManagerWarrantyPolicyResponse | null) => {
  resettingForm = true;
  seriesRequestId += 1;
  productRequestId += 1;
  series.value = [];
  seriesLoading.value = false;
  seriesError.value = '';
  productResults.value = [];
  productLoading.value = false;
  productError.value = '';
  productSearchCompleted.value = false;
  activeProductIndex.value = -1;
  const scopeType = inferScope(policy);
  Object.assign(form, {
    name: policy?.name || '',
    coverageType: policy?.coverage_type || 'supplier',
    scopeType,
    supplierId: policy?.supplier_id ?? null,
    brandId: policy?.brand_id ?? policy?.series_brand_id ?? null,
    seriesId: policy?.series_id ?? null,
    productId: policy?.product_id ?? null,
    productLabel: policy?.product_title || (policy?.product_id ? `Товар #${policy.product_id}` : ''),
    durationMonths: policy?.duration_months ?? '',
    startEvent: policy?.start_event || 'commissioning',
    maintenanceRequired: Boolean(policy?.maintenance_required),
    maintenanceIntervalMonths: policy?.maintenance_interval_months ?? '',
    gracePeriodDays: policy?.grace_period_days ?? 0,
    allowedMaintenanceProvider: policy?.allowed_maintenance_provider || 'any',
    terms: policy?.terms || '',
    isActive: policy?.is_active !== false,
  });
  productQuery.value = form.productLabel;
  productResults.value = [];
  if (scopeType === 'series' && form.brandId) void loadSeries(form.brandId, form.seriesId);
  await nextTick();
  resettingForm = false;
};

const numberOrNull = (value: string | number) => {
  if (value === '') return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
};

const canSave = computed(() => {
  if (!form.name.trim() || !numberOrNull(form.durationMonths)) return false;
  if (form.maintenanceRequired && !numberOrNull(form.maintenanceIntervalMonths)) return false;
  if (form.scopeType === 'supplier') return Boolean(form.supplierId);
  if (form.scopeType === 'brand') return Boolean(form.brandId);
  if (form.scopeType === 'series') return Boolean(form.seriesId);
  return Boolean(form.productId);
});

const selectProduct = (product: ManagerCatalogProductItemResponse) => {
  form.productId = product.id;
  form.productLabel = product.title;
  productQuery.value = product.title;
  productResults.value = [];
  activeProductIndex.value = -1;
  productError.value = '';
};

const close = () => {
  if (props.saving) return;
  seriesRequestId += 1;
  productRequestId += 1;
  emit('close');
};

const onProductKeydown = (event: KeyboardEvent) => {
  if (!productResults.value.length) return;
  if (event.key === 'ArrowDown') {
    event.preventDefault();
    activeProductIndex.value = Math.min(activeProductIndex.value + 1, productResults.value.length - 1);
  } else if (event.key === 'ArrowUp') {
    event.preventDefault();
    activeProductIndex.value = Math.max(activeProductIndex.value - 1, 0);
  } else if (event.key === 'Enter' && activeProductIndex.value >= 0) {
    event.preventDefault();
    const product = productResults.value[activeProductIndex.value];
    if (product) selectProduct(product);
  }
};

const submit = () => {
  if (!canSave.value || props.saving) return;
  emit('save', {
    name: form.name.trim(),
    coverage_type: form.coverageType,
    supplier_id: form.supplierId,
    brand_id: form.scopeType === 'brand' ? form.brandId : null,
    series_id: form.scopeType === 'series' ? form.seriesId : null,
    product_id: form.scopeType === 'product' ? form.productId : null,
    duration_months: numberOrNull(form.durationMonths),
    start_event: form.startEvent,
    maintenance_required: form.maintenanceRequired,
    maintenance_interval_months: form.maintenanceRequired ? numberOrNull(form.maintenanceIntervalMonths) : null,
    grace_period_days: numberOrNull(form.gracePeriodDays) || 0,
    allowed_maintenance_provider: form.allowedMaintenanceProvider,
    terms: form.terms.trim() || null,
    is_active: form.isActive,
  });
};

watch(() => props.open, (open) => {
  if (open) void resetFromPolicy(props.policy);
});

watch(() => form.scopeType, (scopeType) => {
  if (resettingForm) return;
  form.brandId = null;
  form.seriesId = null;
  form.productId = null;
  form.productLabel = '';
  productQuery.value = '';
  productResults.value = [];
  if (scopeType === 'supplier') form.supplierId = null;
});

watch(() => form.brandId, (brandId) => {
  if (resettingForm) return;
  if (form.scopeType !== 'series') return;
  form.seriesId = null;
  void loadSeries(brandId);
}, { flush: 'sync' });

watch(productQuery, (query) => {
  productRequestId += 1;
  productLoading.value = false;
  productError.value = '';
  productSearchCompleted.value = false;
  activeProductIndex.value = -1;
  productResults.value = [];
  if (query.trim() !== form.productLabel) form.productId = null;
}, { flush: 'sync' });

watchDebounced(productQuery, async (query) => {
  const normalizedQuery = query.trim();
  if (form.scopeType !== 'product' || normalizedQuery.length < 2 || normalizedQuery === form.productLabel) return;
  form.productId = null;
  const requestId = ++productRequestId;
  productLoading.value = true;
  productError.value = '';
  try {
    const response = await ManagerService.smartSearchProducts(normalizedQuery, 12);
    if (requestId !== productRequestId || productQuery.value.trim() !== normalizedQuery || form.scopeType !== 'product') return;
    productResults.value = response.items || [];
    activeProductIndex.value = productResults.value.length ? 0 : -1;
    productSearchCompleted.value = true;
  } catch (cause) {
    if (requestId !== productRequestId || productQuery.value.trim() !== normalizedQuery) return;
    productError.value = getApiErrorMessage(cause) || 'Не удалось найти товар';
  } finally {
    if (requestId === productRequestId) productLoading.value = false;
  }
}, { debounce: 350 });

useDialogA11y({
  open: computed(() => props.open),
  dialogRef,
  initialFocusRef: closeButtonRef,
  close,
});
</script>

<template>
  <Teleport to="body">
    <div v-if="open" class="fixed inset-0 z-[130] flex items-end justify-center bg-black/50 sm:items-center sm:p-4" @click.self="close">
      <section ref="dialogRef" class="flex max-h-[94vh] w-full max-w-2xl flex-col overflow-hidden rounded-t-lg border border-slate-200 bg-white shadow-2xl sm:rounded-lg dark:border-slate-700 dark:bg-slate-900" role="dialog" aria-modal="true" aria-labelledby="warranty-policy-dialog-title" tabindex="-1">
        <header class="z-20 flex shrink-0 items-center justify-between gap-3 border-b border-slate-200 bg-white px-4 py-3 dark:border-slate-700 dark:bg-slate-900">
          <div class="flex min-w-0 items-center gap-2">
            <ShieldCheck class="h-5 w-5 shrink-0 text-teal-700 dark:text-teal-300" />
            <h2 id="warranty-policy-dialog-title" class="truncate text-base font-semibold text-slate-950 dark:text-white">{{ policy ? 'Изменить правило' : 'Новое правило гарантии' }}</h2>
          </div>
          <button ref="closeButtonRef" type="button" class="inline-flex h-8 w-8 items-center justify-center rounded-md text-slate-500 hover:bg-slate-100 disabled:opacity-50 dark:hover:bg-slate-800" :disabled="saving" aria-label="Закрыть" @click="close"><X class="h-4 w-4" /></button>
        </header>

        <form class="min-h-0 flex-1 space-y-4 overflow-y-auto p-4" @submit.prevent="submit">
          <label class="field-label">Название правила<input v-model="form.name" class="field-input" placeholder="Например: MDV Integra Pro, 4 года" /></label>

          <div class="grid grid-cols-2 gap-2" aria-label="Тип гарантии">
            <button type="button" class="min-h-10 rounded-md border px-3 text-sm font-semibold" :class="form.coverageType === 'supplier' ? 'border-teal-600 bg-teal-50 text-teal-800 dark:bg-teal-950/40 dark:text-teal-200' : 'border-slate-200 text-slate-600 dark:border-slate-700 dark:text-slate-300'" @click="form.coverageType = 'supplier'">Оборудование</button>
            <button type="button" class="min-h-10 rounded-md border px-3 text-sm font-semibold" :class="form.coverageType === 'mvn_work' ? 'border-teal-600 bg-teal-50 text-teal-800 dark:bg-teal-950/40 dark:text-teal-200' : 'border-slate-200 text-slate-600 dark:border-slate-700 dark:text-slate-300'" @click="form.coverageType = 'mvn_work'">Работы MVN</button>
          </div>

          <div class="grid gap-3 sm:grid-cols-2">
            <label class="field-label">Применяется к<select v-model="form.scopeType" class="field-input"><option value="supplier">Поставщику</option><option value="brand">Бренду</option><option value="series">Серии</option><option value="product">Конкретному товару</option></select></label>
            <label v-if="form.scopeType !== 'supplier'" class="field-label">Поставщик, если правило только для него<select v-model="form.supplierId" class="field-input"><option :value="null">Любой поставщик</option><option v-for="supplier in suppliers" :key="supplier.id" :value="supplier.id">{{ supplier.name }}</option></select></label>
            <label v-if="form.scopeType === 'supplier'" class="field-label">Поставщик<select v-model="form.supplierId" class="field-input" required><option :value="null" disabled>Выберите поставщика</option><option v-for="supplier in suppliers" :key="supplier.id" :value="supplier.id">{{ supplier.name }}</option></select></label>
            <label v-if="form.scopeType === 'brand' || form.scopeType === 'series'" class="field-label">Бренд<select v-model="form.brandId" class="field-input" required><option :value="null" disabled>Выберите бренд</option><option v-for="brand in brands" :key="brand.id" :value="brand.id">{{ brand.title }}</option></select></label>
            <label v-if="form.scopeType === 'series'" class="field-label">
              Серия
              <select v-model="form.seriesId" class="field-input" :disabled="!form.brandId || seriesLoading" required><option :value="null" disabled>{{ seriesLoading ? 'Загружаем серии...' : 'Выберите серию' }}</option><option v-for="item in series" :key="item.id" :value="item.id">{{ item.title }}</option></select>
              <span v-if="seriesError" class="mt-1 block text-xs text-red-700 dark:text-red-300" role="alert">{{ seriesError }}</span>
            </label>
            <label v-if="form.scopeType === 'product'" class="field-label relative sm:col-span-2">
              Товар
              <span class="relative mt-1 block">
                <Search class="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                <input
                  v-model="productQuery"
                  class="field-input pl-9"
                  placeholder="Начните вводить модель"
                  role="combobox"
                  aria-autocomplete="list"
                  aria-controls="warranty-product-results"
                  :aria-expanded="Boolean(productResults.length)"
                  :aria-activedescendant="activeProductIndex >= 0 ? `warranty-product-${productResults[activeProductIndex]?.id}` : undefined"
                  @keydown="onProductKeydown"
                />
              </span>
              <span v-if="productLoading" class="mt-1 flex items-center gap-1 text-xs text-slate-500" aria-live="polite"><LoaderCircle class="h-3.5 w-3.5 animate-spin" /> Ищем товар</span>
              <span v-else-if="productError" class="mt-1 block text-xs text-red-700 dark:text-red-300" role="alert">{{ productError }}</span>
              <span v-else-if="form.productId" class="mt-1 block text-xs text-emerald-700 dark:text-emerald-300">Выбрано: {{ form.productLabel }}</span>
              <span v-else-if="productSearchCompleted && !productResults.length" class="mt-1 block text-xs text-slate-500">Ничего не найдено</span>
              <span v-if="productResults.length" id="warranty-product-results" class="absolute inset-x-0 top-full z-30 mt-1 max-h-52 overflow-y-auto rounded-md border border-slate-200 bg-white p-1 shadow-xl dark:border-slate-700 dark:bg-slate-900" role="listbox">
                <button
                  v-for="(product, index) in productResults"
                  :id="`warranty-product-${product.id}`"
                  :key="product.id"
                  type="button"
                  role="option"
                  :aria-selected="index === activeProductIndex"
                  class="block w-full rounded px-3 py-2 text-left text-sm hover:bg-slate-100 dark:hover:bg-slate-800"
                  :class="index === activeProductIndex ? 'bg-slate-100 dark:bg-slate-800' : ''"
                  @mousemove="activeProductIndex = index"
                  @click="selectProduct(product)"
                >{{ product.title }}</button>
              </span>
            </label>
          </div>

          <div class="grid gap-3 sm:grid-cols-3">
            <label class="field-label">Срок, месяцев<input v-model="form.durationMonths" class="field-input" type="number" min="1" max="240" required /></label>
            <label class="field-label">Начало срока<select v-model="form.startEvent" class="field-input"><option value="sale">Продажа</option><option value="installation">Монтаж</option><option value="commissioning">Ввод в эксплуатацию</option><option value="manual">Дата вручную</option></select></label>
            <label class="field-label">Кто проводит ТО<select v-model="form.allowedMaintenanceProvider" class="field-input"><option value="any">Любой исполнитель</option><option value="mvn">Только MVN</option><option value="authorized">Авторизованный сервис</option></select></label>
          </div>

          <label class="flex items-center gap-3 rounded-md border border-slate-200 px-3 py-2 text-sm font-semibold text-slate-700 dark:border-slate-700 dark:text-slate-200"><input v-model="form.maintenanceRequired" type="checkbox" class="h-4 w-4 accent-teal-600" /> Для сохранения гарантии обязательно регулярное ТО</label>
          <div v-if="form.maintenanceRequired" class="grid gap-3 sm:grid-cols-2"><label class="field-label">Интервал ТО, месяцев<input v-model="form.maintenanceIntervalMonths" class="field-input" type="number" min="1" max="60" required /></label><label class="field-label">Льготный период, дней<input v-model="form.gracePeriodDays" class="field-input" type="number" min="0" max="365" /></label></div>
          <label class="field-label">Условия<textarea v-model="form.terms" class="field-input min-h-24" placeholder="Что покрывается, исключения и требования к обслуживанию" /></label>
          <label class="flex items-center gap-3 text-sm font-semibold text-slate-700 dark:text-slate-200"><input v-model="form.isActive" type="checkbox" class="h-4 w-4 accent-teal-600" /> Правило активно</label>
          <p v-if="error" class="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950/40 dark:text-red-200">{{ error }}</p>

          <footer class="sticky bottom-0 z-20 -mx-4 -mb-4 flex justify-end gap-2 border-t border-slate-200 bg-white px-4 py-3 dark:border-slate-700 dark:bg-slate-900"><button type="button" class="btn-mini-outline" :disabled="saving" @click="close">Отмена</button><button type="submit" class="btn-mini" :disabled="saving || !canSave"><LoaderCircle v-if="saving" class="h-4 w-4 animate-spin" /><ShieldCheck v-else class="h-4 w-4" />{{ saving ? 'Сохраняем...' : 'Сохранить правило' }}</button></footer>
        </form>
      </section>
    </div>
  </Teleport>
</template>
