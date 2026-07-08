<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';
import {
  CheckCircle2,
  Clipboard,
  Copy,
  PackageCheck,
  PackagePlus,
  RefreshCw,
  Search,
  Truck,
  Warehouse,
} from 'lucide-vue-next';
import { api } from '../api';
import { getApiErrorMessage } from '../utils/api-errors';

type SupplyStatus =
  | 'draft'
  | 'awaiting_reply'
  | 'reserved'
  | 'ordered'
  | 'ready_for_pickup'
  | 'picked_up'
  | 'received'
  | 'canceled';

const statusOptions: Array<{ value: SupplyStatus | ''; label: string }> = [
  { value: '', label: 'Все статусы' },
  { value: 'draft', label: 'Черновик' },
  { value: 'awaiting_reply', label: 'Ждем ответ' },
  { value: 'reserved', label: 'Бронь' },
  { value: 'ordered', label: 'Заказано' },
  { value: 'ready_for_pickup', label: 'Готово к забору' },
  { value: 'picked_up', label: 'Забрано' },
  { value: 'received', label: 'Получено' },
  { value: 'canceled', label: 'Отменено' },
];

const statusLabels: Record<string, string> = Object.fromEntries(statusOptions.filter((item) => item.value).map((item) => [item.value, item.label]));
const intentLabels: Record<string, string> = {
  reserve: 'Забронировать',
  order: 'Заказать',
};
const paymentLabels: Record<string, string> = {
  cash: 'наличные',
  bank: 'безнал',
  mixed: 'смешанная',
  unknown: 'не указана',
};

const loading = ref(false);
const savingStock = ref(false);
const actionLoading = ref('');
const error = ref('');
const toast = ref('');

const requests = ref<any[]>([]);
const suppliers = ref<any[]>([]);
const warehousesBySupplier = ref<Record<number, any[]>>({});
const productOptions = ref<any[]>([]);
const productSearchLoading = ref(false);
let productSearchId = 0;

const filters = ref({
  status: '',
  supplier_id: 0,
  warehouse_id: 0,
  source_type: '',
});

const stockForm = ref({
  supplier_id: 0,
  warehouse_id: 0,
  intent: 'order',
  payment_method: 'unknown',
  product_id: 0,
  title: '',
  qty: 1,
  unit_cost: null as number | null,
  comment: '',
});

const selectedSupplier = computed(() => suppliers.value.find((supplier) => supplier.id === Number(stockForm.value.supplier_id)) || null);
const stockWarehouses = computed(() => warehousesBySupplier.value[Number(stockForm.value.supplier_id)] || []);
const filteredWarehouses = computed(() => {
  if (filters.value.supplier_id) return warehousesBySupplier.value[Number(filters.value.supplier_id)] || [];
  return Object.values(warehousesBySupplier.value).flat();
});

const groupedRequests = computed(() => {
  const groups = new Map<string, { key: string; title: string; requests: any[] }>();
  for (const request of requests.value) {
    const key = `${request.supplier_id || 0}:${request.warehouse_id || 0}`;
    const title = `${request.supplier_name || 'Поставщик'} · ${request.warehouse_name || request.warehouse_address || 'склад не выбран'}`;
    if (!groups.has(key)) groups.set(key, { key, title, requests: [] });
    groups.get(key)!.requests.push(request);
  }
  return Array.from(groups.values());
});

const activeRequestIds = computed(() => requests.value.map((request) => request.id));

const formatMoney = (value: unknown) => {
  const numberValue = Number(value || 0);
  if (!Number.isFinite(numberValue)) return '0 BYN';
  return `${numberValue.toLocaleString('ru-RU')} BYN`;
};

const formatDate = (value?: string | null) => {
  if (!value) return '';
  try {
    return new Date(value).toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });
  } catch {
    return value;
  }
};

