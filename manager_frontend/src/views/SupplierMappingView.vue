<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';
import { api } from '../api';
import { getApiErrorMessage } from '../utils/api-errors';
import { confirmDialog } from '../services/ui-feedback';

const loading = ref(false);
const error = ref('');
const toast = ref('');
const unmapped = ref<any[]>([]);
const suppliers = ref<any[]>([]);
const sources = ref<any[]>([]);
const supplierFilterId = ref('');
const sourceFilterId = ref('');
const expandedKey = ref<string | null>(null);
const suggestionMap = ref<Record<string, any>>({});
const selectedProductMap = ref<Record<string, number | null>>({});
const bulkSelection = ref<Record<string, boolean>>({});
const suggestionLoading = ref(false);
const applyLoading = ref(false);
const inlineSearchQuery = ref<Record<string, string>>({});
const inlineCandidates = ref<Record<string, any[]>>({});
const sourceUrlCandidates = ref<any[]>([]);
const sourceUrlSelection = ref<Record<string, boolean>>({});
const sourceUrlLoading = ref(false);
const sourceUrlImportLoading = ref(false);
const importWithRelated = ref(false);

const keyOf = (offer: any) => `${offer.supplier_id}:${offer.external_id}`;
const readyToApplyCount = computed(() => Object.keys(bulkSelection.value).filter((k) => bulkSelection.value[k] && selectedProductMap.value[k]).length);
const selectedSourceUrlCount = computed(() => Object.keys(sourceUrlSelection.value).filter((url) => sourceUrlSelection.value[url]).length);

const normalizeCandidate = (candidate: any) => ({
  ...candidate,
  id: candidate?.id ?? candidate?.product_id,
});

const confidenceClass = (confidence: number) => {
  if (confidence >= 75) return 'bg-green-50 text-green-700 border-green-200';
  if (confidence >= 45) return 'bg-amber-50 text-amber-700 border-amber-200';
  return 'bg-gray-50 text-gray-600 border-gray-200';
};

const setToast = (message: string) => {
  toast.value = message;
  window.setTimeout(() => {
    if (toast.value === message) toast.value = '';
  }, 3000);
};

const filteredSources = computed(() =>
  sources.value.filter((s) => !supplierFilterId.value || String(s.supplier_id) === supplierFilterId.value),
);

const loadFilters = async () => {
  const [sup, src] = await Promise.all([api.listSuppliers(), api.listSupplierSources()]);
  suppliers.value = sup.items || [];
  sources.value = src.items || [];
};

const loadUnmapped = async () => {
  loading.value = true;
  error.value = '';
  try {
    const res = await api.listUnmappedSupplierOffers(
      1,
      100,
      supplierFilterId.value ? Number(supplierFilterId.value) : undefined,
      sourceFilterId.value ? Number(sourceFilterId.value) : undefined,
    );
    unmapped.value = res.items || [];
    expandedKey.value = null;
  } catch (e) {
    error.value = getApiErrorMessage(e);
  } finally {
    loading.value = false;
  }
};

const loadSourceUrlCandidates = async () => {
  sourceUrlLoading.value = true;
  error.value = '';
  try {
    const res = await api.listSupplierSourceUrlImportCandidates(
      100,
      supplierFilterId.value ? Number(supplierFilterId.value) : undefined,
      sourceFilterId.value ? Number(sourceFilterId.value) : undefined,
    );
    sourceUrlCandidates.value = res.items || [];
    sourceUrlSelection.value = {};
    for (const item of sourceUrlCandidates.value) {
      if (item.source_url) sourceUrlSelection.value[item.source_url] = true;
    }
  } catch (e) {
    error.value = getApiErrorMessage(e);
  } finally {
    sourceUrlLoading.value = false;
  }
};

