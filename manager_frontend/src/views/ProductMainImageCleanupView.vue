<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import {
  AlertTriangle,
  Check,
  ExternalLink,
  Loader2,
  Plus,
  RefreshCw,
  X,
} from 'lucide-vue-next';
import {
  api,
  type ProductMainImageCleanupBatchResponse,
  type ProductMainImageCleanupItemResponse,
} from '../api';
import { getApiErrorMessage } from '../utils/api-errors';

type StatusFilter = 'all' | 'candidate_ready' | 'failed' | 'skipped' | 'rejected' | 'approved';

const batches = ref<ProductMainImageCleanupBatchResponse[]>([]);
const items = ref<ProductMainImageCleanupItemResponse[]>([]);
const selectedBatchId = ref<number | null>(null);
const selectedIds = ref<number[]>([]);
const statusFilter = ref<StatusFilter>('all');
const batchLimit = ref(50);
const processorMethod = ref('noop');
const rejectReason = ref('Не подходит для публичной карточки');
const loadingBatches = ref(false);
const loadingItems = ref(false);
const creating = ref(false);
const actionLoading = ref(false);
const error = ref('');
const notice = ref('');

const statusLabels: Record<string, string> = {
  candidate_ready: 'Готов к проверке',
  failed: 'Ошибка',
  skipped: 'Пропущен',
  pending: 'Ожидает',
  processing: 'В обработке',
  rejected: 'Отклонён',
  approved: 'Одобрен',
};

const statusClasses: Record<string, string> = {
  candidate_ready: 'border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-500/30 dark:bg-emerald-500/10 dark:text-emerald-300',
  failed: 'border-red-200 bg-red-50 text-red-700 dark:border-red-500/30 dark:bg-red-500/10 dark:text-red-300',
  skipped: 'border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-300',
  pending: 'border-slate-200 bg-slate-50 text-slate-700 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-300',
  processing: 'border-sky-200 bg-sky-50 text-sky-700 dark:border-sky-500/30 dark:bg-sky-500/10 dark:text-sky-300',
  rejected: 'border-slate-200 bg-slate-100 text-slate-700 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-300',
  approved: 'border-teal-200 bg-teal-50 text-teal-700 dark:border-teal-500/30 dark:bg-teal-500/10 dark:text-teal-300',
};

const actionableItems = computed(() => items.value.filter((item) => item.status === 'candidate_ready' && item.id));
const selectedActionableIds = computed(() => selectedIds.value.filter((id) => {
  return actionableItems.value.some((item) => item.id === id);
}));

const countsByStatus = computed(() => {
  return items.value.reduce<Record<string, number>>((acc, item) => {
    acc[item.status] = (acc[item.status] || 0) + 1;
    return acc;
  }, {});
});

const displayedItems = computed(() => {
  const filtered = statusFilter.value === 'all'
    ? [...items.value]
    : items.value.filter((item) => item.status === statusFilter.value);
  return filtered.sort((a, b) => riskRank(a) - riskRank(b) || String(b.updated_at).localeCompare(String(a.updated_at)));
});

const selectedBatch = computed(() => {
  return batches.value.find((batch) => batch.id === selectedBatchId.value) || null;
});

const allVisibleActionableSelected = computed(() => {
  const visibleIds = displayedItems.value
    .filter((item) => item.status === 'candidate_ready' && item.id)
    .map((item) => Number(item.id));
  return visibleIds.length > 0 && visibleIds.every((id) => selectedIds.value.includes(id));
});

const filters = computed(() => [
  { value: 'all', label: 'Все', count: items.value.length },
  { value: 'failed', label: 'Ошибки', count: countsByStatus.value.failed || 0 },
  { value: 'skipped', label: 'Пропущены', count: countsByStatus.value.skipped || 0 },
  { value: 'candidate_ready', label: 'К проверке', count: countsByStatus.value.candidate_ready || 0 },
  { value: 'rejected', label: 'Отклонены', count: countsByStatus.value.rejected || 0 },
  { value: 'approved', label: 'Одобрены', count: countsByStatus.value.approved || 0 },
] as Array<{ value: StatusFilter; label: string; count: number }>);

