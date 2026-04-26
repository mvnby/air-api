<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch } from 'vue';
import { Search, Users, ChevronLeft, ChevronRight, Phone, Mail, Building, Plus, Star } from 'lucide-vue-next';
import { api } from '../api';
import type { ManagerCatalogCustomerItemResponse } from '../client';
import { CUSTOMER_UPDATED_EVENT, type CustomerUpdatedEventPayload } from '../utils/customer-events';
import CreateOrderModal from '../components/CreateOrderModal.vue';

// --- State ---
const customers = ref<ManagerCatalogCustomerItemResponse[]>([]);
const loading = ref(false);
const searchQuery = ref('');
const typeFilter = ref('');
const onlyWithOrders = ref(false);
const page = ref(1);
const meta = ref({ total: 0, pages: 1, limit: 20 });
const recentlyUpdated = ref<Record<number, number>>({});
const favoriteSaving = ref<Record<number, boolean>>({});
const cleanupTimers = new Map<number, number>();
const toast = ref('');
const showCreateOrder = ref(false);
const createOrderCustomer = ref<{ id: number; name: string } | null>(null);

function sortCustomerItems(items: ManagerCatalogCustomerItemResponse[]) {
  return [...items].sort((a, b) => {
    const favoriteDiff = Number(Boolean(b.is_favorite)) - Number(Boolean(a.is_favorite));
    if (favoriteDiff !== 0) return favoriteDiff;
    return new Date(b.created_at || 0).getTime() - new Date(a.created_at || 0).getTime();
  });
}

function openCreateOrder(customer: ManagerCatalogCustomerItemResponse) {
  createOrderCustomer.value = { id: customer.id, name: customer.full_legal_name || customer.name || `Клиент #${customer.id}` };
  showCreateOrder.value = true;
}

async function toggleFavorite(customer: ManagerCatalogCustomerItemResponse) {
  if (favoriteSaving.value[customer.id]) return;

  const nextFavorite = !customer.is_favorite;
  favoriteSaving.value = { ...favoriteSaving.value, [customer.id]: true };
  customers.value = sortCustomerItems(customers.value.map((item) => (
    item.id === customer.id ? { ...item, is_favorite: nextFavorite } : item
  )));

  try {
    const updated = await api.patchManagerCustomer(customer.id, { is_favorite: nextFavorite });
    customers.value = sortCustomerItems(customers.value.map((item) => (item.id === updated.id ? { ...item, ...updated } : item)));
    setToast(nextFavorite ? 'Клиент добавлен в избранное' : 'Клиент убран из избранного');
  } catch (e) {
    console.error('Failed to toggle customer favorite', e);
    customers.value = sortCustomerItems(customers.value.map((item) => (
      item.id === customer.id ? { ...item, is_favorite: !nextFavorite } : item
    )));
    setToast('Не удалось обновить избранное');
  } finally {
    const nextSaving = { ...favoriteSaving.value };
    delete nextSaving[customer.id];
    favoriteSaving.value = nextSaving;
  }
}

function onOrderCreated(orderId: number) {
  showCreateOrder.value = false;
  createOrderCustomer.value = null;
  window.history.pushState({}, '', `/manager/orders/kanban?orderId=${orderId}`);
  window.dispatchEvent(new PopStateEvent('popstate'));
}

function setToast(msg: string) {
  toast.value = msg;
  setTimeout(() => {
    if (toast.value === msg) toast.value = '';
  }, 3000);
}

const TYPE_MAP: Record<string, { label: string; icon: string }> = {
  individual: { label: 'Физ. лицо', icon: '👤' },
  company: { label: 'Юр. лицо', icon: '🏢' },
};

// --- Fetch ---
async function loadCustomers() {
  loading.value = true;
  try {
    const data = await api.getManagerCustomers(
      page.value,
      meta.value.limit,
      searchQuery.value || undefined,
      typeFilter.value || undefined,
      onlyWithOrders.value,
    );
    customers.value = sortCustomerItems(data.items);
    meta.value = data.meta;
  } catch (e) {
    console.error('Failed to load customers', e);
    setToast('Не удалось загрузить список клиентов');
  } finally {
    loading.value = false;
  }
}

