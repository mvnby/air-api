<script setup lang="ts">
import { nextTick, ref, watch } from 'vue';
import { ManagerCatalogDecisionService } from '../../client';
import type { CatalogDecisionSelectionItem } from '../../services/catalog-decision-selection';
import { getApiErrorMessage } from '../../utils/api-errors';

const props = defineProps<{ open: boolean; items: CatalogDecisionSelectionItem[] }>();
const emit = defineEmits<{ close: []; created: [collectionId: number] }>();
const title = ref('');
const saving = ref(false);
const error = ref('');
const titleInput = ref<HTMLInputElement | null>(null);

const defaultTitle = () => `Подборка ${new Intl.DateTimeFormat('ru-BY', { dateStyle: 'short' }).format(new Date())}`;

watch(() => props.open, async (open) => {
  if (!open) return;
  title.value = defaultTitle();
  error.value = '';
  await nextTick();
  titleInput.value?.select();
}, { immediate: true });

const submit = async () => {
  const normalized = title.value.trim();
  if (!normalized || saving.value) return;
  saving.value = true;
  error.value = '';
  try {
    const collection = await ManagerCatalogDecisionService.createManagerCatalogDecisionCollection({
      title: normalized,
      product_ids: props.items.map(item => item.id),
    });
    emit('created', collection.id);
  } catch (err) {
    error.value = getApiErrorMessage(err) || 'Не удалось создать подборку';
  } finally {
    saving.value = false;
  }
};
</script>

<template>
  <Teleport to="body">
    <div v-if="open" class="fixed inset-0 z-50 flex items-end justify-center bg-gray-950/40 p-0 sm:items-center sm:p-4" @click.self="emit('close')">
      <form class="w-full rounded-t-2xl bg-white p-5 shadow-xl sm:max-w-lg sm:rounded-2xl" @submit.prevent="submit">
        <div class="flex items-start justify-between gap-4">
          <div><h2 class="text-lg font-bold text-gray-900">Создать подборку</h2><p class="mt-1 text-sm text-gray-500">В неё войдут {{ items.length }} выбранных моделей.</p></div>
          <button type="button" class="material-icons-round text-gray-400" aria-label="Закрыть" @click="emit('close')">close</button>
        </div>
        <label class="mt-5 block text-sm font-medium text-gray-700">Название<input ref="titleInput" v-model="title" maxlength="180" class="mt-1 w-full rounded-xl border border-gray-300 px-3 py-2.5 outline-none focus:border-teal-600 focus:ring-2 focus:ring-teal-100" /></label>
        <p v-if="error" class="mt-3 rounded-lg bg-red-50 p-3 text-sm text-red-700">{{ error }}</p>
        <div class="mt-5 flex justify-end gap-2"><button type="button" class="rounded-xl px-4 py-2.5 text-sm font-semibold text-gray-600" @click="emit('close')">Отмена</button><button type="submit" class="rounded-xl bg-teal-600 px-4 py-2.5 text-sm font-semibold text-white disabled:opacity-50" :disabled="saving || !title.trim()">{{ saving ? 'Создаём…' : 'Создать' }}</button></div>
      </form>
    </div>
  </Teleport>
</template>