const runSuggestions = async (offers: any[]) => {
  if (!offers.length) return;
  suggestionLoading.value = true;
  try {
    const payload = {
      items: offers.map((o) => ({ supplier_id: o.supplier_id, external_id: o.external_id, title_raw: o.title_raw })),
      limit_per_offer: 5,
    };
    const res = await api.suggestSupplierOffers(payload);
    for (const row of res.items || []) {
      const key = `${row.supplier_id}:${row.external_id}`;
      suggestionMap.value[key] = row;
      inlineSearchQuery.value[key] = row.normalized_query || '';
      inlineCandidates.value[key] = (row.candidates || []).map(normalizeCandidate);
      if (row.auto_eligible && row.candidates?.length === 1) {
        const candidate = row.candidates?.[0];
        selectedProductMap.value[key] = candidate ? candidate.product_id : null;
        bulkSelection.value[key] = true;
      }
    }
  } catch (e) {
    error.value = getApiErrorMessage(e);
  } finally {
    suggestionLoading.value = false;
  }
};

const runSuggestionsAll = async () => {
  await runSuggestions(unmapped.value);
};

const toggleMap = async (offer: any) => {
  const key = keyOf(offer);
  expandedKey.value = expandedKey.value === key ? null : key;
  if (!suggestionMap.value[key]) {
    await runSuggestions([offer]);
  }
};

const searchInline = async (offer: any) => {
  const key = keyOf(offer);
  const q = (inlineSearchQuery.value[key] || '').trim();
  if (!q) return;
  try {
    inlineCandidates.value[key] = (await api.smartSearchProducts(q, 20)).map(normalizeCandidate);
    suggestionMap.value[key] = {
      ...(suggestionMap.value[key] || {}),
      auto_eligible: inlineCandidates.value[key].length === 1,
      reason: inlineCandidates.value[key].length === 1 ? 'single_exact' : 'manual_search',
    };
    if (inlineCandidates.value[key].length === 1) {
      selectedProductMap.value[key] = inlineCandidates.value[key][0].id;
    }
  } catch (e) {
    error.value = getApiErrorMessage(e);
  }
};

const saveInline = async (offer: any) => {
  const key = keyOf(offer);
  const productId = selectedProductMap.value[key];
  if (!productId) return;
  try {
    await api.createSupplierMapping({
      product_id: productId,
      supplier_id: offer.supplier_id,
      external_id: offer.external_id,
    });
    unmapped.value = unmapped.value.filter((x) => keyOf(x) !== key);
    expandedKey.value = null;
    setToast('Маппинг сохранен');
  } catch (e) {
    error.value = getApiErrorMessage(e);
  }
};

const applyBulk = async () => {
  const items = unmapped.value
    .map((offer) => {
      const key = keyOf(offer);
      return {
        key,
        supplier_id: offer.supplier_id,
        external_id: offer.external_id,
        product_id: selectedProductMap.value[key],
        enabled: !!bulkSelection.value[key],
      };
    })
    .filter((x) => x.enabled && x.product_id)
    .map((x) => ({ supplier_id: x.supplier_id, external_id: x.external_id, product_id: Number(x.product_id) }));
  if (!items.length) {
    setToast('Нет выбранных маппингов');
    return;
  }

  applyLoading.value = true;
  try {
    await api.createSupplierMappingsBulk({ items, skip_conflicts: true });
    const applied = new Set(items.map((i) => `${i.supplier_id}:${i.external_id}`));
    unmapped.value = unmapped.value.filter((o) => !applied.has(keyOf(o)));
    expandedKey.value = null;
    setToast(`Маппинги применены: ${items.length}`);
  } catch (e) {
    error.value = getApiErrorMessage(e);
  } finally {
    applyLoading.value = false;
  }
};

