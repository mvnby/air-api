<script setup lang="ts">
import { computed, ref } from 'vue';
import type { CatalogDecisionSelectionItem } from '../../services/catalog-decision-selection';
const props = defineProps<{ items: CatalogDecisionSelectionItem[]; targetOrderId?: number; targeted?: boolean; busy?: boolean; canAttach?: boolean }>();
const emit = defineEmits<{ remove: [id: number]; clear: []; compare: []; createCollection: []; attachOrder: []; attachTarget: []; createOrder: [] }>();
const expanded = ref(false);
const compareAllowed = computed(() => props.items.length >= 2 && props.items.length <= 4);
</script>

<template>
  <aside v-if="items.length" class="catalog-selection-tray fixed inset-x-3 bottom-3 z-20 mx-auto max-w-5xl rounded-2xl border border-brand-200 bg-white p-3 shadow-lg md:bottom-4" aria-label="Подборка клиента">
    <div class="flex flex-wrap items-center gap-x-3 gap-y-1">
      <button type="button" class="inline-flex min-h-9 items-center gap-2 text-sm font-semibold text-gray-900" :aria-expanded="expanded" aria-controls="catalog-selection-items" @click="expanded = !expanded">Выбрано: {{ items.length }} из 24<span aria-hidden="true">{{ expanded ? '▴' : '▾' }}</span></button>
      <p class="mr-auto hidden text-xs text-gray-500 sm:block">Сохранится в этом браузере на сутки.</p>
      <button type="button" :class="expanded ? '' : 'hidden sm:block'" class="ml-auto min-h-9 text-xs text-gray-600 underline underline-offset-2" :disabled="busy" @click="emit('clear')">Начать новый подбор</button>
    </div>
    <div v-if="expanded" id="catalog-selection-items" class="mb-2 flex max-h-24 sm:max-h-32 flex-wrap gap-1.5 overflow-y-auto border-t border-gray-100 pt-2">
      <div v-for="item in items" :key="item.id" class="flex max-w-full items-center gap-1 rounded-lg bg-brand-50 py-1 pl-2 text-xs text-brand-900">
        <span class="min-w-0 break-words">{{ item.title }}</span><button type="button" class="h-8 w-8 shrink-0 rounded-lg text-base hover:bg-brand-100" :aria-label="`Убрать ${item.title}`" :disabled="busy" @click="emit('remove', item.id)">×</button>
      </div>
    </div>
    <div class="flex flex-wrap items-center gap-2">
      <button type="button" class="min-h-10 rounded-xl border border-gray-300 px-3 py-2 text-sm font-semibold text-gray-700 disabled:opacity-50" :disabled="busy || !compareAllowed" :title="compareAllowed ? 'Сравнить выбранные модели' : 'Для сравнения выберите от 2 до 4 моделей'" @click="emit('compare')">Сравнить {{ compareAllowed ? `(${items.length})` : '2–4 модели' }}</button>
      <button v-if="targeted" type="button" class="min-h-10 flex-1 rounded-xl bg-brand-600 px-3 py-2 text-sm font-semibold text-white disabled:opacity-50" :disabled="busy || !canAttach" @click="emit('attachTarget')">{{ busy ? 'Добавляем…' : `Добавить в вариант заказа #${targetOrderId || '—'}` }}</button>
      <template v-else>
        <button type="button" :class="expanded ? '' : 'hidden sm:block'" class="min-h-10 rounded-xl border border-gray-300 px-3 py-2 text-sm font-semibold text-gray-700" :disabled="busy" @click="emit('attachOrder')">В существующий заказ</button>
        <button type="button" :class="expanded ? '' : 'hidden sm:block'" class="min-h-10 rounded-xl border border-gray-300 px-3 py-2 text-sm font-semibold text-gray-700" :disabled="busy" @click="emit('createOrder')">Новый заказ</button>
        <button type="button" class="min-h-10 flex-1 rounded-xl bg-brand-600 px-3 py-2 text-sm font-semibold text-white" :disabled="busy" @click="emit('createCollection')">Создать подборку</button>
      </template>
    </div>
  </aside>
</template>

<style scoped>
@media (min-width: 768px) {
  .catalog-selection-tray {
    left: calc(var(--kitlane-sidebar-width, 0px) + 1rem);
    right: 1rem;
  }
  :global(.kitlane-shell.is-collapsed) .catalog-selection-tray {
    left: calc(var(--kitlane-sidebar-compact, 0px) + 1rem);
  }
}
</style>