const requestQty = (request: any) => (request.lines || []).reduce((sum: number, line: any) => sum + Number(line.qty || 0), 0);
const requestReceivedQty = (request: any) => (request.lines || []).reduce((sum: number, line: any) => sum + Number(line.received_qty || 0), 0);

const setToast = (message: string) => {
  toast.value = message;
  window.setTimeout(() => {
    if (toast.value === message) toast.value = '';
  }, 2600);
};

const copyText = async (text: string) => {
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    const area = document.createElement('textarea');
    area.value = text;
    area.style.position = 'fixed';
    area.style.left = '-9999px';
    document.body.appendChild(area);
    area.select();
    document.execCommand('copy');
    document.body.removeChild(area);
  }
};

const loadSuppliers = async () => {
  const response = await api.listSuppliers();
  suppliers.value = response.items || [];
};

const loadWarehouses = async (supplierId: number) => {
  if (!supplierId || warehousesBySupplier.value[supplierId]) return warehousesBySupplier.value[supplierId] || [];
  const response = await api.listSupplierWarehouses(supplierId);
  warehousesBySupplier.value = {
    ...warehousesBySupplier.value,
    [supplierId]: response.items || [],
  };
  return warehousesBySupplier.value[supplierId];
};

const preloadVisibleWarehouses = async () => {
  const ids = new Set<number>();
  for (const supplier of suppliers.value) ids.add(Number(supplier.id));
  for (const request of requests.value) ids.add(Number(request.supplier_id));
  await Promise.all(Array.from(ids).filter(Boolean).map((id) => loadWarehouses(id)));
};

const loadRequests = async () => {
  loading.value = true;
  error.value = '';
  try {
    const response = await api.listSupplyRequests({
      limit: 100,
      status: filters.value.status || null,
      supplierId: filters.value.supplier_id || null,
      warehouseId: filters.value.warehouse_id || null,
      sourceType: filters.value.source_type || null,
    });
    requests.value = response.items || [];
    await preloadVisibleWarehouses();
  } catch (err) {
    error.value = getApiErrorMessage(err);
  } finally {
    loading.value = false;
  }
};

const searchProducts = async () => {
  const query = stockForm.value.title.trim();
  stockForm.value.product_id = 0;
  if (query.length < 2) {
    productOptions.value = [];
    return;
  }
  const requestId = ++productSearchId;
  productSearchLoading.value = true;
  try {
    const items = await api.smartSearchProducts(query, 10);
    if (requestId === productSearchId) productOptions.value = items || [];
  } catch (err) {
    if (requestId === productSearchId) productOptions.value = [];
    setToast(`Ошибка поиска товара: ${getApiErrorMessage(err)}`);
  } finally {
    if (requestId === productSearchId) productSearchLoading.value = false;
  }
};

const selectProduct = (product: any) => {
  stockForm.value.product_id = Number(product.id || 0);
  stockForm.value.title = String(product.title || '');
  productOptions.value = [];
};

const resetStockForm = () => {
  const supplierId = Number(stockForm.value.supplier_id || 0);
  stockForm.value = {
    supplier_id: supplierId,
    warehouse_id: 0,
    intent: 'order',
    payment_method: selectedSupplier.value?.default_payment_method || 'unknown',
    product_id: 0,
    title: '',
    qty: 1,
    unit_cost: null,
    comment: '',
  };
};

const createStockRequest = async () => {
  if (!stockForm.value.supplier_id) {
    setToast('Выберите поставщика.');
    return;
  }
  if (!stockForm.value.product_id && !stockForm.value.title.trim()) {
    setToast('Выберите товар или укажите ручное название.');
    return;
  }
  savingStock.value = true;
  try {
    await api.createStockSupplyRequest({
      intent: stockForm.value.intent,
      comment: stockForm.value.comment || null,
      lines: [{
        supplier_id: Number(stockForm.value.supplier_id),
        warehouse_id: stockForm.value.warehouse_id ? Number(stockForm.value.warehouse_id) : null,
        product_id: stockForm.value.product_id ? Number(stockForm.value.product_id) : null,
        title: stockForm.value.title.trim() || null,
        qty: Number(stockForm.value.qty || 1),
        payment_method: stockForm.value.payment_method,
        unit_cost: stockForm.value.unit_cost,
        comment: stockForm.value.comment || null,
      }],
    });
    setToast('Строка добавлена в поставки.');
    resetStockForm();
    await loadRequests();
  } catch (err) {
    setToast(`Ошибка создания поставки: ${getApiErrorMessage(err)}`);
  } finally {
    savingStock.value = false;
  }
};

