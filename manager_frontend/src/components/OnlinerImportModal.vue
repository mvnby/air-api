<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue';
import { api, type CatalogImportJobStatusResponse, type MdvCatalogPreviewResponse } from '../api';
import { getApiErrorMessage } from '../utils/api-errors';

const emit = defineEmits<{
  (e: 'close'): void;
  (e: 'imported', successCount: number): void;
}>();

const urlsText = ref('');
const withRelated = ref(false);
const updateExisting = ref(false);
const loading = ref(false);
const result = ref<{ success_count: number; error_count: number; errors: string[] } | null>(null);
const importError = ref('');
const importJobId = ref('');
const importProgress = ref<CatalogImportJobStatusResponse | null>(null);
const mdvPreview = ref<MdvCatalogPreviewResponse | null>(null);
const mdvLoading = ref(false);
const mdvError = ref('');
let pollTimer: ReturnType<typeof window.setInterval> | null = null;

type MdvCatalogKey = 'household' | 'semi' | 'multi';

const mdvCatalogOptions: Array<{ key: MdvCatalogKey; label: string; short: string }> = [
  { key: 'household', label: 'Бытовые', short: 'Дом' },
  { key: 'semi', label: 'Полупром', short: 'Полупром' },
  { key: 'multi', label: 'Мультисплит', short: 'Мульти' },
];
const mdvReplaceOptions: Array<'semi' | 'multi'> = ['semi', 'multi'];

const mdvCatalogSelection = ref<Record<MdvCatalogKey, boolean>>({
  household: true,
  semi: true,
  multi: true,
});
const mdvReplaceLegacySelection = ref<Record<'semi' | 'multi', boolean>>({
  semi: false,
  multi: false,
});

const importPresets = [
  {
    id: 'energolux-severcon',
    label: 'Energolux',
    source: 'Severcon',
    url: 'https://www.severcon.ru/bitrix/catalog_export/yandex_187449.php',
    withRelated: false,
    updateExisting: true,
  },
];

const parsedUrls = () =>
  urlsText.value
    .split('\n')
    .map((u) => u.trim())
    .filter(Boolean);

const selectedMdvCatalogs = computed(() =>
  mdvCatalogOptions
    .filter((item) => mdvCatalogSelection.value[item.key])
    .map((item) => item.key)
);

const selectedMdvReplaceCatalogs = computed(() =>
  (['semi', 'multi'] as const).filter((key) => mdvReplaceLegacySelection.value[key])
);

const mdvCatalogLabel = (key: string) =>
  mdvCatalogOptions.find((item) => item.key === key)?.label || key;

const progressPercent = computed(() => {
  const progress = importProgress.value;
  if (!progress?.total) return 0;
  return Math.min(100, Math.round(((progress.processed ?? 0) / progress.total) * 100));
});

const stageLabel = computed(() => {
  const stage = importProgress.value?.stage;
  if (stage === 'expanding') return 'Ищем товары';
  if (stage === 'expanded') return 'Список найден';
  if (stage === 'importing') return 'Импортируем';
  if (stage === 'completed') return 'Готово';
  if (stage === 'failed') return 'Ошибка';
  return 'В очереди';
});

const isImportFinished = (status?: string) => status === 'success' || status === 'failed';

const stopPolling = () => {
  if (pollTimer !== null) {
    window.clearInterval(pollTimer);
    pollTimer = null;
  }
};

const applyImportStatus = (status: CatalogImportJobStatusResponse) => {
  importProgress.value = status;
  importJobId.value = status.job_id;
  loading.value = !isImportFinished(status.status);

  if (status.status === 'success') {
    result.value = {
      success_count: status.success_count ?? 0,
      error_count: status.error_count ?? 0,
      errors: status.errors ?? [],
    };
  } else if (status.status === 'failed') {
    importError.value = status.error || 'Импорт завершился с ошибкой';
  }
};

