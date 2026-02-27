<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';
import { api } from '../api';
import { getApiErrorMessage } from '../utils/api-errors';

const loading = ref(false);
const error = ref('');
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

const keyOf = (offer: any) => `${offer.supplier_id}:${offer.external_id}`;

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
      inlineCandidates.value[key] = row.candidates || [];
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
    inlineCandidates.value[key] = await api.smartSearchProducts(q, 20);
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
  if (!items.length) return;

  applyLoading.value = true;
  try {
    await api.createSupplierMappingsBulk({ items, skip_conflicts: true });
    const applied = new Set(items.map((i) => `${i.supplier_id}:${i.external_id}`));
    unmapped.value = unmapped.value.filter((o) => !applied.has(keyOf(o)));
    expandedKey.value = null;
  } catch (e) {
    error.value = getApiErrorMessage(e);
  } finally {
    applyLoading.value = false;
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
          {{ Object.keys(bulkSelection).filter((k) => bulkSelection[k] && selectedProductMap[k]).length }}
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
              <td class="p-3">{{ offer.title_raw || '—' }}</td>
              <td class="p-3">{{ offer.qty }}</td>
              <td class="p-3">{{ offer.wholesale_value || '—' }} <span v-if="offer.wholesale_currency">{{ offer.wholesale_currency }}</span></td>
              <td class="p-3">
                <span
                  v-if="suggestionMap[keyOf(offer)]?.auto_eligible"
                  class="inline-flex rounded px-2 py-1 text-xs bg-green-50 text-green-700 border border-green-200"
                >
                  1:1
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
                    <label v-for="p in inlineCandidates[keyOf(offer)] || []" :key="p.id" class="flex items-center gap-2 border rounded px-3 py-2 bg-white">
                      <input v-model.number="selectedProductMap[keyOf(offer)]" type="radio" :value="p.id" />
                      <span>{{ p.title }} ({{ p.price }} BYN)</span>
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