const copySupplierMessage = async (requestId: number, markSent = false) => {
  const key = `supplier:${requestId}:${markSent}`;
  actionLoading.value = key;
  try {
    const response = await api.generateSupplyRequestSupplierMessage(requestId, markSent);
    await copyText(response.text || '');
    setToast(markSent ? 'Текст скопирован, заявка отмечена отправленной.' : 'Текст поставщику скопирован.');
    if (markSent) await loadRequests();
  } catch (err) {
    setToast(`Не удалось подготовить сообщение: ${getApiErrorMessage(err)}`);
  } finally {
    actionLoading.value = '';
  }
};

const copyLogisticsMessage = async (requestIds: number[], markSent = false) => {
  if (!requestIds.length) return;
  const key = `logistics:${requestIds.join(',')}:${markSent}`;
  actionLoading.value = key;
  try {
    const response = await api.generateSupplyLogisticsMessage({ request_ids: requestIds, mark_sent: markSent });
    await copyText(response.text || '');
    setToast(markSent ? 'Текст логисту скопирован и отмечен.' : 'Текст логисту скопирован.');
    if (markSent) await loadRequests();
  } catch (err) {
    setToast(`Не удалось подготовить логистику: ${getApiErrorMessage(err)}`);
  } finally {
    actionLoading.value = '';
  }
};

const updateRequestStatus = async (request: any, status: SupplyStatus) => {
  const key = `status:${request.id}`;
  actionLoading.value = key;
  try {
    await api.patchSupplyRequest(request.id, { status });
    setToast('Статус поставки обновлен.');
    await loadRequests();
  } catch (err) {
    setToast(`Не удалось обновить статус: ${getApiErrorMessage(err)}`);
  } finally {
    actionLoading.value = '';
  }
};

const markRequestReceived = async (request: any) => {
  const key = `received:${request.id}`;
  actionLoading.value = key;
  try {
    for (const line of request.lines || []) {
      await api.patchSupplyRequestLine(line.id, {
        status: 'received',
        received_qty: Number(line.qty || 0),
      });
    }
    setToast('Поставка отмечена полученной.');
    await loadRequests();
  } catch (err) {
    setToast(`Не удалось отметить получение: ${getApiErrorMessage(err)}`);
  } finally {
    actionLoading.value = '';
  }
};

watch(() => filters.value.supplier_id, async (supplierId) => {
  filters.value.warehouse_id = 0;
  if (supplierId) await loadWarehouses(Number(supplierId));
  await loadRequests();
});

watch(() => [filters.value.status, filters.value.warehouse_id, filters.value.source_type], () => {
  void loadRequests();
});

watch(() => stockForm.value.supplier_id, async (supplierId) => {
  stockForm.value.warehouse_id = 0;
  if (supplierId) {
    await loadWarehouses(Number(supplierId));
    stockForm.value.payment_method = selectedSupplier.value?.default_payment_method || 'unknown';
  }
});

onMounted(async () => {
  await loadSuppliers();
  if (suppliers.value.length) {
    stockForm.value.supplier_id = suppliers.value[0].id;
    stockForm.value.payment_method = suppliers.value[0].default_payment_method || 'unknown';
    await loadWarehouses(suppliers.value[0].id);
  }
  await loadRequests();
});
</script>

