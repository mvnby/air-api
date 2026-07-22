<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { Check, ChevronDown, ChevronUp, Plus, Sparkles, Trash2 } from 'lucide-vue-next';
import {
  ManagerFeaturesService,
  type FeatureLinkPayload,
  type ManagerFeatureResponse,
  type ManagerProductFeatureWorkspaceResponse,
  type PublicFeatureResponse,
} from '../../client';
import type { Product } from '../../api';
import { getApiErrorMessage } from '../../utils/api-errors';

const props = defineProps<{ product: Product }>();

type FeatureWorkspace = ManagerProductFeatureWorkspaceResponse & {
  effective: PublicFeatureResponse[];
  automatic_suggestions: PublicFeatureResponse[];
  inherited: PublicFeatureResponse[];
  manual: PublicFeatureResponse[];
  manual_assignments: FeatureLinkPayload[];
  disabled_feature_ids: number[];
};

const normalizeWorkspace = (data: ManagerProductFeatureWorkspaceResponse): FeatureWorkspace => ({
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
const error = ref('');
const query = ref('');
const expandedId = ref<number | null>(null);

const sourceLabels: Record<string, string> = {
  product_override: 'Переопределена', product_manual: 'Вручную', series: 'От серии', brand: 'От бренда', derived: 'По правилу',
};

const assignmentMap = computed(() => new Map(assignments.value.map((item) => [item.feature_id, item])));
const effectiveMap = computed(() => new Map((workspace.value?.effective || []).map((item) => [item.id, item])));
const inheritedIds = computed(() => new Set((workspace.value?.inherited || []).map((item) => item.id)));
const derivedIds = computed(() => new Set(
  (workspace.value?.effective || []).filter((item) => item.source === 'derived').map((item) => item.id),
));
const visibleLibrary = computed(() => {
  const needle = query.value.trim().toLocaleLowerCase('ru');
  return library.value.filter((item) => !needle || `${item.name} ${item.slug}`.toLocaleLowerCase('ru').includes(needle));
});

const syncAssignments = (data: ManagerProductFeatureWorkspaceResponse) => {
  assignments.value = (data.manual_assignments || []).map((item) => ({ ...item }));
};

const load = async () => {
  loading.value = true;
  error.value = '';
  try {
    const [featureData, libraryData] = await Promise.all([
      ManagerFeaturesService.getManagerProductFeatures(props.product.id),
      ManagerFeaturesService.listManagerFeatures(undefined, undefined, undefined, undefined, true),
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
  error.value = '';
  try {
    const next = await ManagerFeaturesService.updateManagerProductFeatures(props.product.id, {
      assignments: assignments.value,
    });
    workspace.value = normalizeWorkspace(next);
    syncAssignments(workspace.value);
  } catch (cause) {
    error.value = getApiErrorMessage(cause);
  } finally {
    saving.value = false;
  }
};

const toggleFeature = async (feature: ManagerFeatureResponse) => {
  if (derivedIds.value.has(feature.id)) {
    workspace.value = normalizeWorkspace(await ManagerFeaturesService.deleteManagerProductFeature(props.product.id, feature.id));
    syncAssignments(workspace.value);
    return;
  }
  if (inheritedIds.value.has(feature.id)) {
    await toggleInherited(feature);
    return;
  }
  const index = assignments.value.findIndex((item) => item.feature_id === feature.id);
  if (index >= 0) assignments.value.splice(index, 1);
  else assignments.value.push({ feature_id: feature.id, source: 'manual', is_enabled: true, sort_order: feature.sort_order });
  await persist();
};

const toggleInherited = async (feature: { id: number; sort_order?: number }) => {
  const index = assignments.value.findIndex((item) => item.feature_id === feature.id);
  if (index >= 0) assignments.value.splice(index, 1);
  else assignments.value.push({ feature_id: feature.id, source: 'manual', is_enabled: false, sort_order: feature.sort_order || 0 });
  await persist();
};

const applySuggestions = async (ids: number[]) => {
  if (!ids.length || saving.value) return;
  saving.value = true;
  try {
    workspace.value = normalizeWorkspace(await ManagerFeaturesService.applyManagerProductFeatureSuggestions(
      props.product.id, { feature_ids: ids },
    ));
    syncAssignments(workspace.value);
  } catch (cause) {
    error.value = getApiErrorMessage(cause);
  } finally {
    saving.value = false;
  }
};

const overrideFor = (featureId: number) => assignmentMap.value.get(featureId);
const expandOverride = (feature: ManagerFeatureResponse) => {
  const existing = overrideFor(feature.id);
  if (!existing) assignments.value.push({ feature_id: feature.id, source: 'manual', is_enabled: true, sort_order: feature.sort_order });
  expandedId.value = expandedId.value === feature.id ? null : feature.id;
};

onMounted(load);
</script>

<template>
  <section class="min-w-0 bg-white p-5 shadow-sm dark:bg-slate-900 sm:p-6">
    <div class="mb-5 flex flex-wrap items-start justify-between gap-3 border-b border-gray-200 pb-4 dark:border-slate-800">
      <div><h2 class="text-lg font-bold text-gray-950 dark:text-white">Фичи товара</h2><p class="mt-1 text-sm text-gray-500">Наследование, точечные overrides и автоматические правила</p></div>
      <span v-if="saving" class="text-xs font-semibold text-teal-700">Сохранение…</span>
    </div>
    <p v-if="error" class="mb-4 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">{{ error }}</p>
    <div v-if="loading" class="py-16 text-center text-sm text-gray-500">Загрузка фич…</div>
    <template v-else-if="workspace">
      <section v-if="workspace.automatic_suggestions.length" class="mb-6 border-y border-teal-200 bg-teal-50/70 py-4 dark:border-teal-900 dark:bg-teal-950/20">
        <div class="mb-3 flex items-center justify-between gap-3"><div class="flex items-center gap-2"><Sparkles class="h-4 w-4 text-teal-600" /><h3 class="font-bold text-teal-950 dark:text-teal-100">Автоматические предложения</h3></div><button type="button" class="h-8 rounded-md bg-teal-600 px-3 text-xs font-semibold text-white" @click="applySuggestions(workspace.automatic_suggestions.map(item => item.id))">Применить все</button></div>
        <div class="flex flex-wrap gap-2"><button v-for="feature in workspace.automatic_suggestions" :key="feature.id" type="button" class="inline-flex items-center gap-2 rounded-md border border-teal-200 bg-white px-3 py-2 text-left text-sm dark:border-teal-800 dark:bg-slate-900" :title="feature.applied_rule || ''" @click="applySuggestions([feature.id])"><Plus class="h-4 w-4" />{{ feature.name }}</button></div>
      </section>

      <section class="mb-7">
        <h3 class="mb-3 text-xs font-bold uppercase tracking-[0.16em] text-gray-500">Действуют на товаре</h3>
        <div class="divide-y divide-gray-100 border-y border-gray-200 dark:divide-slate-800 dark:border-slate-800">
          <div v-for="feature in workspace.effective" :key="feature.id" class="flex items-center gap-3 py-3">
            <img v-if="feature.icon_url || feature.image_url" :src="feature.icon_url || feature.image_url || ''" class="h-9 w-9 rounded-md object-cover" alt="" />
            <div class="min-w-0 flex-1"><p class="truncate font-semibold text-gray-950 dark:text-white">{{ feature.name }}</p><p class="truncate text-xs text-gray-500">{{ feature.category.name }} · {{ sourceLabels[feature.source] }}</p></div>
            <button v-if="inheritedIds.has(feature.id)" type="button" class="h-8 rounded-md border border-gray-200 px-2 text-xs font-semibold text-gray-600 dark:border-slate-700" @click="toggleInherited(feature)">Скрыть</button>
            <button v-else type="button" class="flex h-8 w-8 items-center justify-center rounded-md text-gray-400 hover:bg-red-50 hover:text-red-600" title="Убрать с товара" @click="toggleFeature(library.find(item => item.id === feature.id)!)"><Trash2 class="h-4 w-4" /></button>
          </div>
          <p v-if="!workspace.effective.length" class="py-5 text-sm text-gray-500">Для товара пока нет фич</p>
        </div>
      </section>

      <section>
        <div class="mb-3 flex flex-wrap items-center justify-between gap-2"><h3 class="text-xs font-bold uppercase tracking-[0.16em] text-gray-500">Библиотека</h3><input v-model="query" class="h-9 w-full rounded-md border border-gray-200 bg-transparent px-3 text-sm dark:border-slate-700 sm:w-64" placeholder="Найти фичу" /></div>
        <div class="divide-y divide-gray-100 border-y border-gray-200 dark:divide-slate-800 dark:border-slate-800">
          <div v-for="feature in visibleLibrary" :key="feature.id" class="py-3">
            <div class="flex items-center gap-3">
              <button type="button" class="flex h-8 w-8 shrink-0 items-center justify-center rounded-md border" :class="effectiveMap.has(feature.id) ? 'border-teal-600 bg-teal-600 text-white' : 'border-gray-300 text-transparent dark:border-slate-600'" :title="effectiveMap.has(feature.id) ? 'Убрать' : 'Добавить'" @click="toggleFeature(feature)"><Check class="h-4 w-4" /></button>
              <div class="min-w-0 flex-1"><p class="truncate font-semibold text-gray-900 dark:text-white">{{ feature.name }}</p><p class="truncate text-xs text-gray-500">{{ feature.category.name }} · {{ feature.slug }}</p></div>
              <span v-if="workspace.disabled_feature_ids.includes(feature.id)" class="text-xs font-semibold text-amber-700">Скрыта</span>
              <button type="button" class="flex h-8 items-center gap-1 rounded-md px-2 text-xs font-semibold text-gray-500 hover:bg-gray-100 dark:hover:bg-slate-800" @click="expandOverride(feature)">Override<ChevronUp v-if="expandedId === feature.id" class="h-3.5 w-3.5" /><ChevronDown v-else class="h-3.5 w-3.5" /></button>
            </div>
            <div v-if="expandedId === feature.id && overrideFor(feature.id)" class="mt-3 grid gap-2 pl-11 sm:grid-cols-2">
              <label><span class="block text-xs font-semibold text-gray-500">Название</span><input v-model="overrideFor(feature.id)!.override_title" class="mt-1 h-9 w-full rounded-md border border-gray-200 bg-transparent px-3 text-sm dark:border-slate-700" :placeholder="feature.name" /></label>
              <label><span class="block text-xs font-semibold text-gray-500">Изображение</span><input v-model="overrideFor(feature.id)!.override_image_url" class="mt-1 h-9 w-full rounded-md border border-gray-200 bg-transparent px-3 text-sm dark:border-slate-700" placeholder="https://…" /></label>
              <label class="sm:col-span-2"><span class="block text-xs font-semibold text-gray-500">Описание</span><textarea v-model="overrideFor(feature.id)!.override_description" rows="2" class="mt-1 w-full rounded-md border border-gray-200 bg-transparent px-3 py-2 text-sm dark:border-slate-700" /></label>
              <div class="sm:col-span-2 flex justify-end"><button type="button" class="h-8 rounded-md bg-teal-600 px-3 text-xs font-semibold text-white" @click="persist">Сохранить override</button></div>
            </div>
          </div>
        </div>
      </section>
    </template>
  </section>
</template>
