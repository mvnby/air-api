<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { api } from '../api';
import type {
  ManagerInstallationRateResponse,
  ManagerInstallationRateUpdatePayload,
} from '../client';
import { getApiErrorMessage } from '../utils/api-errors';

const props = defineProps<{
  modelValue: boolean;
  rate?: ManagerInstallationRateResponse | null;
}>();

const emit = defineEmits<{
  (event: 'update:modelValue', value: boolean): void;
  (event: 'success'): void;
}>();

const loading = ref(false);
const error = ref('');
type InstallationRateForm = {
  base_price: number;
  extra_pipe_price: number;
  included_pipe_meters: number;
  comment: string | null;
};

const formData = ref<InstallationRateForm>({
  base_price: 0,
  extra_pipe_price: 0,
  included_pipe_meters: 0,
  comment: null,
});

const isAutomatic = computed(() => props.rate?.selection_status === 'automatic_fixed');

const resetForm = () => {
  const rate = props.rate;
  formData.value = {
    base_price: rate?.base_price ?? 0,
    extra_pipe_price: rate?.extra_pipe_price ?? 0,
    included_pipe_meters: rate?.included_pipe_meters ?? 0,
    comment: rate?.comment ?? null,
  };
  error.value = '';
};

watch(
  () => props.modelValue,
  (value) => {
    if (value) resetForm();
  },
);

const close = () => {
  if (!loading.value) emit('update:modelValue', false);
};

const submit = async () => {
  if (!props.rate) return;
  if (formData.value.base_price < 0 || formData.value.extra_pipe_price < 0 || formData.value.included_pipe_meters < 0) {
    error.value = 'Цена и метры не могут быть отрицательными';
    return;
  }
  loading.value = true;
  error.value = '';
  try {
    const payload: ManagerInstallationRateUpdatePayload = { ...formData.value };
    await api.updateManagerInstallationRate(props.rate.id, payload);
    emit('success');
    close();
  } catch (e) {
    error.value = getApiErrorMessage(e);
  } finally {
    loading.value = false;
  }
};
</script>