const startSourceUrlImport = async () => {
  const urls = sourceUrlCandidates.value
    .map((item) => item.source_url)
    .filter((url) => url && sourceUrlSelection.value[url]);
  const uniqueUrls = Array.from(new Set(urls));
  if (!uniqueUrls.length) {
    setToast('Нет выбранных ссылок');
    return;
  }
  if (!await confirmDialog({
    title: 'Запустить импорт?',
    description: `Будет импортировано товаров: ${uniqueUrls.length}.`,
    confirmText: 'Запустить импорт',
    variant: 'warning',
  })) return;

  sourceUrlImportLoading.value = true;
  try {
    const job = await api.startSupplierSourceUrlImport({
      urls: uniqueUrls,
      with_related: importWithRelated.value,
      update_existing: false,
    });
    setToast(`Импорт запущен: ${job.job_id}`);
    await loadSourceUrlCandidates();
  } catch (e) {
    error.value = getApiErrorMessage(e);
  } finally {
    sourceUrlImportLoading.value = false;
  }
};

watch(supplierFilterId, async (value) => {
  if (!value) {
    sourceFilterId.value = '';
  } else {
    const sourceValid = filteredSources.value.some((s) => String(s.id) === sourceFilterId.value);
    if (!sourceValid) sourceFilterId.value = '';
  }
  await loadUnmapped();
});

watch(sourceFilterId, loadUnmapped);

onMounted(async () => {
  await loadFilters();
  await loadUnmapped();
});
</script>

