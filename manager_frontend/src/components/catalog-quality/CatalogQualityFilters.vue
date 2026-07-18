<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { Bookmark, BookmarkPlus, ChevronDown, Search, SlidersHorizontal, X } from 'lucide-vue-next';
import type { ManagerCatalogQualityFilterOptionsResponse } from '../../client';
import {
  createDefaultCatalogQualityState,
  type CatalogQualityFilterState,
  type CatalogQualitySavedView,
} from './catalog-quality-state';

const props = defineProps<{
  modelValue: CatalogQualityFilterState;
  options?: ManagerCatalogQualityFilterOptionsResponse;
  savedViews: CatalogQualitySavedView[];
  loading?: boolean;
}>();

const emit = defineEmits<{
  'update:modelValue': [value: CatalogQualityFilterState];
  'apply-view': [view: CatalogQualitySavedView];
  'save-view': [name: string];
  'delete-view': [id: string];
}>();

const showSaveInput = ref(false);
const viewName = ref('');

const patchState = (patch: Partial<CatalogQualityFilterState>) => {
  emit('update:modelValue', { ...props.modelValue, ...patch, page: 1 });
};

const equipmentSubtypes = computed(() => props.modelValue.equipmentType
  ? (props.options?.equipment_subtypes ?? []).filter((item) => item.parent_value === props.modelValue.equipmentType)
  : []);

const seriesOptions = computed(() => props.modelValue.brandId
  ? (props.options?.series ?? []).filter((item) => item.parent_value === props.modelValue.brandId)
  : []);

const findLabel = (group: keyof ManagerCatalogQualityFilterOptionsResponse, value: string) =>
  (props.options?.[group] ?? []).find((item) => item.value === value)?.label ?? value;

const activeChips = computed(() => {
  const state = props.modelValue;
  const chips: Array<{ key: keyof CatalogQualityFilterState; label: string }> = [];
  if (state.equipmentType) chips.push({ key: 'equipmentType', label: `Тип: ${findLabel('equipment_types', state.equipmentType)}` });
  if (state.equipmentSubtype) chips.push({ key: 'equipmentSubtype', label: `Подтип: ${findLabel('equipment_subtypes', state.equipmentSubtype)}` });
  if (state.brandId) chips.push({ key: 'brandId', label: `Бренд: ${findLabel('brands', state.brandId)}` });
  if (state.seriesId) chips.push({ key: 'seriesId', label: `Серия: ${findLabel('series', state.seriesId)}` });
  if (state.seriesState) chips.push({ key: 'seriesState', label: state.seriesState === 'missing' ? 'Без серии' : 'С серией' });
  if (state.supplierId) chips.push({ key: 'supplierId', label: `Поставщик: ${findLabel('suppliers', state.supplierId)}` });
  if (state.supplierState) chips.push({
    key: 'supplierState',
    label: `Маппинг: ${{ mapped: 'есть', in_stock: 'есть в наличии', unmapped: 'отсутствует', multiple: 'несколько поставщиков' }[state.supplierState]}`,
  });
  if (state.publication) chips.push({ key: 'publication', label: state.publication === 'published' ? 'Опубликовано' : 'Скрыто' });
  if (state.availability) chips.push({ key: 'availability', label: state.availability === 'in_stock' ? 'В наличии' : 'Нет в наличии' });
  if (state.priority) chips.push({ key: 'priority', label: `Приоритет: ${state.priority === 'high' ? 'высокий' : state.priority === 'medium' ? 'средний' : 'низкий'}` });
  if (state.category !== 'all') chips.push({ key: 'category', label: `Проблема: ${{ media: 'медиа', identity: 'бренд и серия', specs: 'характеристики', commerce: 'цена и наличие', supplier: 'поставщики' }[state.category]}` });
  if (state.severity !== 'all') chips.push({ key: 'severity', label: `Серьёзность: ${{ critical: 'критично', warning: 'предупреждение', info: 'заметка' }[state.severity]}` });
  if (state.issueCode) chips.push({ key: 'issueCode', label: `Причина: ${state.issueCode}` });
  if (state.scoreMin) chips.push({ key: 'scoreMin', label: `Score от ${state.scoreMin}` });
  if (state.scoreMax) chips.push({ key: 'scoreMax', label: `Score до ${state.scoreMax}` });
  if (state.onlyFixable) chips.push({ key: 'onlyFixable', label: 'Исправимо в Manager' });
  if (!state.onlyProblems) chips.push({ key: 'onlyProblems', label: 'Включая карточки без проблем' });
  return chips;
});

