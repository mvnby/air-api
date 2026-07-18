<script setup lang="ts">
import { computed, ref } from 'vue';
import { Bookmark, BookmarkPlus, Search, SlidersHorizontal, X } from 'lucide-vue-next';
import type { ManagerCatalogQualityFilterOptionsResponse } from '../../client';
import type {
  CatalogQualityFilterState,
  CatalogQualitySavedView,
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
  if (state.equipmentType) chips.push({ key: 'equipmentType', label: findLabel('equipment_types', state.equipmentType) });
  if (state.equipmentSubtype) chips.push({ key: 'equipmentSubtype', label: findLabel('equipment_subtypes', state.equipmentSubtype) });
  if (state.brandId) chips.push({ key: 'brandId', label: findLabel('brands', state.brandId) });
  if (state.seriesId) chips.push({ key: 'seriesId', label: findLabel('series', state.seriesId) });
  if (state.seriesState) chips.push({ key: 'seriesState', label: state.seriesState === 'missing' ? 'Без серии' : 'С серией' });
  if (state.supplierId) chips.push({ key: 'supplierId', label: findLabel('suppliers', state.supplierId) });
  if (state.supplierState) chips.push({
    key: 'supplierState',
    label: { mapped: 'Есть маппинг', in_stock: 'Есть у поставщика', unmapped: 'Без маппинга', multiple: 'Несколько поставщиков' }[state.supplierState],
  });
  if (state.publication) chips.push({ key: 'publication', label: state.publication === 'published' ? 'Опубликовано' : 'Скрыто' });
  if (state.availability) chips.push({ key: 'availability', label: state.availability === 'in_stock' ? 'В наличии' : 'Нет в наличии' });
  if (state.priority) chips.push({ key: 'priority', label: `Приоритет: ${state.priority === 'high' ? 'высокий' : state.priority === 'medium' ? 'средний' : 'низкий'}` });
  if (state.category !== 'all') chips.push({ key: 'category', label: { media: 'Медиа', identity: 'Бренд и серия', specs: 'Характеристики', commerce: 'Цена и наличие', supplier: 'Поставщики' }[state.category] });
  if (state.severity !== 'all') chips.push({ key: 'severity', label: { critical: 'Критично', warning: 'Предупреждение', info: 'Заметка' }[state.severity] });
  if (state.issueCode) chips.push({ key: 'issueCode', label: `Причина: ${state.issueCode}` });
  if (state.scoreMin) chips.push({ key: 'scoreMin', label: `Score от ${state.scoreMin}` });
  if (state.scoreMax) chips.push({ key: 'scoreMax', label: `Score до ${state.scoreMax}` });
  if (state.onlyFixable) chips.push({ key: 'onlyFixable', label: 'Можно исправить в Manager' });
  if (!state.onlyProblems) chips.push({ key: 'onlyProblems', label: 'Включая карточки без проблем' });
  return chips;
});

