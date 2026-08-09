<script setup lang="ts">
import type { ManagerBrand, ManagerBrandSeries } from "../../api";
import SeriesList from "./SeriesList.vue";

defineProps<{
  brands: ManagerBrand[];
  loading: boolean;
  query: string;
  error: string;
  selectedBrandId: number | null;
  reordering: boolean;
  reorderDisabled: boolean;
  draggedBrandId: number | null;
  dropTargetId: number | null;
  seriesItems: ManagerBrandSeries[];
  seriesLoading: boolean;
  seriesError: string;
  seriesReordering: boolean;
  seriesReorderDisabled: boolean;
  draggedSeriesId: number | null;
  seriesDropTargetId: number | null;
  expandedSeriesIds: Set<number>;
}>();

const emit = defineEmits<{
  "update:query": [value: string];
  select: [brand: ManagerBrand];
  edit: [brand: ManagerBrand];
  delete: [brand: ManagerBrand];
  brandDragStart: [event: DragEvent, brand: ManagerBrand];
  brandDragOver: [event: DragEvent, brand: ManagerBrand];
  brandDragLeave: [brandId: number];
  brandDrop: [brand: ManagerBrand];
  brandDragEnd: [];
  createSeries: [];
  editSeries: [series: ManagerBrandSeries];
  deleteSeries: [series: ManagerBrandSeries];
  openSeriesProducts: [series: ManagerBrandSeries];
  toggleSeriesExpanded: [seriesId: number];
  toggleSeriesFromCard: [series: ManagerBrandSeries];
  seriesDragStart: [event: DragEvent, series: ManagerBrandSeries];
  seriesDragOver: [event: DragEvent, series: ManagerBrandSeries];
  seriesDragLeave: [seriesId: number];
  seriesDrop: [series: ManagerBrandSeries];
  seriesDragEnd: [];
}>();

const forwardSeriesDragStart = (event: DragEvent, series: ManagerBrandSeries) =>
  emit("seriesDragStart", event, series);
const forwardSeriesDragOver = (event: DragEvent, series: ManagerBrandSeries) =>
  emit("seriesDragOver", event, series);
</script>

