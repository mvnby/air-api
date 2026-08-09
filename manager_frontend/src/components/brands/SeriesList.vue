<script setup lang="ts">
import type { ManagerBrand, ManagerBrandSeries } from "../../api";

const props = defineProps<{
  brand: ManagerBrand;
  items: ManagerBrandSeries[];
  loading: boolean;
  error: string;
  reordering: boolean;
  reorderDisabled: boolean;
  draggedId: number | null;
  dropTargetId: number | null;
  expandedIds: Set<number>;
}>();

const emit = defineEmits<{
  create: [];
  edit: [series: ManagerBrandSeries];
  delete: [series: ManagerBrandSeries];
  openProducts: [series: ManagerBrandSeries];
  toggleExpanded: [seriesId: number];
  toggleFromCard: [series: ManagerBrandSeries];
  dragStart: [event: DragEvent, series: ManagerBrandSeries];
  dragOver: [event: DragEvent, series: ManagerBrandSeries];
  dragLeave: [seriesId: number];
  drop: [series: ManagerBrandSeries];
  dragEnd: [];
}>();

const isExpanded = (seriesId: number) => props.expandedIds.has(seriesId);
const hasDetails = (series: ManagerBrandSeries) =>
  Boolean(
    series.tagline ||
    series.short_description ||
    series.description ||
    series.hero_image ||
    series.gallery_images?.length ||
    series.brand_features?.length ||
    series.content_blocks?.length ||
    series.footnotes?.length ||
    series.seo_title ||
    series.seo_description ||
    series.source_url,
  );
const onCardClick = (series: ManagerBrandSeries) => {
  if (hasDetails(series)) emit("toggleFromCard", series);
};
const productLabel = (count: number | undefined) => {
  const value = Math.max(0, Number(count) || 0);
  const mod100 = value % 100;
  const mod10 = value % 10;
  const noun =
    mod100 >= 11 && mod100 <= 14
      ? "товаров"
      : mod10 === 1
        ? "товар"
        : mod10 >= 2 && mod10 <= 4
          ? "товара"
          : "товаров";
  return `${value} ${noun}`;
};
</script>

