<script setup lang="ts">
import { computed, ref, onMounted, onUnmounted, watch } from 'vue';
import { Search, Users, ChevronLeft, ChevronRight, Phone, Mail, Plus, Star, X } from 'lucide-vue-next';
import { api } from '../api';
import type { ManagerCatalogCustomerItemResponse } from '../client';
import { managerSession } from '../services/manager-session';
import { CUSTOMER_UPDATED_EVENT, type CustomerUpdatedEventPayload } from '../utils/customer-events';
import CreateOrderModal from '../components/CreateOrderModal.vue';
import CustomerIntakeDialog from '../components/customers/CustomerIntakeDialog.vue';

// --- State ---
type CustomerListItem = ManagerCatalogCustomerItemResponse & {
  primary_contact?: { name?: string | null; role?: string | null; phone?: string | null; email?: string | null } | null;
};
const customers = ref<CustomerListItem[]>([]);
const loading = ref(false);
const searchQuery = ref('');
const typeFilter = ref('');
const onlyWithOrders = ref(false);
const onlyFavorites = ref(false);
const includeArchived = ref(false);
const page = ref(1);
const meta = ref({ total: 0, pages: 1, limit: 20 });
const loadError = ref('');
const hasLoaded = ref(false);
const recentlyUpdated = ref<Record<number, number>>({});
const favoriteSaving = ref<Record<number, boolean>>({});
const cleanupTimers = new Map<number, number>();
const toast = ref('');
const showCreateOrder = ref(false);
const showCreateCustomer = ref(false);
const createOrderCustomer = ref<{ id: number; name: string } | null>(null);
let loadRequestId = 0;
let isUnmounted = false;
let isMounted = false;
let searchTimer: number | undefined;
const filterStorageKey = computed(() => {
  const auth = managerSession.auth.value;
  if (!auth) return '';
  const user = auth.staff_user_id ? `staff-${auth.staff_user_id}` : `user-${encodeURIComponent(auth.username.trim().toLowerCase())}`;
  return `manager:customers:v2:${auth.tenant_id}:${user}`;
});

function restoreFilters() {
  searchQuery.value = '';
  typeFilter.value = '';
  onlyWithOrders.value = false;
  onlyFavorites.value = false;
  includeArchived.value = false;
  page.value = 1;
  if (!filterStorageKey.value) return;
  try {
    const saved = JSON.parse(sessionStorage.getItem(filterStorageKey.value) || '{}');
    if (typeof saved.search === 'string') searchQuery.value = saved.search;
    if (['', 'company', 'individual_entrepreneur', 'individual'].includes(saved.type)) typeFilter.value = saved.type;
    onlyWithOrders.value = saved.orders === true;
    onlyFavorites.value = saved.favorites === true;
    includeArchived.value = saved.archived === true;
    if (Number.isInteger(saved.page) && saved.page > 0) page.value = saved.page;
  } catch { /* The current workspace starts with default filters. */ }
}

function sortCustomerItems(items: CustomerListItem[]) {
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
    if (onlyFavorites.value) void loadCustomers();
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
  const requestId = ++loadRequestId;
  loading.value = true;
  loadError.value = '';
  try {
    const data = await api.getManagerCustomers(
      page.value,
      meta.value.limit,
      searchQuery.value || undefined,
      typeFilter.value || undefined,
      onlyWithOrders.value,
      onlyFavorites.value,
      includeArchived.value,
    );
    if (isUnmounted || requestId !== loadRequestId) return;
    customers.value = sortCustomerItems(data.items);
    meta.value = data.meta;
    hasLoaded.value = true;
  } catch (e) {
    if (isUnmounted || requestId !== loadRequestId) return;
    console.error('Failed to load customers', e);
    loadError.value = 'Не удалось загрузить список клиентов. Проверьте соединение и повторите попытку.';
  } finally {
    if (!isUnmounted && requestId === loadRequestId) loading.value = false;
  }
}

function onSearch() {
  cancelScheduledSearch();
  page.value = 1;
  void loadCustomers();
}

function scheduleSearch() {
  cancelScheduledSearch();
  loadRequestId += 1;
  searchTimer = window.setTimeout(onSearch, 300);
}

function cancelScheduledSearch() {
  if (!searchTimer) return;
  window.clearTimeout(searchTimer);
  searchTimer = undefined;
}

function clearSearch() {
  if (!searchQuery.value) return;
  searchQuery.value = '';
  onSearch();
}

function onTypeChange() {
  cancelScheduledSearch();
  loadRequestId += 1;
  page.value = 1;
  void loadCustomers();
}

function selectType(next: string) {
  if (typeFilter.value === next) return;
  typeFilter.value = next;
  onTypeChange();
}

function toggleOrders() {
  onlyWithOrders.value = !onlyWithOrders.value;
  onTypeChange();
}

