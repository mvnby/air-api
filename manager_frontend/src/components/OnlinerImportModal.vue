<script setup lang="ts">
import { ref } from 'vue';
import { api } from '../api';
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

const parsedUrls = () =>
  urlsText.value
    .split('\n')
    .map((u) => u.trim())
    .filter(Boolean);

const handleImport = async () => {
  const urls = parsedUrls();
  if (urls.length === 0) return;

  loading.value = true;
  result.value = null;
  importError.value = '';

  try {
    const res = await api.importFromOnliner(urls, withRelated.value, updateExisting.value);
    result.value = res;
    if (res.success_count > 0) {
      emit('imported', res.success_count);
    }
  } catch (e) {
    importError.value = getApiErrorMessage(e);
  } finally {
    loading.value = false;
  }
};

const handleClose = () => {
  if (!loading.value) emit('close');
};
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
          class="w-full max-w-lg rounded-2xl bg-[#1e293b] border border-slate-700/60 shadow-2xl flex flex-col overflow-hidden"
          style="max-height: 90vh"
        >
          <!-- Header -->
          <div class="flex items-center justify-between px-6 py-4 border-b border-slate-700/50">
            <div class="flex items-center gap-3">
              <span class="material-icons-round text-teal-400 text-2xl">cloud_download</span>
              <h2 class="text-lg font-bold text-white">Импорт из Onliner</h2>
            </div>
            <button
              @click="handleClose"
              :disabled="loading"
              class="text-slate-400 hover:text-white transition-colors disabled:opacity-40"
            >
              <span class="material-icons-round text-xl">close</span>
            </button>
          </div>

          <!-- Body -->
          <div class="px-6 py-5 space-y-5 overflow-y-auto">
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
                placeholder="https://catalog.onliner.by/split_systems/midea/msmb-09hrn8-wifib&#10;https://catalog.onliner.by/split_systems/samsung/..."
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
                <p class="text-sm font-medium text-slate-200">Добавить сопутствующие модели</p>
                <p class="text-xs text-slate-500 mt-0.5">
                  Импортировать также связанные модели с каждой страницы
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
              :disabled="loading"
              class="px-4 py-2 rounded-lg text-sm text-slate-300 hover:text-white hover:bg-slate-700 transition-colors disabled:opacity-40"
            >
              Закрыть
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
.modal-fade-enter-from .max-w-lg {
  transform: scale(0.96) translateY(8px);
}
.modal-fade-leave-to .max-w-lg {
  transform: scale(0.96) translateY(8px);
}
</style>
