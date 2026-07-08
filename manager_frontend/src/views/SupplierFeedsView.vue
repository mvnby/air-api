<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';
import { api } from '../api';
import { getApiErrorMessage } from '../utils/api-errors';
import {
  Building2,
  CheckCircle2,
  CircleAlert,
  FileSearch,
  FileSpreadsheet,
  MapPin,
  Pencil,
  Plus,
  RefreshCw,
  Trash2,
  UserRound,
  Warehouse,
} from 'lucide-vue-next';

type SupplierTab = 'profile' | 'contacts' | 'warehouses' | 'prices';
type CurrencyMode = 'BYN' | 'USD' | 'EUR' | 'COLUMN';

const loading = ref(false);
const error = ref('');
const toast = ref('');
const suppliers = ref<any[]>([]);
const sources = ref<any[]>([]);
const contacts = ref<any[]>([]);
const warehouses = ref<any[]>([]);
const supplierSheets = ref<any[]>([]);
const activeTab = ref<SupplierTab>('profile');
const selectedSupplierId = ref<number | null>(null);

const syncingSourceId = ref<number | null>(null);
const syncingAll = ref(false);
const analyzingSourceId = ref<number | null>(null);
const sourceAnalysis = ref<any | null>(null);
const loadingSheets = ref(false);
const savingSupplier = ref(false);
const savingContact = ref(false);
const savingWarehouse = ref(false);
const savingSource = ref(false);
const deletingSupplierId = ref<number | null>(null);
const deletingContactId = ref<number | null>(null);
const deletingWarehouseId = ref<number | null>(null);
const deletingSourceId = ref<number | null>(null);
const editingSourceId = ref<number | null>(null);
const editingContactId = ref<number | null>(null);
const editingWarehouseId = ref<number | null>(null);

const emptySupplierForm = () => ({
  name: '',
  priority: 100,
  spreadsheet_id_or_url: '',
  is_active: true,
  legal_name: '',
  tax_id: '',
  legal_address: '',
  postal_address: '',
  default_payment_method: 'unknown',
  payment_comment: '',
});

const emptyContactForm = () => ({
  name: '',
  role: '',
  phone: '',
  viber: '',
  telegram_username: '',
  telegram_chat_id: '',
  email: '',
  preferred_channel: 'phone',
  default_for_orders: false,
  default_for_logistics: false,
  comment: '',
});

const emptyWarehouseForm = () => ({
  name: '',
  address: '',
  contact_id: null as number | null,
  contact_name: '',
  contact_phone: '',
  work_hours: '',
  pickup_notes: '',
  is_default: false,
});

const emptySourceForm = () => ({
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
  col_source_url: '',
  is_active: true,
});

const supplierForm = ref(emptySupplierForm());
const contactForm = ref(emptyContactForm());
const warehouseForm = ref(emptyWarehouseForm());
const sourceForm = ref(emptySourceForm());
const currencyMode = ref<CurrencyMode>('USD');
const currencyColumn = ref('D');

const activeSupplier = computed(() => suppliers.value.find((s) => s.id === selectedSupplierId.value) || null);
const sourcesForSelected = computed(() => (
  selectedSupplierId.value
    ? sources.value.filter((source) => source.supplier_id === selectedSupplierId.value)
    : sources.value
));

const paymentLabel = (value: string) => ({
  cash: 'наличные',
  bank: 'безнал',
  mixed: 'смешанная',
  unknown: 'не указано',
}[value] || 'не указано');

const setToast = (message: string) => {
  toast.value = message;
  window.setTimeout(() => {
    if (toast.value === message) toast.value = '';
  }, 3000);
};

const loadSupplierRelations = async (supplierId: number) => {
  const [contactRes, warehouseRes] = await Promise.all([
    api.listSupplierContacts(supplierId),
    api.listSupplierWarehouses(supplierId),
  ]);
  contacts.value = contactRes.items || [];
  warehouses.value = warehouseRes.items || [];
};

const loadSupplierSheets = async (supplierId: number) => {
  if (!supplierId) return;
  loadingSheets.value = true;
  try {
    const res = await api.listSupplierSheets(supplierId);
    supplierSheets.value = res.items || [];
  } catch {
    supplierSheets.value = [];
  } finally {
    loadingSheets.value = false;
  }
};

