<script setup lang="ts">
import { onMounted, ref } from 'vue';
import { api } from '../api';
import { getApiErrorMessage } from '../utils/api-errors';

const loading = ref(false);
const error = ref('');
const suppliers = ref<any[]>([]);
const sources = ref<any[]>([]);
const syncingSourceId = ref<number | null>(null);
const savingSource = ref(false);
const deletingSourceId = ref<number | null>(null);
const editingSourceId = ref<number | null>(null);

const supplierForm = ref({
  name: '',
  code: '',
  is_active: true,
  priority: 100,
});

const sourceForm = ref({
  supplier_id: 0,
  source_type: 'google_sheet',
  spreadsheet_id: '',
  sheet_name: '',
  range_a1: '',
  city_bucket: 'minsk',
  header_row_index: 1,
  col_external_id: '',
  col_title: 'B',
  col_wholesale: 'C',
  col_wholesale_currency: 'USD',
  col_rrc_byn: 'E',
  col_qty: 'F',
  is_active: true,
});
const currencyMode = ref<'BYN' | 'USD' | 'EUR' | 'COLUMN'>('USD');
const currencyColumn = ref('D');

const GOOGLE_SHEET_RE = /\/spreadsheets\/d\/([a-zA-Z0-9-_]+)/i;

const extractSpreadsheetId = (value: string): string => {
  const raw = (value || '').trim();
  if (!raw) return '';
  const match = raw.match(GOOGLE_SHEET_RE);
  return match?.[1] ?? raw;
};

const extractRangeFromUrl = (value: string): string => {
  const raw = (value || '').trim();
  if (!raw.startsWith('http')) return raw;
  try {
    const url = new URL(raw);
    const range = url.searchParams.get('range');
    return range ? decodeURIComponent(range) : '';
  } catch {
    return raw;
  }
};

const shortError = (value?: string): string => {
  if (!value) return '—';
  const normalized = value.replace(/\s+/g, ' ').trim();
  return normalized.length > 140 ? `${normalized.slice(0, 140)}...` : normalized;
};

const resetSourceForm = () => {
  editingSourceId.value = null;
  sourceForm.value = {
    supplier_id: suppliers.value.length ? suppliers.value[0].id : 0,
    source_type: 'google_sheet',
    spreadsheet_id: '',
    sheet_name: '',
    range_a1: '',
    city_bucket: 'minsk',
    header_row_index: 1,
    col_external_id: '',
    col_title: 'B',
    col_wholesale: 'C',
    col_wholesale_currency: 'USD',
    col_rrc_byn: 'E',
    col_qty: 'F',
    is_active: true,
  };
  currencyMode.value = 'USD';
  currencyColumn.value = 'D';
};

const loadDefaultSpreadsheetId = async () => {
  try {
    const settings = await api.listManagerSettings();
    const item = (settings.items || []).find((s: any) => s.key === 'supplier_default_spreadsheet_id');
    if (item?.value && !sourceForm.value.spreadsheet_id) {
      sourceForm.value.spreadsheet_id = item.value;
    }
  } catch {
    // optional
  }
};

const loadData = async () => {
  loading.value = true;
  error.value = '';
  try {
    const [sup, src] = await Promise.all([api.listSuppliers(), api.listSupplierSources()]);
    suppliers.value = sup.items || [];
    sources.value = src.items || [];
    if (!sourceForm.value.supplier_id && suppliers.value.length) {
      sourceForm.value.supplier_id = suppliers.value[0].id;
    }
  } catch (e) {
    error.value = getApiErrorMessage(e);
  } finally {
    loading.value = false;
  }
};

const createSupplier = async () => {
  try {
    await api.createSupplier(supplierForm.value);
    supplierForm.value = { name: '', code: '', is_active: true, priority: 100 };
    await loadData();
  } catch (e) {
    error.value = getApiErrorMessage(e);
  }
};

const saveSource = async () => {
  savingSource.value = true;
  try {
    const normalizedCurrency =
      currencyMode.value === 'COLUMN'
        ? (currencyColumn.value || '').trim().toUpperCase()
        : currencyMode.value;
    const payload = {
      ...sourceForm.value,
      spreadsheet_id: extractSpreadsheetId(sourceForm.value.spreadsheet_id),
      range_a1: extractRangeFromUrl(sourceForm.value.range_a1),
      col_external_id: (sourceForm.value.col_external_id || '').trim().toUpperCase(),
      col_title: (sourceForm.value.col_title || '').trim().toUpperCase(),
      col_wholesale: (sourceForm.value.col_wholesale || '').trim().toUpperCase(),
      col_wholesale_currency: normalizedCurrency,
      col_rrc_byn: (sourceForm.value.col_rrc_byn || '').trim().toUpperCase(),
      col_qty: (sourceForm.value.col_qty || '').trim().toUpperCase(),
    };

    if (editingSourceId.value) {
      await api.patchSupplierSource(editingSourceId.value, payload);
    } else {
      await api.createSupplierSource(payload);
    }
    resetSourceForm();
    await loadData();
  } catch (e) {
    error.value = getApiErrorMessage(e);
  } finally {
    savingSource.value = false;
  }
};

