<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { Search, PauseCircle } from 'lucide-vue-next';
import { api } from '../api';

// --- State ---
const orders = ref<any[]>([]);
const loading = ref(false);
const searchQuery = ref('');
const hideOnHold = ref(false);
const page = ref(1);
const meta = ref({ total: 0, pages: 1, limit: 100 });

// --- Column config ---
const COLUMNS = [
  { key: 'negotiation', label: '🤝 Переговоры', color: '#f59e0b' },
  { key: 'execution',   label: '🔧 Монтаж',     color: '#3b82f6' },
  { key: 'closed',      label: '✅ Закрыто',     color: '#22c55e' },
];

const CLOSING_RESULT_LABELS: Record<string, { label: string; color: string }> = {
  won:  { label: '✅ Успех', color: '#22c55e' },
  lost: { label: '❌ Отказ', color: '#ef4444' },
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

// --- Computed: filtered orders per column ---
const visibleOrders = computed(() =>
  orders.value.filter(o => !hideOnHold.value || !o.is_on_hold)
);

function ordersForColumn(colKey: string) {
  return visibleOrders.value.filter(o => o.status === colKey);
}

// --- Fetch ---
async function loadOrders() {
  loading.value = true;
  try {
    const data = await api.getManagerOrders({
      segment: 'b2c',
      page: page.value,
      limit: meta.value.limit,
      search: searchQuery.value || undefined,
    });
    orders.value = data.items;
    meta.value = data.meta;
  } catch (e) {
    console.error('Failed to load orders', e);
  } finally {
    loading.value = false;
  }
}

function formatDate(iso: string | null) {
  if (!iso) return '—';
  return new Date(iso).toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric' });
}

function formatMoney(val: number) {
  return val.toLocaleString('ru-RU') + ' ₽';
}

onMounted(loadOrders);
</script>

<template>
  <div class="orders-view">
    <!-- Header -->
    <div class="view-header">
      <h1 class="text-2xl font-bold text-gray-900 dark:text-white tracking-tight flex items-center gap-3">
        <span class="material-icons-round text-teal-600 dark:text-teal-400">view_kanban</span>
        Воронка сделок
      </h1>
      <div class="header-controls">
        <div class="search-box">
          <Search :size="16" />
          <input
            v-model="searchQuery"
            placeholder="Поиск..."
            @keyup.enter="loadOrders"
          />
        </div>
        <!-- On-Hold Toggle -->
        <button
          class="hold-toggle"
          :class="{ active: hideOnHold }"
          @click="hideOnHold = !hideOnHold"
          :title="hideOnHold ? 'Показать отложенные' : 'Скрыть отложенные'"
        >
          <PauseCircle :size="16" />
          {{ hideOnHold ? 'Показать паузу' : 'Скрыть паузу' }}
        </button>
      </div>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="loading-state">
      <div class="spinner"></div>
      <p>Загрузка...</p>
    </div>

    <!-- Kanban Board -->
    <div v-else class="kanban-board">
      <div
        v-for="col in COLUMNS"
        :key="col.key"
        class="kanban-column"
      >
        <!-- Column Header -->
        <div class="column-header" :style="{ borderColor: col.color }">
          <span class="column-title">{{ col.label }}</span>
          <span class="column-count" :style="{ background: col.color + '22', color: col.color }">
            {{ ordersForColumn(col.key).length }}
          </span>
        </div>

        <!-- Cards -->
        <div class="column-cards">
          <div
            v-for="order in ordersForColumn(col.key)"
            :key="order.id"
            class="kanban-card"
            :class="{ 'on-hold': order.is_on_hold }"
          >
            <!-- On-hold badge -->
            <div v-if="order.is_on_hold" class="hold-badge">
              ⏸ {{ order.on_hold_reason || 'Пауза' }}
            </div>

            <!-- Customer -->
            <div class="card-customer">
              <span class="customer-name">{{ order.customer?.name || 'Без имени' }}</span>
              <span class="customer-phone">{{ order.customer?.phone || '' }}</span>
            </div>

            <!-- Amount -->
            <div class="card-amount" :class="{ paid: order.is_paid }">
              {{ formatMoney(order.total_amount) }}
            </div>

            <!-- Closing result (for closed column) -->
            <div v-if="col.key === 'closed' && order.closing_result" class="closing-result"
              :style="{ color: CLOSING_RESULT_LABELS[order.closing_result]?.color }">
              {{ CLOSING_RESULT_LABELS[order.closing_result]?.label }}
            </div>

            <!-- Footer -->
            <div class="card-footer">
              <span class="card-source">{{ SOURCE_MAP[order.lead_source] || order.lead_source }}</span>
              <span class="card-date">{{ formatDate(order.created_at) }}</span>
            </div>

            <!-- Measurement date -->
            <div v-if="order.measurement_date" class="card-meta">
              📐 Замер: {{ formatDate(order.measurement_date) }}
            </div>
            <!-- Installation date -->
            <div v-if="order.installation_date" class="card-meta">
              🔧 Монтаж: {{ formatDate(order.installation_date) }}
            </div>
          </div>

          <!-- Empty column placeholder -->
          <div v-if="ordersForColumn(col.key).length === 0" class="column-empty">
            Нет сделок
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.orders-view {
  padding: 24px 32px;
  height: 100%;
}

.view-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 24px;
  flex-wrap: wrap;
  gap: 12px;
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
.search-box:focus-within { border-color: #007f80; }
.search-box input {
  border: none;
  background: transparent;
  outline: none;
  font-size: 14px;
  width: 180px;
  color: #333;
}
:global(.dark) .search-box input { color: #e5e7eb; }

/* On-hold toggle */
.hold-toggle {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 14px;
  border-radius: 10px;
  border: 1px solid #e0e4ea;
  background: #f4f6f9;
  font-size: 13px;
  cursor: pointer;
  color: #666;
  transition: all 0.2s;
}
.hold-toggle:hover { border-color: #f59e0b; color: #f59e0b; }
.hold-toggle.active { background: #fff7ed; border-color: #f59e0b; color: #d97706; }

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

/* Kanban Board */
.kanban-board {
  display: flex;
  gap: 16px;
  align-items: flex-start;
  overflow-x: auto;
  padding-bottom: 24px;
}

.kanban-column {
  flex: 1;
  min-width: 300px;
  max-width: 400px;
  background: #f8f9fc;
  border-radius: 14px;
  padding: 0;
  overflow: hidden;
  border: 1px solid #e8eaf0;
}
:global(.dark) .kanban-column { background: #1f2937; border-color: #374151; }

.column-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 16px;
  border-bottom: 3px solid;
  background: #fff;
}
:global(.dark) .column-header { background: #111827; }

.column-title {
  font-size: 15px;
  font-weight: 700;
  color: #1a1a2e;
}
:global(.dark) .column-title { color: #f3f4f6; }

.column-count {
  font-size: 12px;
  font-weight: 700;
  padding: 3px 9px;
  border-radius: 20px;
}

.column-cards {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 12px;
  min-height: 100px;
}

/* Cards */
.kanban-card {
  background: #fff;
  border-radius: 10px;
  padding: 14px;
  border: 1px solid #e8eaf0;
  box-shadow: 0 1px 3px rgba(0,0,0,0.06);
  transition: box-shadow 0.2s, opacity 0.2s;
  cursor: pointer;
}
.kanban-card:hover {
  box-shadow: 0 4px 12px rgba(0,0,0,0.1);
}
.kanban-card.on-hold {
  opacity: 0.55;
  border-style: dashed;
}
:global(.dark) .kanban-card { background: #273549; border-color: #374151; }

.hold-badge {
  font-size: 11px;
  color: #92400e;
  background: #fef3c7;
  border-radius: 4px;
  padding: 2px 7px;
  margin-bottom: 8px;
  display: inline-block;
}

.card-customer {
  display: flex;
  flex-direction: column;
  gap: 2px;
  margin-bottom: 8px;
}
.customer-name {
  font-weight: 600;
  font-size: 14px;
  color: #1a1a2e;
}
:global(.dark) .customer-name { color: #f3f4f6; }
.customer-phone {
  font-size: 12px;
  color: #888;
}

.card-amount {
  font-size: 16px;
  font-weight: 700;
  color: #333;
  margin-bottom: 8px;
}
.card-amount.paid { color: #22c55e; }
:global(.dark) .card-amount { color: #e5e7eb; }

.closing-result {
  font-size: 13px;
  font-weight: 600;
  margin-bottom: 6px;
}

.card-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 11px;
  color: #aaa;
  margin-top: 6px;
}

.card-meta {
  font-size: 11px;
  color: #888;
  margin-top: 4px;
}

.column-empty {
  text-align: center;
  padding: 32px 0;
  color: #ccc;
  font-size: 13px;
}
</style>
