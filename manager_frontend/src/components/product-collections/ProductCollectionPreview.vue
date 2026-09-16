<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { Eye, ImageOff, Loader2 } from 'lucide-vue-next';
import type {
  ManagerProductCollectionResponse,
  ProductCollectionPreviewResponse,
} from '../../client';
import { placementLabel } from './product-collection-placements';

const props = defineProps<{
  active: ManagerProductCollectionResponse;
  preview: ProductCollectionPreviewResponse | null;
  previewSaved: boolean;
  loading?: boolean;
}>();

const emit = defineEmits<{
  load: [surfaceKey: string, slotKey: string];
}>();

const savedPlacements = computed(() => props.active.placements || []);
const selectedIndex = ref(0);
const selectedPlacement = computed(() => savedPlacements.value[selectedIndex.value] || null);
const displayMode = computed(() => props.preview?.display_mode || selectedPlacement.value?.display_mode || 'grid');
const gridClass = computed(() => {
  if (displayMode.value === 'single') return 'preview-grid--single';
  if (displayMode.value === 'carousel') return 'preview-grid--carousel';
  if (displayMode.value === 'tiles') return 'preview-grid--tiles';
  const columns = props.preview?.grid_columns || selectedPlacement.value?.grid_columns || 4;
  if (columns <= 2) return 'preview-grid--2';
  if (columns === 3) return 'preview-grid--3';
  return 'preview-grid--4';
});
const selectedPlacementLabel = computed(() => selectedPlacement.value
  ? placementLabel(selectedPlacement.value)
  : 'Размещение не сохранено');
const modeLabel = computed(() => ({
  carousel: 'Слайдер', grid: 'Сетка', tiles: 'Плитки', single: 'Один товар',
}[displayMode.value]));
const publicationWarnings = computed(() => {
  const warnings: string[] = [];
  const placement = selectedPlacement.value;
  const now = Date.now();
  if (props.active.status === 'draft') warnings.push('Подборка сохранена как черновик и сейчас не показывается на сайте.');
  if (props.active.status === 'archived') warnings.push('Подборка находится в архиве и сейчас не показывается на сайте.');
  if (placement && !placement.is_enabled) warnings.push('Выбранное размещение выключено.');
  if (props.active.starts_at && new Date(props.active.starts_at).getTime() > now) warnings.push('Показ подборки начнётся по сохранённому расписанию позже.');
  if (placement?.starts_at && new Date(placement.starts_at).getTime() > now) warnings.push('Показ в выбранном месте начнётся по сохранённому расписанию позже.');
  if (props.active.ends_at && new Date(props.active.ends_at).getTime() <= now) warnings.push('Показ подборки по сохранённому расписанию уже завершён.');
  if (placement?.ends_at && new Date(placement.ends_at).getTime() <= now) warnings.push('Показ в выбранном месте по сохранённому расписанию уже завершён.');
  return warnings;
});

const load = () => {
  const placement = selectedPlacement.value;
  if (!placement || !props.previewSaved) return;
  emit('load', placement.surface_key, placement.slot_key);
};

const changePlacement = (event: Event) => {
  selectedIndex.value = Number((event.target as HTMLSelectElement).value);
  load();
};

watch(() => props.active.id, () => {
  selectedIndex.value = 0;
});
</script>

