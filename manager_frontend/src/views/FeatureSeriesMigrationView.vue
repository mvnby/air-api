<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { ArrowLeft, RefreshCw } from "lucide-vue-next";
import { confirmDialog } from "../services/ui-feedback";
import { getApiErrorMessage } from "../utils/api-errors";
import {
  featureSeriesMigrationApi,
  type FeatureSeriesMigrationCandidate,
} from "../components/features/feature-series-migration-api";

const candidates = ref<FeatureSeriesMigrationCandidate[]>([]);
const selected = ref<Set<string>>(new Set());
const loading = ref(true);
const applying = ref(false);
const error = ref("");
const selectedCandidates = computed(() =>
  candidates.value.filter((candidate) =>
    selected.value.has(candidate.candidate_token),
  ),
);

const load = async () => {
  loading.value = true;
  error.value = "";
  try {
    const preview = await featureSeriesMigrationApi.preview();
    candidates.value = preview.candidates || [];
    selected.value = new Set();
  } catch (cause) {
    error.value = getApiErrorMessage(cause);
  } finally {
    loading.value = false;
  }
};

const toggle = (token: string) => {
  const next = new Set(selected.value);
  if (next.has(token)) next.delete(token);
  else next.add(token);
  selected.value = next;
};

const apply = async () => {
  if (!selectedCandidates.value.length || applying.value) return;
  if (
    !(await confirmDialog({
      title: "Перенести выбранные связи?",
      description: `Будет обработано кандидатов: ${selectedCandidates.value.length}. Изменения применятся только к показанному preview.`,
      confirmText: "Перенести",
      variant: "warning",
    }))
  )
    return;
  applying.value = true;
  error.value = "";
  try {
    await featureSeriesMigrationApi.apply(selectedCandidates.value);
    await load();
  } catch (cause) {
    const status = (cause as Error & { status?: number }).status;
    error.value =
      status === 409
        ? "Данные изменились. Preview обновлён — проверьте выбор и повторите."
        : getApiErrorMessage(cause);
    if (status === 409) await load();
  } finally {
    applying.value = false;
  }
};

onMounted(load);
</script>

<template>
  <div class="min-h-full bg-gray-50 px-4 py-6 dark:bg-slate-950 sm:px-6">
    <div class="mx-auto max-w-5xl">
      <div class="mb-5 flex flex-wrap items-center justify-between gap-3">
        <div>
          <a
            href="/manager/features"
            class="inline-flex items-center gap-1 text-sm font-semibold text-teal-700"
            ><ArrowLeft class="h-4 w-4" />К библиотеке фич</a
          >
          <h1 class="mt-2 text-2xl font-bold text-gray-950 dark:text-white">
            Перенос фич в серии
          </h1>
          <p class="mt-1 text-sm text-gray-500">
            Preview повторяющихся назначений товаров. Выберите только
            подтверждённые связи.
          </p>
        </div>
        <button
          type="button"
          class="inline-flex h-9 items-center gap-2 rounded-md border border-gray-200 px-3 text-sm font-semibold dark:border-slate-700"
          :disabled="loading"
          @click="load"
        >
          <RefreshCw class="h-4 w-4" />Обновить
        </button>
      </div>
      <p
        v-if="error"
        class="mb-4 rounded-md bg-red-50 px-4 py-3 text-sm text-red-700"
      >
        {{ error }}
      </p>
      <div v-if="loading" class="py-16 text-center text-sm text-gray-500">
        Собираем preview…
      </div>
      <template v-else
        ><div class="mb-3 flex items-center justify-between">
          <span class="text-sm text-gray-500"
            >Выбрано: {{ selectedCandidates.length }} из
            {{ candidates.length }}</span
          ><button
            type="button"
            class="h-9 rounded-md bg-teal-600 px-4 text-sm font-semibold text-white disabled:opacity-50"
            :disabled="!selectedCandidates.length || applying"
            @click="apply"
          >
            {{ applying ? "Перенос…" : "Перенести выбранные" }}
          </button>
        </div>
        <div
          class="overflow-hidden border-y border-gray-200 bg-white dark:border-slate-800 dark:bg-slate-950"
        >
          <label
            v-for="candidate in candidates"
            :key="candidate.candidate_token"
            class="flex cursor-pointer items-center gap-3 border-b border-gray-100 px-4 py-3 last:border-0 dark:border-slate-800"
            ><input
              type="checkbox"
              :checked="selected.has(candidate.candidate_token)"
              @change="toggle(candidate.candidate_token)"
            /><span class="min-w-0 flex-1"
              ><span
                class="block font-semibold text-gray-950 dark:text-white"
                >{{ candidate.feature_name }}</span
              ><span class="block text-xs text-gray-500"
                >{{ candidate.brand_title }} ·
                {{ candidate.series_title }}</span
              ></span
            ><span class="text-right text-xs font-semibold text-gray-500"
              >{{ candidate.matching_assignments_count }} из
              {{ candidate.published_products_count }} товаров</span
            ></label
          >
          <p
            v-if="!candidates.length"
            class="px-4 py-16 text-center text-sm text-gray-500"
          >
            Подходящих повторяющихся связей нет.
          </p>
        </div></template
      >
    </div>
  </div>
</template>