function onSearch() {
  page.value = 1;
  loadCustomers();
}

function onTypeChange() {
  page.value = 1;
  loadCustomers();
}

function goToPage(p: number) {
  if (p < 1 || p > meta.value.pages) return;
  page.value = p;
  loadCustomers();
}

function formatDate(iso: string | null) {
  if (!iso) return '—';
  const d = new Date(iso);
  return d.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric' });
}

function openCustomerProfile(customerId: number) {
  window.history.pushState({}, '', `/manager/customers/profile?customerId=${customerId}`);
  window.dispatchEvent(new PopStateEvent('popstate'));
}

onMounted(() => {
  const customerIdRaw = new URLSearchParams(window.location.search).get('customerId');
  if (customerIdRaw) {
    const customerId = Number(customerIdRaw);
    if (Number.isFinite(customerId) && customerId > 0) {
      openCustomerProfile(customerId);
      return;
    }
  }

  const sQuery = sessionStorage.getItem('customers_search');
  if (sQuery) searchQuery.value = sQuery;
  
  const sType = sessionStorage.getItem('customers_type');
  if (sType !== null) typeFilter.value = sType;
  
  const sOrders = sessionStorage.getItem('customers_orders');
  if (sOrders) onlyWithOrders.value = sOrders === 'true';
  
  const sPage = sessionStorage.getItem('customers_page');
  if (sPage) page.value = Number(sPage) || 1;

  void loadCustomers();
});

watch([searchQuery, typeFilter, onlyWithOrders, page], () => {
  sessionStorage.setItem('customers_search', searchQuery.value);
  sessionStorage.setItem('customers_type', typeFilter.value);
  sessionStorage.setItem('customers_orders', String(onlyWithOrders.value));
  sessionStorage.setItem('customers_page', String(page.value));
});

const handleCustomerUpdated = (event: Event) => {
  const detail = (event as CustomEvent<CustomerUpdatedEventPayload>).detail;
  const updated = detail?.customer;
  if (!updated) return;
  customers.value = customers.value.map((item) => (item.id === updated.id ? { ...item, ...updated } : item));
  recentlyUpdated.value[updated.id] = Date.now();
  const prevTimer = cleanupTimers.get(updated.id);
  if (prevTimer) {
    window.clearTimeout(prevTimer);
  }
  const timer = window.setTimeout(() => {
    delete recentlyUpdated.value[updated.id];
    cleanupTimers.delete(updated.id);
  }, 12000);
  cleanupTimers.set(updated.id, timer);
};

onMounted(() => {
  window.addEventListener(CUSTOMER_UPDATED_EVENT, handleCustomerUpdated);
});

onUnmounted(() => {
  window.removeEventListener(CUSTOMER_UPDATED_EVENT, handleCustomerUpdated);
  cleanupTimers.forEach((timer) => window.clearTimeout(timer));
  cleanupTimers.clear();
});
</script>

