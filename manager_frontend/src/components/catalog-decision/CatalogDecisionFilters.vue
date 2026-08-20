<script setup lang="ts">
import { computed } from 'vue';
import type { CatalogDecisionFilters as FilterState } from '../../services/catalog-decision-api';

const props = defineProps<{
  modelValue: FilterState;
  brands: Array<{ id: number; title: string }>;
  series: Array<{ id: number; title: string; brandId?: number | null }>;
}>();
const emit = defineEmits<{ 'update:modelValue': [value: FilterState]; reset: [] }>();

const btuClasses = [7, 9, 12, 18, 24, 36, 42, 60];
const categories = [
  { value: 'household', label: 'Бытовой', icon: 'home' },
  { value: 'multi', label: 'Мультисплит', icon: 'grid_view' },
  { value: 'semi_industrial', label: 'Полупром', icon: 'business' },
] as const;
const forms = [
  { value: 'wall', label: 'Настенный', icon: 'crop_landscape' },
  { value: 'cassette', label: 'Кассетный', icon: 'grid_4x4' },
  { value: 'duct', label: 'Канальный', icon: 'air' },
  { value: 'floor_ceiling', label: 'Нап.-потол.', icon: 'view_stream' },
  { value: 'column', label: 'Колонный', icon: 'view_agenda' },
] as const;

const selectedBrandIds = computed(() => props.modelValue.brandIds ?? []);
const visibleSeries = computed(() => !selectedBrandIds.value.length ? [] : props.series.filter(item => item.brandId && selectedBrandIds.value.includes(item.brandId)));
const update = (patch: Partial<FilterState>) => emit('update:modelValue', { ...props.modelValue, ...patch });
const toggleList = (key: 'coolingBtuClasses' | 'brandIds' | 'seriesIds', value: number) => {
  const current = props.modelValue[key] ?? [];
  update({ [key]: current.includes(value) ? current.filter(item => item !== value) : [...current, value] } as Partial<FilterState>);
};
const toggleSingle = <T extends 'category' | 'indoorFormFactor'>(key: T, value: NonNullable<FilterState[T]>) => update({ [key]: props.modelValue[key] === value ? undefined : value } as Partial<FilterState>);
const toggleBrand = (brandId: number) => {
  const next = selectedBrandIds.value.includes(brandId) ? selectedBrandIds.value.filter(id => id !== brandId) : [...selectedBrandIds.value, brandId];
  const allowedSeries = props.series.filter(item => item.brandId && next.includes(item.brandId)).map(item => item.id);
  update({ brandIds: next, seriesIds: (props.modelValue.seriesIds ?? []).filter(id => allowedSeries.includes(id)) });
};
</script>