function toggleFavorites() {
  onlyFavorites.value = !onlyFavorites.value;
  onTypeChange();
}

function toggleArchived() {
  includeArchived.value = !includeArchived.value;
  onTypeChange();
}

function goToPage(p: number) {
  if (p < 1 || p > meta.value.pages) return;
  cancelScheduledSearch();
  loadRequestId += 1;
  page.value = p;
  void loadCustomers();
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

  isMounted = true;
  restoreFilters();
  void loadCustomers();
});

watch([searchQuery, typeFilter, onlyWithOrders, onlyFavorites, includeArchived, page], () => {
  if (!filterStorageKey.value) return;
  try {
    sessionStorage.setItem(filterStorageKey.value, JSON.stringify({
      search: searchQuery.value, type: typeFilter.value,
      orders: onlyWithOrders.value, favorites: onlyFavorites.value,
      archived: includeArchived.value, page: page.value,
    }));
  } catch { /* Browsers can disable session storage. */ }
});

watch(filterStorageKey, () => {
  if (isUnmounted || !isMounted) return;
  cancelScheduledSearch();
  loadRequestId += 1;
  customers.value = [];
  meta.value = { total: 0, pages: 1, limit: 20 };
  hasLoaded.value = false;
  loadError.value = '';
  loading.value = false;
  restoreFilters();
  if (filterStorageKey.value) void loadCustomers();
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
  isUnmounted = true;
  loadRequestId += 1;
  cancelScheduledSearch();
  window.removeEventListener(CUSTOMER_UPDATED_EVENT, handleCustomerUpdated);
  cleanupTimers.forEach((timer) => window.clearTimeout(timer));
  cleanupTimers.clear();
});
</script>

