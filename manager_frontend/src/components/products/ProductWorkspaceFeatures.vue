<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { Check, Trash2 } from "lucide-vue-next";
import {
  ManagerFeaturesService,
  type FeatureLinkPayload,
  type ManagerFeatureResponse,
  type ManagerProductFeatureWorkspaceResponse,
  type PublicFeatureResponse,
} from "../../client";
import type { Product } from "../../api";
import { getApiErrorMessage } from "../../utils/api-errors";

const props = defineProps<{ product: Product }>();

type FeatureWorkspace = ManagerProductFeatureWorkspaceResponse & {
  effective: PublicFeatureResponse[];
  automatic_suggestions: PublicFeatureResponse[];
  inherited: PublicFeatureResponse[];
  manual: PublicFeatureResponse[];
  manual_assignments: FeatureLinkPayload[];
  disabled_feature_ids: number[];
};

const normalizeWorkspace = (
  data: ManagerProductFeatureWorkspaceResponse,
): FeatureWorkspace => ({
  ...data,
  effective: data.effective || [],
  automatic_suggestions: data.automatic_suggestions || [],
  inherited: data.inherited || [],
  manual: data.manual || [],
  manual_assignments: data.manual_assignments || [],
  disabled_feature_ids: data.disabled_feature_ids || [],
});

const workspace = ref<FeatureWorkspace | null>(null);
const library = ref<ManagerFeatureResponse[]>([]);
const assignments = ref<FeatureLinkPayload[]>([]);
const loading = ref(true);
const saving = ref(false);
const error = ref("");
const query = ref("");

const sourceLabels: Record<string, string> = {
  product_manual: "Добавлена к товару",
  series: "От серии",
  brand: "От бренда",
  derived: "По правилу",
};

const effectiveMap = computed(
  () =>
    new Map((workspace.value?.effective || []).map((item) => [item.id, item])),
);
const inheritedIds = computed(
  () =>
    new Set([
      ...(workspace.value?.inherited || []).map((item) => item.id),
      ...(workspace.value?.effective || [])
        .filter(
          (item) =>
            item.source === "series" ||
            item.source === "brand" ||
            item.source === "derived",
        )
        .map((item) => item.id),
    ]),
);
const visibleLibrary = computed(() => {
  const needle = query.value.trim().toLocaleLowerCase("ru");
  return library.value.filter(
    (item) =>
      !needle ||
      `${item.name} ${item.slug}`.toLocaleLowerCase("ru").includes(needle),
  );
});

const syncAssignments = (data: ManagerProductFeatureWorkspaceResponse) => {
  assignments.value = (data.manual_assignments || []).map((item) => ({
    ...item,
  }));
};

const load = async () => {
  loading.value = true;
  error.value = "";
  try {
    const [featureData, libraryData] = await Promise.all([
      ManagerFeaturesService.getManagerProductFeatures(props.product.id),
      ManagerFeaturesService.listManagerFeatures(
        undefined,
        undefined,
        undefined,
        props.product.id,
        undefined,
        true,
      ),
    ]);
    workspace.value = normalizeWorkspace(featureData);
    library.value = libraryData.items;
    syncAssignments(featureData);
  } catch (cause) {
    error.value = getApiErrorMessage(cause);
  } finally {
    loading.value = false;
  }
};

const persist = async () => {
  if (saving.value) return;
  saving.value = true;
  error.value = "";
  try {
    const next = await ManagerFeaturesService.updateManagerProductFeatures(
      props.product.id,
      {
        assignments: assignments.value,
      },
    );
    workspace.value = normalizeWorkspace(next);
    syncAssignments(workspace.value);
  } catch (cause) {
    error.value = getApiErrorMessage(cause);
  } finally {
    saving.value = false;
  }
};

const toggleFeature = async (feature: ManagerFeatureResponse) => {
  if (workspace.value?.disabled_feature_ids.includes(feature.id)) {
    await toggleInherited(feature);
    return;
  }
  if (inheritedIds.value.has(feature.id)) {
    await toggleInherited(feature);
    return;
  }
  const index = assignments.value.findIndex(
    (item) => item.feature_id === feature.id,
  );
  if (index >= 0) assignments.value.splice(index, 1);
  else
    assignments.value.push({
      feature_id: feature.id,
      source: "manual",
      is_enabled: true,
      sort_order: feature.sort_order,
    });
  await persist();
};

const toggleInherited = async (feature: {
  id: number;
  sort_order?: number;
}) => {
  const index = assignments.value.findIndex(
    (item) => item.feature_id === feature.id,
  );
  if (index >= 0) assignments.value.splice(index, 1);
  else
    assignments.value.push({
      feature_id: feature.id,
      source: "manual",
      is_enabled: false,
      sort_order: feature.sort_order || 0,
    });
  await persist();
};

