<script setup lang="ts">
import { computed, onMounted, ref, type Component } from 'vue';
import { BarChart3, CalendarClock, ChevronRight, CircleAlert, ExternalLink, FileWarning, Inbox, Megaphone, Search, ShoppingBag, WalletCards } from 'lucide-vue-next';
import { api, type DashboardStatsResponse } from '../api';
import type { DashboardOverviewResponse } from '../client';
import { MANAGER_CAPABILITY, hasManagerCapability } from '../manager-capabilities';
import { managerSession } from '../services/manager-session';
import DashboardAdvertising from '../components/dashboard/DashboardAdvertising.vue';
import DashboardFunnel from '../components/dashboard/DashboardFunnel.vue';
import DashboardKpiGrid from '../components/dashboard/DashboardKpiGrid.vue';
import DashboardLoadingState from '../components/dashboard/DashboardLoadingState.vue';
import DashboardSalesChart from '../components/dashboard/DashboardSalesChart.vue';
import DashboardSiteSeo from '../components/dashboard/DashboardSiteSeo.vue';
import { formatDashboardComparisonPeriod, formatDashboardCurrency } from '../services/dashboard-overview';

type DashboardTab = 'sales' | 'site-seo' | 'advertising';
const tabs: Array<{ id: DashboardTab; label: string; icon: Component }> = [
  { id: 'sales', label: 'Продажи', icon: ShoppingBag },
  { id: 'site-seo', label: 'Сайт и SEO', icon: BarChart3 },
  { id: 'advertising', label: 'Реклама', icon: Megaphone },
];
const activeTab = ref<DashboardTab>('sales');
const overview = ref<DashboardOverviewResponse | null>(null);
const overviewLoading = ref(true);
const overviewError = ref(false);
const operationalLoading = ref(true);
const operationalError = ref(false);
const leadsLoading = ref(true);
const leadsError = ref(false);
const stats = ref<DashboardStatsResponse | null>(null);
const leadsCount = ref(0);
const canManageIntegrations = computed(() => hasManagerCapability(managerSession.auth.value, MANAGER_CAPABILITY.analyticsManage));
const overdueTouchpoints = computed(() => stats.value?.upcoming_touchpoints?.filter(touch => isOverdue(touch.next_followup_date)) || []);
const firstOverdueTouchpoint = computed(() => overdueTouchpoints.value[0] || null);

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
  leadsLoading.value = true;
  leadsError.value = false;
  try {
    leadsCount.value = (await api.getLeadsCounter()).count;
  } catch (error) {
    console.error('Error fetching leads counter:', error);
    leadsError.value = true;
  } finally {
    leadsLoading.value = false;
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
const selectTab = (tab: DashboardTab) => { activeTab.value = tab; };
const selectTabFromKey = (event: KeyboardEvent) => {
  const current = tabs.findIndex(tab => tab.id === activeTab.value);
  let next = current;
  if (event.key === 'ArrowRight') next = (current + 1) % tabs.length;
  else if (event.key === 'ArrowLeft') next = (current + tabs.length - 1) % tabs.length;
  else if (event.key === 'Home') next = 0;
  else if (event.key === 'End') next = tabs.length - 1;
  else return;
  const selected = tabs[next]!;
  event.preventDefault();
  selectTab(selected.id);
  document.getElementById(`dashboard-tab-${selected.id}`)?.focus();
};
const formatDate = (value: string) => new Date(value).toLocaleDateString('ru-RU', { day: '2-digit', month: 'short', year: 'numeric' });
const isOverdue = (value: string) => new Date(value).getTime() < Date.now();
const deadlineLabel = (value: string) => isOverdue(value)
  ? `просрочено ${Math.max(1, Math.floor((Date.now() - new Date(value).getTime()) / 86_400_000))} дн.`
  : `до ${formatDate(value)}`;
const hasOverdueContracts = computed(() => stats.value?.expiring_contracts?.some(item => isOverdue(item.valid_until)) || false);
const openOrder = (id: number) => navigate(`/manager/orders/kanban?orderId=${id}`);
const openCustomer = (id: number) => navigate(`/manager/customers/profile?customerId=${id}&returnTo=${encodeURIComponent('/manager')}`);
const shortText = (value?: string | null, limit = 120) => {
  const text = (value || '').trim();
  return text.length > limit ? `${text.slice(0, limit)}...` : text;
};
</script>

<template>
  <div class="min-h-full bg-slate-50 p-4 text-slate-900 dark:bg-[#0f172a] dark:text-white sm:p-6">
    <header class="mb-5">
      <h1 class="text-2xl font-semibold tracking-tight text-slate-950 dark:text-white">Эффективность работы</h1>
      <p v-if="overview" class="mt-1 text-sm text-slate-500 dark:text-slate-400">{{ formatDashboardComparisonPeriod(overview.period) }}</p>
    </header>
    <nav class="mb-6 grid grid-cols-3 gap-1 border-b border-slate-200 dark:border-slate-700 sm:gap-2" role="tablist" aria-label="Разделы эффективности">
      <button v-for="tab in tabs" :id="`dashboard-tab-${tab.id}`" :key="tab.id" type="button" role="tab" :aria-selected="activeTab === tab.id" :aria-controls="`dashboard-panel-${tab.id}`" class="inline-flex min-w-0 items-center justify-center gap-1 border-b-2 px-2 py-3 text-xs font-semibold focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500 sm:gap-2 sm:px-3 sm:text-sm" :class="activeTab === tab.id ? 'border-teal-600 bg-teal-50 text-teal-800 dark:border-teal-400 dark:bg-teal-950/30 dark:text-teal-200' : 'border-transparent text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white'" @click="selectTab(tab.id)" @keydown="selectTabFromKey"><component :is="tab.icon" class="hidden h-4 w-4 shrink-0 min-[360px]:block" aria-hidden="true" /><span class="truncate">{{ tab.label }}</span></button>
    </nav>

    <section v-if="activeTab === 'sales'" id="dashboard-panel-sales" role="tabpanel" aria-labelledby="dashboard-tab-sales" class="space-y-5">
      <section class="rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-800">
        <div class="flex items-center justify-between gap-3"><h2 class="text-lg font-semibold text-slate-900 dark:text-white">Требует внимания</h2><span class="text-xs text-slate-500 dark:text-slate-400">На сейчас</span></div>
        <div v-if="operationalLoading || leadsLoading" class="mt-3 text-sm text-slate-500 dark:text-slate-400">Проверяем срочные действия...</div>
        <template v-else>
        <p v-if="leadsError || operationalError" class="mt-3 text-sm text-slate-500 dark:text-slate-400">Часть проверок недоступна. Доступные действия показаны ниже.</p>
        <div v-if="leadsCount || stats?.bank_receipts_review_count || firstOverdueTouchpoint" class="mt-4 grid gap-3 md:grid-cols-3">
          <button v-if="leadsCount" type="button" class="flex items-center gap-3 rounded-lg bg-slate-50 p-3 text-left hover:bg-teal-50 dark:bg-slate-900/40 dark:hover:bg-teal-950/30" @click="navigate('/manager/leads')"><Inbox class="h-5 w-5 shrink-0 text-teal-600" aria-hidden="true" /><span><strong class="block text-sm">{{ leadsCount }} входящих</strong><span class="text-xs text-slate-500">Разобрать заявки</span></span></button>
          <button v-if="stats?.bank_receipts_review_count" type="button" class="flex items-center gap-3 rounded-lg bg-slate-50 p-3 text-left hover:bg-teal-50 dark:bg-slate-900/40 dark:hover:bg-teal-950/30" @click="navigate('/manager/payments')"><WalletCards class="h-5 w-5 shrink-0 text-teal-600" aria-hidden="true" /><span><strong class="block text-sm">{{ stats.bank_receipts_review_count }} поступлений</strong><span class="text-xs text-slate-500">Связать с заказами</span></span></button>
          <button v-if="firstOverdueTouchpoint" type="button" class="flex items-center gap-3 rounded-lg bg-slate-50 p-3 text-left hover:bg-teal-50 dark:bg-slate-900/40 dark:hover:bg-teal-950/30" @click="openOrder(firstOverdueTouchpoint.order_id)"><CalendarClock class="h-5 w-5 shrink-0 text-rose-600" aria-hidden="true" /><span><strong class="block text-sm">Просроченные касания</strong><span class="text-xs text-slate-500">Вернуться к клиентам</span></span></button>
        </div>
        <p v-else-if="!leadsError && !operationalError" class="mt-3 text-sm text-slate-500 dark:text-slate-400">Срочных действий нет.</p>
        </template>
      </section>
      <DashboardLoadingState v-if="overviewLoading" />
      <section v-else-if="overviewError" class="rounded-xl border border-rose-200 bg-white p-6 text-center dark:border-rose-900/60 dark:bg-slate-800">
        <CircleAlert class="mx-auto h-8 w-8 text-rose-500" aria-hidden="true" />
        <h2 class="mt-2 font-semibold text-slate-900 dark:text-white">Не удалось загрузить сводку</h2>
        <p class="mt-1 text-sm text-slate-500 dark:text-slate-400">Операционные списки ниже остаются доступны.</p>
        <button type="button" class="mt-4 rounded-lg bg-teal-600 px-4 py-2 text-sm font-semibold text-white hover:bg-teal-700" @click="fetchOverview">Повторить</button>
      </section>
      <template v-else-if="overview">
      <DashboardKpiGrid :kpis="overview.kpis" />
      <div class="grid gap-4 lg:grid-cols-[minmax(0,1.3fr)_minmax(0,0.9fr)]"><DashboardSalesChart :series="overview.sales_series" /><DashboardFunnel :stages="overview.funnel" /></div>
      </template>
      <section v-if="stats && (stats.bank_receipts_review_count || 0) > 0" class="pt-2">
        <h2 class="mb-3 text-lg font-semibold text-slate-800 dark:text-gray-300">Поступления требуют проверки</h2>
        <article v-for="receipt in stats.bank_receipts_review" :key="receipt.id" class="mb-3 rounded-xl border border-amber-200 bg-white p-4 dark:border-amber-500/30 dark:bg-[#1e293b]">
          <div class="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between"><div><p class="font-semibold text-slate-900 dark:text-white">{{ formatDashboardCurrency(receipt.amount) }} <span class="ml-2 text-sm font-normal text-slate-500">{{ receipt.payer_name || 'Плательщик не указан' }}</span></p><p class="mt-1 text-xs text-slate-500">УНП {{ receipt.payer_unp || 'не указан' }} · документ {{ receipt.payment_document_number || 'не указан' }}</p><p class="mt-2 text-sm text-slate-600 dark:text-slate-300">{{ shortText(receipt.payment_purpose) }}</p></div><button v-if="receipt.candidate_order_ids?.length" type="button" class="inline-flex items-center gap-1 self-start rounded-lg bg-teal-600 px-3 py-2 text-sm font-semibold text-white" @click="openOrder(receipt.candidate_order_ids[0]!)">Заказ #{{ receipt.candidate_order_ids[0] }}<ExternalLink class="h-4 w-4" /></button><button v-else type="button" class="inline-flex items-center gap-1 self-start rounded-lg border border-slate-200 px-3 py-2 text-sm font-semibold" @click="navigate('/manager/orders/kanban')"><Search class="h-4 w-4" />Найти заказ</button></div>
        </article>
      </section>
      <section v-if="stats && stats.expiring_contracts?.length" class="pt-2">
        <h2 class="mb-3 text-lg font-semibold text-slate-800 dark:text-gray-300">{{ hasOverdueContracts ? 'Договоры требуют внимания' : 'Договоры к продлению' }}</h2>
        <article v-for="contract in stats.expiring_contracts" :key="contract.contract_id" class="mb-3 flex items-center justify-between rounded-xl border border-amber-200 bg-white p-4 dark:border-amber-500/30 dark:bg-[#1e293b]"><button class="text-left" type="button" @click="openCustomer(contract.customer_id)"><strong>{{ contract.customer_name }} · {{ contract.number }}</strong><span class="mt-1 flex items-center gap-1 text-sm" :class="isOverdue(contract.valid_until) ? 'font-semibold text-rose-600' : 'text-amber-600'"><FileWarning class="h-4 w-4" />{{ deadlineLabel(contract.valid_until) }}</span></button><a v-if="contract.edit_url" :href="contract.edit_url" target="_blank" class="text-slate-400 hover:text-teal-500" title="Открыть договор"><ExternalLink class="h-5 w-5" /></a></article>
      </section>
      <section class="pt-2">
        <h2 class="mb-3 text-lg font-semibold text-slate-800 dark:text-gray-300">{{ overdueTouchpoints.length ? 'Касания требуют внимания' : 'Ближайшие касания' }}</h2>
        <div v-if="operationalLoading" class="rounded-xl border border-slate-200 bg-white p-5 text-sm text-slate-500">Загрузка задач...</div>
        <div v-else-if="operationalError" class="rounded-xl border border-slate-200 bg-white p-5 text-sm text-slate-500">Операционные данные временно недоступны.</div>
        <div v-else-if="stats && stats.upcoming_touchpoints.length" class="space-y-3"><button v-for="touch in stats.upcoming_touchpoints" :key="touch.order_id" type="button" class="flex w-full items-center justify-between rounded-xl border border-slate-200 bg-white p-4 text-left hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-800" @click="openOrder(touch.order_id)"><span><strong>Заказ #{{ touch.order_id }} — {{ touch.customer_name }}</strong><span v-if="touch.title" class="ml-2 text-sm text-slate-500">({{ touch.title }})</span><span class="mt-1 block text-sm" :class="isOverdue(touch.next_followup_date) ? 'font-semibold text-rose-600' : 'text-slate-500'">{{ touch.phone ? `${touch.phone} · ` : '' }}{{ deadlineLabel(touch.next_followup_date) }}</span></span><ChevronRight class="h-5 w-5 text-slate-400" /></button></div>
        <div v-else class="rounded-xl border border-dashed border-slate-200 bg-slate-100 p-6 text-center text-sm text-slate-500">Нет срочных касаний.</div>
      </section>
    </section>
    <DashboardLoadingState v-else-if="overviewLoading" />
    <section v-else-if="overviewError" class="rounded-xl border border-rose-200 bg-white p-6 text-center dark:border-rose-900/60 dark:bg-slate-800"><CircleAlert class="mx-auto h-8 w-8 text-rose-500" aria-hidden="true" /><h2 class="mt-2 font-semibold text-slate-900 dark:text-white">Не удалось загрузить сводку</h2><button type="button" class="mt-4 rounded-lg bg-teal-600 px-4 py-2 text-sm font-semibold text-white hover:bg-teal-700" @click="fetchOverview">Повторить</button></section>
    <section v-else-if="overview && activeTab === 'site-seo'" id="dashboard-panel-site-seo" role="tabpanel" aria-labelledby="dashboard-tab-site-seo"><DashboardSiteSeo :marketing="overview.marketing" :search-demand="overview.search_demand" :can-manage-integrations="canManageIntegrations" /></section>
    <section v-else-if="overview" id="dashboard-panel-advertising" role="tabpanel" aria-labelledby="dashboard-tab-advertising"><DashboardAdvertising :marketing="overview.marketing" :can-manage-integrations="canManageIntegrations" /></section>
  </div>
</template>
