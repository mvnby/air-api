<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { ExternalLink, MoreHorizontal, Search, Store } from 'lucide-vue-next';
import { api } from '../../api';
import type { SupplierOfferResponse } from '../../client/models/SupplierOfferResponse';
import { getApiErrorMessage } from '../../utils/api-errors';
import { confirmDialog } from '../../services/ui-feedback';
import { isSupplierOffersConflict, productSupplierOffersApi, type SupplierOfferCandidate } from '../../services/product-supplier-offers-api';
import type { Meta } from '../../client/models/Meta';

const props = defineProps<{
  productId: number;
  offers: SupplierOfferResponse[];
  offersLoading: boolean;
  offersError: string;
  vitebskQty: number;
  stockSaving: boolean;
  unlinkingMappingId: number | null;
}>();

const emit = defineEmits<{
  (event: 'update:vitebskQty', value: number): void;
  (event: 'save-stock'): void;
  (event: 'unlink', offer: SupplierOfferResponse): void;
  (event: 'mapped'): void;
}>();

const suppliers = ref<any[]>([]);
const sources = ref<any[]>([]);
const supplierId = ref('');
const sourceId = ref('');
const query = ref('');
const candidates = ref<SupplierOfferCandidate[]>([]);
const candidatesLoading = ref(false);
const candidatesError = ref('');
const mappingOfferId = ref<number | null>(null);
const candidatePage = ref(1);
const candidateLimit = 25;
const candidateMeta = ref<Meta>({ total: 0, page: 1, limit: candidateLimit, pages: 1 });

const filteredSources = computed(() => sources.value.filter((source) => (
  !supplierId.value || String(source.supplier_id) === supplierId.value
)));

const candidateStatusLabel = (offer: SupplierOfferCandidate): string => ({
  current: 'Привязана к этому товару',
  free: 'Свободна',
  conflict: 'Привязана к другому товару',
  inactive: 'Неактивна',
}[offer.status] || offer.status);

const candidateStatusClass = (offer: SupplierOfferCandidate): string => ({
  current: 'bg-emerald-50 text-emerald-700',
  free: 'bg-teal-50 text-teal-700',
  conflict: 'bg-amber-50 text-amber-800',
  inactive: 'bg-gray-100 text-gray-500',
}[offer.status] || 'bg-slate-100 text-slate-600');

const candidateActionLabel = (offer: SupplierOfferCandidate): string => {
  if (offer.status === 'current') return 'Уже привязана';
  if (offer.status === 'inactive') return 'Неактивна';
  return offer.status === 'conflict' ? 'Перепривязать' : 'Привязать';
};

const money = (value: number | null | undefined, currency = '') => (
  value == null ? '—' : `${new Intl.NumberFormat('ru-BY', { maximumFractionDigits: 2 }).format(value)}${currency ? ` ${currency}` : ''}`
);

const updatedLabel = (value: string): string => {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '—';
  return new Intl.DateTimeFormat('ru-BY', { day: '2-digit', month: '2-digit', year: 'numeric' }).format(date);
};

const loadFilters = async () => {
  try {
    const [supplierResponse, sourceResponse] = await Promise.all([api.listSuppliers(), api.listSupplierSources()]);
    suppliers.value = supplierResponse.items || [];
    sources.value = sourceResponse.items || [];
  } catch (cause) {
    candidatesError.value = `Не удалось загрузить поставщиков: ${getApiErrorMessage(cause)}`;
  }
};

const loadCandidates = async () => {
  if (!supplierId.value) {
    candidatesError.value = 'Сначала выберите поставщика.';
    return;
  }
  candidatesLoading.value = true;
  candidatesError.value = '';
  try {
    const response = await productSupplierOffersApi.listCandidates(props.productId, {
      supplierId: Number(supplierId.value),
      sourceId: sourceId.value ? Number(sourceId.value) : null,
      q: query.value,
      page: candidatePage.value,
      limit: candidateLimit,
    });
    candidates.value = response.items || [];
    candidateMeta.value = response.meta;
  } catch (cause) {
    candidatesError.value = `Не удалось загрузить позиции прайса: ${getApiErrorMessage(cause)}`;
  } finally {
    candidatesLoading.value = false;
  }
};

