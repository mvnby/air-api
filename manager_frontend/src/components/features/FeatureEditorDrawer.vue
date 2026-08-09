<script setup lang="ts">
import { computed, reactive, ref, watch } from "vue";
import { Plus, Trash2, X } from "lucide-vue-next";
import {
  ManagerFeaturesService,
  type FeatureCategoryResponse,
  type FeatureCreatePayload,
  type FeatureRulePayload,
  type ManagerBrandResponse,
  type ManagerFeatureResponse,
} from "../../client";
import MediaField from "../MediaField.vue";
import { getApiErrorMessage } from "../../utils/api-errors";
import { confirmDialog } from "../../services/ui-feedback";
import { contentAiApi, type DraftMode } from "../content-ai/content-ai-api";

type RuleDraft = FeatureRulePayload & { valueText: string };
type FeatureDraft = Omit<FeatureCreatePayload, "rules" | "scope_type"> & {
  scope_type: "universal" | "brand";
  replaces_feature_id: number | null;
  rules: RuleDraft[];
};
type CatalogFeature = ManagerFeatureResponse & {
  replaces_feature_id?: number | null;
};

const props = defineProps<{
  open: boolean;
  feature: CatalogFeature | null;
  categories: FeatureCategoryResponse[];
  brands: ManagerBrandResponse[];
  features: CatalogFeature[];
}>();

const emit = defineEmits<{
  close: [];
  saved: [];
}>();

const saving = ref(false);
const contentAiLoading = ref(false);
const contentAiError = ref("");

const blankDraft = (): FeatureDraft => ({
  name: "",
  slug: null,
  short_description: null,
  full_description: null,
  category_id: props.categories[0]?.id || 0,
  scope_type: "universal",
  brand_id: null,
  replaces_feature_id: null,
  icon: null,
  image_url: null,
  video_url: null,
  footnote: null,
  source_url: null,
  aliases: [],
  seo_title: null,
  seo_description: null,
  source_notes: null,
  legal_notes: null,
  is_active: true,
  sort_order: 0,
  rules: [],
});

const draft = reactive<FeatureDraft>(blankDraft());

const iconValue = computed({
  get: () => draft.icon || "",
  set: (value: string) => {
    draft.icon = value || null;
  },
});
const imageValue = computed({
  get: () => draft.image_url || "",
  set: (value: string) => {
    draft.image_url = value || null;
  },
});
const universalFeatures = computed(() =>
  props.features.filter(
    (feature) =>
      feature.scope_type === "universal" && feature.id !== props.feature?.id,
  ),
);

const resetDraft = (feature: CatalogFeature | null) => {
  const next = feature
    ? ({
        name: feature.name,
        slug: feature.slug,
        short_description: feature.short_description || null,
        full_description: feature.full_description || null,
        category_id: feature.category.id,
        scope_type: feature.scope_type === "brand" ? "brand" : "universal",
        brand_id: feature.brand_id || null,
        replaces_feature_id: feature.replaces_feature_id || null,
        icon: feature.icon || null,
        image_url: feature.image_url || null,
        video_url: feature.video_url || null,
        footnote: feature.footnote || null,
        source_url: feature.source_url || null,
        aliases: feature.aliases || [],
        seo_title: feature.seo_title || null,
        seo_description: feature.seo_description || null,
        source_notes: feature.source_notes || null,
        legal_notes: feature.legal_notes || null,
        is_active: feature.is_active,
        sort_order: feature.sort_order,
        rules: (feature.rules || []).map((rule) => ({
          spec_key: rule.spec_key,
          operator: rule.operator,
          target_value: rule.target_value,
          is_active: rule.is_active,
          sort_order: rule.sort_order,
          valueText:
            rule.target_value == null
              ? ""
              : typeof rule.target_value === "string"
                ? rule.target_value
                : JSON.stringify(rule.target_value),
        })),
      } satisfies FeatureDraft)
    : blankDraft();
  Object.assign(draft, next);
  contentAiError.value = "";
};

watch(
  () => [props.open, props.feature] as const,
  ([open, feature]) => {
    if (open) resetDraft(feature);
  },
  { immediate: true },
);

const close = () => emit("close");

