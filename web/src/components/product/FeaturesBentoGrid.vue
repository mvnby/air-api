<template>
  <div v-if="cards && cards.length > 0" class="features-bento-grid mt-12 mb-16">
    <h2 class="text-2xl font-bold mb-6 text-slate-800 dark:text-gray-100">Ключевые особенности</h2>
    <div class="grid grid-cols-2 md:grid-cols-3 gap-4">
        <BentoCard 
            v-for="card in cards" 
            :key="card.id" 
            :card="card" 
            :class="{ 'col-span-2': card.layout === 'wide', 'col-span-2 md:col-span-1': card.layout === 'normal' }"
        />
    </div>
  </div>
</template>

<script setup lang="ts">
import BentoCard from './BentoCard.vue';
import type { BentoCard as BentoCardType } from '../../utils/bento-cards';

defineProps<{
  cards: BentoCardType[]
}>();
</script>

<style scoped>
.features-bento-grid {
  width: 100%;
}
</style>