const startPolling = () => {
  stopPolling();
  pollTimer = window.setInterval(() => {
    void refreshImportStatus();
  }, 1500);
};

const refreshImportStatus = async () => {
  if (!importJobId.value) return;

  try {
    const status = await api.getImportProductsJobStatus(importJobId.value);
    applyImportStatus(status);

    if (isImportFinished(status.status)) {
      stopPolling();
      if (status.status === 'success' && (status.success_count ?? 0) > 0) {
        emit('imported', status.success_count ?? 0);
      }
    }
  } catch (e) {
    stopPolling();
    loading.value = false;
    importError.value = getApiErrorMessage(e);
  }
};

const handleImport = async () => {
  const urls = parsedUrls();
  if (urls.length === 0) return;

  loading.value = true;
  result.value = null;
  importError.value = '';
  importJobId.value = '';
  importProgress.value = null;
  stopPolling();

  try {
    const job = await api.startImportProductsJob(urls, withRelated.value, updateExisting.value);
    importJobId.value = job.job_id;
    startPolling();
    await refreshImportStatus();
  } catch (e) {
    importError.value = getApiErrorMessage(e);
    loading.value = false;
  }
};

const handleMdvPreview = async () => {
  if (selectedMdvCatalogs.value.length === 0) return;
  mdvLoading.value = true;
  mdvError.value = '';
  mdvPreview.value = null;
  try {
    mdvPreview.value = await api.previewMdvCatalogImport({
      catalogs: selectedMdvCatalogs.value,
      sample_limit: 20,
      replace_legacy_catalogs: selectedMdvReplaceCatalogs.value,
    });
  } catch (e) {
    mdvError.value = getApiErrorMessage(e);
  } finally {
    mdvLoading.value = false;
  }
};

const handleMdvImport = async () => {
  if (selectedMdvCatalogs.value.length === 0) return;
  loading.value = true;
  result.value = null;
  importError.value = '';
  mdvError.value = '';
  importJobId.value = '';
  importProgress.value = null;
  stopPolling();

  try {
    const job = await api.startMdvCatalogImportJob({
      catalogs: selectedMdvCatalogs.value,
      update_existing: true,
      replace_legacy_catalogs: selectedMdvReplaceCatalogs.value,
    });
    importJobId.value = job.job_id;
    startPolling();
    await refreshImportStatus();
  } catch (e) {
    mdvError.value = getApiErrorMessage(e);
    loading.value = false;
  }
};

const applyImportPreset = (preset: (typeof importPresets)[number]) => {
  if (loading.value) return;
  urlsText.value = preset.url;
  withRelated.value = preset.withRelated;
  updateExisting.value = preset.updateExisting;
  result.value = null;
  importError.value = '';
  mdvError.value = '';
};

const handleClose = () => {
  emit('close');
};

const restoreCurrentImportJob = async () => {
  try {
    const status = await api.getCurrentImportProductsJobStatus();
    applyImportStatus(status);
    if (!isImportFinished(status.status)) {
      startPolling();
    }
  } catch {
    // No import job has been started in this app process.
  }
};

onMounted(() => {
  void restoreCurrentImportJob();
});
onBeforeUnmount(stopPolling);
</script>