const selectSupplier = async (supplier: any | null) => {
  selectedSupplierId.value = supplier?.id || null;
  sourceAnalysis.value = null;
  editingSourceId.value = null;
  if (supplier) {
    supplierForm.value = {
      name: supplier.name || '',
      priority: supplier.priority ?? 100,
      spreadsheet_id_or_url: supplier.spreadsheet_url || supplier.spreadsheet_id || '',
      is_active: supplier.is_active ?? true,
      legal_name: supplier.legal_name || '',
      tax_id: supplier.tax_id || '',
      legal_address: supplier.legal_address || '',
      postal_address: supplier.postal_address || '',
      default_payment_method: supplier.default_payment_method || 'unknown',
      payment_comment: supplier.payment_comment || '',
    };
    sourceForm.value = { ...sourceForm.value, supplier_id: supplier.id };
    await Promise.all([loadSupplierRelations(supplier.id), loadSupplierSheets(supplier.id)]);
  } else {
    supplierForm.value = emptySupplierForm();
    contacts.value = [];
    warehouses.value = [];
    supplierSheets.value = [];
    sourceForm.value = emptySourceForm();
  }
};

const loadData = async () => {
  loading.value = true;
  error.value = '';
  try {
    const [sup, src] = await Promise.all([api.listSuppliers(), api.listSupplierSources()]);
    suppliers.value = sup.items || [];
    sources.value = src.items || [];
    const nextSupplier = selectedSupplierId.value
      ? suppliers.value.find((item) => item.id === selectedSupplierId.value)
      : suppliers.value[0];
    await selectSupplier(nextSupplier || null);
  } catch (err) {
    error.value = getApiErrorMessage(err);
  } finally {
    loading.value = false;
  }
};

const saveSupplier = async () => {
  savingSupplier.value = true;
  try {
    const payload = { ...supplierForm.value };
    const wasExisting = Boolean(selectedSupplierId.value);
    const result = selectedSupplierId.value
      ? await api.patchSupplier(selectedSupplierId.value, payload)
      : await api.createSupplier(payload);
    selectedSupplierId.value = result.id;
    await loadData();
    setToast(wasExisting ? 'Поставщик сохранен' : 'Поставщик создан');
  } catch (err) {
    error.value = getApiErrorMessage(err);
  } finally {
    savingSupplier.value = false;
  }
};

const deleteSupplier = async () => {
  if (!activeSupplier.value?.id) return;
  if (!confirm('Удалить поставщика со всеми прайсами и закупочными заявками?')) return;
  deletingSupplierId.value = activeSupplier.value.id;
  try {
    await api.deleteSupplier(activeSupplier.value.id);
    selectedSupplierId.value = null;
    await loadData();
    setToast('Поставщик удален');
  } catch (err) {
    error.value = getApiErrorMessage(err);
  } finally {
    deletingSupplierId.value = null;
  }
};

const resetContactForm = () => {
  editingContactId.value = null;
  contactForm.value = emptyContactForm();
};

const saveContact = async () => {
  if (!activeSupplier.value?.id) return;
  savingContact.value = true;
  try {
    if (editingContactId.value) {
      await api.patchSupplierContact(activeSupplier.value.id, editingContactId.value, contactForm.value);
    } else {
      await api.createSupplierContact(activeSupplier.value.id, contactForm.value);
    }
    await loadSupplierRelations(activeSupplier.value.id);
    resetContactForm();
    setToast('Контакт сохранен');
  } catch (err) {
    error.value = getApiErrorMessage(err);
  } finally {
    savingContact.value = false;
  }
};

const editContact = (contact: any) => {
  editingContactId.value = contact.id;
  contactForm.value = {
    name: contact.name || '',
    role: contact.role || '',
    phone: contact.phone || '',
    viber: contact.viber || '',
    telegram_username: contact.telegram_username || '',
    telegram_chat_id: contact.telegram_chat_id || '',
    email: contact.email || '',
    preferred_channel: contact.preferred_channel || 'phone',
    default_for_orders: Boolean(contact.default_for_orders),
    default_for_logistics: Boolean(contact.default_for_logistics),
    comment: contact.comment || '',
  };
};

const deleteContact = async (contactId: number) => {
  if (!activeSupplier.value?.id || !confirm('Удалить контакт?')) return;
  deletingContactId.value = contactId;
  try {
    await api.deleteSupplierContact(activeSupplier.value.id, contactId);
    await loadSupplierRelations(activeSupplier.value.id);
    resetContactForm();
    setToast('Контакт удален');
  } catch (err) {
    error.value = getApiErrorMessage(err);
  } finally {
    deletingContactId.value = null;
  }
};

const resetWarehouseForm = () => {
  editingWarehouseId.value = null;
  warehouseForm.value = emptyWarehouseForm();
};

