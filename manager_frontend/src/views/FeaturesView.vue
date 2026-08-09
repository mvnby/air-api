<script setup lang="ts">
import { onMounted, ref } from "vue";
import { Archive, Plus, Search } from "lucide-vue-next";
import {
  ManagerBrandsService,
  ManagerFeaturesService,
  type FeatureCategoryResponse,
  type ManagerBrandResponse,
  type ManagerFeatureResponse,
} from "../client";
import FeatureEditorDrawer from "../components/features/FeatureEditorDrawer.vue";
import { getApiErrorMessage } from "../utils/api-errors";
import { confirmDialog } from "../services/ui-feedback";

type CatalogFeature = ManagerFeatureResponse & {
  replaces_feature_id?: number | null;
};

const categories = ref<FeatureCategoryResponse[]>([]);
const items = ref<CatalogFeature[]>([]);
const brands = ref<ManagerBrandResponse[]>([]);
const replacementFeatures = ref<CatalogFeature[]>([]);
const loading = ref(true);
const error = ref("");
const search = ref("");
const categoryId = ref<number | "">("");
const brandId = ref<number | "">("");
const scope = ref<"universal" | "brand" | "">("");
const showArchived = ref(false);
const editorOpen = ref(false);
const editingFeature = ref<CatalogFeature | null>(null);

const scopeLabels: Record<"universal" | "brand", string> = {
  universal: "Общая",
  brand: "Брендовая",
};

const sourceCount = (item: ManagerFeatureResponse) =>
  Number(item.brands_count || 0) +
  Number(item.series_count || 0) +
  Number(item.products_count || 0);

const load = async () => {
  loading.value = true;
  error.value = "";
  try {
    const [categoryRows, brandRows, response] = await Promise.all([
      categories.value.length
        ? Promise.resolve(categories.value)
        : ManagerFeaturesService.listManagerFeatureCategories(),
      brands.value.length
        ? Promise.resolve({ items: brands.value })
        : ManagerBrandsService.listManagerBrands(),
      ManagerFeaturesService.listManagerFeatures(
        search.value.trim() || undefined,
        categoryId.value || undefined,
        brandId.value || undefined,
        undefined,
        scope.value || undefined,
        !showArchived.value,
      ),
    ]);
    categories.value = categoryRows;
    brands.value = brandRows.items;
    items.value = response.items;
  } catch (cause) {
    error.value = getApiErrorMessage(cause);
  } finally {
    loading.value = false;
  }
};

const loadReplacementFeatures = async () => {
  try {
    const response = await ManagerFeaturesService.listManagerFeatures(
      undefined,
      undefined,
      undefined,
      undefined,
      "universal",
      true,
    );
    replacementFeatures.value = response.items;
  } catch (cause) {
    error.value = getApiErrorMessage(cause);
  }
};

const openCreate = async () => {
  editingFeature.value = null;
  editorOpen.value = true;
  await loadReplacementFeatures();
};

const openEdit = async (feature: CatalogFeature) => {
  editingFeature.value = feature;
  editorOpen.value = true;
  await loadReplacementFeatures();
};

const closeEditor = () => {
  editorOpen.value = false;
  editingFeature.value = null;
};

const onEditorSaved = async () => {
  closeEditor();
  await load();
};

const archive = async (feature: CatalogFeature) => {
  const confirmed = await confirmDialog({
    title: "Архивировать фичу?",
    description: feature.name,
    confirmText: "Архивировать",
    variant: "warning",
  });
  if (!confirmed) return;

  try {
    await ManagerFeaturesService.archiveManagerFeature(feature.id);
    await load();
  } catch (cause) {
    error.value = getApiErrorMessage(cause);
  }
};

const toggleArchived = async () => {
  showArchived.value = !showArchived.value;
  await load();
};

onMounted(load);
</script>

