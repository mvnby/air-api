<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { api, type DashboardStatsResponse } from '../api';
import type { DashboardOverviewResponse } from '../client';
import DashboardFunnel from '../components/dashboard/DashboardFunnel.vue';
import DashboardKpiGrid from '../components/dashboard/DashboardKpiGrid.vue';
import DashboardLoadingState from '../components/dashboard/DashboardLoadingState.vue';
import DashboardMarketing from '../components/dashboard/DashboardMarketing.vue';
import DashboardModeSwitch from '../components/dashboard/DashboardModeSwitch.vue';
import DashboardQuickActions from '../components/dashboard/DashboardQuickActions.vue';
import DashboardSalesChart from '../components/dashboard/DashboardSalesChart.vue';
import DashboardSearchDemand from '../components/dashboard/DashboardSearchDemand.vue';
import {
  formatDashboardCurrency,
  loadDashboardMode,
  saveDashboardMode,
  type DashboardMode,
} from '../services/dashboard-overview';

const mode = ref<DashboardMode>(loadDashboardMode());
const overview = ref<DashboardOverviewResponse | null>(null);
const overviewLoading = ref(true);
const overviewError = ref(false);
const operationalLoading = ref(true);
const operationalError = ref(false);
const stats = ref<DashboardStatsResponse | null>(null);
const leadsCount = ref(0);

const modeSubtitle = computed(() => (
  mode.value === 'manager'
    ? 'Операционная сводка и ближайшие действия'
    : 'Финансовый результат и эффективность бизнеса'
));

const setMode = (nextMode: DashboardMode) => {
  mode.value = nextMode;
  saveDashboardMode(nextMode);
};

const fetchOverview = async () => {
  overviewLoading.value = true;
  overviewError.value = false;
  try {
    overview.value = await api.getDashboardOverview();
  } catch (error) {
    console.error('Error fetching dashboard overview:', error);
    overviewError.value = true;
  } finally {
    overviewLoading.value = false;
  }
};

const fetchOperationalBlocks = async () => {
  operationalLoading.value = true;
  operationalError.value = false;
  try {
    stats.value = await api.getDashboardStats();
  } catch (error) {
    console.error('Error fetching operational dashboard blocks:', error);
    operationalError.value = true;
  } finally {
    operationalLoading.value = false;
  }
};

const fetchLeadsCounter = async () => {
  try {
    leadsCount.value = (await api.getLeadsCounter()).count;
  } catch (error) {
    console.error('Error fetching leads counter:', error);
  }
};

onMounted(() => {
  void fetchOverview();
  void fetchOperationalBlocks();
  void fetchLeadsCounter();
});

const navigate = (path: string) => {
  if (window.location.pathname !== path) {
    window.history.pushState({}, '', path);
    window.dispatchEvent(new Event('popstate'));
  }
};

const formatDate = (dateStr: string) => new Date(dateStr).toLocaleDateString('ru-RU', {
  day: '2-digit',
  month: 'short',
  year: 'numeric',
});

const openCustomer = (customerId: number) => {
  navigate(`/manager/customers/profile?customerId=${customerId}&returnTo=${encodeURIComponent('/manager')}`);
};

const openOrder = (orderId: number) => navigate(`/manager/orders/kanban?orderId=${orderId}`);

const shortText = (value?: string | null, limit = 120) => {
  const text = (value || '').trim();
  return text.length > limit ? `${text.slice(0, limit)}...` : text;
};
</script>

