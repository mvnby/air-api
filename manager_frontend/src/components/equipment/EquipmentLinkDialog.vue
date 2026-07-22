<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { Link2, LoaderCircle, X } from 'lucide-vue-next';
import type { ManagerEquipmentItemResponse } from '../../client';
import { useDialogA11y } from '../../composables/useDialogA11y';

const props = defineProps<{
  open: boolean;
  items: ManagerEquipmentItemResponse[];
  linkedIds: number[];
  loading: boolean;
  saving: boolean;
  error?: string;
}>();

const emit = defineEmits<{
  close: [];
  confirm: [payload: { equipmentId: number; role: string }];
}>();

const equipmentId = ref<number | null>(null);
const role = ref('other');
const dialogRef = ref<HTMLElement | null>(null);
const closeButtonRef = ref<HTMLElement | null>(null);

const availableItems = computed(() => props.items.filter((item) => !props.linkedIds.includes(item.id)));

const titleFor = (item: ManagerEquipmentItemResponse) => (
  item.display_name
  || [item.brand, item.model].filter(Boolean).join(' ')
  || item.serial
  || `Оборудование #${item.id}`
);

watch(() => props.open, (open) => {
  if (!open) return;
  equipmentId.value = null;
  role.value = 'other';
});

const confirm = () => {
  if (!equipmentId.value || props.saving) return;
  emit('confirm', { equipmentId: equipmentId.value, role: role.value });
};

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
      <section ref="dialogRef" class="w-full max-w-lg rounded-t-lg border border-slate-200 bg-white shadow-2xl sm:rounded-lg dark:border-slate-700 dark:bg-slate-900" role="dialog" aria-modal="true" aria-labelledby="equipment-link-dialog-title" tabindex="-1">
        <header class="flex items-center justify-between gap-3 border-b border-slate-200 px-4 py-3 dark:border-slate-700">
          <div class="flex min-w-0 items-center gap-2">
            <Link2 class="h-5 w-5 shrink-0 text-teal-700 dark:text-teal-300" />
            <h2 id="equipment-link-dialog-title" class="truncate text-base font-semibold text-slate-950 dark:text-white">Привязать оборудование</h2>
          </div>
          <button ref="closeButtonRef" type="button" class="inline-flex h-8 w-8 items-center justify-center rounded-md text-slate-500 hover:bg-slate-100 disabled:opacity-50 dark:hover:bg-slate-800" :disabled="saving" aria-label="Закрыть" @click="close">
            <X class="h-4 w-4" />
          </button>
        </header>

        <form class="space-y-4 p-4" @submit.prevent="confirm">
          <p class="text-sm text-slate-600 dark:text-slate-300">
            В списке только оборудование этого клиента. Уже привязанные позиции скрыты.
          </p>

          <div v-if="loading" class="flex items-center gap-2 py-6 text-sm text-slate-500">
            <LoaderCircle class="h-4 w-4 animate-spin" />
            Загружаем оборудование клиента
          </div>
          <label v-else class="field-label">
            Оборудование
            <select v-model="equipmentId" class="field-input" required>
              <option :value="null" disabled>Выберите оборудование</option>
              <option v-for="item in availableItems" :key="item.id" :value="item.id">
                {{ titleFor(item) }}{{ item.serial ? ` · ${item.serial}` : '' }}
              </option>
            </select>
          </label>

          <label class="field-label">
            Роль в заказе
            <select v-model="role" class="field-input">
              <option value="sale">Продажа</option>
              <option value="installation">Монтаж</option>
              <option value="maintenance">Обслуживание</option>
              <option value="repair">Ремонт</option>
              <option value="diagnostic">Диагностика</option>
              <option value="warranty_case">Гарантийный случай</option>
              <option value="other">Другое</option>
            </select>
          </label>

          <p v-if="!loading && !availableItems.length" class="rounded-md bg-slate-50 px-3 py-2 text-sm text-slate-600 dark:bg-slate-800 dark:text-slate-300">
            Свободного оборудования у клиента нет. Его можно создать вручную.
          </p>
          <p v-if="error" class="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950/40 dark:text-red-200">{{ error }}</p>

          <footer class="flex justify-end gap-2 border-t border-slate-200 pt-3 dark:border-slate-700">
            <button type="button" class="btn-mini-outline" :disabled="saving" @click="close">Отмена</button>
            <button type="submit" class="btn-mini" :disabled="saving || loading || !equipmentId">
              <LoaderCircle v-if="saving" class="h-4 w-4 animate-spin" />
              <Link2 v-else class="h-4 w-4" />
              {{ saving ? 'Привязываем...' : 'Привязать' }}
            </button>
          </footer>
        </form>
      </section>
    </div>
  </Teleport>
</template>