<template>
  <div class="max-w-7xl mx-auto p-6 space-y-4">
    <Transition name="fade">
      <div v-if="toast" class="fixed top-6 right-6 z-[100] rounded-xl bg-teal-600 px-6 py-3 font-medium text-white shadow-2xl">
        {{ toast }}
      </div>
    </Transition>

    <h1 class="text-2xl font-bold text-slate-900 dark:text-white">Маппинг прайсов</h1>
    <p v-if="error" class="rounded-lg bg-red-50 border border-red-200 text-red-700 px-3 py-2 text-sm">{{ error }}</p>

    <div class="bg-white dark:bg-slate-800 border border-gray-200 dark:border-slate-700 rounded-xl p-3">
      <div class="flex flex-wrap items-center gap-2">
        <select v-model="supplierFilterId" class="px-3 py-2 rounded border min-w-52">
          <option value="">Все поставщики</option>
          <option v-for="s in suppliers" :key="s.id" :value="String(s.id)">{{ s.name }}</option>
        </select>
        <select v-model="sourceFilterId" class="px-3 py-2 rounded border min-w-56">
          <option value="">Все источники</option>
          <option v-for="src in filteredSources" :key="src.id" :value="String(src.id)">
            {{ src.supplier_name || `#${src.supplier_id}` }} / {{ src.sheet_name || `source #${src.id}` }}
          </option>
        </select>
        <button
          class="px-3 py-2 rounded bg-slate-900 text-white disabled:opacity-50"
          :disabled="suggestionLoading || loading"
          @click="runSuggestionsAll"
        >
          {{ suggestionLoading ? 'Подбор...' : 'Подобрать автоматически' }}
        </button>
        <span class="text-sm text-gray-600">
          Готово к подтверждению:
          {{ readyToApplyCount }}
        </span>
        <button
          class="px-3 py-2 rounded bg-teal-600 text-white disabled:opacity-50"
          :disabled="applyLoading"
          @click="applyBulk"
        >
          {{ applyLoading ? 'Применение...' : 'Применить выбранные' }}
        </button>
      </div>
    </div>

    <section class="bg-white dark:bg-slate-800 border border-blue-100 dark:border-slate-700 rounded-xl p-3">
      <div class="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 class="font-semibold text-slate-900 dark:text-white">Добавить товары из source URL</h2>
          <p class="text-sm text-slate-500">
            Показывает незамапленные строки прайса с Onliner/source URL, которых еще нет в каталоге.
          </p>
        </div>
        <div class="flex flex-wrap items-center gap-2">
          <label class="inline-flex items-center gap-2 rounded border px-3 py-2 text-sm">
            <input v-model="importWithRelated" type="checkbox" />
            связанные модели
          </label>
          <button
            class="px-3 py-2 rounded border border-blue-200 text-blue-700 disabled:opacity-50"
            :disabled="sourceUrlLoading"
            @click="loadSourceUrlCandidates"
          >
            {{ sourceUrlLoading ? 'Проверка...' : 'Показать кандидатов' }}
          </button>
          <button
            class="px-3 py-2 rounded bg-teal-600 text-white disabled:opacity-50"
            :disabled="sourceUrlImportLoading || !selectedSourceUrlCount"
            @click="startSourceUrlImport"
          >
            {{ sourceUrlImportLoading ? 'Запуск...' : `Импортировать: ${selectedSourceUrlCount}` }}
          </button>
        </div>
      </div>
      <div v-if="sourceUrlCandidates.length" class="mt-3 grid gap-2 md:grid-cols-2">
        <label
          v-for="item in sourceUrlCandidates"
          :key="item.source_url"
          class="flex gap-3 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm"
        >
          <input v-model="sourceUrlSelection[item.source_url]" type="checkbox" class="mt-1" />
          <span class="min-w-0">
            <span class="block truncate font-medium">{{ item.title_raw || item.source_url }}</span>
            <span class="mt-1 block text-xs text-slate-500">
              {{ item.supplier_name || item.supplier_id }}<span v-if="item.source_name"> · {{ item.source_name }}</span>
              <span v-if="item.rrc_byn"> · {{ item.rrc_byn }} BYN</span>
              <span v-if="item.qty"> · {{ item.qty }} шт.</span>
            </span>
            <span v-if="item.model_tokens?.length" class="mt-1 block truncate font-mono text-xs text-slate-500">
              {{ item.model_tokens.join(', ') }}
            </span>
            <a :href="item.source_url" target="_blank" rel="noreferrer" class="mt-1 inline-flex text-xs text-blue-700 underline">
              открыть источник
            </a>
          </span>
        </label>
      </div>
      <p v-else-if="sourceUrlLoading === false" class="mt-3 text-sm text-slate-500">
        Нажмите проверку, чтобы найти товары для добавления.
      </p>
    </section>

    <div class="bg-white dark:bg-slate-800 border border-gray-200 dark:border-slate-700 rounded-xl overflow-hidden">
      <table class="w-full text-sm">
        <thead class="bg-gray-50 dark:bg-slate-900/40 text-gray-500">
          <tr>
            <th class="p-3 text-left">Batch</th>
            <th class="p-3 text-left">Supplier</th>
            <th class="p-3 text-left">SKU/ID</th>
            <th class="p-3 text-left">Title</th>
            <th class="p-3 text-left">Qty</th>
            <th class="p-3 text-left">Wholesale</th>
            <th class="p-3 text-left">Сигнал</th>
            <th class="p-3 text-right">Action</th>
          </tr>
        </thead>
        <tbody>
          <template v-for="offer in unmapped" :key="`${offer.supplier_id}:${offer.external_id}`">
            <tr class="border-t border-gray-100 dark:border-slate-700">
              <td class="p-3">
                <input
                  type="checkbox"
                  :checked="!!bulkSelection[keyOf(offer)]"
                  @change="bulkSelection[keyOf(offer)] = !bulkSelection[keyOf(offer)]"
                />
              </td>
              <td class="p-3">{{ offer.supplier_name || offer.supplier_id }}</td>
              <td class="p-3 font-mono">{{ offer.external_id }}</td>
              <td class="p-3">
                <span class="block">{{ offer.title_raw || '—' }}</span>
                <a
                  v-if="offer.source_url"
                  :href="offer.source_url"
                  target="_blank"
                  rel="noreferrer"
                  class="mt-1 inline-flex rounded border border-blue-200 bg-blue-50 px-1.5 py-0.5 text-[11px] font-medium text-blue-700"
                >
                  source URL
                </a>
              </td>
              <td class="p-3">{{ offer.qty }}</td>
              <td class="p-3">{{ offer.wholesale_value || '—' }} <span v-if="offer.wholesale_currency">{{ offer.wholesale_currency }}</span></td>
              <td class="p-3">
                <div v-if="offer.model_tokens?.length" class="mb-1 flex flex-wrap gap-1">
                  <span v-for="token in offer.model_tokens.slice(0, 4)" :key="`${keyOf(offer)}-${token}`" class="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-[11px] text-slate-600">
                    {{ token }}
                  </span>
                </div>
                <span
                  v-if="suggestionMap[keyOf(offer)]?.auto_eligible"
                  class="inline-flex rounded px-2 py-1 text-xs bg-green-50 text-green-700 border border-green-200"
                >
                  {{ suggestionMap[keyOf(offer)]?.candidates?.[0]?.confidence ?? 100 }}%
                </span>
                <span
                  v-else-if="suggestionMap[keyOf(offer)]"
                  class="inline-flex rounded px-2 py-1 text-xs border"
                  :class="confidenceClass(suggestionMap[keyOf(offer)]?.candidates?.[0]?.confidence || 0)"
                >
                  {{ suggestionMap[keyOf(offer)]?.reason || 'проверить' }}
                </span>
                <span
                  v-else
                  class="inline-flex rounded px-2 py-1 text-xs bg-amber-50 text-amber-700 border border-amber-200"
                >
                  Нужно выбрать
                </span>
              </td>
              <td class="p-3 text-right">
                <button class="px-2 py-1 rounded bg-teal-600 text-white" @click="toggleMap(offer)">Map</button>
              </td>
            </tr>

            <tr v-if="expandedKey === keyOf(offer)" class="border-t border-dashed border-gray-200">
              <td colspan="8" class="p-3 bg-gray-50/60">
                <div class="space-y-3">
                  <div class="flex gap-2">
                    <input
                      v-model="inlineSearchQuery[keyOf(offer)]"
                      class="flex-1 px-3 py-2 rounded border"
                      placeholder="Поиск товара..."
                      @keyup.enter="searchInline(offer)"
                    />
                    <button @click="searchInline(offer)" class="px-3 py-2 rounded bg-slate-900 text-white">Найти</button>
                  </div>
                  <div class="grid md:grid-cols-2 gap-2 max-h-64 overflow-y-auto">
                    <label v-for="p in inlineCandidates[keyOf(offer)] || []" :key="p.id" class="flex items-start gap-2 border rounded px-3 py-2 bg-white">
                      <input v-model.number="selectedProductMap[keyOf(offer)]" type="radio" :value="p.id" />
                      <span class="min-w-0">
                        <span class="block font-medium">{{ p.title }} ({{ p.price }} BYN)</span>
                        <span v-if="p.confidence !== undefined" class="mt-1 inline-flex rounded border px-1.5 py-0.5 text-[11px]" :class="confidenceClass(p.confidence)">
                          {{ p.confidence }}% · score {{ p.score }}
                        </span>
                        <span v-if="p.explanations?.length" class="mt-1 block text-xs text-gray-500">
                          {{ p.explanations.join(' · ') }}
                        </span>
                        <a
                          v-if="p.source_url"
                          :href="p.source_url"
                          target="_blank"
                          rel="noreferrer"
                          class="mt-1 inline-flex text-xs text-blue-700 underline"
                        >
                          Открыть источник
                        </a>
                      </span>
                    </label>
                  </div>
                  <div class="flex justify-end gap-2">
                    <button class="px-3 py-2 rounded border" @click="expandedKey = null">Отмена</button>
                    <button
                      class="px-3 py-2 rounded bg-teal-600 text-white disabled:opacity-50"
                      :disabled="!selectedProductMap[keyOf(offer)]"
                      @click="saveInline(offer)"
                    >
                      Сохранить маппинг
                    </button>
                  </div>
                </div>
              </td>
            </tr>
          </template>
        </tbody>
      </table>
      <div v-if="loading" class="p-4 text-sm text-gray-500">Загрузка...</div>
    </div>
  </div>
</template>