<template>
  <div class="min-h-full bg-gray-50 px-4 py-6 dark:bg-slate-950 sm:px-6">
    <div class="mx-auto max-w-[1500px]">
      <header class="mb-5 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 class="text-2xl font-bold text-gray-950 dark:text-white">
            Библиотека фич
          </h1>
          <p class="mt-1 text-sm text-gray-500 dark:text-slate-400">
            Единые преимущества для брендов, серий и товаров
          </p>
        </div>
        <div class="flex items-center gap-2">
          <a
            href="/manager/features/series-migration"
            class="inline-flex h-10 items-center rounded-md border border-gray-200 px-3 text-sm font-semibold text-gray-700 hover:bg-gray-100 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800"
          >
            Перенос в серии
          </a>
          <button
            type="button"
            class="inline-flex h-10 items-center gap-2 rounded-md bg-teal-600 px-4 text-sm font-semibold text-white hover:bg-teal-700"
            @click="openCreate"
          >
            <Plus class="h-4 w-4" />
            Новая фича
          </button>
        </div>
      </header>

      <div
        class="mb-4 grid gap-2 border-y border-gray-200 bg-white py-3 dark:border-slate-800 dark:bg-slate-950 lg:grid-cols-[minmax(220px,1fr)_190px_190px_160px_auto]"
      >
        <label class="relative">
          <Search class="absolute left-3 top-2.5 h-4 w-4 text-gray-400" />
          <input
            v-model="search"
            class="h-9 w-full rounded-md border border-gray-200 bg-transparent pl-9 pr-3 text-sm dark:border-slate-700"
            placeholder="Название или slug"
            @keyup.enter="load"
          />
        </label>
        <select
          v-model="categoryId"
          class="h-9 rounded-md border border-gray-200 bg-transparent px-3 text-sm dark:border-slate-700"
          @change="load"
        >
          <option value="">Все категории</option>
          <option
            v-for="category in categories"
            :key="category.id"
            :value="category.id"
          >
            {{ category.name }}
          </option>
        </select>
        <select
          v-model="brandId"
          class="h-9 rounded-md border border-gray-200 bg-transparent px-3 text-sm dark:border-slate-700"
          @change="load"
        >
          <option value="">Все бренды</option>
          <option v-for="brand in brands" :key="brand.id" :value="brand.id">
            {{ brand.title }}
          </option>
        </select>
        <select
          v-model="scope"
          class="h-9 rounded-md border border-gray-200 bg-transparent px-3 text-sm dark:border-slate-700"
          @change="load"
        >
          <option value="">Все виды</option>
          <option
            v-for="(label, value) in scopeLabels"
            :key="value"
            :value="value"
          >
            {{ label }}
          </option>
        </select>
        <button
          type="button"
          class="inline-flex h-9 items-center justify-center gap-2 rounded-md border border-gray-200 px-3 text-sm font-semibold dark:border-slate-700"
          :class="
            showArchived
              ? 'bg-gray-900 text-white dark:bg-white dark:text-slate-950'
              : ''
          "
          @click="toggleArchived"
        >
          <Archive class="h-4 w-4" />
          Архив
        </button>
      </div>

      <p
        v-if="error"
        class="mb-4 rounded-md bg-red-50 px-4 py-3 text-sm text-red-700"
      >
        {{ error }}
      </p>
      <div v-if="loading" class="py-20 text-center text-gray-500">
        Загрузка…
      </div>
      <div
        v-else
        class="overflow-hidden border-y border-gray-200 bg-white dark:border-slate-800 dark:bg-slate-950"
      >
        <div
          v-for="feature in items"
          :key="feature.id"
          role="button"
          tabindex="0"
          class="grid w-full cursor-pointer gap-2 border-b border-gray-100 px-4 py-3 text-left last:border-0 hover:bg-gray-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-teal-600 dark:border-slate-800 dark:hover:bg-slate-900 md:grid-cols-[minmax(240px,1fr)_180px_150px_150px_auto] md:items-center"
          @click="openEdit(feature)"
          @keydown.enter="openEdit(feature)"
          @keydown.space.prevent="openEdit(feature)"
        >
          <div class="min-w-0">
            <p class="truncate font-semibold text-gray-950 dark:text-white">
              {{ feature.name }}
            </p>
            <p class="truncate text-xs text-gray-500">
              {{ feature.slug }}
              <span v-if="feature.short_description">
                · {{ feature.short_description }}</span
              >
            </p>
          </div>
          <span class="text-sm text-gray-600 dark:text-slate-300">{{
            feature.category.name
          }}</span>
          <span class="text-sm text-gray-600 dark:text-slate-300">{{
            scopeLabels[feature.scope_type === "brand" ? "brand" : "universal"]
          }}</span>
          <span class="text-xs text-gray-500"
            >{{ sourceCount(feature) }} связей ·
            {{ feature.rules?.length || 0 }} правил</span
          >
          <button
            v-if="feature.is_active"
            type="button"
            class="flex h-8 w-8 items-center justify-center rounded-md text-gray-400 hover:bg-red-50 hover:text-red-600"
            title="Архивировать"
            @click.stop="archive(feature)"
          >
            <Archive class="h-4 w-4" />
          </button>
        </div>
        <p v-if="!items.length" class="py-16 text-center text-sm text-gray-500">
          Фичи не найдены
        </p>
      </div>
    </div>

    <FeatureEditorDrawer
      :open="editorOpen"
      :feature="editingFeature"
      :categories="categories"
      :brands="brands"
      :features="replacementFeatures"
      @close="closeEditor"
      @saved="onEditorSaved"
    />
  </div>
</template>