<template>
  <div class="customers-view">
    <!-- Header -->
    <div class="view-header">
      <h1 class="text-2xl font-bold text-gray-900 dark:text-white tracking-tight flex items-center gap-3">
        <span class="material-icons-round text-teal-600 dark:text-teal-400">group</span>
        Клиенты
      </h1>
      <div class="header-controls">
        <div class="search-box">
          <Search :size="16" />
          <input
            v-model="searchQuery"
            placeholder="Поиск клиентов..."
            @keyup.enter="onSearch"
          />
        </div>
        <div class="flex bg-gray-100 dark:bg-slate-700 p-1 rounded-lg">
          <button 
              @click="typeFilter = ''; onTypeChange()"
              class="px-3 py-1.5 text-sm rounded-md transition-all"
              :class="!typeFilter ? 'bg-white dark:bg-slate-600 text-teal-700 dark:text-teal-400 shadow-sm font-medium' : 'text-gray-500 dark:text-slate-400 hover:text-gray-700 dark:hover:text-slate-200'"
          >Все</button>
          <button 
              @click="typeFilter = 'individual'; onTypeChange()"
              class="px-3 py-1.5 text-sm rounded-md transition-all"
              :class="typeFilter === 'individual' ? 'bg-white dark:bg-slate-600 text-teal-700 dark:text-teal-400 shadow-sm font-medium' : 'text-gray-500 dark:text-slate-400 hover:text-gray-700 dark:hover:text-slate-200'"
          >Физ. лица</button>
          <button 
              @click="typeFilter = 'company'; onTypeChange()"
              class="px-3 py-1.5 text-sm rounded-md transition-all"
              :class="typeFilter === 'company' ? 'bg-white dark:bg-slate-600 text-teal-700 dark:text-teal-400 shadow-sm font-medium' : 'text-gray-500 dark:text-slate-400 hover:text-gray-700 dark:hover:text-slate-200'"
          >Юр. лица</button>
        </div>
        <label class="inline-flex items-center gap-2 rounded-lg border border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-800 px-3 py-2 text-sm text-gray-700 dark:text-slate-300">
          <input v-model="onlyWithOrders" type="checkbox" @change="onTypeChange" />
          Только с заказами
        </label>
      </div>
    </div>

    <!-- Toast -->
    <Transition name="fade">
      <div v-if="toast" class="fixed top-6 right-6 z-[100] bg-teal-600 text-white px-6 py-3 rounded-xl shadow-2xl font-medium animate-in slide-in-from-top-4 duration-300">
        {{ toast }}
      </div>
    </Transition>

    <!-- Loading -->
    <div v-if="loading" class="loading-state">
      <div class="spinner"></div>
      <p>Загрузка...</p>
    </div>

    <!-- Empty -->
    <div v-else-if="customers.length === 0" class="empty-state border border-dashed border-gray-300 dark:border-slate-700 bg-white dark:bg-slate-800">
      <div class="flex justify-center mb-4">
        <Users :size="64" class="text-gray-300 dark:text-slate-600" />
      </div>
      <h2 class="text-xl font-bold mb-2 text-gray-900 dark:text-white">Клиенты не найдены</h2>
      <p v-if="searchQuery || typeFilter" class="text-gray-500 dark:text-slate-400">Попробуйте изменить поисковый запрос "{{ searchQuery }}" или фильтры</p>
      <p v-else-if="onlyWithOrders" class="text-gray-500 dark:text-slate-400">Нет клиентов с заказами по текущим фильтрам.</p>
      <div v-else class="text-gray-500 dark:text-slate-400">
        <p>Клиентская база пуста.</p>
        <p class="text-xs mt-1">Клиенты появятся здесь при создании заказов или лидов.</p>
      </div>
    </div>

    <!-- Cards Grid -->
    <div v-else class="customers-grid">
      <div v-for="customer in customers" :key="customer.id" class="customer-card">
        <div class="card-header">
          <div class="avatar" :class="customer.type">
            {{ (customer.name || 'К').charAt(0).toUpperCase() }}
          </div>
          <div class="card-info">
            <div class="customer-name">{{ customer.name }}</div>
            <span class="type-badge" :class="customer.type">
              {{ TYPE_MAP[customer.type]?.icon }} {{ TYPE_MAP[customer.type]?.label || customer.type }}
            </span>
            <span v-if="recentlyUpdated[customer.id]" class="updated-badge">обновлено</span>
          </div>
        </div>

        <div class="card-details">
          <div class="detail-row" v-if="customer.phone">
            <Phone :size="14" />
            <span>{{ customer.phone }}</span>
          </div>
          <div class="detail-row" v-if="customer.email">
            <Mail :size="14" />
            <span>{{ customer.email }}</span>
          </div>
          <div class="detail-row" v-if="customer.inn">
            <Building :size="14" />
            <span>ИНН: {{ customer.inn }}</span>
          </div>
          <div class="detail-row" v-if="customer.full_legal_name">
            <Building :size="14" />
            <span class="legal-name">{{ customer.full_legal_name }}</span>
          </div>
        </div>

        <div class="card-footer">
          <div class="order-count">
            <span class="count-number">{{ customer.order_count }}</span>
            <span class="count-label">{{ customer.order_count === 1 ? 'заказ' : (customer.order_count >= 2 && customer.order_count <= 4 ? 'заказа' : 'заказов') }}</span>
          </div>
          <div class="footer-actions">
            <div class="date-added">{{ formatDate(customer.created_at) }}</div>
            <button
              class="favorite-btn"
              :class="{ active: customer.is_favorite }"
              :disabled="favoriteSaving[customer.id]"
              :title="customer.is_favorite ? 'Убрать из избранного' : 'Добавить в избранное'"
              @click="toggleFavorite(customer)"
            >
              <Star :size="15" :fill="customer.is_favorite ? 'currentColor' : 'none'" />
            </button>
            <button class="open-btn" @click="openCreateOrder(customer)" title="Создать заказ">
              <Plus :size="14" />
            </button>
            <button class="open-btn" @click="openCustomerProfile(customer.id)">Карточка</button>
          </div>
        </div>
      </div>
    </div>

    <!-- Pagination -->
    <div v-if="meta.pages > 1" class="pagination">
      <button @click="goToPage(page - 1)" :disabled="page <= 1" class="page-btn">
        <ChevronLeft :size="16" />
      </button>
      <span class="page-info">{{ page }} / {{ meta.pages }} ({{ meta.total }} записей)</span>
      <button @click="goToPage(page + 1)" :disabled="page >= meta.pages" class="page-btn">
        <ChevronRight :size="16" />
      </button>
    </div>

    <CreateOrderModal
      v-if="showCreateOrder && createOrderCustomer"
      :customer-id="createOrderCustomer.id"
      :customer-name="createOrderCustomer.name"
      @close="showCreateOrder = false; createOrderCustomer = null"
      @created="onOrderCreated"
    />

  </div>