const advancedActiveCount = computed(() => {
  const state = props.modelValue;
  return [
    state.equipmentSubtype,
    state.seriesState,
    state.priority,
    state.category !== 'all',
    state.severity !== 'all',
    state.scoreMin,
    state.scoreMax,
    state.onlyFixable,
    !state.onlyProblems,
  ].filter(Boolean).length;
});

const showAdvanced = ref(advancedActiveCount.value > 0);
watch(advancedActiveCount, (count) => {
  if (count > 0) showAdvanced.value = true;
});

const viewComparisonKeys: Array<keyof CatalogQualityFilterState> = [
  'q', 'equipmentType', 'equipmentSubtype', 'brandId', 'seriesId', 'seriesState',
  'supplierId', 'supplierState', 'publication', 'availability', 'priority',
  'scoreMin', 'scoreMax', 'category', 'severity', 'issueCode', 'onlyProblems',
  'onlyFixable', 'sortBy', 'groupBy',
];

const isViewActive = (view: CatalogQualitySavedView) => {
  const target = { ...createDefaultCatalogQualityState(), ...view.filters };
  return viewComparisonKeys.every((key) => props.modelValue[key] === target[key]);
};

const clearChip = (key: keyof CatalogQualityFilterState) => {
  const defaults = createDefaultCatalogQualityState();
  const patch: Partial<CatalogQualityFilterState> = { [key]: defaults[key] as never };
  if (key === 'equipmentType') patch.equipmentSubtype = '';
  if (key === 'brandId') patch.seriesId = '';
  patchState(patch);
};

const submitView = () => {
  const name = viewName.value.trim();
  if (!name) return;
  emit('save-view', name);
  viewName.value = '';
  showSaveInput.value = false;
};
</script>