const saveWarehouse = async () => {
  if (!activeSupplier.value?.id) return;
  savingWarehouse.value = true;
  try {
    if (editingWarehouseId.value) {
      await api.patchSupplierWarehouse(activeSupplier.value.id, editingWarehouseId.value, warehouseForm.value);
    } else {
      await api.createSupplierWarehouse(activeSupplier.value.id, warehouseForm.value);
    }
    await loadSupplierRelations(activeSupplier.value.id);
    resetWarehouseForm();
    setToast('Склад сохранен');
  } catch (err) {
    error.value = getApiErrorMessage(err);
  } finally {
    savingWarehouse.value = false;
  }
};

const editWarehouse = (warehouseItem: any) => {
  editingWarehouseId.value = warehouseItem.id;
  warehouseForm.value = {
    name: warehouseItem.name || '',
    address: warehouseItem.address || '',
    contact_id: warehouseItem.contact_id || null,
    contact_name: warehouseItem.contact_name || '',
    contact_phone: warehouseItem.contact_phone || '',
    work_hours: warehouseItem.work_hours || '',
    pickup_notes: warehouseItem.pickup_notes || '',
    is_default: Boolean(warehouseItem.is_default),
  };
};

const deleteWarehouse = async (warehouseId: number) => {
  if (!activeSupplier.value?.id || !confirm('Удалить склад отгрузки?')) return;
  deletingWarehouseId.value = warehouseId;
  try {
    await api.deleteSupplierWarehouse(activeSupplier.value.id, warehouseId);
    await loadSupplierRelations(activeSupplier.value.id);
    resetWarehouseForm();
    setToast('Склад удален');
  } catch (err) {
    error.value = getApiErrorMessage(err);
  } finally {
    deletingWarehouseId.value = null;
  }
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

const resetSourceForm = () => {
  editingSourceId.value = null;
  sourceForm.value = {
    ...emptySourceForm(),
    supplier_id: activeSupplier.value?.id || 0,
  };
  currencyMode.value = 'USD';
  currencyColumn.value = 'D';
};

const saveSource = async () => {
  savingSource.value = true;
  try {
    const wasEditing = Boolean(editingSourceId.value);
    const normalizedCurrency = currencyMode.value === 'COLUMN'
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
      col_source_url: (sourceForm.value.col_source_url || '').trim().toUpperCase() || null,
    };
    if (editingSourceId.value) {
      await api.patchSupplierSource(editingSourceId.value, payload);
    } else {
      await api.createSupplierSource(payload);
    }
    await loadData();
    resetSourceForm();
    setToast(wasEditing ? 'Источник обновлен' : 'Источник создан');
  } catch (err) {
    error.value = getApiErrorMessage(err);
  } finally {
    savingSource.value = false;
  }
};

const editSource = async (source: any) => {
  const srcCurrency = (source.col_wholesale_currency || '').toUpperCase();
  const isFixedCurrency = ['BYN', 'USD', 'EUR'].includes(srcCurrency);
  currencyMode.value = isFixedCurrency ? (srcCurrency as CurrencyMode) : 'COLUMN';
  currencyColumn.value = isFixedCurrency ? 'D' : (source.col_wholesale_currency || 'D');
  editingSourceId.value = source.id;
  sourceForm.value = {
    supplier_id: source.supplier_id,
    source_type: source.source_type || 'google_sheet',
    sheet_name: source.sheet_name || '',
    range_a1: source.range_a1 || '',
    city_bucket: source.city_bucket || 'minsk',
    header_row_index: source.header_row_index || 1,
    col_external_id: source.col_external_id || '',
    col_title: source.col_title || 'B',
    col_wholesale: source.col_wholesale || 'C',
    col_wholesale_currency: source.col_wholesale_currency || 'USD',
    col_rrc_byn: source.col_rrc_byn || 'E',
    col_qty: source.col_qty || 'F',
    col_source_url: source.col_source_url || '',
    is_active: source.is_active ?? true,
  };
  await loadSupplierSheets(source.supplier_id);
};

const deleteSource = async (sourceId: number) => {
  if (!confirm('Удалить источник?')) return;
  deletingSourceId.value = sourceId;
  try {
    await api.deleteSupplierSource(sourceId);
    await loadData();
    resetSourceForm();
    setToast('Источник удален');
  } catch (err) {
    error.value = getApiErrorMessage(err);
  } finally {
    deletingSourceId.value = null;
  }
};