const selectScope = (next: "universal" | "brand") => {
  draft.scope_type = next;
  if (next === "universal") {
    draft.brand_id = null;
    draft.replaces_feature_id = null;
  } else {
    draft.rules = [];
  }
};

const addRule = () => {
  draft.rules.push({
    spec_key: "",
    operator: "eq",
    target_value: "",
    is_active: true,
    sort_order: draft.rules.length * 10,
    valueText: "",
  });
};

const removeRule = (index: number) => {
  draft.rules.splice(index, 1);
};

const parseRuleValue = (rule: RuleDraft) => {
  if (rule.operator === "exists") return rule.valueText.trim() !== "false";
  const raw = rule.valueText.trim();
  if (rule.operator === "in") {
    if (raw.startsWith("[")) return JSON.parse(raw);
    return raw
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean);
  }
  if (/^-?\d+(?:[.,]\d+)?$/.test(raw)) return Number(raw.replace(",", "."));
  if (raw === "true" || raw === "false") return raw === "true";
  return raw;
};

const save = async () => {
  if (!draft.name.trim() || !draft.category_id || saving.value) return;

  saving.value = true;
  try {
    const payload = {
      ...draft,
      name: draft.name.trim(),
      slug: draft.slug?.trim() || null,
      aliases: (draft.aliases || []).map((item) => item.trim()).filter(Boolean),
      brand_id: draft.scope_type === "brand" ? draft.brand_id : null,
      replaces_feature_id:
        draft.scope_type === "brand" ? draft.replaces_feature_id : null,
      rules:
        draft.scope_type === "universal"
          ? draft.rules.map(({ valueText: _valueText, ...rule }, index) => ({
              ...rule,
              target_value: parseRuleValue(draft.rules[index]!),
              sort_order: index * 10,
            }))
          : [],
    } satisfies FeatureCreatePayload & { replaces_feature_id: number | null };
    if (props.feature?.id) {
      await ManagerFeaturesService.updateManagerFeature(
        props.feature.id,
        payload,
      );
    } else {
      await ManagerFeaturesService.createManagerFeature(payload);
    }
    emit("saved");
  } catch (cause) {
    contentAiError.value = getApiErrorMessage(cause);
  } finally {
    saving.value = false;
  }
};

const generateContentDraft = async (mode: DraftMode) => {
  const sourceUrl = draft.source_url?.trim() || "";
  const fullDescription = draft.full_description?.trim() || "";
  if (mode === "from_source" && !sourceUrl) {
    contentAiError.value = "Сначала укажите источник.";
    return;
  }
  if (mode === "polish_text" && !fullDescription) {
    contentAiError.value = "Сначала вставьте полное описание.";
    return;
  }

  const hasContent = [
    draft.short_description,
    draft.full_description,
    draft.footnote,
    draft.seo_title,
    draft.seo_description,
  ].some((value) => value?.trim());
  if (hasContent) {
    const confirmed = await confirmDialog({
      title: "Заменить заполненное описание?",
      description:
        "AI подготовит новый черновик. Изменения останутся только в форме до сохранения.",
      confirmText: "Заменить",
      variant: "warning",
    });
    if (!confirmed) return;
  }

  contentAiLoading.value = true;
  contentAiError.value = "";
  try {
    const category = props.categories.find(
      (item) => item.id === draft.category_id,
    );
    const brand = props.brands.find((item) => item.id === draft.brand_id);
    const result = await contentAiApi.featureDraft(
      mode === "from_source"
        ? {
            mode,
            source_url: sourceUrl,
            name: draft.name.trim() || undefined,
            brand_name: brand?.title,
            category_name: category?.name,
          }
        : {
            mode,
            full_description: fullDescription,
            name: draft.name.trim() || undefined,
            brand_name: brand?.title,
            category_name: category?.name,
          },
    );
    draft.short_description = result.short_description;
    draft.full_description = result.full_description;
    if (result.footnote !== undefined) draft.footnote = result.footnote;
    if (result.seo_title !== undefined) draft.seo_title = result.seo_title;
    if (result.seo_description !== undefined) {
      draft.seo_description = result.seo_description;
    }
  } catch (cause) {
    contentAiError.value = getApiErrorMessage(cause);
  } finally {
    contentAiLoading.value = false;
  }
};
</script>

