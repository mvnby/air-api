<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { Search, ShoppingCart, ChevronLeft, ChevronRight } from 'lucide-vue-next';
import { api } from '../api';

// --- State ---
const orders = ref<any[]>([]);
const loading = ref(false);
const searchQuery = ref('');
const statusFilter = ref('');
const page = ref(1);
const meta = ref({ total: 0, pages: 1, limit: 20 });

const STATUS_MAP: Record<string, { label: string; color: string }> = {
  new_lead: { label: 'Новый лид', color: '#007f80' },
  assessment: { label: 'Замер', color: '#2196F3' },
  proposal: { label: 'КП', color: '#9C27B0' },
  negotiation: { label: 'Переговоры', color: '#FF9800' },
  deferred: { label: 'Отложен', color: '#607D8B' },
  won_deposit: { label: 'Задаток', color: '#4CAF50' },
  installation: { label: 'Монтаж', color: '#00BCD4' },
  completed: { label: 'Завершён', color: '#388E3C' },
  canceled: { label: 'Отменён', color: '#F44336' },
};

const SOURCE_MAP: Record<string, string> = {
  site: '🌐 Сайт',
  bot: '🤖 Бот',
  phone: '📞 Звонок',
  email: '📧 Email',
  manager: '👤 Менеджер',
  referral: '🗣 Рекомендация',
  other: '❓ Другое',
};

// --- Fetch ---
async function loadOrders() {
  loading.value = true;
  try {
    const data = await api.getManagerOrders(
      page.value,
      meta.value.limit,
      statusFilter.value || undefined,
      searchQuery.value || undefined,
    );
    orders.value = data.items;
    meta.value = data.meta;
  } catch (e) {
    console.error('Failed to load orders', e);
  } finally {
    loading.value = false;
  }
}

function onSearch() {
  page.value = 1;
  loadOrders();
}

function onStatusChange() {
  page.value = 1;
  loadOrders();
}

function goToPage(p: number) {
  if (p < 1 || p > meta.value.pages) return;
  page.value = p;
  loadOrders();
}

function formatDate(iso: string | null) {
  if (!iso) return '—';
  const d = new Date(iso);
  return d.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric' });
}

function formatMoney(val: number) {
  return val.toLocaleString('ru-RU') + ' руб.';
}

onMounted(loadOrders);
</script>

