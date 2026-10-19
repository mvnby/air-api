<script setup lang="ts">
import { computed, ref } from "vue";
import { Check, Search, Star } from "lucide-vue-next";
import type { ManagerFeatureResponse } from "../../client";
import { FEATURE_DISPLAY_MODES, type FeatureDisplayMode } from "../features/feature-presentation";

export type FeatureAssignment = {
  feature_id: number;
  is_featured: boolean;
  display_mode?: FeatureDisplayMode | null;
};

const props = defineProps<{
  features: ManagerFeatureResponse[];
  modelValue: FeatureAssignment[];
  loading?: boolean;
}>();

const emit = defineEmits<{
  "update:modelValue": [value: FeatureAssignment[]];
}>();
const query = ref("");
const selected = computed(
  () => new Map(props.modelValue.map((item) => [item.feature_id, item])),
);
const featuredCount = computed(
  () => props.modelValue.filter((item) => item.is_featured).length,
);
const visibleFeatures = computed(() => {
  const needle = query.value.trim().toLocaleLowerCase("ru");
  return props.features.filter(
    (feature) =>
      !needle ||
      `${feature.name} ${feature.slug}`
        .toLocaleLowerCase("ru")
        .includes(needle),
  );
});

const toggle = (featureId: number) => {
  const current = selected.value.get(featureId);
  emit(
    "update:modelValue",
    current
      ? props.modelValue.filter((item) => item.feature_id !== featureId)
      : [...props.modelValue, { feature_id: featureId, is_featured: false }],
  );
};

const toggleFeatured = (featureId: number) => {
  const current = selected.value.get(featureId);
  if (!current) return;
  if (!current.is_featured && featuredCount.value >= 3) return;
  emit(
    "update:modelValue",
    props.modelValue.map((item) =>
      item.feature_id === featureId
        ? { ...item, is_featured: !item.is_featured }
        : item,
    ),
  );
};

const setDisplayMode = (featureId: number, event: Event) => {
  const mode = (event.target as HTMLSelectElement).value as FeatureDisplayMode;
  emit(
    "update:modelValue",
    props.modelValue.map((item) =>
      item.feature_id === featureId ? { ...item, display_mode: mode } : item,
    ),
  );
};
</script>

<template>
  <section
    class="space-y-3 border-t border-gray-200 pt-4 dark:border-slate-700"
  >
    <div class="flex flex-wrap items-start justify-between gap-3">
      <div>
        <h3
          class="text-sm font-bold uppercase tracking-[0.16em] text-gray-500 dark:text-slate-400"
        >
          Фичи серии
        </h3>
        <p class="mt-1 text-xs text-gray-500 dark:text-slate-400">
          Выберите общие фичи или фичи этого бренда. До трёх звёзд — главное для
          карточек. Вид показа на странице товара выбирается для каждой фичи.
        </p>
      </div>
      <span class="text-xs font-semibold text-amber-700 dark:text-amber-300"
        >Главные: {{ featuredCount }}/3</span
      >
    </div>
    <label class="relative block"
      ><Search class="absolute left-3 top-2.5 h-4 w-4 text-gray-400" /><input
        v-model="query"
        class="h-9 w-full rounded-lg border border-gray-200 bg-transparent pl-9 pr-3 text-sm dark:border-slate-700"
        placeholder="Найти фичу"
    /></label>
    <p v-if="loading" class="py-4 text-sm text-gray-500">Загрузка фич…</p>
    <div
      v-else
      class="max-h-80 divide-y divide-gray-100 overflow-y-auto rounded-xl border border-gray-200 dark:divide-slate-800 dark:border-slate-700"
    >
      <div
        v-for="feature in visibleFeatures"
        :key="feature.id"
        class="flex flex-wrap items-center gap-2 px-3 py-2.5"
      >
        <button
          type="button"
          class="flex h-7 w-7 shrink-0 items-center justify-center rounded border"
          :class="
            selected.has(feature.id)
              ? 'border-brand-600 bg-brand-600 text-white'
              : 'border-gray-300 text-transparent dark:border-slate-600'
          "
          :aria-pressed="selected.has(feature.id)"
          :aria-label="`${selected.has(feature.id) ? 'Убрать из серии' : 'Добавить в серию'}: ${feature.name}`"
          :title="
            selected.has(feature.id) ? 'Убрать из серии' : 'Добавить в серию'
          "
          @click="toggle(feature.id)"
        >
          <Check class="h-4 w-4" />
        </button>
        <button
          type="button"
          class="min-w-[100px] flex-1 text-left"
          @click="toggle(feature.id)"
        >
          <span
            class="block truncate text-sm font-semibold text-gray-900 dark:text-slate-100"
            >{{ feature.name }}</span
          ><span class="block truncate text-xs text-gray-500"
            >{{ feature.scope_type === "brand" ? "Брендовая" : "Общая" }} ·
            {{ feature.category.name }}</span
          >
        </button>
        <label v-if="selected.has(feature.id)" class="order-last ml-9 w-full sm:order-none sm:ml-0 sm:w-auto">
          <span class="sr-only">Вид показа: {{ feature.name }}</span>
          <select
            :value="selected.get(feature.id)?.display_mode || (selected.get(feature.id)?.is_featured ? 'detailed' : 'icon')"
            :aria-label="`Вид показа: ${feature.name}`"
            class="h-8 w-full rounded-md border border-gray-200 bg-transparent px-2 text-xs text-gray-700 dark:border-slate-700 dark:text-slate-200 sm:w-28"
            @change="setDisplayMode(feature.id, $event)"
          >
            <option v-for="mode in FEATURE_DISPLAY_MODES" :key="mode.value" :value="mode.value">{{ mode.label }}</option>
          </select>
        </label>
        <button
          v-if="selected.has(feature.id)"
          type="button"
          class="flex h-8 w-8 items-center justify-center rounded text-amber-500 hover:bg-amber-50 disabled:cursor-not-allowed disabled:opacity-30 dark:hover:bg-amber-950/30"
          :disabled="
            !selected.get(feature.id)?.is_featured && featuredCount >= 3
          "
          :title="
            selected.get(feature.id)?.is_featured
              ? 'Убрать из главных'
              : 'Отметить главной'
          "
          :aria-label="`${selected.get(feature.id)?.is_featured ? 'Убрать из главных' : 'Отметить главной'}: ${feature.name}`"
          :aria-pressed="selected.get(feature.id)?.is_featured"
          @click="toggleFeatured(feature.id)"
        >
          <Star
            class="h-4 w-4"
            :fill="
              selected.get(feature.id)?.is_featured ? 'currentColor' : 'none'
            "
          />
        </button>
      </div>
      <p v-if="!visibleFeatures.length" class="px-3 py-5 text-sm text-gray-500">
        Фичи не найдены.
      </p>
    </div>
  </section>
</template>
