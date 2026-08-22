<script setup lang="ts">
import { onMounted, ref } from 'vue';
import { CheckCircle2, Link2, Loader2, RefreshCw, Store } from 'lucide-vue-next';

import {
  ManagerAnalyticsConnectionsService,
  type AnalyticsConnectionItem,
  type YandexMetrikaConnectionUpsertPayload,
} from '../client';
import AnalyticsConnectionCard from '../components/integrations/AnalyticsConnectionCard.vue';
import YandexMetrikaDialog from '../components/integrations/YandexMetrikaDialog.vue';
import { managerStorefrontSelection } from '../services/manager-storefront-selection';
import { getApiErrorMessage } from '../utils/api-errors';

const connections = ref<AnalyticsConnectionItem[]>([]);
const loading = ref(true);
const loadError = ref('');
const dialogOpen = ref(false);
const dialogMode = ref<'configure' | 'help'>('configure');
const selectedConnection = ref<AnalyticsConnectionItem | null>(null);
const saving = ref(false);
const saveError = ref('');
const savedMessage = ref('');

const currentStorefrontName = () => {
  const selected = managerStorefrontSelection.selectedSlug.value;
  return managerStorefrontSelection.storefronts.value.find(
    storefront => storefront.slug === selected,
  )?.display_name || 'текущего филиала';
};

const loadConnections = async () => {
  loading.value = true;
  loadError.value = '';
  try {
    const response = await ManagerAnalyticsConnectionsService.listManagerAnalyticsConnections();
    connections.value = response.items;
  } catch (error) {
    loadError.value = getApiErrorMessage(error) || 'Не удалось загрузить подключения';
  } finally {
    loading.value = false;
  }
};

const openDialog = (connection: AnalyticsConnectionItem, mode: 'configure' | 'help') => {
  selectedConnection.value = connection;
  dialogMode.value = mode;
  saveError.value = '';
  savedMessage.value = '';
  dialogOpen.value = true;
};

const saveMetrika = async (payload: YandexMetrikaConnectionUpsertPayload) => {
  if (saving.value) return;
  saving.value = true;
  saveError.value = '';
  try {
    const updated = await ManagerAnalyticsConnectionsService.upsertManagerYandexMetrikaConnection(payload);
    connections.value = connections.value.map(item => (
      item.provider === updated.provider ? updated : item
    ));
    dialogOpen.value = false;
    savedMessage.value = `Яндекс Метрика подключена для филиала «${currentStorefrontName()}»`;
  } catch (error) {
    saveError.value = getApiErrorMessage(error) || 'Не удалось проверить подключение';
  } finally {
    saving.value = false;
  }
};

onMounted(loadConnections);
</script>

<template>
  <section class="min-h-[calc(100vh-4rem)] bg-slate-50 px-4 py-7 dark:bg-slate-950 sm:px-6 lg:px-8">
    <div class="mx-auto max-w-7xl">
      <div class="flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
        <div>
          <div class="flex items-center gap-2 text-xs font-bold uppercase tracking-[0.16em] text-teal-600">
            <Link2 class="h-4 w-4" /> Аккаунт
          </div>
          <h1 class="mt-2 text-3xl font-bold tracking-tight text-slate-950 dark:text-white">Интеграции</h1>
          <p class="mt-2 max-w-2xl text-sm leading-6 text-slate-500 dark:text-slate-400">
            Подключайте аналитику отдельно для каждого филиала. После проверки реальные данные появятся на главной панели.
          </p>
        </div>
        <button
          type="button"
          class="inline-flex items-center justify-center gap-2 rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-sm font-semibold text-slate-700 shadow-sm hover:bg-slate-50 disabled:opacity-60 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200 dark:hover:bg-slate-800"
          :disabled="loading"
          @click="loadConnections"
        >
          <Loader2 v-if="loading" class="h-4 w-4 animate-spin" />
          <RefreshCw v-else class="h-4 w-4" />
          Обновить
        </button>
      </div>

      <div class="mt-6 flex items-start gap-3 rounded-2xl border border-cyan-100 bg-cyan-50 px-4 py-3.5 text-sm text-cyan-950 dark:border-cyan-900/60 dark:bg-cyan-950/30 dark:text-cyan-100">
        <Store class="mt-0.5 h-5 w-5 shrink-0 text-cyan-700" />
        <p>
          Настройки сохраняются только для филиала
          <strong>«{{ currentStorefrontName() }}»</strong>.
          Чтобы подключить другой сайт, сначала переключите филиал слева.
        </p>
      </div>

      <div v-if="savedMessage" data-testid="analytics-saved" class="mt-5 flex items-center gap-2 rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm font-medium text-emerald-800">
        <CheckCircle2 class="h-5 w-5" /> {{ savedMessage }}
      </div>
      <div v-if="loadError" role="alert" class="mt-5 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
        {{ loadError }}
      </div>

      <div v-if="loading && !connections.length" class="mt-8 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <div v-for="index in 4" :key="index" class="h-64 animate-pulse rounded-2xl border border-slate-200 bg-white dark:border-slate-700 dark:bg-slate-900" />
      </div>
      <div v-else class="mt-8 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <AnalyticsConnectionCard
          v-for="connection in connections"
          :key="connection.provider"
          :connection="connection"
          @configure="openDialog($event, 'configure')"
          @help="openDialog($event, 'help')"
        />
      </div>
    </div>

    <YandexMetrikaDialog
      :open="dialogOpen"
      :mode="dialogMode"
      :connection="selectedConnection"
      :saving="saving"
      :error="saveError"
      @close="dialogOpen = false"
      @change-mode="dialogMode = $event"
      @save="saveMetrika"
    />
  </section>
</template>
