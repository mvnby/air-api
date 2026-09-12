<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch } from 'vue';
import { Search, Users, ChevronLeft, ChevronRight, Phone, Mail, Building, Plus, Star, UserPlus } from 'lucide-vue-next';
import { api } from '../api';
import type { ManagerCatalogCustomerItemResponse } from '../client';
import { CUSTOMER_UPDATED_EVENT, type CustomerUpdatedEventPayload } from '../utils/customer-events';
import CreateOrderModal from '../components/CreateOrderModal.vue';
import CreateCustomerModal from '../components/customers/CreateCustomerModal.vue';

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
const showCreateCustomer = ref(false);
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
  individual_entrepreneur: { label: 'ИП', icon: '💼' },
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

function onCustomerCreated(customer: ManagerCatalogCustomerItemResponse) {
  showCreateCustomer.value = false;
  openCustomerProfile(customer.id);
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
        <span class="material-icons-round text-brand-600 dark:text-brand-400">group</span>
        Клиенты
      </h1>
      <div class="header-controls">
        <button
          type="button"
          data-testid="create-customer"
          class="inline-flex items-center gap-2 whitespace-nowrap rounded-lg bg-brand-600 px-4 py-2 text-sm font-semibold text-white shadow-sm transition-colors hover:bg-brand-500"
          @click="showCreateCustomer = true"
        >
          <UserPlus :size="17" />
          Новый клиент
        </button>
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
              :class="!typeFilter ? 'bg-white dark:bg-slate-600 text-brand-700 dark:text-brand-400 shadow-sm font-medium' : 'text-gray-500 dark:text-slate-400 hover:text-gray-700 dark:hover:text-slate-200'"
          >Все</button>
          <button
              @click="typeFilter = 'individual'; onTypeChange()"
              class="px-3 py-1.5 text-sm rounded-md transition-all"
              :class="typeFilter === 'individual' ? 'bg-white dark:bg-slate-600 text-brand-700 dark:text-brand-400 shadow-sm font-medium' : 'text-gray-500 dark:text-slate-400 hover:text-gray-700 dark:hover:text-slate-200'"
          >Физ. лица</button>
          <button
              @click="typeFilter = 'individual_entrepreneur'; onTypeChange()"
              class="px-3 py-1.5 text-sm rounded-md transition-all"
              :class="typeFilter === 'individual_entrepreneur' ? 'bg-white dark:bg-slate-600 text-brand-700 dark:text-brand-400 shadow-sm font-medium' : 'text-gray-500 dark:text-slate-400 hover:text-gray-700 dark:hover:text-slate-200'"
          >ИП</button>
          <button
              @click="typeFilter = 'company'; onTypeChange()"
              class="px-3 py-1.5 text-sm rounded-md transition-all"
              :class="typeFilter === 'company' ? 'bg-white dark:bg-slate-600 text-brand-700 dark:text-brand-400 shadow-sm font-medium' : 'text-gray-500 dark:text-slate-400 hover:text-gray-700 dark:hover:text-slate-200'"
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
      <div v-if="toast" class="fixed top-6 right-6 z-[100] bg-brand-600 text-white px-6 py-3 rounded-xl shadow-2xl font-medium animate-in slide-in-from-top-4 duration-300">
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
        <button type="button" class="mt-4 inline-flex items-center gap-2 rounded-lg bg-brand-600 px-4 py-2 text-sm font-semibold text-white hover:bg-brand-500" @click="showCreateCustomer = true">
          <UserPlus :size="17" />
          Создать первого клиента
        </button>
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

    <CreateCustomerModal
      v-if="showCreateCustomer"
      @close="showCreateCustomer = false"
      @created="onCustomerCreated"
      @open-existing="openCustomerProfile"
    />

  </div>
</template>

<style scoped src="../styles/customers.css"></style>