onMounted(load);
</script>

<template>
  <section class="min-w-0 bg-white p-5 shadow-sm dark:bg-slate-900 sm:p-6">
    <div
      class="mb-5 flex flex-wrap items-start justify-between gap-3 border-b border-gray-200 pb-4 dark:border-slate-800"
    >
      <div>
        <h2 class="text-lg font-bold text-gray-950 dark:text-white">
          Фичи товара
        </h2>
        <p class="mt-1 text-sm text-gray-500">
          Добавьте фичу или скройте унаследованную только для этой модели.
        </p>
      </div>
      <span v-if="saving" class="text-xs font-semibold text-teal-700"
        >Сохранение…</span
      >
    </div>
    <p
      v-if="error"
      class="mb-4 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700"
    >
      {{ error }}
    </p>
    <div v-if="loading" class="py-16 text-center text-sm text-gray-500">
      Загрузка фич…
    </div>
    <template v-else-if="workspace">
      <section class="mb-7">
        <h3
          class="mb-3 text-xs font-bold uppercase tracking-[0.16em] text-gray-500"
        >
          Действуют на товаре
        </h3>
        <div
          class="divide-y divide-gray-100 border-y border-gray-200 dark:divide-slate-800 dark:border-slate-800"
        >
          <div
            v-for="feature in workspace.effective"
            :key="feature.id"
            class="flex items-center gap-3 py-3"
          >
            <img
              v-if="feature.icon_url || feature.image_url"
              :src="feature.icon_url || feature.image_url || ''"
              class="h-9 w-9 rounded-md object-cover"
              alt=""
            />
            <div class="min-w-0 flex-1">
              <p class="truncate font-semibold text-gray-950 dark:text-white">
                {{ feature.name }}
              </p>
              <p class="truncate text-xs text-gray-500">
                {{ feature.category.name }} · {{ sourceLabels[feature.source] }}
              </p>
            </div>
            <button
              v-if="inheritedIds.has(feature.id)"
              type="button"
              class="h-8 rounded-md border border-gray-200 px-2 text-xs font-semibold text-gray-600 dark:border-slate-700"
              @click="toggleInherited(feature)"
            >
              Скрыть
            </button>
            <button
              v-else
              type="button"
              class="flex h-8 w-8 items-center justify-center rounded-md text-gray-400 hover:bg-red-50 hover:text-red-600"
              title="Убрать с товара"
              @click="
                toggleFeature(library.find((item) => item.id === feature.id)!)
              "
            >
              <Trash2 class="h-4 w-4" />
            </button>
          </div>
          <p
            v-if="!workspace.effective.length"
            class="py-5 text-sm text-gray-500"
          >
            Для товара пока нет фич
          </p>
        </div>
      </section>

      <section>
        <div class="mb-3 flex flex-wrap items-center justify-between gap-2">
          <h3
            class="text-xs font-bold uppercase tracking-[0.16em] text-gray-500"
          >
            Библиотека
          </h3>
          <input
            v-model="query"
            class="h-9 w-full rounded-md border border-gray-200 bg-transparent px-3 text-sm dark:border-slate-700 sm:w-64"
            placeholder="Найти фичу"
          />
        </div>
        <div
          class="divide-y divide-gray-100 border-y border-gray-200 dark:divide-slate-800 dark:border-slate-800"
        >
          <div v-for="feature in visibleLibrary" :key="feature.id" class="py-3">
            <div class="flex items-center gap-3">
              <button
                type="button"
                class="flex h-8 w-8 shrink-0 items-center justify-center rounded-md border"
                :class="
                  effectiveMap.has(feature.id)
                    ? 'border-teal-600 bg-teal-600 text-white'
                    : 'border-gray-300 text-transparent dark:border-slate-600'
                "
                :title="effectiveMap.has(feature.id) ? 'Убрать' : 'Добавить'"
                @click="toggleFeature(feature)"
              >
                <Check class="h-4 w-4" />
              </button>
              <div class="min-w-0 flex-1">
                <p class="truncate font-semibold text-gray-900 dark:text-white">
                  {{ feature.name }}
                </p>
                <p class="truncate text-xs text-gray-500">
                  {{ feature.category.name }} · {{ feature.slug }}
                </p>
              </div>
              <span
                v-if="workspace.disabled_feature_ids.includes(feature.id)"
                class="text-xs font-semibold text-amber-700"
                >Скрыта у товара</span
              >
            </div>
          </div>
        </div>
      </section>
    </template>
  </section>
</template>
