<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue';
import { LoaderCircle, Plus, X } from 'lucide-vue-next';
import { useDialogA11y } from '../../composables/useDialogA11y';

const props = defineProps<{
  open: boolean;
  saving: boolean;
  error?: string;
}>();

const emit = defineEmits<{
  close: [];
  confirm: [payload: {
    displayName: string;
    brand: string;
    model: string;
    serial: string;
    installedAt: string;
    role: string;
    notes: string;
  }];
}>();

const form = reactive({
  displayName: '',
  brand: '',
  model: '',
  serial: '',
  installedAt: '',
  role: 'other',
  notes: '',
});
const dialogRef = ref<HTMLElement | null>(null);
const closeButtonRef = ref<HTMLElement | null>(null);

watch(() => props.open, (open) => {
  if (!open) return;
  Object.assign(form, {
    displayName: '',
    brand: '',
    model: '',
    serial: '',
    installedAt: '',
    role: 'other',
    notes: '',
  });
});

const canSubmit = () => Boolean(form.displayName.trim() || form.brand.trim() || form.model.trim() || form.serial.trim());

const close = () => {
  if (!props.saving) emit('close');
};

useDialogA11y({
  open: computed(() => props.open),
  dialogRef,
  initialFocusRef: closeButtonRef,
  close,
});
</script>

<template>
  <Teleport to="body">
    <div
      v-if="open"
      class="fixed inset-0 z-[130] flex items-end justify-center bg-black/50 sm:items-center sm:p-4"
      @click.self="close"
    >
      <section ref="dialogRef" class="max-h-[92vh] w-full max-w-xl overflow-y-auto rounded-t-lg border border-slate-200 bg-white shadow-2xl sm:rounded-lg dark:border-slate-700 dark:bg-slate-900" role="dialog" aria-modal="true" aria-labelledby="equipment-manual-dialog-title" tabindex="-1">
        <header class="sticky top-0 z-10 flex items-center justify-between gap-3 border-b border-slate-200 bg-white px-4 py-3 dark:border-slate-700 dark:bg-slate-900">
          <div class="flex min-w-0 items-center gap-2">
            <Plus class="h-5 w-5 shrink-0 text-teal-700 dark:text-teal-300" />
            <h2 id="equipment-manual-dialog-title" class="truncate text-base font-semibold text-slate-950 dark:text-white">Новое оборудование</h2>
          </div>
          <button ref="closeButtonRef" type="button" class="inline-flex h-8 w-8 items-center justify-center rounded-md text-slate-500 hover:bg-slate-100 disabled:opacity-50 dark:hover:bg-slate-800" :disabled="saving" aria-label="Закрыть" @click="close">
            <X class="h-4 w-4" />
          </button>
        </header>

        <form class="space-y-4 p-4" @submit.prevent="canSubmit() && emit('confirm', { ...form })">
          <p class="text-sm text-slate-600 dark:text-slate-300">
            Для старого или чужого кондиционера достаточно модели либо серийного номера. Каталожный товар не обязателен.
          </p>

          <div class="grid gap-3 sm:grid-cols-2">
            <label class="field-label sm:col-span-2">
              Название на объекте
              <input v-model="form.displayName" class="field-input" placeholder="Кондиционер в серверной" />
            </label>
            <label class="field-label">
              Бренд
              <input v-model="form.brand" class="field-input" placeholder="TCL, MDV, LG" />
            </label>
            <label class="field-label">
              Модель
              <input v-model="form.model" class="field-input" placeholder="TAC-09..." />
            </label>
            <label class="field-label">
              Серийный номер
              <input v-model="form.serial" class="field-input" placeholder="SN..." />
            </label>
            <label class="field-label">
              Дата установки
              <input v-model="form.installedAt" class="field-input" type="date" />
            </label>
            <label class="field-label sm:col-span-2">
              Роль в заказе
              <select v-model="form.role" class="field-input">
                <option value="installation">Монтаж</option>
                <option value="maintenance">Обслуживание</option>
                <option value="repair">Ремонт</option>
                <option value="diagnostic">Диагностика</option>
                <option value="warranty_case">Гарантийный случай</option>
                <option value="sale">Продажа</option>
                <option value="other">Другое</option>
              </select>
            </label>
            <label class="field-label sm:col-span-2">
              Примечание
              <textarea v-model="form.notes" class="field-input min-h-20" placeholder="Где установлено, особенности доступа или состояния" />
            </label>
          </div>

          <p v-if="error" class="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950/40 dark:text-red-200">{{ error }}</p>

          <footer class="flex justify-end gap-2 border-t border-slate-200 pt-3 dark:border-slate-700">
            <button type="button" class="btn-mini-outline" :disabled="saving" @click="close">Отмена</button>
            <button type="submit" class="btn-mini" :disabled="saving || !canSubmit()">
              <LoaderCircle v-if="saving" class="h-4 w-4 animate-spin" />
              <Plus v-else class="h-4 w-4" />
              {{ saving ? 'Создаём...' : 'Создать и привязать' }}
            </button>
          </footer>
        </form>
      </section>
    </div>
  </Teleport>
</template>