const searchCandidates = async () => {
  candidatePage.value = 1;
  await loadCandidates();
};

const goToCandidatePage = async (page: number) => {
  if (page < 1 || page > candidateMeta.value.pages || page === candidatePage.value) return;
  candidatePage.value = page;
  await loadCandidates();
};

const changeSupplier = () => {
  if (!filteredSources.value.some((source) => String(source.id) === sourceId.value)) sourceId.value = '';
  candidatePage.value = 1;
  candidates.value = [];
  candidateMeta.value = { total: 0, page: 1, limit: candidateLimit, pages: 1 };
};

const mapCandidate = async (offer: SupplierOfferCandidate, replaceExisting = false) => {
  if (!replaceExisting && offer.status === 'conflict') {
    const confirmed = await confirmDialog({
      title: 'Позиция уже привязана к другому товару',
      description: `Перепривязать «${offer.title_raw || offer.external_id}» с «${offer.mapped_product_title || 'другого товара'}» к текущему товару?`,
      confirmText: 'Перепривязать',
      variant: 'warning',
    });
    if (confirmed) await mapCandidate(offer, true);
    return;
  }

  mappingOfferId.value = offer.offer_id;
  candidatesError.value = '';
  try {
    await productSupplierOffersApi.map(offer.offer_id, {
      product_id: props.productId,
      replace_existing: replaceExisting,
      expected_mapping_id: replaceExisting ? offer.mapping_id ?? null : null,
      expected_product_id: replaceExisting ? offer.mapped_product_id ?? null : null,
    });
    await loadCandidates();
    emit('mapped');
  } catch (cause) {
    if (isSupplierOffersConflict(cause)) {
      await loadCandidates();
      candidatesError.value = 'Связь этой позиции уже изменилась. Список обновлён — проверьте товар и повторите действие.';
      return;
    }
    candidatesError.value = `Не удалось привязать позицию: ${getApiErrorMessage(cause)}`;
  } finally {
    if (mappingOfferId.value === offer.offer_id) mappingOfferId.value = null;
  }
};

onMounted(() => void loadFilters());
</script>