<template>
  <div class="min-h-screen bg-slate-50 p-4 md:p-6">
    <header class="mb-4 flex flex-col gap-3 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm md:flex-row md:items-center md:justify-between">
      <div>
        <p class="text-xs font-semibold uppercase tracking-[0.18em] text-teal-700">CRM поставки</p>
        <h1 class="text-2xl font-bold text-slate-900">Поставки и брони</h1>
        <p class="mt-1 text-sm text-slate-500">Заявки поставщикам, складовые закупки и тексты для логиста.</p>
      </div>
      <button class="inline-flex items-center justify-center gap-2 rounded-xl border border-slate-200 px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50" :disabled="loading" @click="loadRequests">
        <RefreshCw class="h-4 w-4" /> Обновить
      </button>
    </header>

    <p v-if="error" class="mb-3 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{{ error }}</p>
    <p v-if="toast" class="fixed bottom-4 right-4 z-50 max-w-sm rounded-xl bg-slate-900 px-4 py-3 text-sm font-semibold text-white shadow-xl">{{ toast }}</p>

    <section class="mb-4 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
      <div class="grid gap-3 lg:grid-cols-[1fr_1fr_1fr_1fr_auto]">
        <label class="space-y-1 text-sm">
          <span class="font-semibold text-slate-600">Статус</span>
          <select v-model="filters.status" class="field-input bg-white">
            <option v-for="item in statusOptions" :key="item.value || 'all'" :value="item.value">{{ item.label }}</option>
          </select>
        </label>
        <label class="space-y-1 text-sm">
          <span class="font-semibold text-slate-600">Поставщик</span>
          <select v-model.number="filters.supplier_id" class="field-input bg-white">
            <option :value="0">Все поставщики</option>
            <option v-for="supplier in suppliers" :key="supplier.id" :value="supplier.id">{{ supplier.name }}</option>
          </select>
        </label>
        <label class="space-y-1 text-sm">
          <span class="font-semibold text-slate-600">Склад</span>
          <select v-model.number="filters.warehouse_id" class="field-input bg-white">
            <option :value="0">Все склады</option>
            <option v-for="warehouse in filteredWarehouses" :key="warehouse.id" :value="warehouse.id">{{ warehouse.name || warehouse.address }}</option>
          </select>
        </label>
        <label class="space-y-1 text-sm">
          <span class="font-semibold text-slate-600">Источник</span>
          <select v-model="filters.source_type" class="field-input bg-white">
            <option value="">Заказы и склад</option>
            <option value="order">Только заказы</option>
            <option value="stock">Только склад</option>
          </select>
        </label>
        <button class="mt-6 inline-flex items-center justify-center gap-2 rounded-xl bg-teal-600 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50" :disabled="!activeRequestIds.length" @click="copyLogisticsMessage(activeRequestIds, false)">
          <Truck class="h-4 w-4" /> Логисту
        </button>
      </div>
    </section>

    <div class="grid gap-4 xl:grid-cols-[360px_1fr]">
      <aside class="rounded-2xl border border-teal-100 bg-white p-4 shadow-sm">
        <div class="mb-3 flex items-center gap-2">
          <PackagePlus class="h-5 w-5 text-teal-700" />
          <h2 class="font-semibold text-slate-900">Добавить на склад</h2>
        </div>
        <div class="space-y-3">
          <label class="block text-sm">
            <span class="font-semibold text-slate-600">Поставщик</span>
            <select v-model.number="stockForm.supplier_id" class="field-input mt-1 bg-white">
              <option :value="0">Выберите поставщика</option>
              <option v-for="supplier in suppliers" :key="supplier.id" :value="supplier.id">{{ supplier.name }}</option>
            </select>
          </label>
          <label class="block text-sm">
            <span class="font-semibold text-slate-600">Склад отгрузки</span>
            <select v-model.number="stockForm.warehouse_id" class="field-input mt-1 bg-white">
              <option :value="0">Склад не выбран</option>
              <option v-for="warehouse in stockWarehouses" :key="warehouse.id" :value="warehouse.id">{{ warehouse.name || warehouse.address }}</option>
            </select>
          </label>
          <div class="grid grid-cols-2 gap-2">
            <select v-model="stockForm.intent" class="field-input bg-white">
              <option value="order">Заказать</option>
              <option value="reserve">Забронировать</option>
            </select>
            <select v-model="stockForm.payment_method" class="field-input bg-white">
              <option value="unknown">Оплата не указана</option>
              <option value="cash">Наличные</option>
              <option value="bank">Безнал</option>
              <option value="mixed">Смешанная</option>
            </select>
          </div>
          <label class="relative block text-sm">
            <span class="font-semibold text-slate-600">Товар или ручная строка</span>
            <div class="relative mt-1">
              <Search class="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
              <input v-model="stockForm.title" class="field-input pl-9" placeholder="MDV Iera 09..." @input="searchProducts" />
            </div>
            <div v-if="productSearchLoading || productOptions.length" class="absolute left-0 right-0 top-full z-20 mt-1 max-h-64 overflow-auto rounded-xl border border-slate-200 bg-white p-1 shadow-xl">
              <p v-if="productSearchLoading" class="px-3 py-2 text-xs text-slate-500">Поиск...</p>
              <button v-for="product in productOptions" :key="product.id" type="button" class="block w-full rounded-lg px-3 py-2 text-left text-sm hover:bg-slate-50" @click="selectProduct(product)">
                <span class="font-semibold text-slate-900">{{ product.title }}</span>
                <span class="ml-2 text-xs text-slate-500">#{{ product.id }}</span>
              </button>
            </div>
          </label>
          <div class="grid grid-cols-2 gap-2">
            <label class="text-sm">
              <span class="font-semibold text-slate-600">Кол-во</span>
              <input v-model.number="stockForm.qty" type="number" min="1" class="field-input mt-1" />
            </label>
            <label class="text-sm">
              <span class="font-semibold text-slate-600">Закупка</span>
              <input v-model.number="stockForm.unit_cost" type="number" min="0" class="field-input mt-1" placeholder="опц." />
            </label>
          </div>
          <textarea v-model="stockForm.comment" class="field-input min-h-[84px]" placeholder="Комментарий для поставщика или логиста" />
          <button class="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-teal-600 px-4 py-3 text-sm font-semibold text-white disabled:opacity-50" :disabled="savingStock" @click="createStockRequest">
            <PackagePlus class="h-4 w-4" /> {{ savingStock ? 'Создаю...' : 'Добавить в поставки' }}
          </button>
        </div>
      </aside>

      <main class="space-y-4">
        <div v-if="loading" class="rounded-2xl border border-slate-200 bg-white p-8 text-center text-slate-500">Загрузка поставок...</div>
        <div v-else-if="!requests.length" class="rounded-2xl border border-dashed border-slate-300 bg-white p-8 text-center text-slate-500">Задач поставки по фильтрам нет.</div>
        <section v-for="group in groupedRequests" :key="group.key" class="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
          <header class="mb-3 flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
            <div class="flex items-center gap-2">
              <Warehouse class="h-5 w-5 text-teal-700" />
              <h2 class="font-semibold text-slate-900">{{ group.title }}</h2>
              <span class="rounded-full bg-slate-100 px-2 py-1 text-xs font-semibold text-slate-600">{{ group.requests.length }}</span>
            </div>
            <button class="inline-flex items-center justify-center gap-2 rounded-xl border border-slate-200 px-3 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50" @click="copyLogisticsMessage(group.requests.map((request) => request.id), false)">
              <Clipboard class="h-4 w-4" /> Скопировать логисту
            </button>
          </header>

          <div class="grid gap-3 2xl:grid-cols-2">
            <article v-for="request in group.requests" :key="request.id" class="rounded-xl border border-slate-200 p-3">
              <div class="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                <div class="min-w-0">
                  <div class="mb-2 flex flex-wrap items-center gap-2">
                    <span class="rounded-full bg-teal-50 px-2 py-1 text-xs font-semibold text-teal-700">#{{ request.id }}</span>
                    <span class="rounded-full bg-slate-100 px-2 py-1 text-xs font-semibold text-slate-700">{{ statusLabels[request.status] || request.status }}</span>
                    <span class="rounded-full bg-indigo-50 px-2 py-1 text-xs font-semibold text-indigo-700">{{ intentLabels[request.intent] || request.intent }}</span>
                    <span class="rounded-full bg-amber-50 px-2 py-1 text-xs font-semibold text-amber-700">{{ paymentLabels[request.payment_method] || request.payment_method }}</span>
                  </div>
                  <p class="text-sm text-slate-500">
                    {{ requestQty(request) }} ед. · получено {{ requestReceivedQty(request) }} · {{ formatDate(request.updated_at) }}
                  </p>
                  <p v-if="request.comment" class="mt-1 text-sm text-slate-600">{{ request.comment }}</p>
                </div>
                <div class="flex shrink-0 flex-wrap gap-2">
                  <button class="rounded-lg border border-slate-200 p-2 text-slate-700 hover:bg-slate-50" title="Скопировать поставщику" @click="copySupplierMessage(request.id, false)">
                    <Copy class="h-4 w-4" />
                  </button>
                  <button class="rounded-lg border border-teal-200 p-2 text-teal-700 hover:bg-teal-50" title="Скопировать и отметить отправленным" @click="copySupplierMessage(request.id, true)">
                    <CheckCircle2 class="h-4 w-4" />
                  </button>
                  <button class="rounded-lg border border-emerald-200 p-2 text-emerald-700 hover:bg-emerald-50" title="Отметить полученным" @click="markRequestReceived(request)">
                    <PackageCheck class="h-4 w-4" />
                  </button>
                </div>
              </div>

              <div class="mt-3 overflow-hidden rounded-lg border border-slate-100">
                <div v-for="line in request.lines || []" :key="line.id" class="border-b border-slate-100 p-3 last:border-b-0">
                  <div class="flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
                    <div>
                      <p class="font-semibold text-slate-900">{{ line.title_snapshot }}</p>
                      <p class="mt-1 text-sm text-slate-500">
                        {{ line.qty }} шт. · {{ line.unit_cost_snapshot ? formatMoney(line.unit_cost_snapshot) : 'цена не указана' }}
                        <span v-if="line.order_product_link_id"> · заказная строка #{{ line.order_product_link_id }}</span>
                        <span v-else> · склад</span>
                      </p>
                      <p v-if="line.comment" class="mt-1 text-sm text-slate-500">{{ line.comment }}</p>
                    </div>
                    <div class="flex items-center gap-2">
                      <span class="rounded-full bg-slate-100 px-2 py-1 text-xs font-semibold text-slate-700">{{ statusLabels[line.status] || line.status }}</span>
                      <span class="text-xs text-slate-500">получено {{ line.received_qty }}</span>
                    </div>
                  </div>
                </div>
              </div>

              <div class="mt-3 flex flex-col gap-2 sm:flex-row sm:items-center">
                <select class="field-input bg-white sm:max-w-[220px]" :value="request.status" :disabled="actionLoading === `status:${request.id}`" @change="updateRequestStatus(request, ($event.target as HTMLSelectElement).value as SupplyStatus)">
                  <option v-for="item in statusOptions.filter((option) => option.value)" :key="item.value" :value="item.value">{{ item.label }}</option>
                </select>
                <button class="rounded-xl border border-slate-200 px-3 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50" @click="copyLogisticsMessage([request.id], false)">Логисту</button>
              </div>
            </article>
          </div>
        </section>
      </main>
    </div>
  </div>
</template>