<template>
  <section class="space-y-3 rounded-2xl border border-gray-200 bg-white p-3 shadow-sm md:p-4" aria-label="Быстрые фильтры">
    <div class="flex flex-col gap-2 sm:flex-row">
      <label class="relative flex-1"><span class="material-icons-round pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-gray-400">search</span><input :value="modelValue.search ?? ''" class="w-full rounded-xl border border-gray-200 py-2.5 pl-10 pr-3 text-sm outline-none transition focus:border-teal-500 focus:ring-2 focus:ring-teal-100" placeholder="Например, Gree 12" aria-label="Поиск модели, бренда или серии" @input="update({ search: ($event.target as HTMLInputElement).value || undefined })" /></label>
      <label class="flex cursor-pointer items-center gap-2 rounded-xl border border-gray-200 px-3 py-2 text-sm text-gray-700"><input :checked="Boolean(modelValue.hasWifi)" type="checkbox" class="h-4 w-4 rounded border-gray-300 text-teal-600 focus:ring-teal-500" @change="update({ hasWifi: ($event.target as HTMLInputElement).checked || undefined })" />Wi‑Fi</label>
      <button type="button" :class="modelValue.isInverter ? 'border-teal-600 bg-teal-50 text-teal-800' : 'border-gray-200 text-gray-700'" class="inline-flex items-center justify-center gap-2 rounded-xl border px-3 py-2 text-sm transition" @click="update({ isInverter: modelValue.isInverter ? undefined : true })"><span class="inline-flex h-4 w-7 items-center rounded-full p-0.5" :class="modelValue.isInverter ? 'bg-teal-600' : 'bg-gray-300'"><span class="h-3 w-3 rounded-full bg-white transition" :class="modelValue.isInverter ? 'translate-x-3' : ''" /></span>Инвертор</button>
      <label class="flex cursor-pointer items-center gap-2 rounded-xl border border-gray-200 px-3 py-2 text-sm text-gray-700"><input :checked="Boolean(modelValue.includeOrderable)" type="checkbox" class="h-4 w-4 rounded border-gray-300 text-teal-600 focus:ring-teal-500" @change="update({ includeOrderable: ($event.target as HTMLInputElement).checked })" />Искать заказные</label>
    </div>
    <div class="space-y-1.5"><p class="text-xs font-semibold uppercase tracking-wide text-gray-500">Номинал</p><div class="flex gap-1.5 overflow-x-auto pb-1"><button v-for="btu in btuClasses" :key="btu" type="button" class="h-10 min-w-10 rounded-full border px-2 text-sm font-semibold transition" :class="(modelValue.coolingBtuClasses ?? []).includes(btu) ? 'border-teal-600 bg-teal-600 text-white' : 'border-gray-200 text-gray-700 hover:border-teal-300'" @click="toggleList('coolingBtuClasses', btu)">{{ btu }}</button></div></div>
    <div class="grid gap-3 lg:grid-cols-2"><div class="space-y-1.5"><p class="text-xs font-semibold uppercase tracking-wide text-gray-500">Категория</p><div class="flex gap-1.5 overflow-x-auto pb-1"><button v-for="item in categories" :key="item.value" type="button" class="inline-flex min-h-10 shrink-0 items-center gap-1.5 rounded-xl border px-3 text-sm transition" :class="modelValue.category === item.value ? 'border-teal-600 bg-teal-50 text-teal-800' : 'border-gray-200 text-gray-700'" @click="toggleSingle('category', item.value)"><span class="material-icons-round text-[18px]">{{ item.icon }}</span>{{ item.label }}</button></div></div><div class="space-y-1.5"><p class="text-xs font-semibold uppercase tracking-wide text-gray-500">Тип блока</p><div class="flex gap-1.5 overflow-x-auto pb-1"><button v-for="item in forms" :key="item.value" type="button" class="inline-flex min-h-10 shrink-0 items-center gap-1.5 rounded-xl border px-3 text-sm transition" :class="modelValue.indoorFormFactor === item.value ? 'border-teal-600 bg-teal-50 text-teal-800' : 'border-gray-200 text-gray-700'" @click="toggleSingle('indoorFormFactor', item.value)"><span class="material-icons-round text-[18px]">{{ item.icon }}</span>{{ item.label }}</button></div></div></div>
    <div class="space-y-1.5"><p class="text-xs font-semibold uppercase tracking-wide text-gray-500">Бренды</p><div class="flex gap-1.5 overflow-x-auto pb-1"><button v-for="brand in brands" :key="brand.id" type="button" class="shrink-0 rounded-full border px-3 py-1.5 text-sm transition" :class="selectedBrandIds.includes(brand.id) ? 'border-teal-600 bg-teal-600 text-white' : 'border-gray-200 text-gray-700 hover:border-teal-300'" @click="toggleBrand(brand.id)">{{ brand.title }}</button></div></div>
    <div v-if="selectedBrandIds.length" class="space-y-2 rounded-xl bg-gray-50 p-2.5"><p class="text-xs font-semibold text-gray-600">Серии выбранных брендов</p><div v-for="brand in brands.filter(item => selectedBrandIds.includes(item.id))" :key="brand.id" class="flex items-start gap-2"><span class="w-20 shrink-0 pt-1.5 text-xs font-medium text-gray-500">{{ brand.title }}</span><div class="flex flex-wrap gap-1.5"><button v-for="item in visibleSeries.filter(seriesItem => seriesItem.brandId === brand.id)" :key="item.id" type="button" class="rounded-full border px-2.5 py-1 text-xs transition" :class="(modelValue.seriesIds ?? []).includes(item.id) ? 'border-teal-600 bg-teal-600 text-white' : 'border-gray-200 bg-white text-gray-700'" @click="toggleList('seriesIds', item.id)">{{ item.title }}</button><span v-if="!visibleSeries.some(seriesItem => seriesItem.brandId === brand.id)" class="py-1 text-xs text-gray-400">Нет серий в каталоге</span></div></div></div>
    <div class="flex justify-end"><button v-if="Object.keys(modelValue).some(key => key !== 'isPublished')" type="button" class="text-sm text-gray-500 underline underline-offset-2 hover:text-teal-700" @click="emit('reset')">Сбросить фильтры</button></div>
  </section>
</template>