<template>
  <Teleport to="body">
    <Transition name="modal-fade">
      <div
        v-if="modelValue && rate"
        class="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm"
      >
        <div class="modal-content flex w-full max-w-xl flex-col overflow-hidden rounded-xl border border-gray-200 bg-white shadow-xl dark:border-slate-700/60 dark:bg-[#1e293b]">
          <div class="flex items-center justify-between border-b border-gray-200 bg-gray-50 px-6 py-4 dark:border-slate-700/50 dark:bg-slate-800/50">
            <div>
              <h3 class="text-lg font-semibold text-gray-900 dark:text-white">{{ rate.title }}</h3>
              <p class="mt-0.5 text-xs text-gray-500 dark:text-slate-400">Публичная цена монтажа</p>
            </div>
            <button
              class="text-gray-400 transition-colors hover:text-gray-600 dark:text-slate-400 dark:hover:text-white"
              :disabled="loading"
              @click="close"
            >
              <span class="material-icons-round text-xl">close</span>
            </button>
          </div>

          <div class="max-h-[75vh] space-y-5 overflow-y-auto p-6">
            <div
              v-if="error"
              class="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-600 dark:border-red-500/50 dark:bg-red-900/30 dark:text-red-400"
            >
              {{ error }}
            </div>

            <div class="rounded-xl border border-teal-200 bg-teal-50 p-4 dark:border-teal-500/30 dark:bg-teal-500/10">
              <div class="text-xs font-medium uppercase tracking-wide text-teal-700 dark:text-teal-300">Связка с товаром</div>
              <div class="mt-2 flex items-center gap-2 text-sm text-gray-900 dark:text-slate-100">
                <span class="font-medium">{{ rate.equipment_label }}</span>
                <span class="material-icons-round text-base text-teal-500">arrow_forward</span>
                <span>{{ rate.title }}</span>
              </div>
              <div class="mt-2 text-xs text-teal-800/80 dark:text-teal-200/80">{{ rate.power_label }}</div>
            </div>

            <div
              class="rounded-lg border p-3 text-sm"
              :class="isAutomatic
                ? 'border-emerald-200 bg-emerald-50 text-emerald-800 dark:border-emerald-500/30 dark:bg-emerald-500/10 dark:text-emerald-200'
                : 'border-amber-200 bg-amber-50 text-amber-800 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-200'"
            >
              <div class="font-medium">{{ isAutomatic ? 'Фиксированный расчёт' : 'Цена «от»' }}</div>
              <div class="mt-1 text-xs opacity-80">{{ rate.selection_note }}</div>
            </div>

            <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <label class="block">
                <span class="mb-1 block text-sm font-medium text-gray-700 dark:text-slate-300">
                  {{ isAutomatic ? 'Цена монтажа (BYN)' : 'Цена на витрине «от» (BYN)' }}
                </span>
                <input
                  v-model.number="formData.base_price"
                  type="number"
                  min="0"
                  class="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-gray-900 dark:border-slate-600 dark:bg-slate-900 dark:text-slate-200"
                  :disabled="loading"
                />
              </label>

              <label class="block">
                <span class="mb-1 block text-sm font-medium text-gray-700 dark:text-slate-300">Включено трассы, м</span>
                <input
                  v-model.number="formData.included_pipe_meters"
                  type="number"
                  min="0"
                  class="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-gray-900 dark:border-slate-600 dark:bg-slate-900 dark:text-slate-200"
                  :disabled="loading"
                />
              </label>

              <label class="block sm:col-span-2">
                <span class="mb-1 block text-sm font-medium text-gray-700 dark:text-slate-300">Дополнительный метр трассы (BYN)</span>
                <input
                  v-model.number="formData.extra_pipe_price"
                  type="number"
                  min="0"
                  class="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-gray-900 dark:border-slate-600 dark:bg-slate-900 dark:text-slate-200"
                  :disabled="loading"
                />
              </label>
            </div>

            <label class="block">
              <span class="mb-1 block text-sm font-medium text-gray-700 dark:text-slate-300">Комментарий для покупателя</span>
              <textarea
                v-model="formData.comment"
                rows="3"
                class="w-full resize-none rounded-lg border border-gray-300 bg-white px-3 py-2 text-gray-900 dark:border-slate-600 dark:bg-slate-900 dark:text-slate-200"
                :disabled="loading"
              />
            </label>

            <div class="text-xs text-gray-500 dark:text-slate-400">
              Форм-фактор, диапазон мощности и режим расчёта здесь защищены от случайного изменения. Для их изменения нужна отдельная проверка логики публичного подбора.
            </div>
          </div>

          <div class="flex justify-end gap-3 border-t border-gray-200 bg-gray-50 px-6 py-4 dark:border-slate-700/50 dark:bg-slate-800/30">
            <button
              class="rounded-lg px-4 py-2 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-200 dark:text-slate-300 dark:hover:bg-slate-700"
              :disabled="loading"
              @click="close"
            >
              Отмена
            </button>
            <button
              class="flex items-center gap-2 rounded-lg bg-teal-600 px-4 py-2 text-sm font-medium text-white shadow-lg shadow-teal-900/30 transition-colors hover:bg-teal-500 disabled:opacity-50"
              :disabled="loading"
              @click="submit"
            >
              <span v-if="loading" class="material-icons-round animate-spin text-sm">refresh</span>
              <span v-else class="material-icons-round text-sm">save</span>
              Сохранить цену
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
.modal-fade-enter-active .modal-content,
.modal-fade-leave-active .modal-content {
  transition: transform 0.2s ease;
}
.modal-fade-enter-from .modal-content,
.modal-fade-leave-to .modal-content {
  transform: scale(0.96);
}
</style>