<template>
  <div
    class="mx-3 my-3 rounded-2xl border border-teal-100 bg-white p-4 shadow-sm dark:border-teal-900/60 dark:bg-slate-900"
  >
    <div
      class="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between"
    >
      <div class="min-w-0">
        <p
          class="text-xs font-bold uppercase tracking-[0.18em] text-teal-600 dark:text-teal-300"
        >
          Серии бренда
        </p>
        <h2 class="text-lg font-bold text-gray-900 dark:text-white">
          {{ brand.title }}
        </h2>
        <p
          v-if="brand.description"
          class="mt-1 max-w-4xl text-sm text-gray-500 dark:text-slate-400"
        >
          {{ brand.description }}
        </p>
        <p class="mt-1 text-xs text-gray-500 dark:text-slate-400">
          Описания и фичи попадут на брендовые страницы и в блок связанных
          моделей. Порядок меняется перетаскиванием карточек.
        </p>
      </div>
      <div class="flex shrink-0 flex-wrap items-center gap-2">
        <div
          v-if="reordering"
          class="text-xs font-semibold text-teal-600 dark:text-teal-300"
        >
          Сохраняем порядок...
        </div>
        <button
          type="button"
          class="inline-flex items-center justify-center gap-2 rounded-lg bg-teal-600 px-4 py-2 text-sm font-medium text-white transition-all hover:bg-teal-500"
          @click.stop="emit('create')"
        >
          <span class="material-icons-round text-[18px]">add</span>Новая серия
        </button>
      </div>
    </div>
    <div
      v-if="error"
      class="mt-3 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-900/40 dark:bg-red-900/20 dark:text-red-300"
    >
      {{ error }}
    </div>
    <div v-if="loading" class="py-6 text-sm text-gray-500 dark:text-slate-400">
      Загрузка серий...
    </div>
    <div
      v-else-if="items.length === 0"
      class="mt-3 rounded-xl border border-dashed border-gray-300 px-4 py-8 text-sm text-gray-500 dark:border-slate-700 dark:text-slate-400"
    >
      У бренда пока нет серий. Можно добавить первую вручную.
    </div>
    <div v-else class="mt-3 space-y-2">
      <article
        v-for="series in items"
        :key="series.id"
        class="relative rounded-xl border border-gray-200 bg-slate-50 px-3 py-2.5 pr-20 transition-shadow dark:border-slate-700 dark:bg-slate-900/50 lg:pr-3"
        :class="[
          draggedId === series.id ? 'opacity-50' : '',
          hasDetails(series) ? 'cursor-pointer lg:cursor-default' : '',
        ]"
        :draggable="!reorderDisabled"
        @click="onCardClick(series)"
        @dragstart="emit('dragStart', $event, series)"
        @dragover="emit('dragOver', $event, series)"
        @dragleave="emit('dragLeave', series.id)"
        @drop.prevent="emit('drop', series)"
        @dragend="emit('dragEnd')"
      >
        <span
          v-if="dropTargetId === series.id"
          aria-hidden="true"
          class="pointer-events-none absolute -top-2 left-3 right-3 h-1 rounded-full bg-teal-400 shadow-[0_0_18px_rgba(20,184,166,0.75)] dark:bg-teal-300"
        />
        <div
          class="absolute right-2 top-2 z-10 inline-flex items-center gap-1 lg:hidden"
          @click.stop
        >
          <button
            type="button"
            class="inline-flex h-8 w-8 items-center justify-center rounded-lg border border-gray-200 bg-white/85 text-gray-600 shadow-sm backdrop-blur hover:text-teal-700 dark:border-slate-700 dark:bg-slate-900/85 dark:text-slate-300 dark:hover:text-teal-200"
            title="Изменить серию"
            aria-label="Изменить серию"
            @click.stop="emit('edit', series)"
          >
            <span class="material-icons-round text-[18px]">edit</span></button
          ><button
            type="button"
            class="inline-flex h-8 w-8 items-center justify-center rounded-lg border border-red-200 bg-white/85 text-red-500 shadow-sm backdrop-blur hover:bg-red-50 disabled:opacity-40 dark:border-red-900/60 dark:bg-slate-900/85 dark:hover:bg-red-950/30"
            :disabled="(series.products_count ?? 0) > 0"
            title="Удалить серию"
            aria-label="Удалить серию"
            @click.stop="emit('delete', series)"
          >
            <span class="material-icons-round text-[18px]">delete</span>
          </button>
        </div>
        <div class="flex flex-col gap-2 lg:flex-row lg:items-center lg:gap-3">
          <div class="flex min-w-0 flex-1 items-start gap-2">
            <button
              type="button"
              class="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-gray-200 text-gray-400 transition-colors dark:border-slate-700 dark:text-slate-500"
              :class="
                reorderDisabled
                  ? 'cursor-not-allowed opacity-40'
                  : 'cursor-grab hover:bg-white hover:text-teal-600 active:cursor-grabbing dark:hover:bg-slate-800 dark:hover:text-teal-300'
              "
              :disabled="reorderDisabled"
              title="Перетащите серию выше или ниже"
              @click.stop
            >
              <span class="material-icons-round text-[22px]"
                >drag_indicator</span
              ></button
            ><img
              v-if="series.hero_image"
              :src="series.hero_image"
              :alt="series.title"
              class="h-10 w-10 shrink-0 rounded-lg border border-gray-200 bg-white object-cover dark:border-slate-700"
            />
            <div class="min-w-0 flex-1">
              <div class="flex flex-wrap items-center gap-x-2 gap-y-1">
                <h3
                  class="min-w-0 break-words font-bold leading-tight text-gray-900 dark:text-slate-100"
                >
                  {{ series.title }}
                </h3>
                <span
                  class="inline-flex items-center rounded-full px-2 py-0.5 text-xs font-semibold"
                  :class="
                    series.is_published
                      ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300'
                      : 'bg-gray-100 text-gray-600 dark:bg-slate-700 dark:text-slate-300'
                  "
                  >{{ series.is_published ? "Публичная" : "Скрыта" }}</span
                ><button
                  type="button"
                  class="inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-xs font-semibold text-teal-700 transition-colors hover:bg-teal-50 hover:text-teal-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500 dark:text-teal-300 dark:hover:bg-teal-950/40 dark:hover:text-teal-100"
                  :title="`Показать товары серии ${series.title}`"
                  @click.stop="emit('openProducts', series)"
                >
                  {{ productLabel(series.products_count)
                  }}<span class="material-icons-round text-[14px]"
                    >arrow_outward</span
                  >
                </button>
              </div>
              <p class="text-xs font-mono text-gray-500 dark:text-slate-400">
                {{ series.slug }}
              </p>
              <p
                v-if="series.tagline"
                class="mt-0.5 text-sm font-semibold text-gray-700 dark:text-slate-200"
              >
                {{ series.tagline }}
              </p>
              <p
                v-else-if="series.short_description"
                class="mt-0.5 line-clamp-2 text-sm text-gray-500 dark:text-slate-400"
              >
                {{ series.short_description }}
              </p>
            </div>
          </div>
          <div class="hidden shrink-0 items-center gap-1 lg:inline-flex">
            <button
              v-if="hasDetails(series)"
              type="button"
              class="inline-flex items-center gap-1 rounded border border-gray-200 px-2.5 py-1 text-xs font-semibold hover:bg-white dark:border-slate-700 dark:hover:bg-slate-800"
              :aria-expanded="isExpanded(series.id)"
              @click.stop="emit('toggleExpanded', series.id)"
            >
              <span class="material-icons-round text-[16px]">{{
                isExpanded(series.id) ? "expand_less" : "expand_more"
              }}</span
              >Детали</button
            ><button
              type="button"
              class="rounded border border-gray-200 px-2.5 py-1 text-xs font-semibold hover:bg-white dark:border-slate-700 dark:hover:bg-slate-800"
              @click.stop="emit('edit', series)"
            >
              Изменить</button
            ><button
              type="button"
              class="rounded border border-red-200 px-2.5 py-1 text-xs font-semibold text-red-600 hover:bg-red-50 disabled:opacity-50"
              :disabled="(series.products_count ?? 0) > 0"
              @click.stop="emit('delete', series)"
            >
              Удалить
            </button>
          </div>
        </div>
        <div
          v-if="!isExpanded(series.id)"
          class="mt-2 flex flex-wrap gap-1.5 text-[11px] font-semibold"
        >
          <span
            v-if="series.gallery_images?.length"
            class="rounded-full bg-blue-50 px-2 py-0.5 text-blue-700 dark:bg-blue-950/30 dark:text-blue-200"
            >галерея {{ series.gallery_images.length }}</span
          ><span
            v-if="series.brand_features?.length"
            class="rounded-full bg-indigo-50 px-2 py-0.5 text-indigo-700 dark:bg-indigo-950/30 dark:text-indigo-200"
            >из библиотеки {{ series.brand_features.length }}</span
          ><span
            v-if="series.content_blocks?.length"
            class="rounded-full bg-amber-50 px-2 py-0.5 text-amber-700 dark:bg-amber-950/30 dark:text-amber-200"
            >контент {{ series.content_blocks.length }}</span
          ><span
            v-if="series.seo_title || series.seo_description"
            class="rounded-full bg-emerald-50 px-2 py-0.5 text-emerald-700 dark:bg-emerald-950/30 dark:text-emerald-200"
            >SEO</span
          >
        </div>
        <div
          v-if="isExpanded(series.id)"
          class="mt-2 border-t border-gray-200 pt-2 text-sm text-gray-600 dark:border-slate-700 dark:text-slate-300"
        >
          <p
            v-if="series.tagline"
            class="font-semibold text-gray-800 dark:text-slate-100"
          >
            {{ series.tagline }}
          </p>
          <p v-if="series.short_description" class="mt-1">
            {{ series.short_description }}
          </p>
          <p v-if="series.description">{{ series.description }}</p>
          <div
            v-if="series.brand_features?.length"
            class="mt-2 grid gap-1.5 sm:grid-cols-2"
          >
            <div
              v-for="feature in series.brand_features"
              :key="`${series.id}-brand-feature-${feature.id}`"
              class="rounded-lg border border-indigo-100 bg-indigo-50/60 px-2 py-1.5 text-xs dark:border-indigo-900/60 dark:bg-indigo-950/20"
            >
              <span
                class="font-semibold text-indigo-800 dark:text-indigo-100"
                >{{ feature.title }}</span
              >
              <p
                v-if="feature.text"
                class="mt-0.5 line-clamp-2 text-indigo-700/70 dark:text-indigo-200/70"
              >
                {{ feature.text }}
              </p>
            </div>
          </div>
        </div>
      </article>
    </div>
  </div>
</template>
