<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { api, type DashboardStatsResponse } from '../api';

const loading = ref(true);
const stats = ref<DashboardStatsResponse | null>(null);

const fetchStats = async () => {
  try {
    loading.value = true;
    stats.value = await api.getDashboardStats();
  } catch (error) {
    console.error('Error fetching dashboard stats:', error);
  } finally {
    loading.value = false;
  }
};

onMounted(() => {
  fetchStats();
});

const quickActions = [
  { label: 'Канбан Лидов', icon: 'view_kanban', path: '/manager/leads' },
  { label: 'Заказы', icon: 'shopping_cart', path: '/manager/orders/kanban' },
  { label: 'Календарь', icon: 'calendar_today', path: '/manager/calendar' },
  { label: 'Каталог', icon: 'inventory_2', path: '/manager/products' },
  { label: 'Клиенты', icon: 'group', path: '/manager/customers' },
];

const navigate = (path: string) => {
  if (window.location.pathname !== path) {
    window.history.pushState({}, '', path);
    window.dispatchEvent(new Event('popstate'));
  }
};

const formatCurrency = (val: number) => {
  return new Intl.NumberFormat('ru-RU', { style: 'currency', currency: 'BYN' }).format(val);
};

const formatDate = (dateStr: string) => {
  const d = new Date(dateStr);
  return d.toLocaleDateString('ru-RU', { day: '2-digit', month: 'short', year: 'numeric' });
};
</script>

<template>
  <div class="p-6 bg-slate-50 dark:bg-[#0f172a] min-h-full text-slate-900 dark:text-white transition-colors duration-200">
    <h1 class="text-2xl font-bold text-gray-900 dark:text-white tracking-tight flex items-center gap-3 mb-8">
      <span class="material-icons-round text-teal-600 dark:text-teal-400">space_dashboard</span>
      Главная
    </h1>

    <!-- Section 1: Quick Actions -->
    <section class="mb-10">
      <h2 class="text-xl font-semibold mb-4 text-slate-800 dark:text-gray-300">Быстрая навигация</h2>
      <div class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4">
        <div 
          v-for="action in quickActions" 
          :key="action.path"
          @click="navigate(action.path)"
          class="bg-white dark:bg-[#1e293b] border border-slate-200 dark:border-slate-700/50 p-6 rounded-xl flex flex-col items-center justify-center cursor-pointer transition-all duration-200 hover:-translate-y-1 hover:bg-slate-50 dark:hover:bg-slate-700 hover:shadow-lg hover:shadow-teal-900/10 dark:hover:shadow-teal-900/20"
        >
          <span class="material-icons-round text-4xl mb-3 text-teal-600 dark:text-[#007f80]">{{ action.icon }}</span>
          <span class="font-medium text-slate-700 dark:text-gray-200">{{ action.label }}</span>
        </div>
      </div>
    </section>

    <!-- Section 2: KPI & Analytics -->
    <section class="mb-10">
      <h2 class="text-xl font-semibold mb-4 text-slate-800 dark:text-gray-300">Аналитика за месяц</h2>
      <div v-if="loading" class="flex items-center gap-3 text-slate-500 dark:text-gray-400">
        <span class="material-icons-round animate-spin">refresh</span> Загрузка...
      </div>
      <div v-else-if="stats" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        <div class="bg-white dark:bg-[#1e293b] p-6 rounded-xl border border-slate-200 dark:border-slate-700/50 shadow-sm">
          <div class="text-slate-500 dark:text-gray-400 text-sm font-medium mb-1">Выручка (завершенные заказы)</div>
          <div class="text-3xl font-bold text-teal-600 dark:text-[#007f80]">
            {{ formatCurrency(stats.total_amount) }}
          </div>
        </div>
        <div class="bg-white dark:bg-[#1e293b] p-6 rounded-xl border border-slate-200 dark:border-slate-700/50 shadow-sm">
          <div class="text-slate-500 dark:text-gray-400 text-sm font-medium mb-1">Новых лидов</div>
          <div class="text-3xl font-bold text-teal-600 dark:text-[#007f80]">
            {{ stats.new_leads_count }}
          </div>
        </div>
      </div>
    </section>

    <!-- Section 3: Today's Tasks -->
    <section>
      <h2 class="text-xl font-semibold mb-4 text-slate-800 dark:text-gray-300">Ближайшие касания</h2>
      <div v-if="loading" class="text-slate-500 dark:text-gray-400">Загрузка задач...</div>
      <div v-else-if="stats && stats.upcoming_touchpoints.length > 0" class="flex flex-col gap-3">
        <div 
          v-for="touch in stats.upcoming_touchpoints" 
          :key="touch.order_id"
          class="bg-white dark:bg-[#1e293b] p-4 rounded-xl flex items-center justify-between border border-slate-200 dark:border-slate-700/50 hover:bg-slate-50 dark:hover:bg-slate-800 transition-colors cursor-pointer shadow-sm"
          @click="navigate(`/manager/orders/kanban?orderId=${touch.order_id}`)"
        >
          <div>
            <div class="font-medium text-slate-800 dark:text-gray-200 mb-1">
              Заказ #{{ touch.order_id }} — {{ touch.customer_name }}
              <span v-if="touch.title" class="text-slate-500 dark:text-gray-400 font-normal text-sm ml-2">({{ touch.title }})</span>
            </div>
            <div class="text-sm text-slate-500 dark:text-gray-400 flex items-center gap-4">
              <span v-if="touch.phone" class="flex items-center gap-1">
                <span class="material-icons-round text-[16px]">call</span> {{ touch.phone }}
              </span>
              <span class="flex items-center gap-1 text-rose-500 dark:text-rose-400">
                <span class="material-icons-round text-[16px]">event</span> {{ formatDate(touch.next_followup_date) }}
              </span>
            </div>
          </div>
          <span class="material-icons-round text-slate-400 dark:text-gray-500">chevron_right</span>
        </div>
      </div>
      <div v-else class="text-slate-500 dark:text-gray-400 italic bg-slate-100 dark:bg-[#1e293b]/50 p-6 rounded-xl border border-slate-200 dark:border-slate-800 border-dashed text-center">
        Нет срочных касаний. Отличная работа!
      </div>
    </section>
  </div>
</template>
