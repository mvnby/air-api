<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { Search, Users, ChevronLeft, ChevronRight, Phone, Mail, Building, X } from 'lucide-vue-next';
import { api } from '../api';
import type { ManagerCatalogCustomerItemResponse } from '../client';

// --- State ---
const customers = ref<ManagerCatalogCustomerItemResponse[]>([]);
const loading = ref(false);
const searchQuery = ref('');
const typeFilter = ref('');
const onlyWithOrders = ref(false);
const page = ref(1);
const meta = ref({ total: 0, pages: 1, limit: 20 });
const selectedCustomer = ref<ManagerCatalogCustomerItemResponse | null>(null);

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
    customers.value = data.items;
    meta.value = data.meta;
    await ensureSelectedCustomerFromUrl();
  } catch (e) {
    console.error('Failed to load customers', e);
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

function updateCustomerQueryParam(customerId?: number | null) {
  const url = new URL(window.location.href);
  if (customerId) {
    url.searchParams.set('customerId', String(customerId));
  } else {
    url.searchParams.delete('customerId');
  }
  window.history.replaceState({}, '', `${url.pathname}${url.search}`);
}

function openCustomerCard(customer: ManagerCatalogCustomerItemResponse) {
  selectedCustomer.value = customer;
  updateCustomerQueryParam(customer.id);
}

function closeCustomerCard() {
  selectedCustomer.value = null;
  updateCustomerQueryParam(null);
}

async function ensureSelectedCustomerFromUrl() {
  const customerIdRaw = new URLSearchParams(window.location.search).get('customerId');
  if (!customerIdRaw) return;

  const customerId = Number(customerIdRaw);
  if (!Number.isFinite(customerId) || customerId <= 0) return;

  const inCurrentPage = customers.value.find((item) => item.id === customerId);
  if (inCurrentPage) {
    selectedCustomer.value = inCurrentPage;
    return;
  }

  try {
    const data = await api.getManagerCustomers(1, 20, customerIdRaw, undefined, false);
    const found = (data.items || []).find((item: ManagerCatalogCustomerItemResponse) => item.id === customerId);
    if (found) {
      selectedCustomer.value = found;
    }
  } catch (e) {
    console.error('Failed to open customer by URL', e);
  }
}

onMounted(loadCustomers);
</script>

<template>
  <div class="customers-view">
    <!-- Header -->
    <div class="view-header">
      <h1>Клиенты</h1>
      <div class="header-controls">
        <div class="search-box">
          <Search :size="16" />
          <input
            v-model="searchQuery"
            placeholder="Поиск клиентов..."
            @keyup.enter="onSearch"
          />
        </div>
        <div class="flex bg-gray-100 p-1 rounded-lg">
          <button 
              @click="typeFilter = ''; onTypeChange()"
              class="px-3 py-1.5 text-sm rounded-md transition-all"
              :class="!typeFilter ? 'bg-white text-teal-700 shadow-sm font-medium' : 'text-gray-500 hover:text-gray-700'"
          >Все</button>
          <button 
              @click="typeFilter = 'individual'; onTypeChange()"
              class="px-3 py-1.5 text-sm rounded-md transition-all"
              :class="typeFilter === 'individual' ? 'bg-white text-teal-700 shadow-sm font-medium' : 'text-gray-500 hover:text-gray-700'"
          >Физ. лица</button>
          <button 
              @click="typeFilter = 'company'; onTypeChange()"
              class="px-3 py-1.5 text-sm rounded-md transition-all"
              :class="typeFilter === 'company' ? 'bg-white text-teal-700 shadow-sm font-medium' : 'text-gray-500 hover:text-gray-700'"
          >Юр. лица</button>
        </div>
        <label class="inline-flex items-center gap-2 rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm text-gray-700">
          <input v-model="onlyWithOrders" type="checkbox" @change="onTypeChange" />
          Только с заказами
        </label>
      </div>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="loading-state">
      <div class="spinner"></div>
      <p>Загрузка...</p>
    </div>

    <!-- Empty -->
    <div v-else-if="customers.length === 0" class="empty-state">
      <Users :size="64" color="#ccc" />
      <h2>Клиенты не найдены</h2>
      <p v-if="searchQuery || typeFilter">Попробуйте изменить фильтры или поисковый запрос</p>
      <p v-if="onlyWithOrders">Нет клиентов с заказами по текущим фильтрам.</p>
      <p v-else>Клиенты появятся здесь при создании заказов</p>
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
            <button class="open-btn" @click="openCustomerCard(customer)">Карточка</button>
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

    <div v-if="selectedCustomer" class="drawer-overlay" @click="closeCustomerCard">
      <aside class="customer-drawer" @click.stop>
        <header class="drawer-header">
          <h3>Карточка клиента #{{ selectedCustomer.id }}</h3>
          <button class="icon-btn" @click="closeCustomerCard">
            <X :size="18" />
          </button>
        </header>

        <div class="drawer-body">
          <div class="drawer-row">
            <span class="label">Тип</span>
            <span class="value">{{ TYPE_MAP[selectedCustomer.type]?.label || selectedCustomer.type }}</span>
          </div>
          <div class="drawer-row">
            <span class="label">Имя</span>
            <span class="value">{{ selectedCustomer.name || '—' }}</span>
          </div>
          <div class="drawer-row">
            <span class="label">Телефон</span>
            <span class="value">{{ selectedCustomer.phone || '—' }}</span>
          </div>
          <div class="drawer-row">
            <span class="label">Email</span>
            <span class="value">{{ selectedCustomer.email || '—' }}</span>
          </div>
          <div class="drawer-row">
            <span class="label">УНП</span>
            <span class="value">{{ selectedCustomer.inn || '—' }}</span>
          </div>
          <div class="drawer-row">
            <span class="label">Полное наименование</span>
            <span class="value">{{ selectedCustomer.full_legal_name || '—' }}</span>
          </div>
          <div class="drawer-row">
            <span class="label">Юридический адрес</span>
            <span class="value">{{ selectedCustomer.legal_address || '—' }}</span>
          </div>
          <div class="drawer-row">
            <span class="label">Банк</span>
            <span class="value">{{ selectedCustomer.bank_name || '—' }}</span>
          </div>
          <div class="drawer-row">
            <span class="label">BIC</span>
            <span class="value">{{ selectedCustomer.bic || '—' }}</span>
          </div>
          <div class="drawer-row">
            <span class="label">Расчетный счет (IBAN)</span>
            <span class="value">{{ selectedCustomer.iban || '—' }}</span>
          </div>
          <div class="drawer-row">
            <span class="label">Заказов</span>
            <span class="value">{{ selectedCustomer.order_count }}</span>
          </div>
          <div class="drawer-row">
            <span class="label">Создан</span>
            <span class="value">{{ formatDate(selectedCustomer.created_at) }}</span>
          </div>
        </div>
      </aside>
    </div>
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

.view-header h1 {
  font-size: 28px;
  font-weight: 700;
  color: #1a1a2e;
  margin: 0;
}

.header-controls {
  display: flex;
  gap: 12px;
  align-items: center;
}

.search-box {
  display: flex;
  align-items: center;
  gap: 8px;
  background: #f4f6f9;
  border-radius: 10px;
  padding: 8px 14px;
  border: 1px solid #e0e4ea;
  transition: border-color 0.2s;
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
  color: #333;
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
  border: 3px solid #e0e4ea;
  border-top-color: #007f80;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }

/* Empty */
.empty-state {
  text-align: center;
  padding: 80px 20px;
  background: #f8f9fc;
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
  background: #fff;
  border: 1px solid #e8eaef;
  border-radius: 14px;
  padding: 20px;
  transition: all 0.2s;
}
.customer-card:hover {
  border-color: #007f80;
  box-shadow: 0 4px 20px rgba(0, 127, 128, 0.08);
  transform: translateY(-2px);
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
  color: #1a1a2e;
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
  border-bottom: 1px solid #f0f2f5;
  margin-bottom: 14px;
}

.detail-row {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: #555;
}
.detail-row svg {
  color: #999;
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
  color: #888;
}

.date-added {
  font-size: 12px;
  color: #aaa;
}

.open-btn {
  border: 1px solid #dbe3ea;
  background: #fff;
  border-radius: 8px;
  font-size: 12px;
  padding: 6px 10px;
  color: #007f80;
  font-weight: 600;
  cursor: pointer;
}

.open-btn:hover {
  background: #e6f7f7;
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
  background: #ffffff;
  border-left: 1px solid #e5e9ef;
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
  border: 1px solid #e0e4ea;
  background: #fff;
  cursor: pointer;
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
  border: 1px solid #eef1f6;
  border-radius: 10px;
  padding: 10px 12px;
}

.drawer-row .label {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: #8b94a3;
}

.drawer-row .value {
  color: #232a36;
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
  border: 1px solid #e0e4ea;
  border-radius: 8px;
  background: #fff;
  cursor: pointer;
  color: #333;
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
  color: #666;
}
</style>