<template>
  <div class="orders-view">
    <!-- Header -->
    <div class="view-header">
      <h1>Заказы</h1>
      <div class="header-controls">
        <div class="search-box">
          <Search :size="16" />
          <input
            v-model="searchQuery"
            placeholder="Поиск заказов..."
            @keyup.enter="onSearch"
          />
        </div>
        <select v-model="statusFilter" @change="onStatusChange" class="status-select">
          <option value="">Все статусы</option>
          <option v-for="(v, k) in STATUS_MAP" :key="k" :value="k">{{ v.label }}</option>
        </select>
      </div>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="loading-state">
      <div class="spinner"></div>
      <p>Загрузка...</p>
    </div>

    <!-- Empty -->
    <div v-else-if="orders.length === 0" class="empty-state">
      <ShoppingCart :size="64" color="#ccc" />
      <h2>Заказы не найдены</h2>
      <p v-if="searchQuery || statusFilter">Попробуйте изменить фильтры или поисковый запрос</p>
      <p v-else>Здесь появятся заказы, когда клиенты начнут оформлять покупки</p>
    </div>

    <!-- Table -->
    <div v-else class="orders-table-wrapper">
      <table class="orders-table">
        <thead>
          <tr>
            <th class="col-id">#</th>
            <th class="col-status">Статус</th>
            <th class="col-title">Описание</th>
            <th class="col-customer">Клиент</th>
            <th class="col-products">Товары</th>
            <th class="col-amount">Сумма</th>
            <th class="col-margin">Маржа</th>
            <th class="col-date">Дата</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="order in orders" :key="order.id">
            <td class="col-id">{{ order.id }}</td>
            <td class="col-status">
              <span
                class="status-badge"
                :style="{ backgroundColor: (STATUS_MAP[order.status]?.color || '#999') + '18', color: STATUS_MAP[order.status]?.color || '#999' }"
              >
                {{ STATUS_MAP[order.status]?.label || order.status }}
              </span>
            </td>
            <td class="col-title">
              <div class="order-title">{{ order.title || '—' }}</div>
              <div v-if="order.comment" class="order-comment">{{ order.comment }}</div>
              <div class="order-source">{{ SOURCE_MAP[order.lead_source] || order.lead_source }}</div>
            </td>
            <td class="col-customer">
              <template v-if="order.customer">
                <div class="customer-name">{{ order.customer.name }}</div>
                <div class="customer-phone">{{ order.customer.phone }}</div>
              </template>
              <span v-else class="no-data">—</span>
            </td>
            <td class="col-products">
              <div v-for="p in order.products" :key="p.product_id" class="product-line">
                {{ p.title }} × {{ p.quantity }}
              </div>
              <span v-if="!order.products?.length" class="no-data">—</span>
            </td>
            <td class="col-amount">
              <span :class="{ paid: order.is_paid }">{{ formatMoney(order.total_amount) }}</span>
            </td>
            <td class="col-margin" :class="{ positive: order.margin > 0, negative: order.margin < 0 }">
              {{ formatMoney(order.margin) }}
            </td>
            <td class="col-date">
              <div>{{ formatDate(order.created_at) }}</div>
              <div v-if="order.installation_date" class="install-date">
                🔧 {{ formatDate(order.installation_date) }}
              </div>
            </td>
          </tr>
        </tbody>
      </table>
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
  </div>
</template>

<style scoped>
.orders-view {
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

.status-select {
  padding: 8px 14px;
  border-radius: 10px;
  border: 1px solid #e0e4ea;
  background: #f4f6f9;
  font-size: 14px;
  color: #333;
  cursor: pointer;
  outline: none;
}
.status-select:focus {
  border-color: #007f80;
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

/* Table */
.orders-table-wrapper {
  overflow-x: auto;
  border-radius: 12px;
  border: 1px solid #e0e4ea;
  background: #fff;
}

.orders-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 14px;
}

.orders-table thead {
  background: #f4f6f9;
}

.orders-table th {
  text-align: left;
  padding: 12px 14px;
  font-weight: 600;
  color: #555;
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  white-space: nowrap;
}

.orders-table td {
  padding: 12px 14px;
  border-top: 1px solid #f0f2f5;
  vertical-align: top;
}

.orders-table tbody tr:hover {
  background: #f8fafa;
}

.col-id {
  width: 50px;
  color: #888;
  font-weight: 500;
}

/* Status Badge */
.status-badge {
  display: inline-block;
  padding: 4px 10px;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 600;
  white-space: nowrap;
}

/* Title */
.order-title {
  font-weight: 500;
  color: #1a1a2e;
}
.order-comment {
  font-size: 12px;
  color: #888;
  margin-top: 2px;
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.order-source {
  font-size: 11px;
  color: #aaa;
  margin-top: 4px;
}

/* Customer */
.customer-name {
  font-weight: 500;
  color: #1a1a2e;
}
.customer-phone {
  font-size: 12px;
  color: #888;
  margin-top: 2px;
}

/* Products */
.product-line {
  font-size: 13px;
  color: #555;
  line-height: 1.5;
}

.no-data {
  color: #ccc;
}

/* Amount */
.paid {
  color: #388E3C;
  font-weight: 600;
}

/* Margin */
.positive {
  color: #388E3C;
}
.negative {
  color: #F44336;
}

/* Install date */
.install-date {
  font-size: 12px;
  color: #888;
  margin-top: 2px;
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
