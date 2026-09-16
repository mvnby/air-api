<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue';
import type { CatalogDecisionFilters as FilterState } from '../../services/catalog-decision-api';
import BynSymbol from './BynSymbol.vue';
import EquipmentTypeIcon from './EquipmentTypeIcon.vue';

type RangeName = 'cooling' | 'retail';
type RangeDraft = { min: string; max: string };

const props = defineProps<{
  modelValue: FilterState;
  brands: Array<{ id: number; title: string }>;
  series: Array<{ id: number; title: string; brandId?: number | null }>;
  resetKey?: number;
}>();
const emit = defineEmits<{ 'update:modelValue': [value: FilterState]; reset: [] }>();

const btuGroups = [[7, 9, 12, 18, 24], [30, 36, 42, 60]];
const heatingTemperatures = [-20, -25, -30] as const;
const wifiOptions: Array<{ value: FilterState['wifi'] | undefined; label: string }> = [
  { value: undefined, label: 'Любой' },
  { value: 'builtin', label: 'Встроенный' },
  { value: 'ready', label: 'Опция' },
];
const forms = [
  { value: 'wall', label: 'Настенный' },
  { value: 'cassette', label: 'Кассетный' },
  { value: 'duct', label: 'Канальный' },
  { value: 'floor_ceiling', label: 'Напольно-потолочный' },
  { value: 'console', label: 'Консольный' },
  { value: 'column', label: 'Колонный' },
] as const;

const selectedBrandIds = computed(() => props.modelValue.brandIds ?? []);
const visibleSeries = computed(() => !selectedBrandIds.value.length ? [] : props.series.filter(item => item.brandId && selectedBrandIds.value.includes(item.brandId)));
const coolingRange = reactive<RangeDraft>({ min: '', max: '' });
const retailRange = reactive<RangeDraft>({ min: '', max: '' });
const showAllBrands = ref(false);
const brandSearch = ref('');
const visibleBrands = computed(() => {
  const query = brandSearch.value.trim().toLocaleLowerCase('ru');
  const matching = query ? props.brands.filter(brand => brand.title.toLocaleLowerCase('ru').includes(query)) : props.brands;
  if (showAllBrands.value || query) return matching;
  return matching.filter((brand, index) => index < 8 || selectedBrandIds.value.includes(brand.id));
});
const hiddenBrandCount = computed(() => Math.max(0, props.brands.filter(brand => !selectedBrandIds.value.includes(brand.id)).length - 8));

const toDraft = (value: number | undefined) => value == null ? '' : String(value);
const resetRangeDrafts = () => {
  coolingRange.min = toDraft(props.modelValue.coolingMinKw);
  coolingRange.max = toDraft(props.modelValue.coolingMaxKw);
  retailRange.min = toDraft(props.modelValue.retailMinByn);
  retailRange.max = toDraft(props.modelValue.retailMaxByn);
};
watch(() => props.modelValue.coolingMinKw, value => { coolingRange.min = toDraft(value); }, { immediate: true });
watch(() => props.modelValue.coolingMaxKw, value => { coolingRange.max = toDraft(value); }, { immediate: true });
watch(() => props.modelValue.retailMinByn, value => { retailRange.min = toDraft(value); }, { immediate: true });
watch(() => props.modelValue.retailMaxByn, value => { retailRange.max = toDraft(value); }, { immediate: true });
watch(() => props.resetKey, (next, previous) => { if (next !== undefined && next !== previous) resetRangeDrafts(); });