<template>
  <div class="min-h-full bg-slate-50 p-4 text-slate-900 transition-colors duration-200 dark:bg-[#0f172a] dark:text-white sm:p-6">
    <header class="mb-6 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
      <div>
        <p class="text-sm font-semibold text-teal-700 dark:text-teal-300">Центр управления</p>
        <h1 class="mt-1 text-2xl font-bold tracking-tight text-slate-950 dark:text-white">Мастер Воздуха</h1>
        <p class="mt-1 text-sm text-slate-500 dark:text-slate-400">{{ modeSubtitle }}</p>
      </div>
      <DashboardModeSwitch :model-value="mode" @update:model-value="setMode" />
    </header>
    <DashboardQuickActions :leads-count="leadsCount" @navigate="navigate" />

    <DashboardLoadingState v-if="overviewLoading" />
    <section v-else-if="overviewError" class="rounded-xl border border-rose-200 bg-white p-6 text-center dark:border-rose-900/60 dark:bg-slate-800">
      <span class="material-icons-round text-3xl text-rose-500">cloud_off</span>
      <h2 class="mt-2 font-semibold text-slate-900 dark:text-white">Не удалось загрузить сводку</h2>
      <p class="mt-1 text-sm text-slate-500 dark:text-slate-400">Операционные блоки ниже остаются доступны.</p>
      <button type="button" class="mt-4 rounded-lg bg-teal-600 px-4 py-2 text-sm font-semibold text-white hover:bg-teal-700" @click="fetchOverview">Повторить</button>
    </section>
    <template v-else-if="overview">
      <DashboardKpiGrid :kpis="overview.kpis" :mode="mode" />
      <div class="mt-4 grid gap-4 lg:grid-cols-[minmax(0,1.3fr)_minmax(0,0.9fr)]">
        <DashboardSalesChart :series="overview.sales_series" />
        <DashboardFunnel :stages="overview.funnel" />
      </div>
      <div class="mt-4"><DashboardMarketing :marketing="overview.marketing" /></div>
      <div class="mt-4"><DashboardSearchDemand :demand="overview.search_demand" /></div>
    </template>

    <section v-if="stats && (stats.bank_receipts_review_count || 0) > 0" class="mt-8">
      <div class="mb-3 flex items-center justify-between gap-3">
        <h2 class="text-lg font-semibold text-slate-800 dark:text-gray-300">Поступления требуют проверки</h2>
        <span class="inline-flex min-w-7 items-center justify-center rounded-full bg-amber-500 px-2 py-1 text-xs font-bold text-white">{{ stats.bank_receipts_review_count }}</span>
      </div>
      <div class="flex flex-col gap-3">
        <div v-for="receipt in stats.bank_receipts_review" :key="receipt.id" class="rounded-xl border border-amber-200 bg-white p-4 dark:border-amber-500/30 dark:bg-[#1e293b]">
          <div class="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            <div class="min-w-0">
              <div class="flex flex-wrap items-center gap-2">
                <span class="font-semibold text-slate-900 dark:text-white">{{ formatDashboardCurrency(receipt.amount) }}</span>
                <span class="text-sm text-slate-500 dark:text-slate-400">{{ receipt.payer_name || 'Плательщик не указан' }}</span>
              </div>
              <div class="mt-1 text-xs text-slate-500 dark:text-slate-400">УНП {{ receipt.payer_unp || 'не указан' }} · документ {{ receipt.payment_document_number || 'не указан' }}</div>
              <p class="mt-2 text-sm text-slate-600 dark:text-slate-300">{{ shortText(receipt.payment_purpose) }}</p>
            </div>
            <button v-if="receipt.candidate_order_ids?.length" type="button" class="inline-flex items-center justify-center gap-1 rounded-lg bg-teal-600 px-3 py-2 text-sm font-semibold text-white hover:bg-teal-700" @click="receipt.candidate_order_ids?.[0] && openOrder(receipt.candidate_order_ids[0])">
              <span class="material-icons-round text-[16px]">open_in_new</span>
              Заказ #{{ receipt.candidate_order_ids[0] }}
            </button>
            <button v-else type="button" class="inline-flex items-center justify-center gap-1 rounded-lg border border-slate-200 px-3 py-2 text-sm font-semibold text-slate-600 dark:border-slate-700 dark:text-slate-300" @click="navigate('/manager/orders/kanban')">
              <span class="material-icons-round text-[16px]">search</span>
              Найти заказ
            </button>
          </div>
        </div>
      </div>
    </section>

    <section v-if="stats && stats.expiring_contracts?.length" class="mt-8">
      <h2 class="mb-3 text-lg font-semibold text-slate-800 dark:text-gray-300">Договоры к продлению</h2>
      <div class="flex flex-col gap-3">
        <div v-for="contract in stats.expiring_contracts" :key="contract.contract_id" class="flex items-center justify-between rounded-xl border border-amber-200 bg-white p-4 dark:border-amber-500/30 dark:bg-[#1e293b]">
          <button class="text-left" type="button" @click="openCustomer(contract.customer_id)">
            <div class="font-medium text-slate-800 dark:text-gray-200">{{ contract.customer_name }} · {{ contract.number }}</div>
            <div class="mt-1 flex items-center gap-1 text-sm text-amber-600 dark:text-amber-400"><span class="material-icons-round text-[16px]">event_busy</span>до {{ formatDate(contract.valid_until) }}</div>
          </button>
          <a v-if="contract.edit_url" :href="contract.edit_url" target="_blank" class="material-icons-round text-slate-400 hover:text-teal-500" title="Открыть договор">open_in_new</a>
        </div>
      </div>
    </section>

    <section class="mt-8">
      <h2 class="mb-3 text-lg font-semibold text-slate-800 dark:text-gray-300">Ближайшие касания</h2>
      <div v-if="operationalLoading" class="rounded-xl border border-slate-200 bg-white p-5 text-sm text-slate-500 dark:border-slate-700 dark:bg-[#1e293b] dark:text-slate-400">Загрузка задач...</div>
      <div v-else-if="operationalError" class="rounded-xl border border-slate-200 bg-white p-5 text-sm text-slate-500 dark:border-slate-700 dark:bg-[#1e293b] dark:text-slate-400">Операционные данные временно недоступны.</div>
      <div v-else-if="stats && stats.upcoming_touchpoints.length > 0" class="flex flex-col gap-3">
        <button v-for="touch in stats.upcoming_touchpoints" :key="touch.order_id" type="button" class="flex items-center justify-between rounded-xl border border-slate-200 bg-white p-4 text-left hover:bg-slate-50 dark:border-slate-700/50 dark:bg-[#1e293b] dark:hover:bg-slate-800" @click="openOrder(touch.order_id)">
          <div>
            <div class="font-medium text-slate-800 dark:text-gray-200">Заказ #{{ touch.order_id }} — {{ touch.customer_name }}<span v-if="touch.title" class="ml-2 text-sm font-normal text-slate-500 dark:text-gray-400">({{ touch.title }})</span></div>
            <div class="mt-1 flex flex-wrap gap-4 text-sm text-slate-500 dark:text-gray-400">
              <span v-if="touch.phone" class="flex items-center gap-1"><span class="material-icons-round text-[16px]">call</span>{{ touch.phone }}</span>
              <span class="flex items-center gap-1 text-rose-500 dark:text-rose-400"><span class="material-icons-round text-[16px]">event</span>{{ formatDate(touch.next_followup_date) }}</span>
            </div>
          </div>
          <span class="material-icons-round text-slate-400 dark:text-gray-500">chevron_right</span>
        </button>
      </div>
      <div v-else class="rounded-xl border border-dashed border-slate-200 bg-slate-100 p-6 text-center text-sm italic text-slate-500 dark:border-slate-800 dark:bg-[#1e293b]/50 dark:text-gray-400">Нет срочных касаний.</div>
    </section>
  </div>
</template>