<template>
  <div
    v-if="open"
    class="fixed inset-0 z-50 flex justify-end bg-black/45"
    @click.self="close"
  >
    <form
      class="h-full w-full max-w-2xl overflow-y-auto bg-white p-5 shadow-2xl dark:bg-slate-950"
      @submit.prevent="save"
    >
      <div class="mb-5 flex items-center justify-between">
        <h2 class="text-xl font-bold dark:text-white">
          {{ feature ? "Редактирование фичи" : "Новая фича" }}
        </h2>
        <button
          type="button"
          class="flex h-9 w-9 items-center justify-center rounded-md hover:bg-gray-100 dark:hover:bg-slate-800"
          @click="close"
        >
          <X class="h-5 w-5" />
        </button>
      </div>

      <div class="grid gap-4 sm:grid-cols-2">
        <label class="sm:col-span-2">
          <span class="field-label">Название</span>
          <input v-model="draft.name" required class="field-input" />
        </label>
        <label>
          <span class="field-label">Slug</span>
          <input
            v-model="draft.slug"
            class="field-input"
            placeholder="создаётся автоматически"
          />
        </label>
        <label>
          <span class="field-label">Категория</span>
          <select v-model="draft.category_id" required class="field-input">
            <option
              v-for="category in categories"
              :key="category.id"
              :value="category.id"
            >
              {{ category.name }}
            </option>
          </select>
        </label>
        <div class="sm:col-span-2">
          <span class="field-label">Вид фичи</span>
          <div
            class="inline-flex rounded-md border border-gray-200 p-1 dark:border-slate-700"
          >
            <button
              type="button"
              class="rounded px-3 py-1.5 text-sm font-semibold"
              :class="
                draft.scope_type === 'universal'
                  ? 'bg-teal-600 text-white'
                  : 'text-gray-600 dark:text-slate-300'
              "
              @click="selectScope('universal')"
            >
              Общая
            </button>
            <button
              type="button"
              class="rounded px-3 py-1.5 text-sm font-semibold"
              :class="
                draft.scope_type === 'brand'
                  ? 'bg-teal-600 text-white'
                  : 'text-gray-600 dark:text-slate-300'
              "
              @click="selectScope('brand')"
            >
              Брендовая
            </button>
          </div>
          <p class="mt-1 text-xs text-gray-500">
            Общую можно назначить любой серии; брендовая доступна только сериям
            выбранного бренда.
          </p>
        </div>
        <label v-if="draft.scope_type === 'brand'"
          ><span class="field-label">Бренд</span
          ><select v-model="draft.brand_id" required class="field-input">
            <option :value="null" disabled>Выберите бренд</option>
            <option v-for="brand in brands" :key="brand.id" :value="brand.id">
              {{ brand.title }}
            </option>
          </select></label
        >
        <label v-if="draft.scope_type === 'brand'"
          ><span class="field-label">Заменяет общую фичу</span
          ><select v-model="draft.replaces_feature_id" class="field-input">
            <option :value="null">Не заменяет</option>
            <option
              v-for="universalFeature in universalFeatures"
              :key="universalFeature.id"
              :value="universalFeature.id"
            >
              {{ universalFeature.name }}
            </option>
          </select></label
        >
        <label class="sm:col-span-2"
          ><span class="field-label">Краткое описание</span
          ><input v-model="draft.short_description" class="field-input"
        /></label>
        <label class="sm:col-span-2"
          ><span class="field-label flex items-center justify-between gap-2"
            ><span>Полное описание</span
            ><button
              type="button"
              class="text-teal-700 hover:underline disabled:opacity-50 dark:text-teal-300"
              :disabled="contentAiLoading"
              @click="generateContentDraft('polish_text')"
            >
              {{ contentAiLoading ? "Подготовка…" : "Оформить и сократить" }}
            </button></span
          ><textarea
            v-model="draft.full_description"
            rows="4"
            class="field-input h-auto py-2"
          />
        </label>
        <MediaField
          v-model="iconValue"
          label="Иконка или SVG"
          kind="feature"
          :tags="['feature', 'icon']"
          accept="image/svg+xml,.svg,image/png,image/jpeg,image/webp"
          placeholder="/media/library/original/feature-icon.svg"
        />
        <MediaField
          v-model="imageValue"
          label="Иллюстрация"
          kind="feature"
          :tags="['feature', 'illustration']"
        />
        <label
          ><span class="field-label flex items-center justify-between gap-2"
            ><span>Источник</span
            ><button
              type="button"
              class="text-teal-700 hover:underline disabled:opacity-50 dark:text-teal-300"
              :disabled="contentAiLoading"
              @click="generateContentDraft('from_source')"
            >
              Взять из источника
            </button></span
          ><input
            v-model="draft.source_url"
            class="field-input"
            placeholder="https://…"
        /></label>
        <label
          ><span class="field-label">Сноска</span
          ><input v-model="draft.footnote" class="field-input"
        /></label>
        <label class="sm:col-span-2">
          <span class="field-label">SEO title</span>
          <input v-model="draft.seo_title" class="field-input" />
        </label>
        <label class="sm:col-span-2">
          <span class="field-label">SEO description</span>
          <textarea
            v-model="draft.seo_description"
            rows="3"
            class="field-input h-auto py-2"
          />
        </label>
      </div>
      <p
        v-if="contentAiError"
        class="mt-4 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700"
      >
        {{ contentAiError }}
      </p>
      <section
        v-if="draft.scope_type === 'universal'"
        class="mt-7 border-t border-gray-200 pt-5 dark:border-slate-800"
      >
        <div class="mb-3 flex items-center justify-between">
          <div>
            <h3 class="font-bold dark:text-white">
              Автоматическое назначение по характеристикам
            </h3>
            <p class="text-xs text-gray-500">
              Все активные правила должны выполняться одновременно
            </p>
          </div>
          <button
            type="button"
            class="inline-flex h-8 items-center gap-1 rounded-md border border-gray-200 px-2 text-xs font-semibold dark:border-slate-700"
            @click="addRule"
          >
            <Plus class="h-3.5 w-3.5" />Правило
          </button>
        </div>
        <div
          v-for="(rule, index) in draft.rules"
          :key="index"
          class="mb-2 grid gap-2 sm:grid-cols-[1fr_120px_1fr_36px]"
        >
          <input
            v-model="rule.spec_key"
            class="field-input"
            placeholder="spec key"
          /><select v-model="rule.operator" class="field-input">
            <option
              v-for="operator in [
                'eq',
                'neq',
                'gt',
                'gte',
                'lt',
                'lte',
                'in',
                'contains',
                'exists',
              ]"
              :key="operator"
            >
              {{ operator }}
            </option></select
          ><input
            v-model="rule.valueText"
            class="field-input"
            :disabled="rule.operator === 'exists'"
            :placeholder="rule.operator === 'in' ? 'wifi, quiet' : 'значение'"
          /><button
            type="button"
            class="flex h-10 items-center justify-center rounded-md text-gray-400 hover:bg-red-50 hover:text-red-600"
            title="Удалить правило"
            @click="removeRule(index)"
          >
            <Trash2 class="h-4 w-4" />
          </button>
        </div>
      </section>
      <div
        class="sticky bottom-0 mt-8 flex justify-end gap-2 border-t border-gray-200 bg-white py-4 dark:border-slate-800 dark:bg-slate-950"
      >
        <button
          type="button"
          class="h-10 rounded-md px-4 text-sm font-semibold text-gray-600"
          @click="close"
        >
          Отмена</button
        ><button
          type="submit"
          class="h-10 rounded-md bg-teal-600 px-5 text-sm font-semibold text-white hover:bg-teal-700 disabled:opacity-50"
          :disabled="saving"
        >
          {{ saving ? "Сохранение…" : "Сохранить" }}
        </button>
      </div>
    </form>
  </div>
</template>

<style scoped>
.field-label {
  display: block;
  margin-bottom: 0.35rem;
  font-size: 0.75rem;
  font-weight: 700;
  color: rgb(75 85 99);
}
.field-input {
  width: 100%;
  min-height: 2.5rem;
  border: 1px solid rgb(209 213 219);
  border-radius: 0.375rem;
  background: transparent;
  padding: 0 0.75rem;
  font-size: 0.875rem;
}
:global(.dark) .field-label {
  color: rgb(148 163 184);
}
:global(.dark) .field-input {
  border-color: rgb(51 65 85);
  color: white;
}
</style>