<template>
  <section class="border-b border-gray-200 bg-white px-4 py-3 sm:px-5">
    <div class="flex items-center gap-2 overflow-x-auto pb-1">
      <span class="inline-flex shrink-0 items-center gap-1.5 text-xs font-bold uppercase text-gray-500">
        <Bookmark class="h-4 w-4" />
        Рабочие виды
      </span>
      <div v-for="view in savedViews" :key="view.id" class="inline-flex shrink-0 items-center">
        <button
          class="h-8 rounded-l-lg border px-2.5 text-xs font-semibold transition"
          :class="[
            view.builtin ? 'rounded-r-lg' : '',
            isViewActive(view)
              ? 'border-teal-600 bg-teal-600 text-white'
              : 'border-gray-200 bg-gray-50 text-gray-700 hover:border-teal-300 hover:bg-teal-50 hover:text-teal-800',
          ]"
          @click="emit('apply-view', view)"
        >
          {{ view.name }}
        </button>
        <button
          v-if="!view.builtin"
          class="grid h-8 w-8 place-items-center rounded-r-lg border border-l-0 border-gray-200 text-gray-400 hover:bg-red-50 hover:text-red-600"
          title="Удалить сохраненный вид"
          @click="emit('delete-view', view.id)"
        >
          <X class="h-3.5 w-3.5" />
        </button>
      </div>
      <button
        v-if="!showSaveInput"
        class="inline-flex h-8 shrink-0 items-center gap-1.5 rounded-lg border border-dashed border-gray-300 px-2.5 text-xs font-semibold text-gray-500 hover:border-teal-300 hover:text-teal-700"
        @click="showSaveInput = true"
      >
        <BookmarkPlus class="h-3.5 w-3.5" />
        Сохранить текущие фильтры
      </button>
      <form v-else class="flex shrink-0 items-center gap-1" @submit.prevent="submitView">
        <input v-model="viewName" class="h-8 w-44 rounded-lg border border-gray-300 px-2 text-xs outline-none focus:border-teal-500" placeholder="Название вида" autofocus>
        <button class="h-8 rounded-lg bg-teal-600 px-2.5 text-xs font-semibold text-white">Сохранить</button>
        <button class="grid h-8 w-8 place-items-center rounded-lg text-gray-500 hover:bg-gray-100" type="button" @click="showSaveInput = false"><X class="h-4 w-4" /></button>
      </form>
    </div>

    <div class="mt-3 grid grid-cols-2 gap-2 xl:grid-cols-[minmax(280px,1.4fr)_repeat(4,minmax(145px,0.8fr))]">
      <label class="relative col-span-2 block xl:col-span-1">
        <span class="mb-1 block text-[11px] font-semibold uppercase text-gray-500">Поиск</span>
        <Search class="pointer-events-none absolute bottom-3 left-3 h-4 w-4 text-gray-400" />
        <input
          :value="modelValue.q"
          class="h-10 w-full rounded-lg border border-gray-200 bg-gray-50 pl-9 pr-9 text-sm outline-none focus:border-teal-400 focus:bg-white"
          placeholder="Модель, артикул или название"
          @input="patchState({ q: ($event.target as HTMLInputElement).value })"
        >
        <button v-if="modelValue.q" class="absolute bottom-2.5 right-2.5 grid h-5 w-5 place-items-center text-gray-400 hover:text-gray-700" title="Очистить поиск" @click="patchState({ q: '' })"><X class="h-4 w-4" /></button>
      </label>
      <label>
        <span class="mb-1 block text-[11px] font-semibold uppercase text-gray-500">Тип оборудования</span>
        <select :value="modelValue.equipmentType" class="h-10 w-full rounded-lg border border-gray-200 bg-white px-2 text-sm" @change="patchState({ equipmentType: ($event.target as HTMLSelectElement).value, equipmentSubtype: '' })">
          <option value="">Все типы</option><option v-for="item in options?.equipment_types ?? []" :key="item.value" :value="item.value">{{ item.label }} · {{ item.count }}</option>
        </select>
      </label>
      <label>
        <span class="mb-1 block text-[11px] font-semibold uppercase text-gray-500">Бренд</span>
        <select :value="modelValue.brandId" class="h-10 w-full rounded-lg border border-gray-200 bg-white px-2 text-sm" @change="patchState({ brandId: ($event.target as HTMLSelectElement).value, seriesId: '' })">
          <option value="">Все бренды</option><option v-for="item in options?.brands ?? []" :key="item.value" :value="item.value">{{ item.label }} · {{ item.count }}</option>
        </select>
      </label>
      <label>
        <span class="mb-1 block text-[11px] font-semibold uppercase text-gray-500">Серия</span>
        <select :value="modelValue.seriesId" class="h-10 w-full rounded-lg border border-gray-200 bg-white px-2 text-sm disabled:bg-gray-100" :disabled="!modelValue.brandId" @change="patchState({ seriesId: ($event.target as HTMLSelectElement).value })">
          <option value="">Все серии</option><option v-for="item in seriesOptions" :key="item.value" :value="item.value">{{ item.label }} · {{ item.count }}</option>
        </select>
      </label>
      <label>
        <span class="mb-1 block text-[11px] font-semibold uppercase text-gray-500">Поставщик</span>
        <select :value="modelValue.supplierId" class="h-10 w-full rounded-lg border border-gray-200 bg-white px-2 text-sm" @change="patchState({ supplierId: ($event.target as HTMLSelectElement).value })">
          <option value="">Все поставщики</option><option v-for="item in options?.suppliers ?? []" :key="item.value" :value="item.value">{{ item.label }} · {{ item.count }}</option>
        </select>
      </label>
    </div>

    <div class="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-3">
      <label>
        <span class="mb-1 block text-[11px] font-semibold uppercase text-gray-500">Публикация</span>
        <select :value="modelValue.publication" class="h-9 w-full rounded-lg border border-gray-200 bg-white px-2 text-sm" @change="patchState({ publication: ($event.target as HTMLSelectElement).value as CatalogQualityFilterState['publication'] })">
          <option value="">Любая</option><option value="published">Опубликовано</option><option value="hidden">Скрыто</option>
        </select>
      </label>
      <label>
        <span class="mb-1 block text-[11px] font-semibold uppercase text-gray-500">Наличие</span>
        <select :value="modelValue.availability" class="h-9 w-full rounded-lg border border-gray-200 bg-white px-2 text-sm" @change="patchState({ availability: ($event.target as HTMLSelectElement).value as CatalogQualityFilterState['availability'] })">
          <option value="">Любое</option><option value="in_stock">В наличии</option><option value="out_of_stock">Нет в наличии</option>
        </select>
      </label>
      <label class="col-span-2 sm:col-span-1">
        <span class="mb-1 block text-[11px] font-semibold uppercase text-gray-500">Маппинг прайсов</span>
        <select :value="modelValue.supplierState" class="h-9 w-full rounded-lg border border-gray-200 bg-white px-2 text-sm" @change="patchState({ supplierState: ($event.target as HTMLSelectElement).value as CatalogQualityFilterState['supplierState'], supplierId: ($event.target as HTMLSelectElement).value === 'unmapped' ? '' : modelValue.supplierId })">
          <option value="">Любой</option><option value="mapped">Есть маппинг</option><option value="in_stock">Есть у поставщика</option><option value="unmapped">Без маппинга</option><option value="multiple">Несколько поставщиков</option>
        </select>
      </label>
    </div>

    <button
      class="mt-3 inline-flex h-9 items-center gap-2 rounded-lg border border-gray-200 bg-gray-50 px-3 text-sm font-semibold text-gray-700 hover:border-teal-300 hover:text-teal-800"
      :aria-expanded="showAdvanced"
      @click="showAdvanced = !showAdvanced"
    >
      <SlidersHorizontal class="h-4 w-4" />
      Дополнительные фильтры
      <span v-if="advancedActiveCount" class="rounded-full bg-teal-100 px-2 py-0.5 text-xs text-teal-800">{{ advancedActiveCount }} активных</span>
      <ChevronDown class="h-4 w-4 transition-transform" :class="showAdvanced ? 'rotate-180' : ''" />
    </button>

    <Transition enter-active-class="transition duration-200 ease-out" enter-from-class="-translate-y-1 opacity-0" leave-active-class="transition duration-150 ease-in" leave-to-class="-translate-y-1 opacity-0">
      <div v-if="showAdvanced" class="mt-3 rounded-lg border border-gray-200 bg-gray-50 p-3">
        <div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-5">
          <label><span class="mb-1 block text-[11px] font-semibold uppercase text-gray-500">Подтип</span><select :value="modelValue.equipmentSubtype" class="h-9 w-full rounded-lg border border-gray-200 bg-white px-2 text-sm disabled:bg-gray-100" :disabled="!modelValue.equipmentType" @change="patchState({ equipmentSubtype: ($event.target as HTMLSelectElement).value })"><option value="">Все подтипы</option><option v-for="item in equipmentSubtypes" :key="item.value" :value="item.value">{{ item.label }} · {{ item.count }}</option></select></label>
          <label><span class="mb-1 block text-[11px] font-semibold uppercase text-gray-500">Привязка серии</span><select :value="modelValue.seriesState" class="h-9 w-full rounded-lg border border-gray-200 bg-white px-2 text-sm" @change="patchState({ seriesState: ($event.target as HTMLSelectElement).value as CatalogQualityFilterState['seriesState'] })"><option value="">Любая</option><option value="assigned">С серией</option><option value="missing">Без серии</option></select></label>
          <label><span class="mb-1 block text-[11px] font-semibold uppercase text-gray-500">Рабочий приоритет</span><select :value="modelValue.priority" class="h-9 w-full rounded-lg border border-gray-200 bg-white px-2 text-sm" @change="patchState({ priority: ($event.target as HTMLSelectElement).value as CatalogQualityFilterState['priority'] })"><option value="">Любой</option><option value="high">Высокий</option><option value="medium">Средний</option><option value="low">Низкий</option></select></label>
          <label><span class="mb-1 block text-[11px] font-semibold uppercase text-gray-500">Группа проблем</span><select :value="modelValue.category" class="h-9 w-full rounded-lg border border-gray-200 bg-white px-2 text-sm" @change="patchState({ category: ($event.target as HTMLSelectElement).value as CatalogQualityFilterState['category'] })"><option value="all">Все группы</option><option value="media">Медиа</option><option value="identity">Бренд и серия</option><option value="specs">Характеристики</option><option value="supplier">Поставщики</option><option value="commerce">Цена и наличие</option></select></label>
          <label><span class="mb-1 block text-[11px] font-semibold uppercase text-gray-500">Серьёзность</span><select :value="modelValue.severity" class="h-9 w-full rounded-lg border border-gray-200 bg-white px-2 text-sm" @change="patchState({ severity: ($event.target as HTMLSelectElement).value as CatalogQualityFilterState['severity'] })"><option value="all">Любая</option><option value="critical">Критично</option><option value="warning">Предупреждение</option><option value="info">Заметка</option></select></label>
          <label><span class="mb-1 block text-[11px] font-semibold uppercase text-gray-500">Score от</span><input :value="modelValue.scoreMin" class="h-9 w-full rounded-lg border border-gray-200 bg-white px-2 text-sm outline-none" inputmode="numeric" placeholder="0" @input="patchState({ scoreMin: ($event.target as HTMLInputElement).value })"></label>
          <label><span class="mb-1 block text-[11px] font-semibold uppercase text-gray-500">Score до</span><input :value="modelValue.scoreMax" class="h-9 w-full rounded-lg border border-gray-200 bg-white px-2 text-sm outline-none" inputmode="numeric" placeholder="100" @input="patchState({ scoreMax: ($event.target as HTMLInputElement).value })"></label>
          <label class="flex h-9 items-center gap-2 self-end rounded-lg border border-gray-200 bg-white px-2 text-sm"><input :checked="modelValue.onlyProblems" type="checkbox" @change="patchState({ onlyProblems: ($event.target as HTMLInputElement).checked })">Только с проблемами</label>
          <label class="flex h-9 items-center gap-2 self-end rounded-lg border border-gray-200 bg-white px-2 text-sm"><input :checked="modelValue.onlyFixable" type="checkbox" @change="patchState({ onlyFixable: ($event.target as HTMLInputElement).checked })">Исправимо в Manager</label>
        </div>
      </div>
    </Transition>

    <div v-if="activeChips.length" class="mt-3 flex flex-wrap items-center gap-1.5">
      <span class="text-xs font-semibold text-gray-400">Активно:</span>
      <button v-for="chip in activeChips" :key="chip.key" class="inline-flex min-h-7 items-center gap-1 rounded-full bg-teal-50 px-2.5 py-1 text-xs font-semibold text-teal-800 hover:bg-teal-100" @click="clearChip(chip.key)">{{ chip.label }} <X class="h-3 w-3" /></button>
    </div>
  </section>
</template>