<template>
  <div
    class="rounded-xl border border-gray-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-800/70"
  >
    <div
      class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between"
    >
      <input
        :value="query"
        type="text"
        placeholder="Поиск по названию или slug"
        class="w-full rounded-lg border border-gray-200 bg-slate-100 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-900 sm:max-w-sm"
        @input="emit('update:query', ($event.target as HTMLInputElement).value)"
      />
      <div class="text-xs text-gray-500 dark:text-slate-400">
        <span
          v-if="reordering"
          class="font-semibold text-teal-600 dark:text-teal-300"
          >Сохраняем порядок...</span
        ><span v-else-if="query.trim()"
          >Перетаскивание доступно после очистки поиска.</span
        ><span v-else
          >Всего: {{ brands.length }} · порядок меняется перетаскиванием</span
        >
      </div>
    </div>
    <div
      v-if="error"
      class="mt-4 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-900/40 dark:bg-red-900/20 dark:text-red-300"
    >
      {{ error }}
    </div>
    <div v-if="loading" class="py-6 text-sm text-gray-500 dark:text-slate-400">
      Загрузка брендов...
    </div>
    <div
      v-else-if="brands.length === 0"
      class="py-6 text-sm text-gray-500 dark:text-slate-400"
    >
      Бренды не найдены.
    </div>
    <div v-else class="mt-4 overflow-x-auto">
      <table class="min-w-full text-sm">
        <thead>
          <tr
            class="border-b border-gray-100 text-left text-gray-500 dark:border-slate-700 dark:text-slate-400"
          >
            <th class="w-12 py-2 pr-3 font-semibold">Порядок</th>
            <th class="py-2 pr-3 font-semibold">Бренд</th>
            <th class="py-2 pr-3 font-semibold">Slug</th>
            <th class="py-2 pr-3 font-semibold">Товаров</th>
            <th class="py-2 pr-3 font-semibold">Статус</th>
            <th class="py-2 text-right font-semibold">Действия</th>
          </tr>
        </thead>
        <tbody>
          <template v-for="brand in brands" :key="brand.id"
            ><tr v-if="dropTargetId === brand.id" aria-hidden="true">
              <td colspan="6" class="p-0">
                <div
                  class="mx-3 h-1 rounded-full bg-teal-400 shadow-[0_0_18px_rgba(20,184,166,0.75)] dark:bg-teal-300"
                />
              </td>
            </tr>
            <tr
              class="cursor-pointer border-b border-gray-100 transition-colors dark:border-slate-800/80"
              :class="[
                selectedBrandId === brand.id
                  ? 'bg-teal-50/80 dark:bg-teal-900/20'
                  : 'hover:bg-gray-50 dark:hover:bg-slate-800',
                draggedBrandId === brand.id ? 'opacity-50' : '',
              ]"
              :draggable="!reorderDisabled"
              @dragstart="emit('brandDragStart', $event, brand)"
              @dragover="emit('brandDragOver', $event, brand)"
              @dragleave="emit('brandDragLeave', brand.id)"
              @drop.prevent="emit('brandDrop', brand)"
              @dragend="emit('brandDragEnd')"
              @click="emit('select', brand)"
            >
              <td class="py-2 pr-3">
                <button
                  type="button"
                  class="inline-flex h-8 w-8 items-center justify-center rounded-lg border border-gray-200 text-gray-400 dark:border-slate-700 dark:text-slate-500"
                  :class="
                    reorderDisabled
                      ? 'cursor-not-allowed opacity-40'
                      : 'cursor-grab hover:bg-gray-50 hover:text-teal-600 dark:hover:bg-slate-700 dark:hover:text-teal-300 active:cursor-grabbing'
                  "
                  :disabled="reorderDisabled"
                  title="Перетащите бренд выше или ниже"
                  @click.stop
                >
                  <span class="material-icons-round text-[20px]"
                    >drag_indicator</span
                  >
                </button>
              </td>
              <td class="py-2 pr-3">
                <div class="flex min-w-[220px] items-center gap-2">
                  <img
                    v-if="brand.logo_url"
                    :src="brand.logo_url"
                    :alt="brand.title"
                    class="h-7 w-7 rounded border border-gray-200 bg-white object-contain"
                  />
                  <div>
                    <div
                      class="font-semibold text-gray-800 dark:text-slate-200"
                    >
                      {{ brand.title }}
                    </div>
                    <div
                      v-if="brand.description"
                      class="max-w-[360px] truncate text-xs text-gray-500 dark:text-slate-400"
                    >
                      {{ brand.description }}
                    </div>
                  </div>
                </div>
              </td>
              <td class="py-2 pr-3 font-mono text-gray-600 dark:text-slate-300">
                {{ brand.slug }}
              </td>
              <td class="py-2 pr-3 text-gray-700 dark:text-slate-200">
                {{ brand.products_count }}
              </td>
              <td class="py-2 pr-3">
                <span
                  class="inline-flex items-center rounded-full px-2 py-0.5 text-xs font-semibold"
                  :class="
                    brand.is_published
                      ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300'
                      : 'bg-gray-100 text-gray-600 dark:bg-slate-700 dark:text-slate-300'
                  "
                  >{{ brand.is_published ? "Публичный" : "Скрыт" }}</span
                >
              </td>
              <td class="py-2 text-right">
                <div class="inline-flex items-center justify-end gap-1">
                  <button
                    type="button"
                    class="inline-flex h-8 w-8 items-center justify-center rounded-lg border border-gray-200 text-gray-600 transition-colors hover:bg-gray-50 hover:text-teal-700 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-700 dark:hover:text-teal-200"
                    title="Изменить бренд"
                    aria-label="Изменить бренд"
                    @click.stop="emit('edit', brand)"
                  >
                    <span class="material-icons-round text-[18px]"
                      >edit</span
                    ></button
                  ><button
                    type="button"
                    class="inline-flex h-8 w-8 items-center justify-center rounded-lg border border-red-200 text-red-500 transition-colors hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-40 dark:border-red-900/50 dark:text-red-300 dark:hover:bg-red-950/30"
                    :disabled="(brand.products_count ?? 0) > 0"
                    :title="
                      (brand.products_count ?? 0) > 0
                        ? 'Нельзя удалить бренд с товарами'
                        : 'Удалить бренд'
                    "
                    aria-label="Удалить бренд"
                    @click.stop="emit('delete', brand)"
                  >
                    <span class="material-icons-round text-[18px]">delete</span>
                  </button>
                </div>
              </td>
            </tr>
            <tr
              v-if="selectedBrandId === brand.id"
              class="border-b border-teal-100 bg-teal-50/50 dark:border-teal-900/40 dark:bg-teal-950/10"
            >
              <td colspan="6" class="p-0">
                <SeriesList
                  :brand="brand"
                  :items="seriesItems"
                  :loading="seriesLoading"
                  :error="seriesError"
                  :reordering="seriesReordering"
                  :reorder-disabled="seriesReorderDisabled"
                  :dragged-id="draggedSeriesId"
                  :drop-target-id="seriesDropTargetId"
                  :expanded-ids="expandedSeriesIds"
                  @create="emit('createSeries')"
                  @edit="emit('editSeries', $event)"
                  @delete="emit('deleteSeries', $event)"
                  @open-products="emit('openSeriesProducts', $event)"
                  @toggle-expanded="emit('toggleSeriesExpanded', $event)"
                  @toggle-from-card="emit('toggleSeriesFromCard', $event)"
                  @drag-start="forwardSeriesDragStart"
                  @drag-over="forwardSeriesDragOver"
                  @drag-leave="emit('seriesDragLeave', $event)"
                  @drop="emit('seriesDrop', $event)"
                  @drag-end="emit('seriesDragEnd')"
                />
              </td></tr
          ></template>
        </tbody>
      </table>
    </div>
  </div>
</template>
