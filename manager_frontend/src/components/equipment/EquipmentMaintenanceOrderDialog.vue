<script setup lang="ts">
import { computed, ref } from 'vue';
import { LoaderCircle, Wrench, X } from 'lucide-vue-next';
import { equipmentLocation, equipmentTitle } from './registry';
import type { EquipmentRegistryItem } from './types';
import { useDialogA11y } from './useDialogA11y';

const props = defineProps<{
  equipment: EquipmentRegistryItem;
  loading: boolean;
  error: string;
}>();

const emit = defineEmits<{
  close: [];
  confirm: [];
}>();

const confirmButton = ref<HTMLButtonElement | null>(null);
const dialogRef = ref<HTMLElement | null>(null);

const close = () => {
  if (!props.loading) emit('close');
};

useDialogA11y({
  open: computed(() => true),
  dialogRef,
  initialFocusRef: confirmButton,
  close,
});
</script>

<template>
  <Teleport to="body">
    <div
      class="fixed inset-0 z-[120] flex items-end justify-center bg-black/50 p-0 sm:items-center sm:p-4"
      @click.self="close"
    >
      <section
        ref="dialogRef"
        role="dialog"
        aria-modal="true"
        aria-labelledby="maintenance-order-title"
        aria-describedby="maintenance-order-description"
        tabindex="-1"
        class="w-full max-w-md rounded-t-lg border border-gray-200 bg-white shadow-2xl sm:rounded-lg dark:border-slate-700 dark:bg-slate-800"
      >
        <header class="flex items-center justify-between gap-3 border-b border-gray-200 px-4 py-3 dark:border-slate-700">
          <div class="flex min-w-0 items-center gap-2.5">
            <span class="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-teal-50 text-teal-700 dark:bg-teal-500/10 dark:text-teal-300">
              <Wrench class="h-4 w-4" />
            </span>
            <h2 id="maintenance-order-title" class="truncate text-base font-semibold text-gray-950 dark:text-white">
              Создать заказ на ТО
            </h2>
          </div>
          <button
            type="button"
            class="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-gray-400 transition hover:bg-gray-100 hover:text-gray-700 disabled:opacity-50 dark:text-slate-500 dark:hover:bg-slate-700 dark:hover:text-white"
            :disabled="loading"
            title="Закрыть"
            aria-label="Закрыть"
            @click="close"
          >
            <X class="h-4 w-4" />
          </button>
        </header>

        <form @submit.prevent="emit('confirm')">
          <div class="px-4 py-4">
            <p id="maintenance-order-description" class="text-sm leading-6 text-gray-600 dark:text-slate-300">
              Будет создан новый заказ на плановое техническое обслуживание.
            </p>

            <dl class="mt-4 divide-y divide-gray-200 border-y border-gray-200 text-sm dark:divide-slate-700 dark:border-slate-700">
              <div class="grid grid-cols-[100px,minmax(0,1fr)] gap-3 py-2.5">
                <dt class="text-gray-500 dark:text-slate-400">Оборудование</dt>
                <dd class="break-words font-semibold text-gray-900 dark:text-slate-100">{{ equipmentTitle(equipment) }}</dd>
              </div>
              <div class="grid grid-cols-[100px,minmax(0,1fr)] gap-3 py-2.5">
                <dt class="text-gray-500 dark:text-slate-400">Клиент</dt>
                <dd class="break-words font-semibold text-gray-900 dark:text-slate-100">
                  {{ equipment.customer_name || `Клиент #${equipment.customer_id}` }}
                </dd>
              </div>
              <div v-if="equipmentLocation(equipment)" class="grid grid-cols-[100px,minmax(0,1fr)] gap-3 py-2.5">
                <dt class="text-gray-500 dark:text-slate-400">Объект</dt>
                <dd class="break-words font-semibold text-gray-900 dark:text-slate-100">{{ equipmentLocation(equipment) }}</dd>
              </div>
            </dl>

            <div
              v-if="error"
              class="mt-4 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm font-medium text-red-700 dark:border-red-500/40 dark:bg-red-500/10 dark:text-red-300"
            >
              {{ error }}
            </div>
          </div>

          <footer class="flex items-center justify-end gap-2 border-t border-gray-200 px-4 py-3 dark:border-slate-700">
            <button
              type="button"
              class="min-h-9 rounded-md border border-gray-200 bg-white px-3 text-sm font-semibold text-gray-700 transition hover:bg-gray-50 disabled:opacity-50 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-200 dark:hover:bg-slate-700"
              :disabled="loading"
              @click="close"
            >
              Отмена
            </button>
            <button
              ref="confirmButton"
              type="submit"
              class="inline-flex min-h-9 items-center justify-center gap-2 rounded-md bg-teal-600 px-3 text-sm font-semibold text-white transition hover:bg-teal-700 disabled:cursor-wait disabled:opacity-70"
              :disabled="loading"
            >
              <LoaderCircle v-if="loading" class="h-4 w-4 animate-spin" />
              <Wrench v-else class="h-4 w-4" />
              {{ loading ? 'Создание...' : 'Создать заказ на ТО' }}
            </button>
          </footer>
        </form>
      </section>
    </div>
  </Teleport>
</template>