const parseRangeValue = (value: string) => {
  if (value.trim() === '') return undefined;
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : null;
};
const rangeError = (draft: RangeDraft) => {
  const min = parseRangeValue(draft.min);
  const max = parseRangeValue(draft.max);
  if (min === null || max === null) return 'Укажите число от 0.';
  if (min != null && max != null && min > max) return 'Минимум не может быть больше максимума.';
  return '';
};
const coolingRangeError = computed(() => rangeError(coolingRange));
const retailRangeError = computed(() => rangeError(retailRange));
const update = (patch: Partial<FilterState>) => emit('update:modelValue', { ...props.modelValue, ...patch });
const updateRange = (name: RangeName, bound: keyof RangeDraft, value: string) => {
  const draft = name === 'cooling' ? coolingRange : retailRange;
  draft[bound] = value;
  if (rangeError(draft)) return;
  const min = parseRangeValue(draft.min) as number | undefined;
  const max = parseRangeValue(draft.max) as number | undefined;
  update(name === 'cooling' ? { coolingMinKw: min, coolingMaxKw: max } : { retailMinByn: min, retailMaxByn: max });
};
const toggleList = (key: 'coolingBtuClasses' | 'brandIds' | 'seriesIds', value: number) => {
  const current = props.modelValue[key] ?? [];
  update({ [key]: current.includes(value) ? current.filter(item => item !== value) : [...current, value] } as Partial<FilterState>);
};
const toggleSingle = <T extends 'heatingMin' | 'indoorFormFactor'>(key: T, value: NonNullable<FilterState[T]>) => update({ [key]: props.modelValue[key] === value ? undefined : value } as Partial<FilterState>);
const toggleBrand = (brandId: number) => {
  const next = selectedBrandIds.value.includes(brandId) ? selectedBrandIds.value.filter(id => id !== brandId) : [...selectedBrandIds.value, brandId];
  const allowedSeries = props.series.filter(item => item.brandId && next.includes(item.brandId)).map(item => item.id);
  update({ brandIds: next, seriesIds: (props.modelValue.seriesIds ?? []).filter(id => allowedSeries.includes(id)) });
};
const setWifi = (wifi: FilterState['wifi'] | undefined) => update({ wifi, hasWifi: undefined });
</script>