<template>
  <section class="rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900" data-testid="collection-preview">
    <div class="flex flex-wrap items-end justify-between gap-3">
      <div class="min-w-0 flex-1">
        <h2 class="font-bold">Предпросмотр сохранённой версии</h2>
        <p class="mt-1 text-xs text-slate-500">Показывает раскладку сохранённого состава для выбранного места. Локальные правки появятся здесь после сохранения.</p>
      </div>
      <button class="secondary-button" :disabled="!previewSaved || !selectedPlacement || loading" type="button" @click="load">
        <Loader2 v-if="loading" class="h-4 w-4 animate-spin" />
        <Eye v-else class="h-4 w-4" />
        {{ loading ? 'Загрузка…' : 'Обновить' }}
      </button>
    </div>

    <p v-if="!previewSaved" class="mt-4 rounded-lg bg-amber-50 p-3 text-sm text-amber-900">
      Сохраните изменения, чтобы проверить именно серверную версию подборки.
    </p>
    <p v-else-if="!savedPlacements.length" class="mt-4 rounded-lg bg-amber-50 p-3 text-sm text-amber-900">
      У подборки нет сохранённого размещения. Добавьте место показа и сохраните изменения.
    </p>

    <div v-else class="mt-4">
      <label v-if="savedPlacements.length > 1" class="block max-w-xl text-xs font-semibold text-slate-600">
        Место показа
        <select class="field-input" :value="selectedIndex" @change="changePlacement">
          <option v-for="(placement, index) in savedPlacements" :key="`${placement.surface_key}-${placement.slot_key}-${index}`" :value="index">
            {{ placementLabel(placement) }} · {{ placement.is_enabled ? 'включено' : 'выключено' }}
          </option>
        </select>
      </label>
      <div v-else class="rounded-lg bg-slate-50 px-3 py-2 text-sm dark:bg-slate-800">
        <strong class="break-words">{{ selectedPlacementLabel }}</strong>
        <span class="ml-2 text-xs text-slate-500">{{ selectedPlacement?.is_enabled ? 'включено' : 'выключено' }}</span>
      </div>

      <div v-if="preview" class="mt-4 space-y-3">
        <div class="flex flex-wrap gap-2 text-xs text-slate-600">
          <span class="preview-chip">{{ selectedPlacementLabel }}</span>
          <span class="preview-chip">{{ modeLabel }}</span>
          <span v-if="preview.item_limit" class="preview-chip">До {{ preview.item_limit }} товаров</span>
          <span v-if="displayMode === 'grid'" class="preview-chip">Колонок: {{ preview.grid_columns || selectedPlacement?.grid_columns || 4 }}</span>
        </div>

        <div v-if="publicationWarnings.length" class="space-y-2">
          <p v-for="warning in publicationWarnings" :key="warning" class="rounded-lg bg-slate-100 p-3 text-sm text-slate-700 dark:bg-slate-800 dark:text-slate-200">{{ warning }} Предпросмотр всё равно доступен для проверки макета.</p>
        </div>
        <p v-if="preview.rotation_mode === 'daily' || selectedPlacement?.rotation_mode === 'daily'" class="rounded-lg bg-blue-50 p-3 text-sm text-blue-900">
          При ежедневной смене сайт выбирает одну из подборок этого места. Здесь текущая подборка показана отдельно.
        </p>
        <p v-if="preview.fallback_used" class="rounded-lg bg-amber-50 p-3 text-sm text-amber-900">
          Основной состав не прошёл условия, поэтому показаны товары из резервной подборки.
        </p>
        <p v-else-if="preview.below_min_items" class="rounded-lg bg-amber-50 p-3 text-sm text-amber-900">
          Подходящих товаров меньше минимума. Без рабочего резерва блок на сайте будет скрыт.
        </p>

        <div v-if="preview.items?.length" class="preview-grid" :class="gridClass" :data-display-mode="displayMode">
          <article v-for="item in preview.items" :key="item.product.id" class="product-card">
            <div class="product-image">
              <img v-if="item.product.card_image || item.product.main_image" :src="item.product.card_image || item.product.main_image || ''" :alt="item.product.title" />
              <ImageOff v-else class="h-6 w-6 text-slate-400" />
            </div>
            <div class="min-w-0 p-3">
              <strong class="block break-words text-sm leading-snug">{{ item.product.title }}</strong>
              <p class="mt-2 font-bold">{{ item.product.price }} BYN</p>
              <p class="mt-1 text-xs text-slate-500">{{ item.selection_source === 'fallback' ? 'Из резерва' : item.selection_source === 'automatic' ? 'По правилу' : 'Добавлен вручную' }}</p>
            </div>
          </article>
        </div>
        <p v-else class="rounded-lg border border-dashed border-slate-300 p-6 text-center text-sm text-slate-500">
          Для этого размещения витрина не вернула товары.
        </p>

        <details v-if="preview.excluded_items?.length" class="rounded-lg border border-red-200 bg-red-50/40 p-3">
          <summary class="cursor-pointer text-sm font-bold text-red-900">Исключено товаров: {{ preview.excluded_items.length }}</summary>
          <div class="mt-2 divide-y divide-red-200">
            <div v-for="item in preview.excluded_items" :key="`${item.product_id}-${item.position}`" class="py-2 text-sm">
              <strong class="block break-words text-red-900">{{ item.product_title }}</strong>
              <span class="text-xs text-red-700">{{ item.reasons.join(' ') }}</span>
            </div>
          </div>
        </details>
      </div>
      <p v-else-if="!loading" class="mt-4 rounded-lg border border-dashed border-slate-300 p-6 text-center text-sm text-slate-500">
        Нажмите «Обновить», чтобы получить сохранённый результат с сервера.
      </p>
    </div>
  </section>
</template>

<style scoped>
.secondary-button { display:inline-flex; min-height:38px; align-items:center; justify-content:center; gap:6px; border:1px solid rgb(203 213 225); border-radius:8px; padding:0 12px; font-size:13px; font-weight:700; }
.secondary-button:disabled { opacity:.5; }
.field-input { display:block; width:100%; min-height:38px; margin-top:5px; border:1px solid rgb(203 213 225); border-radius:8px; background:transparent; padding:7px 10px; font-size:14px; }
.preview-chip { border-radius:999px; background:rgb(241 245 249); padding:5px 9px; }
.preview-grid { display:grid; gap:12px; }
.preview-grid--2 { grid-template-columns:repeat(2,minmax(0,1fr)); }
.preview-grid--3 { grid-template-columns:repeat(3,minmax(0,1fr)); }
.preview-grid--4 { grid-template-columns:repeat(4,minmax(0,1fr)); }
.preview-grid--tiles { grid-template-columns:repeat(2,minmax(0,1fr)); }
.preview-grid--tiles .product-card:first-child { grid-column:span 2; }
.preview-grid--single { grid-template-columns:minmax(0,360px); }
.preview-grid--carousel { grid-auto-flow:column; grid-auto-columns:minmax(220px,30%); overflow-x:auto; padding-bottom:6px; }
.product-card { min-width:0; overflow:hidden; border:1px solid rgb(226 232 240); border-radius:12px; background:white; }
.product-image { display:flex; aspect-ratio:4/3; align-items:center; justify-content:center; background:rgb(248 250 252); }
.product-image img { width:100%; height:100%; object-fit:contain; }
@media (max-width: 639px) {
  .preview-grid--2,.preview-grid--3,.preview-grid--4,.preview-grid--tiles { grid-template-columns:minmax(0,1fr); }
  .preview-grid--tiles .product-card:first-child { grid-column:auto; }
  .preview-grid--carousel { grid-auto-columns:minmax(210px,82%); }
}
:global(.dark) .field-input { border-color:rgb(71 85 105); }
:global(.dark) .preview-chip { background:rgb(30 41 59); }
:global(.dark) .product-card { background:rgb(15 23 42); border-color:rgb(51 65 85); }
:global(.dark) .product-image { background:rgb(30 41 59); }
</style>