</template>

<style scoped>
.customers-view {
  padding: 24px 32px;
}

.view-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 24px;
  flex-wrap: wrap;
  gap: 12px;
}

/* .view-header h1 {
  font-size: 28px;
  font-weight: 700;
  color: #1a1a2e;
  margin: 0;
} */

.header-controls {
  display: flex;
  gap: 12px;
  align-items: center;
}

.search-box {
  display: flex;
  align-items: center;
  gap: 8px;
  background: var(--mv-bg);
  border-radius: 10px;
  padding: 8px 14px;
  border: 1px solid var(--mv-border);
  transition: border-color 0.2s;
}
:global(.dark) .search-box {
  background: #1e293b;
  border-color: #334155;
  color: #e2e8f0;
}
.search-box:focus-within {
  border-color: #007f80;
}
.search-box input {
  border: none;
  background: transparent;
  outline: none;
  font-size: 14px;
  width: 200px;
  color: var(--mv-text);
}



/* Loading */
.loading-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 80px 0;
}
.spinner {
  width: 40px;
  height: 40px;
  border: 3px solid var(--mv-border);
  border-top-color: var(--mv-teal);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }

/* Empty */
.empty-state {
  text-align: center;
  padding: 80px 20px;
  background: var(--mv-surface);
  border-radius: 16px;
}
.empty-state h2 {
  margin: 16px 0 8px;
  color: #1a1a2e;
}
.empty-state p {
  color: #888;
  font-size: 14px;
}

/* Grid */
.customers-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 16px;
}

/* Card */
.customer-card {
  background: var(--mv-surface);
  border: 1px solid var(--mv-border);
  border-radius: 14px;
  padding: 20px;
  transition: all 0.2s;
}
.customer-card:hover {
  border-color: #007f80;
  box-shadow: 0 4px 20px rgba(0, 127, 128, 0.08);
  transform: translateY(-2px);
}

.updated-badge {
  display: inline-flex;
  margin-top: 6px;
  align-self: flex-start;
  padding: 2px 8px;
  border-radius: 9999px;
  font-size: 11px;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  background: rgba(16, 185, 129, 0.15);
  color: #059669;
  border: 1px solid rgba(16, 185, 129, 0.35);
}