<template>
  <section class="space-y-3 rounded-2xl border border-gray-200 bg-white p-3 shadow-sm md:p-4" aria-label="Быстрые фильтры">
    <div class="flex flex-wrap items-center gap-2">
      <label class="relative basis-full sm:basis-72 sm:flex-1"><span class="material-icons-round pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-gray-400">search</span><input :value="modelValue.search ?? ''" class="w-full rounded-xl border border-gray-200 py-2.5 pl-10 pr-3 text-sm outline-none transition focus:border-brand-500 focus:ring-2 focus:ring-brand-100" placeholder="Например, Gree 12" aria-label="Поиск модели, бренда или серии" @input="update({ search: ($event.target as HTMLInputElement).value || undefined })" /></label>
      <button type="button" :class="modelValue.isInverter ? 'border-brand-600 bg-brand-50 text-brand-800' : 'border-gray-200 text-gray-700'" class="inline-flex min-h-10 shrink-0 items-center justify-center rounded-xl border px-3 text-sm transition" :aria-pressed="Boolean(modelValue.isInverter)" @click="update({ isInverter: modelValue.isInverter ? undefined : true })">Только инвертор</button>
      <div class="inline-flex overflow-hidden rounded-xl border border-gray-200" aria-label="Наличие">
        <button type="button" class="min-h-10 border-r border-gray-200 px-3 text-sm transition" :class="!modelValue.includeOrderable ? 'bg-brand-600 text-white' : 'text-gray-700'" :aria-pressed="!modelValue.includeOrderable" @click="update({ includeOrderable: false })">В наличии</button>
        <button type="button" class="min-h-10 px-3 text-sm transition" :class="modelValue.includeOrderable ? 'bg-brand-600 text-white' : 'text-gray-700'" :aria-pressed="Boolean(modelValue.includeOrderable)" @click="update({ includeOrderable: true })">Все</button>
      </div>
    </div>

    <div class="space-y-1.5">
      <p class="text-xs font-semibold uppercase tracking-wide text-gray-500">Тип внутреннего блока</p>
      <div class="grid grid-cols-2 gap-1.5 sm:grid-cols-3 xl:grid-cols-6">
        <button v-for="item in forms" :key="item.value" type="button" class="flex min-h-14 items-center gap-1.5 rounded-xl border px-2 py-1.5 text-left text-xs transition" :class="modelValue.indoorFormFactor === item.value ? 'border-brand-600 bg-brand-50 text-brand-800' : 'border-gray-200 text-gray-700 hover:border-brand-300'" :aria-pressed="modelValue.indoorFormFactor === item.value" @click="toggleSingle('indoorFormFactor', item.value)"><EquipmentTypeIcon :type="item.value" />{{ item.label }}</button>
      </div>
    </div>

    <div class="grid gap-4 lg:grid-cols-2">
      <div class="space-y-2">
        <p class="text-xs font-semibold uppercase tracking-wide text-gray-500">Мощность охлаждения · тыс. БТЕ/ч</p>
        <div class="flex flex-wrap items-center justify-between gap-1.5">
          <div v-for="(group, index) in btuGroups" :key="index" class="flex gap-1.5">
            <button v-for="btu in group" :key="btu" type="button" class="h-10 min-w-10 rounded-full border px-2 text-sm font-semibold transition" :class="(modelValue.coolingBtuClasses ?? []).includes(btu) ? 'border-brand-600 bg-brand-600 text-white' : 'border-gray-200 text-gray-700 hover:border-brand-300'" :aria-pressed="(modelValue.coolingBtuClasses ?? []).includes(btu)" @click="toggleList('coolingBtuClasses', btu)">{{ btu }}</button>
          </div>
        </div>
        <div class="flex flex-wrap items-center gap-2 text-sm text-gray-600">
          <span class="w-full text-xs sm:w-auto">Номинальная, кВт</span>
          <input :value="coolingRange.min" type="number" min="0" step="0.1" placeholder="От" aria-label="Мощность охлаждения от, кВт" class="w-24 rounded-lg border border-gray-200 px-3 py-2" :aria-invalid="Boolean(coolingRangeError)" @input="updateRange('cooling', 'min', ($event.target as HTMLInputElement).value)" />
          <span aria-hidden="true">—</span>
          <input :value="coolingRange.max" type="number" min="0" step="0.1" placeholder="До" aria-label="Мощность охлаждения до, кВт" class="w-24 rounded-lg border border-gray-200 px-3 py-2" :aria-invalid="Boolean(coolingRangeError)" @input="updateRange('cooling', 'max', ($event.target as HTMLInputElement).value)" />
        </div>
        <p v-if="coolingRangeError" class="text-xs text-red-600" role="alert">{{ coolingRangeError }}</p>
      </div>

      <div class="space-y-2">
        <p class="text-xs font-semibold uppercase tracking-wide text-gray-500">Обогрев в мороз</p>
        <div class="flex flex-wrap gap-1.5">
          <button v-for="temperature in heatingTemperatures" :key="temperature" type="button" class="min-h-10 rounded-xl border px-4 text-sm font-semibold transition" :class="modelValue.heatingMin === temperature ? 'border-brand-600 bg-brand-600 text-white' : 'border-gray-200 text-gray-700'" :aria-pressed="modelValue.heatingMin === temperature" @click="toggleSingle('heatingMin', temperature)">{{ temperature }} °C</button>
        </div>
        <p class="text-xs text-gray-500">Работа при выбранной температуре или ниже. Теплопроизводительность в мороз проверяется отдельно.</p>
      </div>
    </div>

    <div class="grid gap-4 lg:grid-cols-2">
      <div class="space-y-2">
        <p class="flex items-center gap-1 text-xs font-semibold uppercase tracking-wide text-gray-500">Бюджет, <span aria-label="белорусский рубль"><BynSymbol /></span></p>
        <div class="flex flex-wrap items-center gap-2 text-sm text-gray-600">
          <input :value="retailRange.min" type="number" min="0" step="1" placeholder="От" aria-label="Бюджет от, BYN" class="w-28 rounded-lg border border-gray-200 px-3 py-2" :aria-invalid="Boolean(retailRangeError)" @input="updateRange('retail', 'min', ($event.target as HTMLInputElement).value)" />
          <span aria-hidden="true">—</span>
          <input :value="retailRange.max" type="number" min="0" step="1" placeholder="До" aria-label="Бюджет до, BYN" class="w-28 rounded-lg border border-gray-200 px-3 py-2" :aria-invalid="Boolean(retailRangeError)" @input="updateRange('retail', 'max', ($event.target as HTMLInputElement).value)" />
        </div>
        <p v-if="retailRangeError" class="text-xs text-red-600" role="alert">{{ retailRangeError }}</p>
      </div>

      <div class="space-y-2">
        <p class="text-xs font-semibold uppercase tracking-wide text-gray-500">Wi‑Fi</p>
        <div class="inline-flex overflow-hidden rounded-xl border border-gray-200" aria-label="Наличие Wi-Fi">
          <button v-for="option in wifiOptions" :key="option.label" type="button" class="min-h-10 border-r border-gray-200 px-3 text-sm last:border-r-0" :class="modelValue.wifi === option.value ? 'bg-brand-600 text-white' : 'text-gray-700'" :aria-pressed="modelValue.wifi === option.value" @click="setWifi(option.value)">{{ option.label }}</button>
        </div>
      </div>
    </div>

    <div class="space-y-1.5">
      <p class="text-xs font-semibold uppercase tracking-wide text-gray-500">Бренды</p>
      <template v-if="brands.length">
        <label v-if="showAllBrands" class="relative block max-w-xs"><span class="material-icons-round pointer-events-none absolute left-2 top-1/2 -translate-y-1/2 text-base text-gray-400">search</span><input v-model="brandSearch" type="search" class="w-full rounded-lg border border-gray-200 py-1.5 pl-8 pr-2 text-sm" placeholder="Найти бренд" aria-label="Найти бренд" /></label>
        <div class="flex flex-wrap gap-1.5"><button v-for="brand in visibleBrands" :key="brand.id" type="button" class="rounded-full border px-3 py-1.5 text-sm transition" :class="selectedBrandIds.includes(brand.id) ? 'border-brand-600 bg-brand-600 text-white' : 'border-gray-200 text-gray-700 hover:border-brand-300'" :aria-pressed="selectedBrandIds.includes(brand.id)" @click="toggleBrand(brand.id)">{{ brand.title }}</button><button v-if="hiddenBrandCount && !showAllBrands" type="button" class="rounded-full border border-gray-200 px-3 py-1.5 text-sm text-gray-700 hover:border-brand-300" @click="showAllBrands = true">Ещё {{ hiddenBrandCount }}</button></div>
        <p v-if="showAllBrands && !visibleBrands.length" class="text-sm text-gray-500">Бренд не найден.</p>
      </template>
      <p v-else class="text-sm text-gray-500">Бренды пока не найдены.</p>
    </div>
    <div v-if="selectedBrandIds.length" class="space-y-2 rounded-xl bg-gray-50 p-2.5"><p class="text-xs font-semibold text-gray-600">Серии выбранных брендов</p><div v-for="brand in brands.filter(item => selectedBrandIds.includes(item.id))" :key="brand.id" class="flex items-start gap-2"><span class="w-20 shrink-0 pt-1.5 text-xs font-medium text-gray-500">{{ brand.title }}</span><div class="flex flex-wrap gap-1.5"><button v-for="item in visibleSeries.filter(seriesItem => seriesItem.brandId === brand.id)" :key="item.id" type="button" class="rounded-full border px-2.5 py-1 text-xs transition" :class="(modelValue.seriesIds ?? []).includes(item.id) ? 'border-brand-600 bg-brand-600 text-white' : 'border-gray-200 bg-white text-gray-700'" :aria-pressed="(modelValue.seriesIds ?? []).includes(item.id)" @click="toggleList('seriesIds', item.id)">{{ item.title }}</button><span v-if="!visibleSeries.some(seriesItem => seriesItem.brandId === brand.id)" class="py-1 text-xs text-gray-400">Нет серий в каталоге</span></div></div></div>
  </section>
</template>
