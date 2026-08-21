<script setup lang="ts">
import type { CatalogDecisionSelectionItem } from '../../services/catalog-decision-selection';
defineProps<{ items: CatalogDecisionSelectionItem[] }>();
const emit = defineEmits<{ remove: [id: number]; clear: []; createCollection: []; attachOrder: [] }>();
</script>

<template>
  <aside v-if="items.length" class="fixed inset-x-3 bottom-3 z-20 rounded-2xl border border-teal-200 bg-white p-3 shadow-lg md:bottom-5 md:left-auto md:right-6 md:w-[min(46rem,calc(100vw-3rem))]" aria-label="Подборка клиента"><div class="flex flex-wrap items-center gap-2"><div class="mr-auto"><p class="text-sm font-semibold text-gray-900">В подборке: {{ items.length }}</p><p class="text-xs text-gray-500">Сохранится в этой вкладке ещё 5 минут.</p></div><button type="button" class="text-sm text-gray-500 underline underline-offset-2" @click="emit('clear')">Очистить</button></div><div class="mt-2 flex gap-2 overflow-x-auto pb-1"><div v-for="item in items" :key="item.id" class="flex shrink-0 items-center gap-2 rounded-lg bg-teal-50 px-2 py-1.5 text-xs text-teal-900"><span class="max-w-48 truncate">{{ item.title }}</span><button type="button" class="material-icons-round text-[16px]" :aria-label="`Убрать ${item.title}`" @click="emit('remove', item.id)">close</button></div></div><div class="mt-3 grid grid-cols-2 gap-2"><button type="button" class="rounded-xl border border-teal-600 px-3 py-2 text-sm font-semibold text-teal-700" @click="emit('createCollection')">Создать подборку</button><button type="button" class="rounded-xl bg-teal-600 px-3 py-2 text-sm font-semibold text-white" @click="emit('attachOrder')">К заказу</button></div></aside>
</template>
