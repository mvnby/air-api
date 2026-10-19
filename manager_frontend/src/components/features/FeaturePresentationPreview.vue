<script setup lang="ts">
import { computed } from "vue";
import {
  FEATURE_DISPLAY_MODES,
  featureIconLabel,
  featureIconUrl,
  type FeaturePresentationContent,
} from "./feature-presentation";

const props = defineProps<{ feature: FeaturePresentationContent }>();
const iconUrl = computed(() => featureIconUrl(props.feature));
const iconLabel = computed(() => featureIconLabel(props.feature));
</script>

<template>
  <section class="space-y-3" aria-label="Предпросмотр фичи">
    <div>
      <h3 class="text-sm font-bold text-gray-900 dark:text-slate-100">Три способа показать фичу</h3>
      <p class="mt-1 text-xs text-gray-500 dark:text-slate-400">
        Вид выбирается отдельно для каждой серии. Звезда отмечает главную фичу для карточки.
      </p>
    </div>
    <div class="grid gap-3 sm:grid-cols-2">
      <article
        v-for="mode in FEATURE_DISPLAY_MODES"
        :key="mode.value"
        :data-feature-preview="mode.value"
        class="rounded-xl border border-gray-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-900"
        :class="{ 'sm:col-span-2': mode.value === 'detailed' }"
      >
        <h4 class="mb-4 text-[11px] font-bold uppercase tracking-wider text-gray-500 dark:text-slate-400">{{ mode.label }}</h4>
        <div :class="mode.value === 'icon' ? 'flex flex-col items-start gap-2' : 'flex items-start gap-3'">
          <img
            v-if="iconUrl"
            :src="iconUrl"
            alt=""
            class="h-12 w-12 shrink-0 object-contain"
          />
          <span
            v-else
            class="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-brand-50 text-lg font-bold text-brand-700"
            aria-hidden="true"
          >{{ (feature.name || 'Ф').charAt(0) }}</span>
          <div class="min-w-0">
            <p
              class="break-words text-sm font-semibold text-gray-900 dark:text-slate-100"
              :title="mode.value === 'icon' ? iconLabel : undefined"
            >{{ mode.value === 'icon' ? iconLabel || 'Подпись к иконке' : feature.name || 'Название фичи' }}</p>
            <p
              v-if="mode.value !== 'icon'"
              class="mt-1 whitespace-pre-line break-words text-sm leading-relaxed text-gray-600 dark:text-slate-300"
            >{{ mode.value === 'detailed' ? feature.full_description || feature.short_description || 'Добавьте полное описание.' : feature.short_description || 'Добавьте краткое описание.' }}</p>
          </div>
        </div>
        <img
          v-if="mode.value === 'detailed' && feature.image_url"
          :src="feature.image_url"
          :alt="feature.name || 'Иллюстрация фичи'"
          class="mt-4 max-h-52 w-full rounded-lg object-contain"
        />
      </article>
    </div>
  </section>
</template>