<template>
  <!-- Backdrop -->
  <Teleport to="body">
    <Transition name="modal-fade">
      <div
        class="fixed inset-0 z-[80] flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm"
        @click.self="handleClose"
      >
        <div
          class="w-full max-w-2xl rounded-2xl bg-[#1e293b] border border-slate-700/60 shadow-2xl flex flex-col overflow-hidden"
          style="max-height: 90vh"
        >
          <!-- Header -->
          <div class="flex items-center justify-between px-6 py-4 border-b border-slate-700/50">
            <div class="flex items-center gap-3">
              <span class="material-icons-round text-teal-400 text-2xl">cloud_download</span>
              <h2 class="text-lg font-bold text-white">Импорт товаров</h2>
            </div>
            <button
              @click="handleClose"
              class="text-slate-400 hover:text-white transition-colors"
            >
              <span class="material-icons-round text-xl">close</span>
            </button>
          </div>

          <!-- Body -->
          <div class="px-6 py-5 space-y-5 overflow-y-auto">
            <div>
              <p class="block text-sm font-medium text-slate-300 mb-2">Готовые источники</p>
              <div class="grid grid-cols-1 sm:grid-cols-2 gap-2">
                <button
                  v-for="preset in importPresets"
                  :key="preset.id"
                  type="button"
                  :disabled="loading"
                  @click="applyImportPreset(preset)"
                  class="flex items-center justify-between gap-3 rounded-xl border border-slate-700 bg-slate-800/60 px-4 py-3 text-left transition-colors hover:border-teal-500/60 hover:bg-slate-800 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  <span>
                    <span class="block text-sm font-semibold text-slate-100">{{ preset.label }}</span>
                    <span class="block text-xs text-slate-500 mt-0.5">{{ preset.source }}</span>
                  </span>
                  <span class="material-icons-round text-teal-400 text-xl">sync</span>
                </button>
              </div>
            </div>

            <section class="rounded-xl border border-teal-500/30 bg-teal-950/20 p-4 space-y-4">
              <div class="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3">
                <div>
                  <p class="text-sm font-semibold text-teal-100">MDV официальный каталог</p>
                  <p class="text-xs text-teal-200/70 mt-0.5">JSON, галерея, инструкции, нормализация характеристик</p>
                </div>
                <div class="flex items-center gap-2">
                  <button
                    type="button"
                    :disabled="loading || mdvLoading || selectedMdvCatalogs.length === 0"
                    @click="handleMdvPreview"
                    class="inline-flex items-center gap-1.5 rounded-lg border border-teal-400/50 px-3 py-2 text-xs font-semibold text-teal-100 hover:bg-teal-500/15 disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    <span
                      v-if="mdvLoading"
                      class="h-3.5 w-3.5 rounded-full border-2 border-teal-100/30 border-t-teal-100 animate-spin"
                    />
                    <span v-else class="material-icons-round text-base">fact_check</span>
                    Проверить
                  </button>
                  <button
                    type="button"
                    :disabled="loading || mdvLoading || selectedMdvCatalogs.length === 0"
                    @click="handleMdvImport"
                    class="inline-flex items-center gap-1.5 rounded-lg bg-teal-600 px-3 py-2 text-xs font-semibold text-white hover:bg-teal-500 disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    <span class="material-icons-round text-base">sync</span>
                    Импорт
                  </button>
                </div>
              </div>

              <div class="grid grid-cols-3 gap-2">
                <button
                  v-for="item in mdvCatalogOptions"
                  :key="item.key"
                  type="button"
                  :disabled="loading || mdvLoading"
                  @click="mdvCatalogSelection[item.key] = !mdvCatalogSelection[item.key]"
                  class="rounded-lg border px-3 py-2 text-left transition-colors disabled:opacity-50"
                  :class="mdvCatalogSelection[item.key]
                    ? 'border-teal-400/70 bg-teal-500/20 text-teal-50'
                    : 'border-slate-700 bg-slate-900/60 text-slate-400'"
                >
                  <span class="block text-xs font-semibold">{{ item.short }}</span>
                  <span class="mt-0.5 block text-[11px] opacity-70">{{ item.label }}</span>
                </button>
              </div>

              <div class="rounded-lg border border-slate-700 bg-slate-900/50 p-3">
                <p class="text-[11px] font-semibold uppercase tracking-wide text-slate-500">Legacy-замена</p>
                <div class="mt-2 grid grid-cols-2 gap-2">
                  <label
                    v-for="key in mdvReplaceOptions"
                    :key="key"
                    class="flex items-center gap-2 rounded-lg border border-slate-700 bg-slate-950/30 px-3 py-2 text-xs text-slate-300"
                    :class="{ 'opacity-50': !mdvCatalogSelection[key] }"
                  >
                    <input
                      v-model="mdvReplaceLegacySelection[key]"
                      :disabled="loading || mdvLoading || !mdvCatalogSelection[key]"
                      type="checkbox"
                      class="h-4 w-4 rounded border-slate-600 bg-slate-900 text-teal-500 focus:ring-teal-500"
                    />
                    <span>{{ mdvCatalogLabel(key) }}</span>
                  </label>
                </div>
              </div>

              <div
                v-if="mdvPreview"
                class="rounded-xl border border-slate-700 bg-slate-950/50 p-3 text-xs text-slate-300 space-y-3"
              >
                <div class="grid grid-cols-2 sm:grid-cols-4 gap-2">
                  <div class="rounded-lg bg-slate-900 px-3 py-2">
                    <p class="text-slate-500">Всего</p>
                    <p class="mt-0.5 text-base font-bold text-slate-100 tabular-nums">{{ mdvPreview.total }}</p>
                  </div>
                  <div class="rounded-lg bg-slate-900 px-3 py-2">
                    <p class="text-slate-500">Создать</p>
                    <p class="mt-0.5 text-base font-bold text-emerald-300 tabular-nums">{{ mdvPreview.actions?.create || 0 }}</p>
                  </div>
                  <div class="rounded-lg bg-slate-900 px-3 py-2">
                    <p class="text-slate-500">Обновить</p>
                    <p class="mt-0.5 text-base font-bold text-sky-300 tabular-nums">{{ mdvPreview.actions?.update || 0 }}</p>
                  </div>
                  <div class="rounded-lg bg-slate-900 px-3 py-2">
                    <p class="text-slate-500">Без URL</p>
                    <p class="mt-0.5 text-base font-bold text-amber-300 tabular-nums">{{ mdvPreview.unmatched_source_urls || 0 }}</p>
                  </div>
                </div>

                <div class="flex flex-wrap gap-2">
                  <span
                    v-for="(count, key) in mdvPreview.by_catalog"
                    :key="key"
                    class="rounded-full bg-slate-900 px-2.5 py-1 text-slate-300"
                  >
                    {{ mdvCatalogLabel(String(key)) }}: {{ count }}
                  </span>
                </div>

                <div
                  v-if="mdvPreview.legacy_replace?.enabled"
                  class="rounded-lg border border-amber-500/30 bg-amber-950/20 px-3 py-2 text-amber-100"
                >
                  Legacy: удалить {{ mdvPreview.legacy_replace.deletable_count }},
                  оставить для обновления {{ mdvPreview.legacy_replace.keep_for_update_count }}.
                </div>

                <div v-if="mdvPreview.top_unpromoted_spec_keys?.length" class="rounded-lg bg-slate-900 px-3 py-2">
                  <p class="font-semibold text-slate-200">Новые сырые ключи</p>
                  <p class="mt-1 text-slate-400">
                    {{ mdvPreview.top_unpromoted_spec_keys.slice(0, 8).map((item) => `${item.key} (${item.count})`).join(', ') }}
                  </p>
                </div>
              </div>

              <div v-if="mdvError" class="rounded-lg border border-red-500/40 bg-red-900/20 px-3 py-2 text-xs text-red-300">
                {{ mdvError }}
              </div>
            </section>

            <!-- URL textarea -->
            <div>
              <label class="block text-sm font-medium text-slate-300 mb-2">
                Ссылки на товары
                <span class="text-slate-500 font-normal ml-1">— по одной в строке</span>
              </label>
              <textarea
                v-model="urlsText"
                :disabled="loading"
                rows="7"
                placeholder="https://www.severcon.ru/bitrix/catalog_export/yandex_187449.php&#10;https://catalog.onliner.by/split_systems/midea/msmb-09hrn8-wifib&#10;https://aircond.by/split-sistemy/mdv-integra-pro-inverter-..."
                class="w-full rounded-xl border border-slate-600 bg-slate-900 text-slate-100 placeholder-slate-600 text-sm px-4 py-3 resize-none outline-none focus:ring-2 focus:ring-teal-500 focus:border-transparent transition-all disabled:opacity-50"
              />
              <p class="text-xs text-slate-500 mt-1.5">
                Найдено ссылок: <span class="text-teal-400 font-medium">{{ parsedUrls().length }}</span>
              </p>
            </div>

            <!-- Related toggle -->
            <label
              class="flex items-center justify-between gap-4 rounded-xl border border-slate-700 bg-slate-800/60 px-4 py-3 cursor-pointer select-none"
              :class="{ 'opacity-50 pointer-events-none': loading }"
            >
              <div>
                <p class="text-sm font-medium text-slate-200">Спарсить связанные</p>
                <p class="text-xs text-slate-500 mt-0.5">
                  Серии/модификации для Aircond.by, Onliner и LG24
                </p>
              </div>
              <!-- Toggle switch -->
              <div
                class="relative flex-shrink-0 w-11 h-6 rounded-full transition-colors duration-200"
                :class="withRelated ? 'bg-teal-500' : 'bg-slate-600'"
                @click="withRelated = !withRelated"
              >
                <div
                  class="absolute top-0.5 left-0.5 w-5 h-5 bg-white rounded-full shadow transition-transform duration-200"
                  :class="withRelated ? 'translate-x-5' : 'translate-x-0'"
                />
              </div>
            </label>

            <!-- Re-import existing toggle -->
            <label
              class="flex items-center justify-between gap-4 rounded-xl border border-slate-700 bg-slate-800/60 px-4 py-3 cursor-pointer select-none"
              :class="{ 'opacity-50 pointer-events-none': loading }"
            >
              <div>
                <p class="text-sm font-medium text-slate-200">Обновлять существующие товары</p>
                <p class="text-xs text-slate-500 mt-0.5">
                  Если товар уже есть, обновим цену и характеристики, фото не перезаписываем
                </p>
              </div>
              <div
                class="relative flex-shrink-0 w-11 h-6 rounded-full transition-colors duration-200"
                :class="updateExisting ? 'bg-teal-500' : 'bg-slate-600'"
                @click="updateExisting = !updateExisting"
              >
                <div
                  class="absolute top-0.5 left-0.5 w-5 h-5 bg-white rounded-full shadow transition-transform duration-200"
                  :class="updateExisting ? 'translate-x-5' : 'translate-x-0'"
                />
              </div>
            </label>

            <!-- Progress -->
            <div
              v-if="loading || importProgress"
              class="rounded-xl border border-slate-700 bg-slate-900/70 px-4 py-4 text-sm text-slate-200 space-y-3"
            >
              <div class="flex items-center justify-between gap-3">
                <div>
                  <p class="font-semibold text-slate-100">{{ stageLabel }}</p>
                  <p v-if="loading" class="text-xs text-teal-300 mt-0.5">
                    Идёт в фоне, окно можно закрыть и открыть позже
                  </p>
                  <p v-if="importProgress?.current_title" class="text-xs text-slate-400 mt-0.5">
                    {{ importProgress.current_title }}
                  </p>
                  <p v-else-if="importProgress?.current_url" class="text-xs text-slate-400 mt-0.5 break-all">
                    {{ importProgress.current_url }}
                  </p>
                </div>
                <span class="tabular-nums text-lg font-bold text-teal-300">{{ progressPercent }}%</span>
              </div>

              <div class="h-2 overflow-hidden rounded-full bg-slate-800">
                <div
                  class="h-full rounded-full bg-teal-500 transition-all duration-500"
                  :style="{ width: `${progressPercent}%` }"
                />
              </div>

              <div class="grid grid-cols-2 sm:grid-cols-4 gap-2">
                <div class="rounded-lg bg-slate-800/70 px-3 py-2">
                  <p class="text-[11px] uppercase tracking-wide text-slate-500">Найдено</p>
                  <p class="mt-0.5 font-semibold text-slate-100 tabular-nums">{{ importProgress?.total || 0 }}</p>
                </div>
                <div class="rounded-lg bg-slate-800/70 px-3 py-2">
                  <p class="text-[11px] uppercase tracking-wide text-slate-500">Готово</p>
                  <p class="mt-0.5 font-semibold text-slate-100 tabular-nums">{{ importProgress?.processed || 0 }}</p>
                </div>
                <div class="rounded-lg bg-slate-800/70 px-3 py-2">
                  <p class="text-[11px] uppercase tracking-wide text-slate-500">Успешно</p>
                  <p class="mt-0.5 font-semibold text-emerald-300 tabular-nums">{{ importProgress?.success_count || 0 }}</p>
                </div>
                <div class="rounded-lg bg-slate-800/70 px-3 py-2">
                  <p class="text-[11px] uppercase tracking-wide text-slate-500">Ошибки</p>
                  <p class="mt-0.5 font-semibold text-amber-300 tabular-nums">{{ importProgress?.error_count || 0 }}</p>
                </div>
              </div>

              <ul v-if="importProgress?.errors?.length" class="space-y-1 text-xs text-amber-300">
                <li v-for="(err, i) in importProgress.errors?.slice(-3) || []" :key="i" class="break-words">
                  {{ err }}
                </li>
              </ul>
            </div>

            <!-- Result -->
            <div v-if="result" class="rounded-xl border px-4 py-3 text-sm space-y-1"
              :class="result.error_count === 0
                ? 'border-emerald-500/40 bg-emerald-900/20 text-emerald-300'
                : 'border-amber-500/40 bg-amber-900/20 text-amber-300'"
            >
              <p class="font-semibold">
                ✓ Успешно: {{ result.success_count }}
                <span v-if="result.error_count"> · ✗ Ошибок: {{ result.error_count }}</span>
              </p>
              <ul v-if="result.errors.length" class="mt-2 space-y-1 text-xs text-amber-400 list-disc list-inside">
                <li v-for="(err, i) in result.errors" :key="i">{{ err }}</li>
              </ul>
            </div>

            <!-- General error -->
            <div v-if="importError" class="rounded-xl border border-red-500/40 bg-red-900/20 px-4 py-3 text-sm text-red-300">
              {{ importError }}
            </div>
          </div>

          <!-- Footer -->
          <div class="px-6 py-4 border-t border-slate-700/50 flex justify-end gap-3">
            <button
              @click="handleClose"
              class="px-4 py-2 rounded-lg text-sm text-slate-300 hover:text-white hover:bg-slate-700 transition-colors"
            >
              {{ loading ? 'Скрыть' : 'Закрыть' }}
            </button>
            <button
              @click="handleImport"
              :disabled="loading || parsedUrls().length === 0"
              class="flex items-center gap-2 px-5 py-2 rounded-lg text-sm font-semibold bg-teal-600 hover:bg-teal-500 text-white transition-colors disabled:opacity-50 disabled:cursor-not-allowed shadow-lg shadow-teal-900/30"
            >
              <span
                v-if="loading"
                class="w-4 h-4 rounded-full border-2 border-white/30 border-t-white animate-spin"
              />
              <span class="material-icons-round text-base" v-else>upload</span>
              {{ loading ? 'Импортируем...' : 'Запустить импорт' }}
            </button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.modal-fade-enter-active,
.modal-fade-leave-active {
  transition: opacity 0.2s ease;
}
.modal-fade-enter-from,
.modal-fade-leave-to {
  opacity: 0;
}
.modal-fade-enter-active .w-full,
.modal-fade-leave-active .w-full {
  transition: transform 0.2s ease;
}
.modal-fade-enter-from .max-w-2xl {
  transform: scale(0.96) translateY(8px);
}
.modal-fade-leave-to .max-w-2xl {
  transform: scale(0.96) translateY(8px);
}
</style>
