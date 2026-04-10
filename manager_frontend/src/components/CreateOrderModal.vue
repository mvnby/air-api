<script setup lang="ts">
import { ref } from 'vue';
import { api } from '../api';
import { getApiErrorMessage } from '../utils/api-errors';

const props = defineProps<{
  customerId: number;
  customerName: string;
}>();

const emit = defineEmits<{
  (e: 'close'): void;
  (e: 'created', orderId: number): void;
}>();

const requestText = ref('');
const loading = ref(false);
const error = ref('');

const handleCreate = async () => {
  const text = requestText.value.trim();
  if (!text) return;

  loading.value = true;
  error.value = '';

  try {
    const result = await api.createManagerOrder({
      customer_id: props.customerId,
      source: 'manager',
      request_text: text,
    });
    emit('created', result.id);
  } catch (e) {
    error.value = getApiErrorMessage(e);
  } finally {
    loading.value = false;
  }
};

const handleClose = () => {
  if (!loading.value) emit('close');
};
</script>

<template>
  <Teleport to="body">
    <Transition name="modal-fade">
      <div
        class="fixed inset-0 z-[80] flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm"
        @click.self="handleClose"
      >
        <div
          class="w-full max-w-md rounded-2xl bg-[#1e293b] border border-slate-700/60 shadow-2xl flex flex-col overflow-hidden"
          style="max-height: 90vh"
        >
          <!-- Header -->
          <div class="flex items-center justify-between px-6 py-4 border-b border-slate-700/50">
            <div class="flex items-center gap-3">
              <span class="material-icons-round text-teal-400 text-2xl">add_shopping_cart</span>
              <div>
                <h2 class="text-lg font-bold text-white">Новый заказ</h2>
                <p class="text-xs text-slate-400 mt-0.5">{{ customerName }}</p>
              </div>
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
          <div class="px-6 py-5 space-y-4">
            <div>
              <label class="block text-sm font-medium text-slate-300 mb-2">
                Описание запроса
                <span class="text-slate-500 font-normal ml-1">— что нужно клиенту</span>
              </label>
              <textarea
                v-model="requestText"
                :disabled="loading"
                rows="4"
                placeholder="Кондиционер в комнату 25 м², монтаж с закладкой трассы..."
                class="w-full rounded-xl border border-slate-600 bg-slate-900 text-slate-100 placeholder-slate-600 text-sm px-4 py-3 resize-none outline-none focus:ring-2 focus:ring-teal-500 focus:border-transparent transition-all disabled:opacity-50"
                @keydown.meta.enter="handleCreate"
                @keydown.ctrl.enter="handleCreate"
              />
            </div>

            <p class="text-xs text-slate-500">
              Заказ будет создан в статусе <span class="text-teal-400 font-medium">Переговоры</span>
            </p>

            <!-- Error -->
            <div v-if="error" class="rounded-xl border border-red-500/40 bg-red-900/20 px-4 py-3 text-sm text-red-300">
              {{ error }}
            </div>
          </div>

          <!-- Footer -->
          <div class="px-6 py-4 border-t border-slate-700/50 flex justify-end gap-3">
            <button
              @click="handleClose"
              :disabled="loading"
              class="px-4 py-2 rounded-lg text-sm text-slate-300 hover:text-white hover:bg-slate-700 transition-colors disabled:opacity-40"
            >
              Отмена
            </button>
            <button
              @click="handleCreate"
              :disabled="loading || !requestText.trim()"
              class="flex items-center gap-2 px-5 py-2 rounded-lg text-sm font-semibold bg-teal-600 hover:bg-teal-500 text-white transition-colors disabled:opacity-50 disabled:cursor-not-allowed shadow-lg shadow-teal-900/30"
            >
              <span
                v-if="loading"
                class="w-4 h-4 rounded-full border-2 border-white/30 border-t-white animate-spin"
              />
              <span class="material-icons-round text-base" v-else>add</span>
              {{ loading ? 'Создаём...' : 'Создать заказ' }}
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
</style>