const startEditSource = (src: any) => {
  const srcCurrency = (src.col_wholesale_currency || '').toUpperCase();
  const isFixedCurrency = ['BYN', 'USD', 'EUR'].includes(srcCurrency);
  currencyMode.value = isFixedCurrency ? (srcCurrency as 'BYN' | 'USD' | 'EUR') : 'COLUMN';
  currencyColumn.value = isFixedCurrency ? 'D' : (src.col_wholesale_currency || 'D');
  editingSourceId.value = src.id;
  sourceForm.value = {
    supplier_id: src.supplier_id,
    source_type: src.source_type || 'google_sheet',
    spreadsheet_id: src.spreadsheet_id || '',
    sheet_name: src.sheet_name || '',
    range_a1: src.range_a1 || '',
    city_bucket: src.city_bucket || 'minsk',
    header_row_index: src.header_row_index || 1,
    col_external_id: src.col_external_id || '',
    col_title: src.col_title || 'B',
    col_wholesale: src.col_wholesale || 'C',
    col_wholesale_currency: src.col_wholesale_currency || 'USD',
    col_rrc_byn: src.col_rrc_byn || 'E',
    col_qty: src.col_qty || 'F',
    is_active: src.is_active ?? true,
  };
};

const deleteSource = async (sourceId: number) => {
  if (!confirm('Удалить источник?')) return;
  deletingSourceId.value = sourceId;
  try {
    await api.deleteSupplierSource(sourceId);
    if (editingSourceId.value === sourceId) resetSourceForm();
    await loadData();
  } catch (e) {
    error.value = getApiErrorMessage(e);
  } finally {
    deletingSourceId.value = null;
  }
};

const syncSource = async (sourceId: number) => {
  syncingSourceId.value = sourceId;
  try {
    const result = await api.syncSupplierSource(sourceId);
    if (result.status !== 'success') {
      error.value = result.error || 'Sync завершился с ошибкой';
    }
    await loadData();
  } catch (e) {
    error.value = getApiErrorMessage(e);
  } finally {
    syncingSourceId.value = null;
  }
};

onMounted(async () => {
  await loadData();
  await loadDefaultSpreadsheetId();
});
</script>

