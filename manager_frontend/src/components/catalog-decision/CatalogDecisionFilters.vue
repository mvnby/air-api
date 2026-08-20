<script setup lang="ts">
import { reactive } from 'vue';
import type { CatalogDecisionFilters as FilterState } from '../../services/catalog-decision-api';

const emit = defineEmits<{ apply: [filters: FilterState]; reset: [] }>();
const filters = reactive<FilterState>({ isPublished: true });
const asNumber = (value: string): number | undefined => value === '' ? undefined : Number(value);
const apply = () => emit('apply', { ...filters });
const preset35 = () => {
  filters.coolingMinKw = 3.2;
  filters.coolingMaxKw = 3.8;
  apply();
};
const reset = () => {
  Object.keys(filters).forEach(key => delete filters[key as keyof FilterState]);
  filters.isPublished = true;
  emit('reset');
};
</script>

<template>
  <form class="grid gap-2 rounded-xl border border-gray-200 bg-white p-3 md:grid-cols-4" @submit.prevent="apply">
    <input v-model="filters.search" class="rounded-lg border border-gray-200 px-3 py-2 text-sm" placeholder="Модель, бренд или серия" aria-label="Поиск" />
    <div class="flex gap-2">
      <input :value="filters.coolingMinKw ?? ''" class="min-w-0 rounded-lg border border-gray-200 px-3 py-2 text-sm" placeholder="кВт от" inputmode="decimal" @input="filters.coolingMinKw = asNumber(($event.target as HTMLInputElement).value)" />
      <input :value="filters.coolingMaxKw ?? ''" class="min-w-0 rounded-lg border border-gray-200 px-3 py-2 text-sm" placeholder="кВт до" inputmode="decimal" @input="filters.coolingMaxKw = asNumber(($event.target as HTMLInputElement).value)" />
    </div>
    <select v-model="filters.category" class="rounded-lg border border-gray-200 px-3 py-2 text-sm"><option :value="undefined">Любая категория</option><option value="household">Бытовой</option><option value="multi">Мультисплит</option><option value="semi_industrial">Полупромышленный</option></select>
    <select v-model="filters.indoorFormFactor" class="rounded-lg border border-gray-200 px-3 py-2 text-sm"><option :value="undefined">Любой блок</option><option value="wall">Настенный</option><option value="cassette">Кассетный</option><option value="duct">Канальный</option><option value="floor_ceiling">Напольно-потолочный</option><option value="column">Колонный</option></select>
    <select v-model="filters.wifi" class="rounded-lg border border-gray-200 px-3 py-2 text-sm"><option :value="undefined">Любой Wi‑Fi</option><option value="builtin">Встроен</option><option value="ready">Подготовлен</option><option value="none">Нет</option></select>
    <select v-model="filters.availability" class="rounded-lg border border-gray-200 px-3 py-2 text-sm"><option :value="undefined">Любой остаток</option><option value="in_stock">В наличии</option><option value="out_of_stock">Нет в наличии</option></select>
    <select v-model="filters.isInverter" class="rounded-lg border border-gray-200 px-3 py-2 text-sm"><option :value="undefined">Любой компрессор</option><option :value="true">Инвертор</option><option :value="false">On/off</option></select>
    <div class="flex gap-2"><button type="button" class="rounded-lg border border-teal-300 px-3 py-2 text-sm text-teal-700" @click="preset35">≈ 3.5 кВт</button><button class="rounded-lg bg-teal-600 px-3 py-2 text-sm font-semibold text-white" type="submit">Применить</button><button class="px-2 text-sm text-gray-500" type="button" @click="reset">Сбросить</button></div>
  </form>
</template>