.card-header {
  display: flex;
  gap: 14px;
  align-items: center;
  margin-bottom: 16px;
}

.avatar {
  width: 44px;
  height: 44px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
  font-size: 18px;
  color: #fff;
  flex-shrink: 0;
}
.avatar.individual {
  background: linear-gradient(135deg, #007f80, #00adb5);
}
.avatar.company {
  background: linear-gradient(135deg, #6366f1, #8b5cf6);
}

.card-info {
  flex: 1;
  min-width: 0;
}

.customer-name {
  font-weight: 600;
  font-size: 16px;
  color: var(--mv-text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.type-badge {
  display: inline-block;
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 6px;
  margin-top: 4px;
  font-weight: 500;
}
.type-badge.individual {
  background: #e6f7f7;
  color: #007f80;
}
.type-badge.company {
  background: #eef2ff;
  color: #6366f1;
}

/* Details */
.card-details {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding-bottom: 14px;
  border-bottom: 1px solid var(--mv-border);
  margin-bottom: 14px;
}

.detail-row {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: var(--mv-text-muted);
}
.detail-row svg {
  color: var(--mv-text-muted);
  opacity: 0.7;
  flex-shrink: 0;
}
.legal-name {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* Footer */
.card-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.footer-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

.order-count {
  display: flex;
  align-items: baseline;
  gap: 4px;
}
.count-number {
  font-size: 20px;
  font-weight: 700;
  color: #007f80;
}
.count-label {
  font-size: 13px;
  color: var(--mv-text-muted);
}

.date-added {
  font-size: 12px;
  color: var(--mv-text-muted);
  opacity: 0.6;
}

.open-btn {
  border: 1px solid var(--mv-border);
  background: var(--mv-surface);
  border-radius: 8px;
  font-size: 12px;
  padding: 6px 10px;
  color: var(--mv-teal);
  font-weight: 600;
  cursor: pointer;
}

.open-btn:hover {
  background: var(--mv-bg);
}

.favorite-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border: 1px solid var(--mv-border);
  background: var(--mv-surface);
  border-radius: 8px;
  color: var(--mv-text-muted);
  cursor: pointer;
  transition: all 0.2s;
}

.favorite-btn:hover:not(:disabled),
.favorite-btn.active {
  border-color: rgba(245, 158, 11, 0.55);
  background: rgba(245, 158, 11, 0.12);
  color: #d97706;
}

.favorite-btn:disabled {
  cursor: wait;
  opacity: 0.65;
}

.drawer-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.45);
  z-index: 60;
  display: flex;
  justify-content: flex-end;
}

.customer-drawer {
  width: min(460px, 100%);
  height: 100%;
  background: var(--mv-surface);
  border-left: 1px solid var(--mv-border);
  padding: 20px;
  overflow-y: auto;
}

.drawer-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.drawer-header h3 {
  margin: 0;
  font-size: 20px;
  color: #1a1a2e;
}

.icon-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border-radius: 8px;
  border: 1px solid var(--mv-border);
  background: var(--mv-surface);
  cursor: pointer;
  color: var(--mv-text);
}

.icon-btn:hover {
  background: #f4f6f9;
}

.drawer-body {
  display: grid;
  gap: 10px;
}

.drawer-row {
  display: grid;
  gap: 4px;
  border: 1px solid var(--mv-border);
  border-radius: 10px;
  padding: 10px 12px;
}

.drawer-row .label {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--mv-text-muted);
}

.drawer-row .value {
  color: var(--mv-text);
  font-weight: 600;
  word-break: break-word;
}

/* Pagination */
.pagination {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 16px;
  margin-top: 24px;
}

.page-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border: 1px solid var(--mv-border);
  border-radius: 8px;
  background: var(--mv-surface);
  cursor: pointer;
  color: var(--mv-text);
  transition: all 0.2s;
}
.page-btn:hover:not(:disabled) {
  background: #007f80;
  color: #fff;
  border-color: #007f80;
}
.page-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.page-info {
  font-size: 14px;
  color: var(--mv-text-muted);
}

