<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';
import { api } from '../api';
import { getApiErrorMessage } from '../utils/api-errors';
import { CheckCircle2, CircleAlert, Pencil, RefreshCw, Trash2 } from 'lucide-vue-next';

const loading = ref(false);
const error = ref('');
const suppliers = ref<any[]>([]);
const sources = ref<any[]>([]);
const supplierSheets = ref<any[]>([]);
const syncingSourceId = ref<number | null>(null);
const syncingAll = ref(false);
const savingSource = ref(false);
const savingSupplier = ref(false);
const deletingSourceId = ref<number | null>(null);
const deletingSupplierId = ref<number | null>(null);
const editingSourceId = ref<number | null>(null);
const editingSupplierId = ref<number | null>(null);
const loadingSheets = ref(false);

const supplierForm = ref({
  name: '',
  priority: 100,
  spreadsheet_id_or_url: '',
  is_active: true,
});

const sourceForm = ref({
  supplier_id: 0,
  source_type: 'google_sheet',
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

const activeSupplier = computed(() => suppliers.value.find((s) => s.id === Number(sourceForm.value.supplier_id)));

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

const resetSourceForm = () => {
  editingSourceId.value = null;
  sourceForm.value = {
    supplier_id: suppliers.value.length ? suppliers.value[0].id : 0,
    source_type: 'google_sheet',
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
  supplierSheets.value = [];
};

const loadSupplierSheets = async (supplierId: number) => {
  if (!supplierId) return;
  loadingSheets.value = true;
  try {
    const res = await api.listSupplierSheets(supplierId);
    supplierSheets.value = res.items || [];
  } catch (e) {
    supplierSheets.value = [];
    error.value = getApiErrorMessage(e);
  } finally {
    loadingSheets.value = false;
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
      await loadSupplierSheets(Number(sourceForm.value.supplier_id));
    }
  } catch (e) {
    error.value = getApiErrorMessage(e);
  } finally {
    loading.value = false;
  }
};

const createSupplier = async () => {
  savingSupplier.value = true;
  try {
    if (editingSupplierId.value) {
      await api.patchSupplier(editingSupplierId.value, supplierForm.value);
    } else {
      await api.createSupplier(supplierForm.value);
    }
    supplierForm.value = { name: '', priority: 100, spreadsheet_id_or_url: '', is_active: true };
    editingSupplierId.value = null;
    await loadData();
  } catch (e) {
    error.value = getApiErrorMessage(e);
  } finally {
    savingSupplier.value = false;
  }
};

const startEditSupplier = (supplier: any) => {
  editingSupplierId.value = supplier.id;
  supplierForm.value = {
    name: supplier.name || '',
    priority: supplier.priority ?? 100,
    spreadsheet_id_or_url: supplier.spreadsheet_url || supplier.spreadsheet_id || '',
    is_active: supplier.is_active ?? true,
  };
};

const cancelEditSupplier = () => {
  editingSupplierId.value = null;
  supplierForm.value = { name: '', priority: 100, spreadsheet_id_or_url: '', is_active: true };
};

const deleteSupplier = async (supplierId: number) => {
  if (!confirm('Удалить поставщика и все его источники/офферы?')) return;
  deletingSupplierId.value = supplierId;
  try {
    await api.deleteSupplier(supplierId);
    if (editingSupplierId.value === supplierId) cancelEditSupplier();
    if (sourceForm.value.supplier_id === supplierId) resetSourceForm();
    await loadData();
  } catch (e) {
    error.value = getApiErrorMessage(e);
  } finally {
    deletingSupplierId.value = null;
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

const startEditSource = async (src: any) => {
  const srcCurrency = (src.col_wholesale_currency || '').toUpperCase();
  const isFixedCurrency = ['BYN', 'USD', 'EUR'].includes(srcCurrency);
  currencyMode.value = isFixedCurrency ? (srcCurrency as 'BYN' | 'USD' | 'EUR') : 'COLUMN';
  currencyColumn.value = isFixedCurrency ? 'D' : (src.col_wholesale_currency || 'D');
  editingSourceId.value = src.id;
  sourceForm.value = {
    supplier_id: src.supplier_id,
    source_type: src.source_type || 'google_sheet',
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
  await loadSupplierSheets(src.supplier_id);
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

const syncAll = async () => {
  syncingAll.value = true;
  try {
    await api.syncAllSupplierSources();
    await loadData();
  } catch (e) {
    error.value = getApiErrorMessage(e);
  } finally {
    syncingAll.value = false;
  }
};

watch(
  () => sourceForm.value.supplier_id,
  async (supplierId) => {
    await loadSupplierSheets(Number(supplierId));
    sourceForm.value.sheet_name = '';
  },
);

onMounted(async () => {
  await loadData();
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
      <h2 class="font-semibold mb-3">{{ editingSupplierId ? 'Редактировать поставщика' : 'Добавить поставщика' }}</h2>
      <div class="grid md:grid-cols-4 gap-2">
        <input v-model="supplierForm.name" title="Название поставщика" class="px-3 py-2 rounded border" placeholder="Название" />
        <input v-model.number="supplierForm.priority" title="Приоритет сортировки" type="number" class="px-3 py-2 rounded border" placeholder="Приоритет" />
        <input
          v-model="supplierForm.spreadsheet_id_or_url"
          title="ID или полный URL Google Spreadsheet"
          class="px-3 py-2 rounded border"
          placeholder="Spreadsheet URL/ID"
        />
        <button @click="createSupplier" :disabled="savingSupplier" class="px-3 py-2 rounded bg-teal-600 text-white disabled:opacity-50">
          {{ savingSupplier ? 'Сохранение...' : (editingSupplierId ? 'Сохранить' : 'Создать') }}
        </button>
      </div>
      <div v-if="editingSupplierId" class="mt-2">
        <button @click="cancelEditSupplier" class="px-3 py-2 rounded border">Отмена</button>
      </div>
      <div class="overflow-x-auto mt-4">
        <table class="w-full min-w-[760px] text-sm table-fixed">
          <thead>
            <tr class="text-left text-gray-500">
              <th class="py-2 w-64">Поставщик</th>
              <th class="py-2">Spreadsheet</th>
              <th class="py-2 w-24">Приоритет</th>
              <th class="py-2 w-36 text-right">Actions</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="s in suppliers" :key="s.id" class="border-t border-gray-100 dark:border-slate-700">
              <td class="py-2 pr-2">{{ s.name }}</td>
              <td class="py-2 pr-2 break-all">{{ s.spreadsheet_id || '—' }}</td>
              <td class="py-2 pr-2">{{ s.priority }}</td>
              <td class="py-2 text-right">
                <div class="flex justify-end gap-2 whitespace-nowrap">
                  <button class="p-2 rounded border" title="Редактировать" @click="startEditSupplier(s)">
                    <Pencil class="w-4 h-4" />
                  </button>
                  <button
                    class="p-2 rounded border border-red-300 text-red-600 disabled:opacity-50"
                    title="Удалить поставщика"
                    :disabled="deletingSupplierId === s.id"
                    @click="deleteSupplier(s.id)"
                  >
                    <Trash2 class="w-4 h-4" />
                  </button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <section class="bg-white dark:bg-slate-800 border border-gray-200 dark:border-slate-700 rounded-xl p-4">
      <h2 class="font-semibold mb-3">{{ editingSourceId ? 'Редактировать источник' : 'Добавить источник Google Sheet' }}</h2>
      <div class="grid md:grid-cols-3 gap-2">
        <select v-model.number="sourceForm.supplier_id" title="Выберите поставщика" class="px-3 py-2 rounded border">
          <option v-for="s in suppliers" :key="s.id" :value="s.id">{{ s.name }}</option>
        </select>
        <select
          v-model="sourceForm.sheet_name"
          title="Лист из таблицы поставщика"
          class="px-3 py-2 rounded border"
          :disabled="loadingSheets || !sourceForm.supplier_id"
        >
          <option value="">{{ loadingSheets ? 'Загрузка листов...' : 'Sheet name' }}</option>
          <option v-for="tab in supplierSheets" :key="tab.sheet_id" :value="tab.title">{{ tab.title }}</option>
        </select>
        <input v-model="sourceForm.range_a1" title="Диапазон в A1-формате" class="px-3 py-2 rounded border" placeholder="Range A1, напр. A4:E102" />
        <input
          class="px-3 py-2 rounded border bg-gray-50 text-gray-500"
          :value="activeSupplier?.spreadsheet_id ? `Источник таблицы: ${activeSupplier.spreadsheet_id}` : 'Источник таблицы: задается у поставщика'"
          disabled
        />
        <input class="px-3 py-2 rounded border bg-gray-50 text-gray-500" value="Заголовки определяются автоматически" disabled />
        <select v-model="sourceForm.city_bucket" title="Bucket наличия" class="px-3 py-2 rounded border">
          <option value="minsk">minsk</option>
          <option value="vitebsk">vitebsk</option>
        </select>
      </div>
      <div class="grid md:grid-cols-6 gap-2 mt-2">
        <input v-model="sourceForm.col_external_id" title="SKU/ID (опционально)" class="px-3 py-2 rounded border" placeholder="SKU/ID колонка (опц.)" />
        <input v-model="sourceForm.col_title" title="Колонка названия" class="px-3 py-2 rounded border" placeholder="Название: колонка" />
        <input v-model="sourceForm.col_wholesale" title="Колонка оптовой цены" class="px-3 py-2 rounded border" placeholder="Опт цена: колонка" />
        <select v-model="currencyMode" title="Режим валюты опта" class="px-3 py-2 rounded border">
          <option value="BYN">Валюта: BYN</option>
          <option value="USD">Валюта: USD</option>
          <option value="EUR">Валюта: EUR</option>
          <option value="COLUMN">Валюта из колонки</option>
        </select>
        <input
          v-if="currencyMode === 'COLUMN'"
          v-model="currencyColumn"
          title="Колонка валюты"
          class="px-3 py-2 rounded border"
          placeholder="Колонка валюты, напр. D"
        />
        <input v-else class="px-3 py-2 rounded border bg-gray-50 text-gray-500" :value="currencyMode" disabled />
        <input v-model="sourceForm.col_rrc_byn" title="Колонка РРЦ BYN" class="px-3 py-2 rounded border" placeholder="РРЦ BYN: колонка" />
        <input v-model="sourceForm.col_qty" title="Колонка наличия" class="px-3 py-2 rounded border" placeholder="Наличие: колонка" />
      </div>
      <div class="flex gap-2 mt-3">
        <button @click="saveSource" :disabled="savingSource" class="px-3 py-2 rounded bg-teal-600 text-white disabled:opacity-50">
          {{ savingSource ? 'Сохранение...' : (editingSourceId ? 'Сохранить изменения' : 'Добавить источник') }}
        </button>
        <button v-if="editingSourceId" @click="resetSourceForm" class="px-3 py-2 rounded border">Отмена</button>
      </div>
    </section>

    <section class="bg-white dark:bg-slate-800 border border-gray-200 dark:border-slate-700 rounded-xl p-4">
      <div class="flex items-center justify-between mb-3">
        <h2 class="font-semibold">Источники</h2>
        <button
          @click="syncAll"
          :disabled="syncingAll"
          class="px-3 py-2 rounded bg-slate-900 text-white disabled:opacity-50"
        >
          {{ syncingAll ? 'Sync...' : 'Sync all' }}
        </button>
      </div>
      <div v-if="loading" class="text-sm text-gray-500">Загрузка...</div>
      <div v-else class="overflow-x-auto">
        <table class="w-full min-w-[900px] text-sm table-fixed">
          <thead>
            <tr class="text-left text-gray-500">
              <th class="py-2 w-44">Supplier</th>
              <th class="py-2">Sheet</th>
              <th class="py-2 w-32">Status</th>
              <th class="py-2 w-48">Last sync</th>
              <th class="py-2 w-36 text-right">Actions</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="src in sources" :key="src.id" class="border-t border-gray-100 dark:border-slate-700 align-top">
              <td class="py-2 pr-2">{{ src.supplier_name || `#${src.supplier_id}` }}</td>
              <td class="py-2 pr-2 break-all">{{ src.sheet_name || '—' }} / {{ src.range_a1 || '—' }}</td>
              <td class="py-2 pr-2">
                <span
                  class="inline-flex items-center gap-1"
                  :title="src.last_sync_status === 'error' ? (src.last_sync_error || 'Ошибка синхронизации') : 'Синхронизация успешна'"
                >
                  <CheckCircle2 v-if="src.last_sync_status === 'success'" class="w-4 h-4 text-green-600" />
                  <CircleAlert v-else-if="src.last_sync_status === 'error'" class="w-4 h-4 text-red-600" />
                  <CircleAlert v-else class="w-4 h-4 text-gray-400" />
                  {{ src.last_sync_status || 'never' }}
                </span>
              </td>
              <td class="py-2 pr-2">{{ src.last_sync_at ? new Date(src.last_sync_at).toLocaleString() : '—' }}</td>
              <td class="py-2 text-right">
                <div class="flex justify-end gap-2 whitespace-nowrap">
                  <button class="p-2 rounded border" title="Редактировать" @click="startEditSource(src)">
                    <Pencil class="w-4 h-4" />
                  </button>
                  <button
                    class="p-2 rounded border border-red-300 text-red-600 disabled:opacity-50"
                    title="Удалить"
                    :disabled="deletingSourceId === src.id"
                    @click="deleteSource(src.id)"
                  >
                    <Trash2 class="w-4 h-4" />
                  </button>
                  <button
                    class="p-2 rounded border border-slate-700 text-slate-700 disabled:opacity-50"
                    title="Синхронизировать"
                    :disabled="syncingSourceId === src.id"
                    @click="syncSource(src.id)"
                  >
                    <RefreshCw class="w-4 h-4" />
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
