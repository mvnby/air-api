<script setup lang="ts">
defineProps<{ count: number }>();
</script>
<template>
  <aside v-if="count" class="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-brand-200 bg-brand-50 px-4 py-3 text-sm text-brand-900" aria-label="Выбранное оборудование">
    <span role="status">В подборе: {{ count }} из 24 моделей</span>
    <a href="/manager/catalog-decision" class="font-semibold underline underline-offset-2">Открыть подбор →</a>
  </aside>
</template>
