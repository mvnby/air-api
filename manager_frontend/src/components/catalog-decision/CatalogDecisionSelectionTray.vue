<script setup lang="ts">
import type { CatalogDecisionItem } from '../../services/catalog-decision-api';
defineProps<{ items: CatalogDecisionItem[] }>();
const emit = defineEmits<{ remove: [id: number]; clear: [] }>();
</script>

<template>
  <aside v-if="items.length" class="sticky bottom-3 z-10 rounded-2xl border border-teal-200 bg-white p-3 shadow-lg" aria-label="Подборка клиента"><div class="flex flex-wrap items-center gap-2"><div class="mr-auto"><p class="text-sm font-semibold text-gray-900">В подборке: {{ items.length }}</p><p class="text-xs text-gray-500">Выбранные модели сохраняются, пока вы ищете дальше.</p></div><button type="button" class="text-sm text-gray-500 underline underline-offset-2" @click="emit('clear')">Очистить</button></div><div class="mt-2 flex gap-2 overflow-x-auto pb-1"><div v-for="item in items" :key="item.id" class="flex shrink-0 items-center gap-2 rounded-lg bg-teal-50 px-2 py-1.5 text-xs text-teal-900"><span class="max-w-48 truncate">{{ item.title }}</span><button type="button" class="material-icons-round text-[16px]" :aria-label="`Убрать ${item.title}`" @click="emit('remove', item.id)">close</button></div></div></aside>
</template>