<template>
  <section class="space-y-5">
    <header class="border-b border-gray-100 pb-4 dark:border-slate-800">
      <p class="text-xs font-bold uppercase tracking-[0.16em] text-teal-700 dark:text-teal-300">Поставщики</p>
      <h2 class="mt-1 text-xl font-bold text-gray-950 dark:text-white">Остатки и коммерческие связи</h2>
      <p class="mt-1 text-sm text-gray-500 dark:text-slate-400">Привязывайте конкретную строку прайса к товару и сразу видьте её статус.</p>
    </header>

    <div class="rounded-lg border border-gray-200 bg-gray-50 p-4 dark:border-slate-700 dark:bg-slate-950/30">
      <div class="flex flex-col gap-3 sm:flex-row sm:items-end">
        <label class="flex-1 text-sm font-semibold text-gray-700 dark:text-slate-200">
          Остаток на складе в Витебске
          <input :value="vitebskQty" type="number" min="0" class="mt-1 w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-900" @input="emit('update:vitebskQty', Number(($event.target as HTMLInputElement).value || 0))" />
        </label>
        <button type="button" class="h-10 rounded-lg bg-teal-600 px-4 text-sm font-semibold text-white hover:bg-teal-700 disabled:opacity-50" :disabled="stockSaving" @click="emit('save-stock')">{{ stockSaving ? 'Применяем…' : 'Применить остаток' }}</button>
      </div>
    </div>

    <section class="rounded-lg border border-teal-200 bg-teal-50/40 p-4 dark:border-teal-900 dark:bg-teal-950/20">
      <div class="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p class="text-xs font-bold uppercase tracking-[0.16em] text-teal-700 dark:text-teal-300">Добавить позицию прайса</p>
          <p class="mt-1 text-sm text-gray-600 dark:text-slate-300">Поиск выполняется по выбранному поставщику, источнику и названию/артикулу.</p>
        </div>
        <button type="button" class="inline-flex h-10 items-center justify-center gap-2 rounded-lg bg-teal-600 px-4 text-sm font-semibold text-white disabled:opacity-50" :disabled="candidatesLoading || !supplierId" @click="searchCandidates"><Search class="h-4 w-4" />{{ candidatesLoading ? 'Ищем…' : 'Найти позиции' }}</button>
      </div>
      <div class="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
        <select v-model="supplierId" class="rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-900" @change="changeSupplier">
          <option value="">Выберите поставщика</option>
          <option v-for="supplier in suppliers" :key="supplier.id" :value="String(supplier.id)">{{ supplier.name }}</option>
        </select>
        <select v-model="sourceId" class="rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-900">
          <option value="">Все источники</option>
          <option v-for="source in filteredSources" :key="source.id" :value="String(source.id)">{{ source.sheet_name || source.source_name || `Источник #${source.id}` }}</option>
        </select>
        <input v-model="query" type="search" class="rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-900 sm:col-span-2" placeholder="Название или артикул" @keyup.enter="searchCandidates" />
      </div>
      <p v-if="candidatesError" role="alert" class="mt-3 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-900 dark:bg-red-950/30 dark:text-red-200">{{ candidatesError }}</p>
      <div v-if="candidates.length" class="mt-3 space-y-2">
        <article v-for="offer in candidates" :key="offer.offer_id" class="grid gap-3 rounded-lg border border-teal-100 bg-white p-3 text-sm dark:border-teal-900 dark:bg-slate-900 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-center">
          <div class="min-w-0">
            <div class="flex flex-wrap items-center gap-2"><p class="font-semibold text-gray-900 dark:text-white">{{ offer.title_raw || offer.external_id }}</p><span class="rounded-full px-2 py-0.5 text-[10px]" :class="offer.is_active ? 'bg-emerald-50 text-emerald-700' : 'bg-gray-100 text-gray-500'">{{ offer.is_active ? 'Активна' : 'Неактивна' }}</span><span class="rounded-full px-2 py-0.5 text-[10px]" :class="candidateStatusClass(offer)">{{ candidateStatusLabel(offer) }}</span></div>
            <p class="mt-1 text-xs text-gray-500 dark:text-slate-400">{{ offer.supplier_name || `Поставщик #${offer.supplier_id}` }} · {{ offer.source_name || 'Источник не указан' }} · Артикул: {{ offer.external_id }}</p>
            <p class="mt-1 text-xs text-gray-600 dark:text-slate-300">Остаток: {{ offer.qty }} · Закупка: {{ money(offer.wholesale_value, offer.wholesale_currency || '') }} · РРЦ: {{ money(offer.rrc_byn, 'BYN') }} · {{ updatedLabel(offer.updated_at) }}</p>
            <a v-if="offer.status === 'conflict' && offer.mapped_product_slug" :href="`/manager/products/${offer.mapped_product_id}/main`" class="mt-1 inline-flex text-xs font-semibold text-amber-800 underline dark:text-amber-200">Сейчас: {{ offer.mapped_product_title || offer.mapped_product_slug }}</a>
            <p v-else-if="offer.status === 'conflict'" class="mt-1 text-xs font-semibold text-amber-800 dark:text-amber-200">Сейчас: {{ offer.mapped_product_title || `Товар #${offer.mapped_product_id}` }}</p>
          </div>
          <button type="button" class="h-9 rounded-lg border border-teal-200 px-3 text-sm font-semibold text-teal-700 disabled:opacity-50 dark:border-teal-800 dark:text-teal-300" :disabled="mappingOfferId === offer.offer_id || offer.status === 'current' || offer.status === 'inactive' || !offer.is_active" @click="mapCandidate(offer)">{{ mappingOfferId === offer.offer_id ? 'Привязываем…' : candidateActionLabel(offer) }}</button>
        </article>
        <div class="flex flex-wrap items-center justify-between gap-2 pt-1 text-xs text-gray-500 dark:text-slate-400">
          <span>Показано {{ candidates.length }} из {{ candidateMeta.total }}</span>
          <div class="flex items-center gap-2">
            <button type="button" class="rounded border border-gray-200 bg-white px-2.5 py-1.5 disabled:opacity-40 dark:border-slate-700 dark:bg-slate-900" :disabled="candidatePage <= 1 || candidatesLoading" @click="goToCandidatePage(candidatePage - 1)">Назад</button>
            <span>{{ candidateMeta.page }} из {{ candidateMeta.pages }}</span>
            <button type="button" class="rounded border border-gray-200 bg-white px-2.5 py-1.5 disabled:opacity-40 dark:border-slate-700 dark:bg-slate-900" :disabled="candidatePage >= candidateMeta.pages || candidatesLoading" @click="goToCandidatePage(candidatePage + 1)">Далее</button>
          </div>
        </div>
      </div>
      <p v-else-if="!candidatesLoading && !candidatesError" class="mt-3 text-sm text-gray-500 dark:text-slate-400">Выберите фильтры и найдите строку прайса для привязки.</p>
    </section>

    <p v-if="offersError" role="alert" class="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-900 dark:bg-red-950/30 dark:text-red-200">{{ offersError }}</p>
    <div v-else-if="offersLoading" class="flex min-h-36 items-center justify-center rounded-lg border border-gray-200 text-sm text-gray-500 dark:border-slate-700">Загрузка связанных позиций…</div>
    <div v-else-if="offers.length" class="rounded-lg border border-gray-200 dark:border-slate-700">
      <div class="hidden overflow-x-auto md:block">
        <table class="min-w-[760px] w-full text-left text-sm">
          <thead class="bg-gray-50 text-xs uppercase tracking-wide text-gray-500 dark:bg-slate-950/50 dark:text-slate-400"><tr><th class="px-4 py-3">Поставщик</th><th class="px-4 py-3">Позиция</th><th class="px-4 py-3 text-right">Остаток</th><th class="px-4 py-3 text-right">Закупка</th><th class="px-4 py-3 text-right">РРЦ</th><th class="px-4 py-3">Обновлено</th><th class="w-12 px-2 py-3" /></tr></thead>
          <tbody class="divide-y divide-gray-100 dark:divide-slate-800"><tr v-for="offer in offers" :key="`${offer.supplier_id}-${offer.external_id}`" class="bg-white dark:bg-slate-900"><td class="px-4 py-3 font-semibold text-gray-900 dark:text-white">{{ offer.supplier_name || `#${offer.supplier_id}` }}<span class="mt-1 block w-fit rounded-full px-2 py-0.5 text-[10px]" :class="offer.is_active ? 'bg-emerald-50 text-emerald-700' : 'bg-gray-100 text-gray-500'">{{ offer.is_active ? 'Активно' : 'Неактивно' }}</span></td><td class="max-w-[280px] px-4 py-3"><p class="truncate font-medium text-gray-700 dark:text-slate-200" :title="offer.title_raw || offer.external_id">{{ offer.title_raw || offer.external_id }}</p><a v-if="offer.source_url" :href="offer.source_url" target="_blank" rel="noopener noreferrer" class="mt-0.5 inline-flex items-center gap-1 text-xs text-teal-700 hover:underline dark:text-teal-300"><ExternalLink class="h-3 w-3" />Открыть позицию</a></td><td class="px-4 py-3 text-right font-semibold">{{ offer.qty }}</td><td class="px-4 py-3 text-right">{{ money(offer.wholesale_value, offer.wholesale_currency || '') }}</td><td class="px-4 py-3 text-right">{{ money(offer.rrc_byn, 'BYN') }}</td><td class="px-4 py-3 text-gray-500 dark:text-slate-400">{{ updatedLabel(offer.updated_at) }}</td><td class="relative px-2 py-3 text-right"><details class="relative"><summary class="flex h-8 w-8 cursor-pointer list-none items-center justify-center rounded-md text-gray-500 hover:bg-gray-100 dark:hover:bg-slate-800" title="Действия"><MoreHorizontal class="h-4 w-4" /></summary><div class="absolute right-0 top-9 z-20 w-44 rounded-lg border border-gray-200 bg-white p-1 shadow-xl dark:border-slate-700 dark:bg-slate-900"><button v-if="offer.mapping_id" type="button" class="w-full rounded-md px-3 py-2 text-left text-sm font-semibold text-red-600 hover:bg-red-50" :disabled="unlinkingMappingId === offer.mapping_id" @click="emit('unlink', offer)">{{ unlinkingMappingId === offer.mapping_id ? 'Отвязываем…' : 'Отвязать от товара' }}</button></div></details></td></tr></tbody>
        </table>
      </div>
      <div class="space-y-3 p-3 md:hidden">
        <article v-for="offer in offers" :key="`${offer.supplier_id}-${offer.external_id}`" class="rounded-lg border border-gray-200 p-3 dark:border-slate-700"><div class="flex items-start justify-between gap-3"><div><p class="font-semibold text-gray-900 dark:text-white">{{ offer.supplier_name || `Поставщик #${offer.supplier_id}` }}</p><p class="mt-1 text-sm text-gray-600 dark:text-slate-300">{{ offer.title_raw || offer.external_id }}</p></div><span class="rounded-full px-2 py-0.5 text-[10px]" :class="offer.is_active ? 'bg-emerald-50 text-emerald-700' : 'bg-gray-100 text-gray-500'">{{ offer.is_active ? 'Активно' : 'Неактивно' }}</span></div><dl class="mt-3 grid grid-cols-2 gap-2 text-xs text-gray-500"><div><dt>Остаток</dt><dd class="mt-0.5 font-semibold text-gray-800 dark:text-slate-100">{{ offer.qty }}</dd></div><div><dt>Обновлено</dt><dd class="mt-0.5 font-semibold text-gray-800 dark:text-slate-100">{{ updatedLabel(offer.updated_at) }}</dd></div><div><dt>Закупка</dt><dd class="mt-0.5 font-semibold text-gray-800 dark:text-slate-100">{{ money(offer.wholesale_value, offer.wholesale_currency || '') }}</dd></div><div><dt>РРЦ</dt><dd class="mt-0.5 font-semibold text-gray-800 dark:text-slate-100">{{ money(offer.rrc_byn, 'BYN') }}</dd></div></dl><div class="mt-3 flex gap-3"><a v-if="offer.source_url" :href="offer.source_url" target="_blank" rel="noopener noreferrer" class="text-xs font-semibold text-teal-700">Открыть позицию</a><button v-if="offer.mapping_id" type="button" class="text-xs font-semibold text-red-600 disabled:opacity-50" :disabled="unlinkingMappingId === offer.mapping_id" @click="emit('unlink', offer)">{{ unlinkingMappingId === offer.mapping_id ? 'Отвязываем…' : 'Отвязать' }}</button></div></article>
      </div>
    </div>
    <div v-else class="flex min-h-40 flex-col items-center justify-center rounded-lg border border-dashed border-gray-300 bg-gray-50 px-6 text-center dark:border-slate-700 dark:bg-slate-950/30"><Store class="h-8 w-8 text-gray-300" /><p class="mt-3 font-semibold text-gray-800 dark:text-slate-100">Нет предложений поставщиков</p><p class="mt-1 max-w-md text-sm text-gray-500 dark:text-slate-400">Добавьте позицию прайса выше.</p></div>
  </section>
</template>