:global(.dark) .customers-view .type-badge.individual {
  background: rgba(0, 127, 128, 0.2);
  color: #2dd4bf;
}
:global(.dark) .customers-view .type-badge.company {
  background: rgba(99, 102, 241, 0.2);
  color: #a5b4fc;
}

/* :global(.dark) .customers-view .view-header h1 {
  color: #e2e8f0;
} */

:global(.dark) .customers-view .search-box {
  background: #1e293b;
  border-color: #334155;
  color: #e2e8f0;
}

:global(.dark) .customers-view .search-box input {
  color: #e2e8f0;
}

:global(.dark) .customers-view .search-box input::placeholder {
  color: #94a3b8;
}

:global(.dark) .customers-view .empty-state {
  background: #1e293b;
}

:global(.dark) .customers-view .empty-state h2 {
  color: #e2e8f0;
}

:global(.dark) .customers-view .empty-state p {
  color: #94a3b8;
}

:global(.dark) .customers-view .customer-card {
  background: #1e293b;
  border-color: #334155;
}

:global(.dark) .customers-view .customer-name {
  color: #f8fafc;
}

:global(.dark) .customers-view .detail-row {
  color: #cbd5e1;
}

:global(.dark) .customers-view .detail-row svg {
  color: #94a3b8;
}

:global(.dark) .customers-view .card-details {
  border-bottom-color: #334155;
}

:global(.dark) .customers-view .count-label,
:global(.dark) .customers-view .date-added,
:global(.dark) .customers-view .page-info {
  color: #94a3b8;
}

:global(.dark) .customers-view .open-btn,
:global(.dark) .customers-view .icon-btn,
:global(.dark) .customers-view .favorite-btn,
:global(.dark) .customers-view .page-btn {
  background: #0f172a;
  border-color: #334155;
  color: #e2e8f0;
}

:global(.dark) .customers-view .open-btn:hover,
:global(.dark) .customers-view .icon-btn:hover {
  background: #253246;
}

:global(.dark) .customers-view .favorite-btn:hover:not(:disabled),
:global(.dark) .customers-view .favorite-btn.active {
  border-color: rgba(251, 191, 36, 0.55);
  background: rgba(251, 191, 36, 0.14);
  color: #fbbf24;
}

/* :global(.dark) .customers-view .view-header h1 {
  color: #e2e8f0;
} */

:global(.dark) .customers-view .search-box {
  background: #1e293b;
  border-color: #334155;
  color: #e2e8f0;
}

:global(.dark) .customers-view .search-box input {
  color: #e2e8f0;
}

:global(.dark) .customers-view .search-box input::placeholder {
  color: #94a3b8;
}

:global(.dark) .customers-view .empty-state {
  background: #1e293b;
}

:global(.dark) .customers-view .empty-state h2 {
  color: #e2e8f0;
}

:global(.dark) .customers-view .empty-state p {
  color: #94a3b8;
}

:global(.dark) .customers-view .customer-card {
  background: #1e293b;
  border-color: #334155;
}

:global(.dark) .customers-view .customer-name {
  color: #f8fafc;
}

:global(.dark) .customers-view .detail-row {
  color: #cbd5e1;
}

:global(.dark) .customers-view .detail-row svg {
  color: #94a3b8;
}

:global(.dark) .customers-view .card-details {
  border-bottom-color: #334155;
}

:global(.dark) .customers-view .count-label,
:global(.dark) .customers-view .date-added,
:global(.dark) .customers-view .page-info {
  color: #94a3b8;
}

:global(.dark) .customers-view .open-btn,
:global(.dark) .customers-view .icon-btn,
:global(.dark) .customers-view .favorite-btn,
:global(.dark) .customers-view .page-btn {
  background: #0f172a;
  border-color: #334155;
  color: #e2e8f0;
}

:global(.dark) .customers-view .open-btn:hover,
:global(.dark) .customers-view .icon-btn:hover {
  background: #253246;
}
</style>
