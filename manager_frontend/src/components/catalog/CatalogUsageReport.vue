<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue';
import { BarChart3, X } from 'lucide-vue-next';
import { useDrawerFocusTrap } from '../../composables/useDrawerFocusTrap';
import { MANAGER_CAPABILITY, hasManagerCapability } from '../../manager-capabilities';
import { managerSession } from '../../services/manager-session';
import {
  type CatalogUsageAction,
  type CatalogUsageReport,
  catalogUsageApi,
} from '../../services/catalog-usage-api';
import { getApiErrorMessage } from '../../utils/api-errors';

const props = defineProps<{ open: boolean }>();
const emit = defineEmits<{ close: [] }>();
const dialog = ref<HTMLElement | null>(null);
const { captureFocus, focusContainer, restoreFocus, trapFocus } = useDrawerFocusTrap(dialog);
const days = ref<7 | 30 | 90>(30);
const loading = ref(false);
const error = ref('');
const report = ref<CatalogUsageReport | null>(null);
let pendingRequest: ReturnType<typeof catalogUsageApi.daily> | null = null;

const canViewReport = computed(() => hasManagerCapability(managerSession.auth.value, MANAGER_CAPABILITY.analyticsManage));
const labels: Record<CatalogUsageAction, string> = {
  product_open: 'Открытие товара', filter_apply: 'Применение фильтров', filter_zero_results: 'Нулевой результат',
  edit_basics: 'Основные данные', edit_pricing: 'Цена', edit_specifications: 'Характеристики',
  edit_gallery: 'Галерея', edit_features: 'Особенности', bulk_edit: 'Массовое изменение',
  gallery_quick_exit: 'Быстрый выход из галереи', media_load: 'Загрузка медиа',
};
const totals = computed(() => {
  const values = new Map<CatalogUsageAction, number>();
  for (const item of report.value?.items || []) values.set(item.action, (values.get(item.action) || 0) + item.count);
  return [...values].map(([action, count]) => ({ action, count })).sort((left, right) => right.count - left.count);
});
const maxTotal = computed(() => Math.max(1, ...totals.value.map(item => item.count)));
const total = computed(() => totals.value.reduce((sum, item) => sum + item.count, 0));

const load = async () => {
  pendingRequest?.cancel();
  pendingRequest = null;
  if (!props.open || !canViewReport.value) {
    report.value = null;
    loading.value = false;
    return;
  }
  loading.value = true;
  error.value = '';
  const request = catalogUsageApi.daily({ days: days.value });
  pendingRequest = request;
  try {
    const response = await request;
    if (pendingRequest === request && props.open) report.value = response;
  } catch (requestError) {
    if (pendingRequest === request && !request.isCancelled) error.value = getApiErrorMessage(requestError) || 'Не удалось загрузить статистику';
  } finally {
    if (pendingRequest === request) {
      pendingRequest = null;
      loading.value = false;
    }
  }
};

watch(() => props.open, async (open) => {
  if (open) {
    captureFocus();
    void load();
    await nextTick();
    if (props.open) focusContainer();
  } else {
    pendingRequest?.cancel();
    pendingRequest = null;
    report.value = null;
    await nextTick();
    restoreFocus();
  }
}, { immediate: true });
watch(days, () => { if (props.open) void load(); });
watch(canViewReport, allowed => { if (!allowed && props.open) emit('close'); }, { flush: 'sync' });
onBeforeUnmount(() => pendingRequest?.cancel());
</script>

<template>
  <div v-if="open" ref="dialog" tabindex="-1" class="fixed inset-0 z-[70] overflow-y-auto bg-white p-4 outline-none dark:bg-slate-950 sm:p-6" role="dialog" aria-modal="true" aria-label="Отчёт по каталогу" @keydown.stop="trapFocus" @keydown.esc.stop="emit('close')">
    <div class="mx-auto max-w-3xl">
      <div class="flex items-start justify-between gap-4">
        <div>
          <div class="flex items-center gap-2 text-slate-900 dark:text-white"><BarChart3 :size="20" aria-hidden="true" /><h2 class="text-lg font-semibold">Пилот каталога</h2></div>
          <p class="mt-1 text-sm text-slate-500 dark:text-slate-400">Агрегированные действия участников без данных товаров, форм и пользователей.</p>
        </div>
        <button type="button" class="btn-mini-outline h-9 w-9 justify-center p-0" aria-label="Закрыть отчёт" @click="emit('close')"><X :size="17" /></button>
      </div>
      <label class="field-label mt-5 block max-w-xs">Период<select v-model="days" class="field-input mt-1"><option :value="7">7 дней</option><option :value="30">30 дней</option><option :value="90">90 дней</option></select></label>
      <p v-if="loading" class="mt-6 text-sm text-slate-500">Загрузка…</p>
      <p v-else-if="error" class="mt-6 text-sm text-red-600">{{ error }}</p>
      <template v-else>
        <p class="mt-6 text-sm font-medium text-slate-700 dark:text-slate-200">Всего действий: {{ total }}</p>
        <p v-if="!report?.items.length" class="mt-3 text-sm text-slate-500">За этот период нет данных от участников пилота.</p>
        <div v-else class="mt-4 space-y-3">
          <div v-for="item in totals" :key="item.action" class="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-3 text-sm">
            <div><div class="mb-1 flex justify-between gap-3"><span>{{ labels[item.action] }}</span><span class="text-slate-500">{{ item.count }}</span></div><div class="h-2 overflow-hidden rounded bg-slate-100 dark:bg-slate-800"><div class="h-full rounded bg-brand-500" :style="{ width: `${(item.count / maxTotal) * 100}%` }" /></div></div>
            <span class="text-xs text-slate-500">{{ item.count }}</span>
          </div>
        </div>
      </template>
    </div>
  </div>
</template>