const analyzeSource = async (sourceId: number) => {
  analyzingSourceId.value = sourceId;
  error.value = '';
  try {
    sourceAnalysis.value = await api.analyzeSupplierSource(sourceId, 80);
  } catch (err) {
    error.value = getApiErrorMessage(err);
  } finally {
    analyzingSourceId.value = null;
  }
};

const syncSource = async (sourceId: number) => {
  syncingSourceId.value = sourceId;
  try {
    const result = await api.syncSupplierSource(sourceId);
    if (result.status !== 'success') error.value = result.error || 'Sync завершился с ошибкой';
    else setToast('Синхронизация источника завершена');
    await loadData();
  } catch (err) {
    error.value = getApiErrorMessage(err);
  } finally {
    syncingSourceId.value = null;
  }
};

const syncAll = async () => {
  syncingAll.value = true;
  try {
    await api.syncAllSupplierSources();
    await loadData();
    setToast('Синхронизация всех источников запущена');
  } catch (err) {
    error.value = getApiErrorMessage(err);
  } finally {
    syncingAll.value = false;
  }
};

watch(
  () => sourceForm.value.supplier_id,
  async (supplierId) => {
    if (supplierId) await loadSupplierSheets(Number(supplierId));
    sourceForm.value.sheet_name = '';
  },
);

onMounted(loadData);
</script>