const clearChip = (key: keyof CatalogQualityFilterState) => {
  const defaults: Partial<CatalogQualityFilterState> = {
    category: 'all', severity: 'all', onlyProblems: true, onlyFixable: false,
  };
  const patch: Partial<CatalogQualityFilterState> = { [key]: defaults[key] ?? '' };
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
  <section class="border-y border-gray-200 bg-white px-4 py-4 sm:px-5">
    <div class="flex flex-wrap items-center gap-2">
      <span class="inline-flex items-center gap-1.5 text-xs font-bold uppercase text-gray-500">
        <Bookmark class="h-4 w-4" />
        Рабочие виды
      </span>
      <div v-for="view in savedViews" :key="view.id" class="inline-flex items-center">
        <button
          class="h-8 rounded-l-lg border border-gray-200 bg-gray-50 px-2.5 text-xs font-semibold text-gray-700 transition hover:border-teal-300 hover:bg-teal-50 hover:text-teal-800"
          :class="view.builtin ? 'rounded-r-lg' : ''"
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
        class="inline-flex h-8 items-center gap-1.5 rounded-lg border border-dashed border-gray-300 px-2.5 text-xs font-semibold text-gray-500 hover:border-teal-300 hover:text-teal-700"
        @click="showSaveInput = true"
      >
        <BookmarkPlus class="h-3.5 w-3.5" />
        Сохранить вид
      </button>
      <form v-else class="flex items-center gap-1" @submit.prevent="submitView">
        <input
          v-model="viewName"
          class="h-8 w-44 rounded-lg border border-gray-300 px-2 text-xs outline-none focus:border-teal-500"
          placeholder="Название вида"
          autofocus
        >
        <button class="h-8 rounded-lg bg-teal-600 px-2.5 text-xs font-semibold text-white">Сохранить</button>
        <button class="grid h-8 w-8 place-items-center rounded-lg text-gray-500 hover:bg-gray-100" type="button" @click="showSaveInput = false">
          <X class="h-4 w-4" />
        </button>
      </form>
    </div>

    <div class="mt-4 grid gap-3 xl:grid-cols-[minmax(260px,1.35fr)_repeat(4,minmax(150px,0.8fr))]">
      <label class="relative block">
        <span class="sr-only">Поиск</span>
        <Search class="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
        <input
          :value="modelValue.q"
          class="h-10 w-full rounded-lg border border-gray-200 bg-gray-50 pl-9 pr-3 text-sm outline-none focus:border-teal-400 focus:bg-white"
          placeholder="Название, модель или slug"
          @input="patchState({ q: ($event.target as HTMLInputElement).value })"
        >
      </label>
      <label class="space-y-1">
        <span class="sr-only">Тип оборудования</span>
        <select
          :value="modelValue.equipmentType"
          class="h-10 w-full rounded-lg border border-gray-200 bg-white px-2 text-sm"
          @change="patchState({ equipmentType: ($event.target as HTMLSelectElement).value, equipmentSubtype: '' })"
        >
          <option value="">Все типы</option>
          <option v-for="item in options?.equipment_types ?? []" :key="item.value" :value="item.value">{{ item.label }} · {{ item.count }}</option>
        </select>
      </label>
      <label>
        <span class="sr-only">Подтип</span>
        <select
          :value="modelValue.equipmentSubtype"
          class="h-10 w-full rounded-lg border border-gray-200 bg-white px-2 text-sm disabled:bg-gray-100"
          :disabled="!modelValue.equipmentType"
          @change="patchState({ equipmentSubtype: ($event.target as HTMLSelectElement).value })"
        >
          <option value="">Все подтипы</option>
          <option v-for="item in equipmentSubtypes" :key="item.value" :value="item.value">{{ item.label }} · {{ item.count }}</option>
        </select>
      </label>
      <label>
        <span class="sr-only">Бренд</span>
        <select
          :value="modelValue.brandId"
          class="h-10 w-full rounded-lg border border-gray-200 bg-white px-2 text-sm"
          @change="patchState({ brandId: ($event.target as HTMLSelectElement).value, seriesId: '' })"
        >
          <option value="">Все бренды</option>
          <option v-for="item in options?.brands ?? []" :key="item.value" :value="item.value">{{ item.label }} · {{ item.count }}</option>
        </select>
      </label>
      <label>
        <span class="sr-only">Серия</span>
        <select
          :value="modelValue.seriesId"
          class="h-10 w-full rounded-lg border border-gray-200 bg-white px-2 text-sm disabled:bg-gray-100"
          :disabled="!modelValue.brandId"
          @change="patchState({ seriesId: ($event.target as HTMLSelectElement).value })"
        >
          <option value="">Все серии</option>
          <option v-for="item in seriesOptions" :key="item.value" :value="item.value">{{ item.label }} · {{ item.count }}</option>
        </select>
      </label>
    </div>

    <details class="mt-3 rounded-lg border border-gray-200 bg-gray-50 px-3 py-2">
      <summary class="flex cursor-pointer list-none items-center gap-2 text-sm font-semibold text-gray-700">
        <SlidersHorizontal class="h-4 w-4" />
        Уточнить выбор
      </summary>
      <div class="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-6">
        <select :value="modelValue.seriesState" class="h-9 rounded-lg border border-gray-200 bg-white px-2 text-sm" @change="patchState({ seriesState: ($event.target as HTMLSelectElement).value as CatalogQualityFilterState['seriesState'] })">
          <option value="">Любая привязка серии</option><option value="assigned">С серией</option><option value="missing">Без серии</option>
        </select>
        <select :value="modelValue.supplierId" class="h-9 rounded-lg border border-gray-200 bg-white px-2 text-sm" @change="patchState({ supplierId: ($event.target as HTMLSelectElement).value })">
          <option value="">Все поставщики</option><option v-for="item in options?.suppliers ?? []" :key="item.value" :value="item.value">{{ item.label }} · {{ item.count }}</option>
        </select>
        <select :value="modelValue.supplierState" class="h-9 rounded-lg border border-gray-200 bg-white px-2 text-sm" @change="patchState({ supplierState: ($event.target as HTMLSelectElement).value as CatalogQualityFilterState['supplierState'], supplierId: ($event.target as HTMLSelectElement).value === 'unmapped' ? '' : modelValue.supplierId })">
          <option value="">Любой маппинг</option><option value="mapped">Есть маппинг</option><option value="in_stock">Есть у поставщика</option><option value="unmapped">Без маппинга</option><option value="multiple">Несколько поставщиков</option>
        </select>
        <select :value="modelValue.publication" class="h-9 rounded-lg border border-gray-200 bg-white px-2 text-sm" @change="patchState({ publication: ($event.target as HTMLSelectElement).value as CatalogQualityFilterState['publication'] })">
          <option value="">Любая публикация</option><option value="published">Опубликовано</option><option value="hidden">Скрыто</option>
        </select>
        <select :value="modelValue.availability" class="h-9 rounded-lg border border-gray-200 bg-white px-2 text-sm" @change="patchState({ availability: ($event.target as HTMLSelectElement).value as CatalogQualityFilterState['availability'] })">
          <option value="">Любое наличие</option><option value="in_stock">В наличии</option><option value="out_of_stock">Нет в наличии</option>
        </select>
        <select :value="modelValue.priority" class="h-9 rounded-lg border border-gray-200 bg-white px-2 text-sm" @change="patchState({ priority: ($event.target as HTMLSelectElement).value as CatalogQualityFilterState['priority'] })">
          <option value="">Любой приоритет</option><option value="high">Высокий</option><option value="medium">Средний</option><option value="low">Низкий</option>
        </select>
        <select :value="modelValue.category" class="h-9 rounded-lg border border-gray-200 bg-white px-2 text-sm" @change="patchState({ category: ($event.target as HTMLSelectElement).value as CatalogQualityFilterState['category'] })">
          <option value="all">Все группы проблем</option><option value="media">Медиа</option><option value="identity">Бренд и серия</option><option value="specs">Характеристики</option><option value="supplier">Поставщики</option><option value="commerce">Цена и наличие</option>
        </select>
        <select :value="modelValue.severity" class="h-9 rounded-lg border border-gray-200 bg-white px-2 text-sm" @change="patchState({ severity: ($event.target as HTMLSelectElement).value as CatalogQualityFilterState['severity'] })">
          <option value="all">Любая серьезность</option><option value="critical">Критично</option><option value="warning">Предупреждение</option><option value="info">Заметка</option>
        </select>
        <label class="flex h-9 items-center gap-2 rounded-lg border border-gray-200 bg-white px-2 text-sm"><span class="text-gray-500">Score от</span><input :value="modelValue.scoreMin" class="min-w-0 flex-1 outline-none" inputmode="numeric" @input="patchState({ scoreMin: ($event.target as HTMLInputElement).value })"></label>
        <label class="flex h-9 items-center gap-2 rounded-lg border border-gray-200 bg-white px-2 text-sm"><span class="text-gray-500">до</span><input :value="modelValue.scoreMax" class="min-w-0 flex-1 outline-none" inputmode="numeric" @input="patchState({ scoreMax: ($event.target as HTMLInputElement).value })"></label>
        <label class="flex h-9 items-center gap-2 rounded-lg border border-gray-200 bg-white px-2 text-sm"><input :checked="modelValue.onlyProblems" type="checkbox" @change="patchState({ onlyProblems: ($event.target as HTMLInputElement).checked })">Только с проблемами</label>
        <label class="flex h-9 items-center gap-2 rounded-lg border border-gray-200 bg-white px-2 text-sm"><input :checked="modelValue.onlyFixable" type="checkbox" @change="patchState({ onlyFixable: ($event.target as HTMLInputElement).checked })">Исправимо здесь</label>
      </div>
    </details>

    <div v-if="activeChips.length" class="mt-3 flex flex-wrap items-center gap-1.5">
      <span class="text-xs font-semibold text-gray-400">Выбрано:</span>
      <button v-for="chip in activeChips" :key="chip.key" class="inline-flex h-7 items-center gap-1 rounded-full bg-teal-50 px-2.5 text-xs font-semibold text-teal-800 hover:bg-teal-100" @click="clearChip(chip.key)">
        {{ chip.label }} <X class="h-3 w-3" />
      </button>
    </div>
  </section>
</template>