<template>
  <div class="max-w-7xl mx-auto p-6 space-y-6">
    <h1 class="text-2xl font-bold text-slate-900 dark:text-white">Поставщики и прайсы</h1>
    <p v-if="error" class="rounded-lg bg-red-50 border border-red-200 text-red-700 px-3 py-2 text-sm">{{ error }}</p>
    <p class="rounded-lg bg-blue-50 border border-blue-200 text-blue-800 px-3 py-2 text-sm">
      Для Google API авторизации: <a href="/admin/google_auth" class="underline font-semibold">/admin/google_auth</a>
    </p>

    <section class="bg-white dark:bg-slate-800 border border-gray-200 dark:border-slate-700 rounded-xl p-4">
      <h2 class="font-semibold mb-3">Добавить поставщика</h2>
      <div class="grid md:grid-cols-4 gap-2">
        <input v-model="supplierForm.name" class="px-3 py-2 rounded border" placeholder="Название" />
        <input v-model="supplierForm.code" class="px-3 py-2 rounded border" placeholder="Код" />
        <input v-model.number="supplierForm.priority" type="number" class="px-3 py-2 rounded border" placeholder="Priority" />
        <button @click="createSupplier" class="px-3 py-2 rounded bg-teal-600 text-white">Создать</button>
      </div>
    </section>

    <section class="bg-white dark:bg-slate-800 border border-gray-200 dark:border-slate-700 rounded-xl p-4">
      <h2 class="font-semibold mb-3">{{ editingSourceId ? 'Редактировать источник' : 'Добавить источник Google Sheet' }}</h2>
      <div class="grid md:grid-cols-3 gap-2">
        <select v-model.number="sourceForm.supplier_id" class="px-3 py-2 rounded border">
          <option v-for="s in suppliers" :key="s.id" :value="s.id">{{ s.name }} ({{ s.code }})</option>
        </select>
        <input v-model="sourceForm.spreadsheet_id" class="px-3 py-2 rounded border" placeholder="Spreadsheet ID или URL" />
        <input v-model="sourceForm.sheet_name" class="px-3 py-2 rounded border" placeholder="Sheet name" />
        <input v-model="sourceForm.range_a1" class="px-3 py-2 rounded border" placeholder="Range A1, напр. A42:F" />
        <input class="px-3 py-2 rounded border bg-gray-50 text-gray-500" value="Заголовки определяются автоматически" disabled />
        <select v-model="sourceForm.city_bucket" class="px-3 py-2 rounded border">
          <option value="minsk">minsk</option>
          <option value="vitebsk">vitebsk</option>
        </select>
      </div>
      <div class="grid md:grid-cols-6 gap-2 mt-2">
        <input v-model="sourceForm.col_external_id" class="px-3 py-2 rounded border" placeholder="SKU/ID колонка (опц.)" />
        <input v-model="sourceForm.col_title" class="px-3 py-2 rounded border" placeholder="Название: колонка" />
        <input v-model="sourceForm.col_wholesale" class="px-3 py-2 rounded border" placeholder="Опт цена: колонка" />
        <select v-model="currencyMode" class="px-3 py-2 rounded border">
          <option value="BYN">Валюта: BYN</option>
          <option value="USD">Валюта: USD</option>
          <option value="EUR">Валюта: EUR</option>
          <option value="COLUMN">Валюта из колонки</option>
        </select>
        <input
          v-if="currencyMode === 'COLUMN'"
          v-model="currencyColumn"
          class="px-3 py-2 rounded border"
          placeholder="Колонка валюты, напр. D"
        />
        <input
          v-else
          class="px-3 py-2 rounded border bg-gray-50 text-gray-500"
          :value="currencyMode"
          disabled
        />
        <input v-model="sourceForm.col_rrc_byn" class="px-3 py-2 rounded border" placeholder="РРЦ BYN: колонка" />
        <input v-model="sourceForm.col_qty" class="px-3 py-2 rounded border" placeholder="Наличие: колонка" />
      </div>
      <div class="flex gap-2 mt-3">
        <button @click="saveSource" :disabled="savingSource" class="px-3 py-2 rounded bg-teal-600 text-white disabled:opacity-50">
          {{ savingSource ? 'Сохранение...' : (editingSourceId ? 'Сохранить изменения' : 'Добавить источник') }}
        </button>
        <button v-if="editingSourceId" @click="resetSourceForm" class="px-3 py-2 rounded border">Отмена</button>
      </div>
    </section>

    <section class="bg-white dark:bg-slate-800 border border-gray-200 dark:border-slate-700 rounded-xl p-4">
      <h2 class="font-semibold mb-3">Источники</h2>
      <div v-if="loading" class="text-sm text-gray-500">Загрузка...</div>
      <div v-else class="overflow-x-auto">
        <table class="w-full min-w-[1200px] text-sm table-fixed">
          <thead>
            <tr class="text-left text-gray-500">
              <th class="py-2 w-24">Supplier</th>
              <th class="py-2 w-[360px]">Sheet</th>
              <th class="py-2 w-24">Cols</th>
              <th class="py-2 w-24">Status</th>
              <th class="py-2 w-44">Last sync</th>
              <th class="py-2 w-[280px]">Error</th>
              <th class="py-2 w-60 text-right">Action</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="src in sources" :key="src.id" class="border-t border-gray-100 dark:border-slate-700 align-top">
              <td class="py-2 pr-2">{{ src.supplier_id }}</td>
              <td class="py-2 pr-2 break-all">{{ src.spreadsheet_id }} / {{ src.sheet_name || '—' }} / {{ src.range_a1 || '—' }}</td>
              <td class="py-2 pr-2 text-xs">{{ src.col_title }} {{ src.col_wholesale }} {{ src.col_rrc_byn }} {{ src.col_qty }}</td>
              <td class="py-2 pr-2">{{ src.last_sync_status || 'never' }}</td>
              <td class="py-2 pr-2">{{ src.last_sync_at ? new Date(src.last_sync_at).toLocaleString() : '—' }}</td>
              <td class="py-2 pr-2 text-xs text-red-600 break-words">
                <template v-if="src.last_sync_error">
                  <details>
                    <summary class="cursor-pointer">{{ shortError(src.last_sync_error) }}</summary>
                    <pre class="mt-1 whitespace-pre-wrap break-words font-sans">{{ src.last_sync_error }}</pre>
                  </details>
                </template>
                <template v-else>—</template>
              </td>
              <td class="py-2 text-right">
                <div class="flex justify-end gap-2 whitespace-nowrap">
                  <button class="px-2 py-1 rounded border" @click="startEditSource(src)">Edit</button>
                  <button
                    class="px-2 py-1 rounded bg-red-600 text-white disabled:opacity-50"
                    :disabled="deletingSourceId === src.id"
                    @click="deleteSource(src.id)"
                  >
                    {{ deletingSourceId === src.id ? '...' : 'Delete' }}
                  </button>
                  <button
                    class="px-2 py-1 rounded bg-slate-900 text-white disabled:opacity-50"
                    :disabled="syncingSourceId === src.id"
                    @click="syncSource(src.id)"
                  >
                    {{ syncingSourceId === src.id ? 'Sync...' : 'Sync now' }}
                  </button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  </div>
</template>