const setNotice = (message: string) => {
  notice.value = message;
  window.setTimeout(() => {
    if (notice.value === message) notice.value = '';
  }, 3500);
};

const riskRank = (item: ProductMainImageCleanupItemResponse) => {
  if (item.status === 'failed') return 0;
  if (item.status === 'skipped') return 1;
  if (item.status === 'candidate_ready' && lowScore(item)) return 2;
  if (item.status === 'candidate_ready') return 3;
  if (item.status === 'pending' || item.status === 'processing') return 4;
  if (item.status === 'rejected') return 5;
  if (item.status === 'approved') return 6;
  return 7;
};

const lowScore = (item: ProductMainImageCleanupItemResponse) => {
  const score = item.confidence_score ?? item.quality_score;
  return typeof score === 'number' && score < 0.75;
};

const statusLabel = (status: string) => statusLabels[status] || status;
const statusClass = (status: string) => statusClasses[status] || statusClasses.pending;

const formatDate = (value?: string | null) => {
  if (!value) return '—';
  return new Intl.DateTimeFormat('ru-RU', {
    day: '2-digit',
    month: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(value));
};

const formatScore = (value?: number | null) => {
  if (typeof value !== 'number') return '—';
  return `${Math.round(value * 100)}%`;
};

const imageUrl = (url?: string | null) => {
  if (!url) return '';
  if (url.startsWith('http://') || url.startsWith('https://') || url.startsWith('/')) return url;
  return `/${url}`;
};

const productTitle = (item: ProductMainImageCleanupItemResponse) => {
  return item.product_title || `Товар #${item.product_id}`;
};

const productMeta = (item: ProductMainImageCleanupItemResponse) => {
  return [item.product_brand_title, item.product_series_title, item.product_model].filter(Boolean).join(' / ');
};

const getPublicSiteBaseUrl = () => {
  const configured = String(import.meta.env.WEBSITE_URL || '').trim();
  if (configured) {
    return configured.replace(/\/+$/, '');
  }

  const { protocol, hostname, host } = window.location;
  if (hostname === 'localhost' || hostname === '127.0.0.1') {
    return `${protocol}//${hostname}:4321`;
  }
  return `${protocol}//${host}`;
};

const productLink = (item: ProductMainImageCleanupItemResponse) => {
  return item.product_slug ? `${getPublicSiteBaseUrl()}/product/${item.product_slug}/` : '';
};

const reasonText = (item: ProductMainImageCleanupItemResponse) => {
  return item.failure_reason || item.skip_reason || item.reject_reason || '';
};

const toggleItem = (item: ProductMainImageCleanupItemResponse) => {
  if (item.status !== 'candidate_ready' || !item.id) return;
  const id = Number(item.id);
  selectedIds.value = selectedIds.value.includes(id)
    ? selectedIds.value.filter((selectedId) => selectedId !== id)
    : [...selectedIds.value, id];
};

const toggleVisible = () => {
  const visibleIds = displayedItems.value
    .filter((item) => item.status === 'candidate_ready' && item.id)
    .map((item) => Number(item.id));
  if (allVisibleActionableSelected.value) {
    selectedIds.value = selectedIds.value.filter((id) => !visibleIds.includes(id));
    return;
  }
  selectedIds.value = Array.from(new Set([...selectedIds.value, ...visibleIds]));
};

const loadBatches = async () => {
  loadingBatches.value = true;
  error.value = '';
  try {
    const response = await api.listMainImageCleanupBatches(20, 0);
    batches.value = response.items || [];
    if (!selectedBatchId.value && batches.value[0]?.id) {
      selectedBatchId.value = batches.value[0].id;
    }
  } catch (err) {
    error.value = getApiErrorMessage(err);
  } finally {
    loadingBatches.value = false;
  }
};

const loadItems = async () => {
  loadingItems.value = true;
  error.value = '';
  selectedIds.value = [];
  try {
    const response = await api.listMainImageCleanupItems(selectedBatchId.value, null, 100, 0);
    items.value = response.items || [];
  } catch (err) {
    error.value = getApiErrorMessage(err);
  } finally {
    loadingItems.value = false;
  }
};

const selectBatch = async (batchId?: number | null) => {
  selectedBatchId.value = batchId || null;
  await loadItems();
};

const refreshAll = async () => {
  await loadBatches();
  await loadItems();
};

const createBatch = async () => {
  creating.value = true;
  error.value = '';
  try {
    const response = await api.createMainImageCleanupBatch({
      limit: Math.max(1, Math.min(Number(batchLimit.value) || 50, 50)),
      processor_method: processorMethod.value.trim() || 'noop',
    });
    selectedBatchId.value = response.batch.id || null;
    items.value = response.items || [];
    await loadBatches();
    setNotice(`Пачка создана: ${response.created_count} позиций, готово к проверке ${response.candidate_ready_count}.`);
  } catch (err) {
    error.value = getApiErrorMessage(err);
  } finally {
    creating.value = false;
  }
};

const approveSelected = async () => {
  const ids = selectedActionableIds.value;
  if (ids.length === 0) return;
  if (!confirm(`Одобрить ${ids.length} кандидатов и заменить публичные main_image у товаров?`)) return;
  actionLoading.value = true;
  error.value = '';
  try {
    const response = await api.approveMainImageCleanupItems(ids);
    setNotice(`Одобрено: ${response.updated_count}. Пропущено: ${response.skipped_count}.`);
    await loadItems();
  } catch (err) {
    error.value = getApiErrorMessage(err);
  } finally {
    actionLoading.value = false;
  }
};

const rejectSelected = async () => {
  const ids = selectedActionableIds.value;
  const reason = rejectReason.value.trim();
  if (ids.length === 0) return;
  if (!reason) {
    error.value = 'Укажите причину отклонения.';
    return;
  }
  actionLoading.value = true;
  error.value = '';
  try {
    const response = await api.rejectMainImageCleanupItems(ids, reason);
    setNotice(`Отклонено: ${response.updated_count}. Публичная витрина не изменена.`);
    await loadItems();
  } catch (err) {
    error.value = getApiErrorMessage(err);
  } finally {
    actionLoading.value = false;
  }
};

onMounted(async () => {
  await refreshAll();
});
</script>

<template>
  <div class="space-y-5 p-6">
    <Transition name="fade">
      <div v-if="notice" class="fixed right-6 top-6 z-[100] rounded-lg bg-teal-600 px-4 py-2 text-sm font-semibold text-white shadow-xl">
        {{ notice }}
      </div>
    </Transition>

    <div class="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
      <div>
        <h1 class="text-2xl font-bold tracking-tight text-gray-900 dark:text-white">Проверка main-image</h1>
        <p class="mt-1 max-w-3xl text-sm text-gray-500 dark:text-slate-400">
          Кандидаты в статусе ожидания или отклонения не меняют публичную витрину. Замена `main_image` происходит только после явного одобрения.
        </p>
      </div>

      <div class="flex flex-wrap items-end gap-2">
        <label class="field-label w-24">
          Лимит
          <input v-model.number="batchLimit" min="1" max="50" type="number" class="field-input h-9 py-1.5 text-sm" />
        </label>
        <label class="field-label w-32">
          Процессор
          <input v-model="processorMethod" type="text" class="field-input h-9 py-1.5 text-sm" />
        </label>
        <button
          type="button"
          class="btn-mini h-9"
          :disabled="creating"
          @click="createBatch"
        >
          <Loader2 v-if="creating" class="h-4 w-4 animate-spin" />
          <Plus v-else class="h-4 w-4" />
          Пачка 50
        </button>
        <button type="button" class="btn-mini-outline h-9" :disabled="loadingBatches || loadingItems" @click="refreshAll">
          <RefreshCw class="h-4 w-4" :class="{ 'animate-spin': loadingBatches || loadingItems }" />
          Обновить
        </button>
      </div>
    </div>

    <div v-if="error" class="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-900/40 dark:bg-red-900/20 dark:text-red-300">
      {{ error }}
    </div>

    <div class="grid gap-4 xl:grid-cols-[320px_minmax(0,1fr)]">
      <section class="rounded-lg border border-gray-200 bg-white dark:border-slate-700 dark:bg-slate-800/70">
        <div class="border-b border-gray-100 p-3 dark:border-slate-700">
          <div class="flex items-center justify-between">
            <h2 class="text-sm font-semibold text-gray-900 dark:text-white">Пачки</h2>
            <span class="text-xs text-gray-500 dark:text-slate-400">{{ batches.length }}</span>
          </div>
        </div>

        <div v-if="loadingBatches" class="p-4 text-sm text-gray-500 dark:text-slate-400">Загрузка пачек...</div>
        <div v-else-if="batches.length === 0" class="p-4 text-sm text-gray-500 dark:text-slate-400">Пачек пока нет.</div>
        <div v-else class="max-h-[calc(100vh-240px)] overflow-y-auto p-2">
          <button
            v-for="batch in batches"
            :key="batch.id ?? `batch-${batch.created_at}`"
            type="button"
            class="mb-1 w-full rounded-lg border px-3 py-2 text-left text-sm transition-colors"
            :class="selectedBatchId === batch.id
              ? 'border-teal-300 bg-teal-50 text-teal-900 dark:border-teal-500/40 dark:bg-teal-500/10 dark:text-teal-100'
              : 'border-transparent text-gray-700 hover:bg-gray-50 dark:text-slate-300 dark:hover:bg-slate-700/50'"
            @click="selectBatch(batch.id)"
          >
            <div class="flex items-center justify-between gap-2">
              <span class="font-semibold">#{{ batch.id }}</span>
              <span class="rounded-full border px-2 py-0.5 text-[11px]" :class="statusClass(batch.status)">
                {{ statusLabel(batch.status) }}
              </span>
            </div>
            <div class="mt-1 text-xs text-gray-500 dark:text-slate-400">
              {{ batch.processor_method }} / {{ batch.processor_version || '—' }}
            </div>
            <div class="mt-1 flex justify-between text-xs text-gray-500 dark:text-slate-400">
              <span>Лимит {{ batch.requested_limit }}</span>
              <span>{{ formatDate(batch.created_at) }}</span>
            </div>
          </button>
        </div>
      </section>

      <section class="min-w-0 rounded-lg border border-gray-200 bg-white dark:border-slate-700 dark:bg-slate-800/70">
        <div class="border-b border-gray-100 p-3 dark:border-slate-700">
          <div class="flex flex-col gap-3 2xl:flex-row 2xl:items-center 2xl:justify-between">
            <div>
              <div class="text-sm font-semibold text-gray-900 dark:text-white">
                {{ selectedBatch ? `Пачка #${selectedBatch.id}` : 'Все позиции' }}
              </div>
              <div class="text-xs text-gray-500 dark:text-slate-400">
                Сначала показаны ошибки, пропуски и низкая уверенность.
              </div>
            </div>

            <div class="flex flex-wrap gap-2">
              <button
                v-for="filter in filters"
                :key="filter.value"
                type="button"
                class="rounded-lg border px-2.5 py-1.5 text-xs font-semibold"
                :class="statusFilter === filter.value
                  ? 'border-teal-300 bg-teal-50 text-teal-700 dark:border-teal-500/40 dark:bg-teal-500/10 dark:text-teal-300'
                  : 'border-gray-200 text-gray-600 hover:bg-gray-50 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-700/50'"
                @click="statusFilter = filter.value"
              >
                {{ filter.label }} · {{ filter.count }}
              </button>
            </div>
          </div>

          <div class="mt-3 flex flex-col gap-2 xl:flex-row xl:items-center xl:justify-between">
            <div class="flex flex-wrap items-center gap-2 text-xs text-gray-500 dark:text-slate-400">
              <button type="button" class="btn-mini-outline h-8" :disabled="displayedItems.length === 0" @click="toggleVisible">
                {{ allVisibleActionableSelected ? 'Снять выбор' : 'Выбрать готовые' }}
              </button>
              <span>Выбрано: {{ selectedActionableIds.length }}</span>
              <span class="inline-flex items-center gap-1 text-amber-700 dark:text-amber-300">
                <AlertTriangle class="h-3.5 w-3.5" />
                Approve меняет витрину, reject не меняет.
              </span>
            </div>

            <div class="flex flex-col gap-2 sm:flex-row sm:items-center">
              <input
                v-model="rejectReason"
                type="text"
                class="field-input h-9 min-w-0 py-1.5 text-sm sm:w-72"
                placeholder="Причина отклонения"
              />
              <button type="button" class="btn-mini-outline h-9 text-red-700" :disabled="actionLoading || selectedActionableIds.length === 0" @click="rejectSelected">
                <X class="h-4 w-4" />
                Отклонить
              </button>
              <button type="button" class="btn-mini h-9" :disabled="actionLoading || selectedActionableIds.length === 0" @click="approveSelected">
                <Loader2 v-if="actionLoading" class="h-4 w-4 animate-spin" />
                <Check v-else class="h-4 w-4" />
                Одобрить
              </button>
            </div>
          </div>
        </div>

        <div v-if="loadingItems" class="p-6 text-sm text-gray-500 dark:text-slate-400">Загрузка позиций...</div>
        <div v-else-if="displayedItems.length === 0" class="p-6 text-sm text-gray-500 dark:text-slate-400">Нет позиций для выбранного фильтра.</div>
        <div v-else class="overflow-x-auto">
          <table class="min-w-[1180px] w-full text-sm">
            <thead>
              <tr class="border-b border-gray-100 text-left text-xs font-semibold uppercase text-gray-500 dark:border-slate-700 dark:text-slate-400">
                <th class="w-10 px-3 py-2"></th>
                <th class="px-3 py-2">Товар</th>
                <th class="px-3 py-2">Статус</th>
                <th class="px-3 py-2">Текущая / исходная</th>
                <th class="px-3 py-2">Кандидат</th>
                <th class="px-3 py-2">Процессор</th>
                <th class="px-3 py-2">Скоринг</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="item in displayedItems"
                :key="item.id || `${item.product_id}-${item.original_image_url}`"
                class="border-b border-gray-100 align-top hover:bg-gray-50/70 dark:border-slate-800 dark:hover:bg-slate-800"
              >
                <td class="px-3 py-3">
                  <input
                    type="checkbox"
                    class="h-4 w-4 rounded border-gray-300 text-teal-600"
                    :checked="Boolean(item.id && selectedIds.includes(item.id))"
                    :disabled="item.status !== 'candidate_ready'"
                    @change="toggleItem(item)"
                  />
                </td>
                <td class="max-w-[280px] px-3 py-3">
                  <div class="font-semibold text-gray-900 dark:text-white">{{ productTitle(item) }}</div>
                  <div v-if="productMeta(item)" class="mt-0.5 text-xs text-gray-500 dark:text-slate-400">{{ productMeta(item) }}</div>
                  <div class="mt-1 flex flex-wrap items-center gap-2 text-xs text-gray-500 dark:text-slate-400">
                    <span>ID {{ item.product_id }}</span>
                    <a v-if="productLink(item)" :href="productLink(item)" target="_blank" class="inline-flex items-center gap-1 text-teal-700 hover:text-teal-600 dark:text-teal-300">
                      карточка
                      <ExternalLink class="h-3 w-3" />
                    </a>
                  </div>
                </td>
                <td class="max-w-[230px] px-3 py-3">
                  <span class="inline-flex rounded-full border px-2 py-1 text-xs font-semibold" :class="statusClass(item.status)">
                    {{ statusLabel(item.status) }}
                  </span>
                  <div v-if="lowScore(item)" class="mt-2 text-xs font-semibold text-amber-700 dark:text-amber-300">Низкая уверенность</div>
                  <div v-if="reasonText(item)" class="mt-2 break-words text-xs text-gray-500 dark:text-slate-400">{{ reasonText(item) }}</div>
                </td>
                <td class="px-3 py-3">
                  <div class="flex gap-2">
                    <div class="image-frame">
                      <img v-if="imageUrl(item.product_current_main_image)" :src="imageUrl(item.product_current_main_image)" alt="" />
                      <span v-else>нет</span>
                    </div>
                    <div class="image-frame">
                      <img v-if="imageUrl(item.original_image_url)" :src="imageUrl(item.original_image_url)" alt="" />
                      <span v-else>нет</span>
                    </div>
                  </div>
                  <div class="mt-1 text-[11px] text-gray-400">слева текущая, справа исходная</div>
                </td>
                <td class="px-3 py-3">
                  <div class="image-frame checkerboard">
                    <img v-if="imageUrl(item.candidate_image_url)" :src="imageUrl(item.candidate_image_url)" alt="" />
                    <span v-else>нет</span>
                  </div>
                  <div v-if="item.candidate_width || item.candidate_height" class="mt-1 text-[11px] text-gray-400">
                    {{ item.candidate_width || '—' }}×{{ item.candidate_height || '—' }}
                  </div>
                </td>
                <td class="max-w-[180px] px-3 py-3 text-xs text-gray-600 dark:text-slate-300">
                  <div class="font-semibold">{{ item.processor_method || '—' }}</div>
                  <div class="mt-1 break-words text-gray-500 dark:text-slate-400">{{ item.processor_version || '—' }}</div>
                  <div v-if="item.candidate_storage_provider" class="mt-1 text-gray-400">{{ item.candidate_storage_provider }}</div>
                </td>
                <td class="px-3 py-3 text-xs text-gray-600 dark:text-slate-300">
                  <div>Confidence: <span class="font-semibold">{{ formatScore(item.confidence_score) }}</span></div>
                  <div class="mt-1">Quality: <span class="font-semibold">{{ formatScore(item.quality_score) }}</span></div>
                  <div class="mt-2 text-gray-400">Обновлено {{ formatDate(item.updated_at) }}</div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
    </div>
  </div>
</template>

<style scoped>
.image-frame {
  display: flex;
  width: 88px;
  height: 70px;
  flex: 0 0 auto;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  border: 1px solid rgb(226 232 240);
  border-radius: 8px;
  background: rgb(248 250 252);
  color: rgb(148 163 184);
  font-size: 12px;
}

.image-frame img {
  width: 100%;
  height: 100%;
  object-fit: contain;
}

.checkerboard {
  background-color: rgb(248 250 252);
  background-image:
    linear-gradient(45deg, rgb(226 232 240) 25%, transparent 25%),
    linear-gradient(-45deg, rgb(226 232 240) 25%, transparent 25%),
    linear-gradient(45deg, transparent 75%, rgb(226 232 240) 75%),
    linear-gradient(-45deg, transparent 75%, rgb(226 232 240) 75%);
  background-position: 0 0, 0 8px, 8px -8px, -8px 0;
  background-size: 16px 16px;
}

:global(.dark) .image-frame {
  border-color: rgb(51 65 85);
  background: rgb(15 23 42);
  color: rgb(100 116 139);
}

:global(.dark) .checkerboard {
  background-color: rgb(15 23 42);
  background-image:
    linear-gradient(45deg, rgb(51 65 85) 25%, transparent 25%),
    linear-gradient(-45deg, rgb(51 65 85) 25%, transparent 25%),
    linear-gradient(45deg, transparent 75%, rgb(51 65 85) 75%),
    linear-gradient(-45deg, transparent 75%, rgb(51 65 85) 75%);
}
</style>