<template>
  <div class="customers-view">
    <header class="customers-header">
      <h1>Клиенты</h1>
      <button type="button" data-testid="create-customer" class="customers-create" @click="showCreateCustomer = true">Новый клиент</button>
    </header>
    <div class="customers-toolbar">
      <label class="search-box">
        <Search :size="16" aria-hidden="true" />
        <input v-model="searchQuery" aria-label="Поиск клиентов по имени, телефону, email или УНП" placeholder="Имя, телефон, email или УНП" @input="scheduleSearch" @keyup.enter="onSearch" />
        <button v-if="searchQuery" type="button" class="search-clear" aria-label="Очистить поиск" @click="clearSearch"><X :size="15" /></button>
      </label>
      <div class="customers-filter-line">
        <div class="customer-type-segments" role="group" aria-label="Тип клиента">
          <button v-for="option in [
            { value: '', label: 'Все' },
            { value: 'company', label: 'Юрлица' },
            { value: 'individual_entrepreneur', label: 'ИП' },
            { value: 'individual', label: 'Физлица' },
          ]" :key="option.label" type="button" :aria-pressed="typeFilter === option.value" :class="{ active: typeFilter === option.value }" @click="selectType(option.value)">{{ option.label }}</button>
        </div>
        <button type="button" class="customer-filter-chip" :class="{ active: onlyFavorites }" :aria-pressed="onlyFavorites" @click="toggleFavorites"><Star :size="14" aria-hidden="true" /> Избранные</button>
        <button type="button" class="customer-filter-chip" :class="{ active: onlyWithOrders }" :aria-pressed="onlyWithOrders" @click="toggleOrders">С заказами</button>
        <button type="button" class="customer-filter-chip" :class="{ active: includeArchived }" :aria-pressed="includeArchived" @click="toggleArchived">С архивом</button>
        <span v-if="hasLoaded && !loading && !loadError" class="customers-count" aria-live="polite">{{ meta.total }}</span>
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

    <div v-else-if="loadError" class="empty-state border border-dashed border-red-200 bg-white dark:border-red-900/50 dark:bg-slate-800">
      <h2 class="text-xl font-bold mb-2 text-gray-900 dark:text-white">Список не загрузился</h2>
      <p>{{ loadError }}</p>
      <button type="button" class="mt-4 inline-flex items-center gap-2 rounded-lg bg-brand-600 px-4 py-2 text-sm font-semibold text-white hover:bg-brand-500" @click="loadCustomers">
        Повторить
      </button>
    </div>

    <!-- Empty -->
    <div v-else-if="hasLoaded && customers.length === 0" class="empty-state border border-dashed border-gray-300 dark:border-slate-700 bg-white dark:bg-slate-800">
      <div class="flex justify-center mb-4">
        <Users :size="64" class="text-gray-300 dark:text-slate-600" />
      </div>
      <h2 class="text-xl font-bold mb-2 text-gray-900 dark:text-white">Клиенты не найдены</h2>
      <p v-if="searchQuery || typeFilter || onlyFavorites || onlyWithOrders || includeArchived" class="text-gray-500 dark:text-slate-400">Попробуйте изменить поиск или фильтры.</p>
      <div v-else class="text-gray-500 dark:text-slate-400">
        <p>Клиентская база пуста.</p>
        <button type="button" class="mt-4 inline-flex items-center gap-2 rounded-lg bg-brand-600 px-4 py-2 text-sm font-semibold text-white hover:bg-brand-500" @click="showCreateCustomer = true">
          Создать первого клиента
        </button>
      </div>
    </div>

    <div v-else class="customers-list-wrap">
      <table class="customers-list">
        <thead>
          <tr>
            <th scope="col">Клиент</th>
            <th scope="col">Контакты</th>
            <th scope="col">УНП</th>
            <th scope="col">Заказы</th>
            <th scope="col" class="customers-actions-heading">Действия</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="customer in customers" :key="customer.id">
            <td data-label="Клиент" class="customer-primary-cell">
              <a
                class="customer-name-link"
                :href="`/manager/customers/profile?customerId=${customer.id}`"
                :title="customer.full_legal_name || customer.name || `Клиент #${customer.id}`"
              >
                {{ customer.name || customer.full_legal_name || `Клиент #${customer.id}` }}
              </a>
              <div class="customer-meta">
                <span class="type-badge" :class="customer.type">
                  {{ TYPE_MAP[customer.type]?.icon }} {{ TYPE_MAP[customer.type]?.label || customer.type }}
                </span>
                <span v-if="customer.is_archived" class="customer-archived-badge">Архив</span>
                <span v-if="recentlyUpdated[customer.id]" class="updated-badge">обновлено</span>
              </div>
            </td>
            <td data-label="Контакты" class="customer-contacts-cell">
              <div class="customer-contacts">
                <div v-if="customer.primary_contact?.name" class="customer-contact-person"><strong>{{ customer.primary_contact.name }}</strong><span v-if="customer.primary_contact.role"> · {{ customer.primary_contact.role }}</span></div>
                <a v-if="customer.primary_contact?.phone || customer.phone" :href="`tel:${customer.primary_contact?.phone || customer.phone}`" class="customer-contact-link">
                  <Phone :size="14" aria-hidden="true" />{{ customer.primary_contact?.phone || customer.phone }}
                </a>
                <a v-if="customer.primary_contact?.email || customer.email" :href="`mailto:${customer.primary_contact?.email || customer.email}`" class="customer-contact-link customer-email-link">
                  <Mail :size="14" aria-hidden="true" />{{ customer.primary_contact?.email || customer.email }}
                </a>
                <span v-if="!customer.primary_contact?.phone && !customer.phone && !customer.primary_contact?.email && !customer.email" class="customer-empty">—</span>
                <a class="customer-contact-edit" :href="`/manager/customers/profile?customerId=${customer.id}&editContact=1`">Изменить контакт</a>
              </div>
            </td>
            <td data-label="УНП">
              <span v-if="customer.inn" class="customer-inn">{{ customer.inn }}</span>
              <span v-else class="customer-empty">—</span>
            </td>
            <td data-label="Заказы" class="customer-order-count"><strong>{{ customer.order_count }}</strong><span class="customer-order-label"> заказов</span></td>
            <td data-label="Действия" class="customer-actions-cell">
              <div class="customer-actions">
                <button
                  type="button"
                  class="favorite-btn"
                  :class="{ active: customer.is_favorite }"
                  :disabled="favoriteSaving[customer.id]"
                  :aria-pressed="Boolean(customer.is_favorite)"
                  :aria-label="customer.is_favorite ? `Убрать ${customer.name} из избранного` : `Добавить ${customer.name} в избранное`"
                  @click="toggleFavorite(customer)"
                >
                  <Star :size="16" :fill="customer.is_favorite ? 'currentColor' : 'none'" />
                </button>
                <button type="button" class="open-btn" title="Создать заказ" aria-label="Создать заказ" @click="openCreateOrder(customer)">
                  <Plus :size="15" aria-hidden="true" />
                  Заказ
                </button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Pagination -->
    <div v-if="!loadError && meta.pages > 1" class="pagination">
      <button aria-label="Предыдущая страница" @click="goToPage(page - 1)" :disabled="loading || page <= 1" class="page-btn">
        <ChevronLeft :size="16" />
      </button>
      <span class="page-info">{{ page }} / {{ meta.pages }} ({{ meta.total }} записей)</span>
      <button aria-label="Следующая страница" @click="goToPage(page + 1)" :disabled="loading || page >= meta.pages" class="page-btn">
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

    <CustomerIntakeDialog
      v-if="showCreateCustomer"
      data-testid="create-customer-modal"
      @close="showCreateCustomer = false"
      @created="onCustomerCreated"
      @open-existing="openCustomerProfile"
    />

  </div>
</template>

<style scoped src="../styles/customers.css"></style>