<template>
  <div class="mx-auto max-w-7xl space-y-5 p-4 sm:p-6">
    <Transition name="fade">
      <div v-if="toast" class="fixed right-6 top-6 z-[100] rounded-xl bg-teal-600 px-5 py-3 font-medium text-white shadow-2xl">
        {{ toast }}
      </div>
    </Transition>

    <header class="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
      <div>
        <p class="text-xs font-bold uppercase tracking-[0.22em] text-teal-700">CRM поставщики</p>
        <h1 class="text-2xl font-bold text-slate-900">Поставщики и прайсы</h1>
      </div>
      <button class="inline-flex items-center justify-center gap-2 rounded-xl bg-teal-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-teal-700" @click="selectSupplier(null)">
        <Plus class="h-4 w-4" />
        Новый поставщик
      </button>
    </header>

    <p v-if="error" class="rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{{ error }}</p>

    <div class="grid gap-4 lg:grid-cols-[320px_minmax(0,1fr)]">
      <aside class="rounded-2xl border border-slate-200 bg-white p-3 shadow-sm">
        <div class="mb-3 flex items-center justify-between">
          <h2 class="text-sm font-semibold text-slate-900">Поставщики</h2>
          <span class="rounded-full bg-slate-100 px-2 py-1 text-xs text-slate-500">{{ suppliers.length }}</span>
        </div>
        <div v-if="loading" class="rounded-xl border border-dashed border-slate-200 px-3 py-8 text-center text-sm text-slate-500">Загрузка...</div>
        <div v-else class="max-h-[calc(100vh-190px)] space-y-2 overflow-y-auto pr-1">
          <button
            v-for="supplier in suppliers"
            :key="supplier.id"
            class="w-full rounded-xl border px-3 py-2 text-left transition"
            :class="selectedSupplierId === supplier.id ? 'border-teal-300 bg-teal-50 text-teal-950' : 'border-slate-200 bg-white hover:border-teal-200 hover:bg-slate-50'"
            @click="selectSupplier(supplier)"
          >
            <span class="flex items-start justify-between gap-2">
              <span class="min-w-0">
                <span class="block truncate text-sm font-semibold">{{ supplier.name }}</span>
                <span class="mt-0.5 block truncate text-xs text-slate-500">{{ supplier.legal_name || supplier.code }}</span>
              </span>
              <span class="shrink-0 rounded-full px-2 py-0.5 text-[11px]" :class="supplier.is_active ? 'bg-emerald-50 text-emerald-700' : 'bg-slate-100 text-slate-500'">
                {{ supplier.is_active ? 'активен' : 'выкл.' }}
              </span>
            </span>
            <span class="mt-2 flex flex-wrap gap-1 text-[11px] text-slate-500">
              <span>{{ paymentLabel(supplier.default_payment_method) }}</span>
              <span v-if="supplier.tax_id">· УНП {{ supplier.tax_id }}</span>
            </span>
          </button>
        </div>
      </aside>

      <section class="min-w-0 rounded-2xl border border-slate-200 bg-white shadow-sm">
        <div class="border-b border-slate-100 p-4">
          <div class="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            <div class="min-w-0">
              <p class="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">{{ activeSupplier ? activeSupplier.code : 'новый' }}</p>
              <h2 class="truncate text-xl font-bold text-slate-900">{{ activeSupplier?.name || 'Новый поставщик' }}</h2>
              <p class="mt-1 text-sm text-slate-500">Юр. адрес, почтовый адрес и склады отгрузки хранятся отдельно.</p>
            </div>
            <button
              v-if="activeSupplier"
              class="inline-flex items-center justify-center gap-2 rounded-xl border border-red-200 px-3 py-2 text-sm font-semibold text-red-600 hover:bg-red-50 disabled:opacity-50"
              :disabled="deletingSupplierId === activeSupplier.id"
              @click="deleteSupplier"
            >
              <Trash2 class="h-4 w-4" />
              Удалить
            </button>
          </div>
          <div class="mt-4 flex gap-2 overflow-x-auto">
            <button
              v-for="tab in [
                { id: 'profile', label: 'Профиль', icon: Building2 },
                { id: 'contacts', label: 'Контакты', icon: UserRound },
                { id: 'warehouses', label: 'Склады', icon: Warehouse },
                { id: 'prices', label: 'Прайсы', icon: FileSpreadsheet },
              ]"
              :key="tab.id"
              class="inline-flex shrink-0 items-center gap-2 rounded-xl px-3 py-2 text-sm font-semibold transition"
              :class="activeTab === tab.id ? 'bg-teal-600 text-white shadow-sm' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'"
              @click="activeTab = tab.id as SupplierTab"
            >
              <component :is="tab.icon" class="h-4 w-4" />
              {{ tab.label }}
            </button>
          </div>
        </div>

        <div class="p-4">
          <div v-if="activeTab === 'profile'" class="space-y-4">
            <div class="grid gap-3 md:grid-cols-2">
              <label class="space-y-1 text-sm font-medium text-slate-600">Название<input v-model="supplierForm.name" class="field-input" placeholder="Биоконд" /></label>
              <label class="space-y-1 text-sm font-medium text-slate-600">Приоритет<input v-model.number="supplierForm.priority" type="number" class="field-input" /></label>
              <label class="space-y-1 text-sm font-medium text-slate-600 md:col-span-2">Google Spreadsheet URL/ID<input v-model="supplierForm.spreadsheet_id_or_url" class="field-input" placeholder="https://docs.google.com/spreadsheets/..." /></label>
              <label class="space-y-1 text-sm font-medium text-slate-600">Юридическое название<input v-model="supplierForm.legal_name" class="field-input" placeholder="ООО / УП..." /></label>
              <label class="space-y-1 text-sm font-medium text-slate-600">УНП / рег. номер<input v-model="supplierForm.tax_id" class="field-input" /></label>
              <label class="space-y-1 text-sm font-medium text-slate-600">Юр. адрес<textarea v-model="supplierForm.legal_address" class="field-input min-h-[76px]" /></label>
              <label class="space-y-1 text-sm font-medium text-slate-600">Почтовый адрес / документы<textarea v-model="supplierForm.postal_address" class="field-input min-h-[76px]" /></label>
              <label class="space-y-1 text-sm font-medium text-slate-600">
                Оплата по умолчанию
                <select v-model="supplierForm.default_payment_method" class="field-input">
                  <option value="unknown">Не указано</option>
                  <option value="cash">Наличные</option>
                  <option value="bank">Безнал</option>
                  <option value="mixed">Смешанная</option>
                </select>
              </label>
              <label class="flex items-center gap-2 rounded-xl border border-slate-200 px-3 py-2 text-sm font-medium text-slate-700">
                <input v-model="supplierForm.is_active" type="checkbox" class="rounded text-teal-600" />
                Активный поставщик
              </label>
              <label class="space-y-1 text-sm font-medium text-slate-600 md:col-span-2">Комментарий по оплате<textarea v-model="supplierForm.payment_comment" class="field-input min-h-[72px]" placeholder="Например: SaveIN и Iera по безналу, остальное наличными" /></label>
            </div>
            <button class="inline-flex items-center justify-center rounded-xl bg-teal-600 px-5 py-2.5 text-sm font-semibold text-white hover:bg-teal-700 disabled:opacity-50" :disabled="savingSupplier" @click="saveSupplier">
              {{ savingSupplier ? 'Сохранение...' : 'Сохранить профиль' }}
            </button>
          </div>

          <div v-else-if="activeTab === 'contacts'" class="grid gap-4 xl:grid-cols-[minmax(0,1fr)_360px]">
            <div class="space-y-2">
              <article v-for="contact in contacts" :key="contact.id" class="rounded-xl border border-slate-200 p-3">
                <div class="flex items-start justify-between gap-3">
                  <div class="min-w-0">
                    <p class="truncate font-semibold text-slate-900">{{ contact.name }}</p>
                    <p class="text-sm text-slate-500">{{ contact.role || 'Контакт' }}</p>
                    <p class="mt-2 text-sm text-slate-700">{{ [contact.phone, contact.viber && `Viber ${contact.viber}`, contact.telegram_username && `TG ${contact.telegram_username}`, contact.email].filter(Boolean).join(' · ') || 'каналы не заполнены' }}</p>
                    <div class="mt-2 flex flex-wrap gap-1 text-[11px] font-semibold">
                      <span v-if="contact.default_for_orders" class="rounded-full bg-teal-50 px-2 py-0.5 text-teal-700">заказы</span>
                      <span v-if="contact.default_for_logistics" class="rounded-full bg-cyan-50 px-2 py-0.5 text-cyan-700">логистика</span>
                    </div>
                  </div>
                  <div class="flex shrink-0 gap-2">
                    <button class="rounded-lg border border-slate-200 p-2 text-slate-600 hover:bg-slate-50" title="Редактировать" @click="editContact(contact)"><Pencil class="h-4 w-4" /></button>
                    <button class="rounded-lg border border-red-200 p-2 text-red-600 hover:bg-red-50 disabled:opacity-50" :disabled="deletingContactId === contact.id" title="Удалить" @click="deleteContact(contact.id)"><Trash2 class="h-4 w-4" /></button>
                  </div>
                </div>
              </article>
              <div v-if="!contacts.length" class="rounded-xl border border-dashed border-slate-200 px-3 py-8 text-center text-sm text-slate-500">Контакты пока не заведены.</div>
            </div>
            <form class="rounded-xl border border-slate-200 bg-slate-50 p-3" @submit.prevent="saveContact">
              <h3 class="mb-3 font-semibold text-slate-900">{{ editingContactId ? 'Редактировать контакт' : 'Новый контакт' }}</h3>
              <div class="space-y-2">
                <input v-model="contactForm.name" required class="field-input bg-white" placeholder="Имя" />
                <input v-model="contactForm.role" class="field-input bg-white" placeholder="Роль: менеджер, склад..." />
                <input v-model="contactForm.phone" class="field-input bg-white" placeholder="Телефон" />
                <input v-model="contactForm.viber" class="field-input bg-white" placeholder="Viber" />
                <input v-model="contactForm.telegram_username" class="field-input bg-white" placeholder="Telegram username" />
                <input v-model="contactForm.email" class="field-input bg-white" placeholder="Email" />
                <select v-model="contactForm.preferred_channel" class="field-input bg-white">
                  <option value="phone">Телефон</option>
                  <option value="viber">Viber</option>
                  <option value="telegram">Telegram</option>
                  <option value="email">Email</option>
                  <option value="other">Другое</option>
                </select>
                <label class="flex items-center gap-2 text-sm text-slate-700"><input v-model="contactForm.default_for_orders" type="checkbox" /> По умолчанию для заказов</label>
                <label class="flex items-center gap-2 text-sm text-slate-700"><input v-model="contactForm.default_for_logistics" type="checkbox" /> По умолчанию для логистики</label>
                <textarea v-model="contactForm.comment" class="field-input bg-white" placeholder="Комментарий" />
              </div>
              <div class="mt-3 flex gap-2">
                <button class="flex-1 rounded-xl bg-teal-600 px-3 py-2 text-sm font-semibold text-white disabled:opacity-50" :disabled="savingContact">{{ savingContact ? '...' : 'Сохранить' }}</button>
                <button v-if="editingContactId" type="button" class="rounded-xl border border-slate-200 px-3 py-2 text-sm font-semibold" @click="resetContactForm">Отмена</button>
              </div>
            </form>
          </div>

          <div v-else-if="activeTab === 'warehouses'" class="grid gap-4 xl:grid-cols-[minmax(0,1fr)_380px]">
            <div class="space-y-2">
              <article v-for="warehouseItem in warehouses" :key="warehouseItem.id" class="rounded-xl border border-slate-200 p-3">
                <div class="flex items-start justify-between gap-3">
                  <div class="min-w-0">
                    <p class="flex flex-wrap items-center gap-2 font-semibold text-slate-900">
                      <MapPin class="h-4 w-4 text-teal-600" />
                      {{ warehouseItem.name }}
                      <span v-if="warehouseItem.is_default" class="rounded-full bg-teal-50 px-2 py-0.5 text-[11px] text-teal-700">по умолчанию</span>
                    </p>
                    <p class="mt-1 text-sm text-slate-700">{{ warehouseItem.address }}</p>
                    <p class="mt-2 text-sm text-slate-500">{{ [warehouseItem.contact_name, warehouseItem.contact_phone, warehouseItem.work_hours].filter(Boolean).join(' · ') || 'контакт и режим не заполнены' }}</p>
                    <p v-if="warehouseItem.pickup_notes" class="mt-2 rounded-lg bg-slate-50 px-2 py-1 text-xs text-slate-600">{{ warehouseItem.pickup_notes }}</p>
                  </div>
                  <div class="flex shrink-0 gap-2">
                    <button class="rounded-lg border border-slate-200 p-2 text-slate-600 hover:bg-slate-50" title="Редактировать" @click="editWarehouse(warehouseItem)"><Pencil class="h-4 w-4" /></button>
                    <button class="rounded-lg border border-red-200 p-2 text-red-600 hover:bg-red-50 disabled:opacity-50" :disabled="deletingWarehouseId === warehouseItem.id" title="Удалить" @click="deleteWarehouse(warehouseItem.id)"><Trash2 class="h-4 w-4" /></button>
                  </div>
                </div>
              </article>
              <div v-if="!warehouses.length" class="rounded-xl border border-dashed border-slate-200 px-3 py-8 text-center text-sm text-slate-500">Склады отгрузки пока не заведены.</div>
            </div>
            <form class="rounded-xl border border-slate-200 bg-slate-50 p-3" @submit.prevent="saveWarehouse">
              <h3 class="mb-3 font-semibold text-slate-900">{{ editingWarehouseId ? 'Редактировать склад' : 'Новый склад' }}</h3>
              <div class="space-y-2">
                <input v-model="warehouseForm.name" required class="field-input bg-white" placeholder="Название склада" />
                <textarea v-model="warehouseForm.address" required class="field-input min-h-[80px] bg-white" placeholder="Адрес склада / точки отгрузки" />
                <select v-model="warehouseForm.contact_id" class="field-input bg-white">
                  <option :value="null">Контакт из справочника не выбран</option>
                  <option v-for="contact in contacts" :key="contact.id" :value="contact.id">{{ contact.name }}</option>
                </select>
                <input v-model="warehouseForm.contact_name" class="field-input bg-white" placeholder="Контакт на складе" />
                <input v-model="warehouseForm.contact_phone" class="field-input bg-white" placeholder="Телефон склада" />
                <input v-model="warehouseForm.work_hours" class="field-input bg-white" placeholder="Режим работы" />
                <textarea v-model="warehouseForm.pickup_notes" class="field-input bg-white" placeholder="Примечания для забора" />
                <label class="flex items-center gap-2 text-sm text-slate-700"><input v-model="warehouseForm.is_default" type="checkbox" /> Склад по умолчанию</label>
              </div>
              <div class="mt-3 flex gap-2">
                <button class="flex-1 rounded-xl bg-teal-600 px-3 py-2 text-sm font-semibold text-white disabled:opacity-50" :disabled="savingWarehouse">{{ savingWarehouse ? '...' : 'Сохранить' }}</button>
                <button v-if="editingWarehouseId" type="button" class="rounded-xl border border-slate-200 px-3 py-2 text-sm font-semibold" @click="resetWarehouseForm">Отмена</button>
              </div>
            </form>
          </div>

          <div v-else class="space-y-4">
            <section class="rounded-xl border border-slate-200 bg-slate-50 p-3">
              <h3 class="mb-3 font-semibold text-slate-900">{{ editingSourceId ? 'Редактировать источник' : 'Добавить источник Google Sheet' }}</h3>
              <div class="grid gap-2 md:grid-cols-3">
                <select v-model.number="sourceForm.supplier_id" class="field-input bg-white">
                  <option v-for="supplier in suppliers" :key="supplier.id" :value="supplier.id">{{ supplier.name }}</option>
                </select>
                <select v-model="sourceForm.sheet_name" class="field-input bg-white" :disabled="loadingSheets || !sourceForm.supplier_id">
                  <option value="">{{ loadingSheets ? 'Загрузка листов...' : 'Sheet name' }}</option>
                  <option v-for="tab in supplierSheets" :key="tab.sheet_id" :value="tab.title">{{ tab.title }}</option>
                </select>
                <input v-model="sourceForm.range_a1" class="field-input bg-white" placeholder="Range A1, напр. A4:E102" />
              </div>
              <div class="mt-2 grid gap-2 md:grid-cols-4 xl:grid-cols-7">
                <input v-model="sourceForm.col_external_id" class="field-input bg-white" placeholder="SKU/ID колонка" />
                <input v-model="sourceForm.col_title" class="field-input bg-white" placeholder="Название" />
                <input v-model="sourceForm.col_wholesale" class="field-input bg-white" placeholder="Опт цена" />
                <select v-model="currencyMode" class="field-input bg-white">
                  <option value="BYN">Валюта: BYN</option>
                  <option value="USD">Валюта: USD</option>
                  <option value="EUR">Валюта: EUR</option>
                  <option value="COLUMN">Валюта из колонки</option>
                </select>
                <input v-if="currencyMode === 'COLUMN'" v-model="currencyColumn" class="field-input bg-white" placeholder="Колонка валюты" />
                <input v-else class="field-input bg-white text-slate-500" :value="currencyMode" disabled />
                <input v-model="sourceForm.col_rrc_byn" class="field-input bg-white" placeholder="РРЦ BYN" />
                <input v-model="sourceForm.col_qty" class="field-input bg-white" placeholder="Наличие" />
                <input v-model="sourceForm.col_source_url" class="field-input bg-white" placeholder="URL/Onliner" />
              </div>
              <div class="mt-3 flex flex-wrap gap-2">
                <button class="rounded-xl bg-teal-600 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50" :disabled="savingSource" @click="saveSource">{{ savingSource ? '...' : 'Сохранить источник' }}</button>
                <button v-if="editingSourceId" class="rounded-xl border border-slate-200 px-4 py-2 text-sm font-semibold" @click="resetSourceForm">Отмена</button>
                <button class="ml-auto rounded-xl bg-slate-900 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50" :disabled="syncingAll" @click="syncAll">{{ syncingAll ? 'Sync...' : 'Sync all' }}</button>
              </div>
            </section>

            <section class="overflow-x-auto rounded-xl border border-slate-200">
              <table class="w-full min-w-[900px] text-sm">
                <thead class="bg-slate-50 text-left text-slate-500">
                  <tr>
                    <th class="px-3 py-2">Supplier</th>
                    <th class="px-3 py-2">Sheet</th>
                    <th class="px-3 py-2">Status</th>
                    <th class="px-3 py-2">Last sync</th>
                    <th class="px-3 py-2 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="source in sourcesForSelected" :key="source.id" class="border-t border-slate-100 align-top">
                    <td class="px-3 py-2">{{ source.supplier_name || `#${source.supplier_id}` }}</td>
                    <td class="px-3 py-2">{{ source.sheet_name || '—' }} / {{ source.range_a1 || '—' }}</td>
                    <td class="px-3 py-2">
                      <span class="inline-flex items-center gap-1">
                        <CheckCircle2 v-if="source.last_sync_status === 'success'" class="h-4 w-4 text-green-600" />
                        <CircleAlert v-else-if="source.last_sync_status === 'error'" class="h-4 w-4 text-red-600" />
                        <CircleAlert v-else class="h-4 w-4 text-gray-400" />
                        {{ source.last_sync_status || 'never' }}
                      </span>
                    </td>
                    <td class="px-3 py-2">{{ source.last_sync_at ? new Date(source.last_sync_at).toLocaleString() : '—' }}</td>
                    <td class="px-3 py-2 text-right">
                      <div class="flex justify-end gap-2 whitespace-nowrap">
                        <button class="rounded-lg border p-2" title="Редактировать" @click="editSource(source)"><Pencil class="h-4 w-4" /></button>
                        <button class="rounded-lg border border-red-300 p-2 text-red-600 disabled:opacity-50" :disabled="deletingSourceId === source.id" title="Удалить" @click="deleteSource(source.id)"><Trash2 class="h-4 w-4" /></button>
                        <button class="rounded-lg border border-blue-300 p-2 text-blue-700 disabled:opacity-50" :disabled="analyzingSourceId === source.id" title="Анализ строк" @click="analyzeSource(source.id)"><FileSearch class="h-4 w-4" /></button>
                        <button class="rounded-lg border border-slate-700 p-2 text-slate-700 disabled:opacity-50" :disabled="syncingSourceId === source.id" title="Синхронизировать" @click="syncSource(source.id)"><RefreshCw class="h-4 w-4" /></button>
                      </div>
                    </td>
                  </tr>
                </tbody>
              </table>
            </section>
          </div>
        </div>
      </section>
    </div>
  </div>
</template>
