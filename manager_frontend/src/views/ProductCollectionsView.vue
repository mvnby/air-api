<script setup lang="ts">
import {
  computed,
  nextTick,
  onBeforeUnmount,
  onMounted,
  ref,
  watch,
} from "vue";
import { LayoutPanelTop } from "lucide-vue-next";
import {
  ManagerProductCollectionsService,
  type ManagerProductCollectionCreate,
  type ManagerProductCollectionItemResponse,
  type ManagerProductCollectionPlacementPayload,
  type ManagerProductCollectionProductOptionResponse,
  type ManagerProductCollectionResponse,
  type ManagerProductCollectionWorkspacePayload,
  type ProductCollectionPreviewResponse,
  type ProductCollectionRuleOptionsResponse,
} from "../client";
import { getApiErrorMessage } from "../utils/api-errors";
import { confirmDialog } from "../services/ui-feedback";
import {
  MANAGER_CAPABILITY,
  hasManagerCapability,
} from "../manager-capabilities";
import { managerSession } from "../services/manager-session";
import { registerUnsavedNavigationGuard } from "../services/unsaved-navigation-guard";
import ProductCollectionsList from "../components/product-collections/ProductCollectionsList.vue";
import ProductCollectionEditor from "../components/product-collections/ProductCollectionEditor.vue";
import {
  collectionFormFrom,
  collectionItemsFrom,
  collectionPayload,
  defaultPlacements,
  emptyCollectionForm,
  itemPayloads,
  placementPayloads,
  type CollectionForm,
} from "../components/product-collections/product-collection-workspace";
import { sanitizeProductCollectionRuleConfig } from "../components/product-collections/product-collection-rule-permissions";

const emit = defineEmits<{
  "location-change": [location: string];
}>();

const collections = ref<ManagerProductCollectionResponse[]>([]);
const active = ref<ManagerProductCollectionResponse | null>(null);
const form = ref<CollectionForm>(emptyCollectionForm());
const items = ref<ManagerProductCollectionItemResponse[]>([]);
const placements = ref<ManagerProductCollectionPlacementPayload[]>([]);
const ruleOptions = ref<ProductCollectionRuleOptionsResponse>({});
const searchResults = ref<ManagerProductCollectionProductOptionResponse[]>([]);
const preview = ref<ProductCollectionPreviewResponse | null>(null);
const loading = ref(false);
const saving = ref(false);
const searching = ref(false);
const previewing = ref(false);
const message = ref("");
const error = ref("");
const overview = ref<"collections" | "placements">("collections");
const dirty = ref(false);
const editorTab = ref<"products" | "details" | "placements">("products");
const previewSaved = computed(() => Boolean(active.value?.id) && !dirty.value);
const canManagePlatform = computed(() =>
  hasManagerCapability(
    managerSession.auth.value,
    MANAGER_CAPABILITY.platformManage,
  ),
);
const isEditing = computed(() => active.value !== null || dirty.value);
type PlacementOverviewRow = {
  collection: ManagerProductCollectionResponse;
  placement: NonNullable<
    ManagerProductCollectionResponse["placements"]
  >[number];
};
const safeCollectionPayload = (): ManagerProductCollectionCreate => ({
  ...collectionPayload(form.value),
  rule_config: sanitizeProductCollectionRuleConfig(
    form.value.rule_config,
    canManagePlatform.value,
  ),
});
const updateLocation = (
  collection?: ManagerProductCollectionResponse | null,
) => {
  const url = new URL(window.location.href);
  if (collection?.id)
    url.searchParams.set("collectionId", String(collection.id));
  else url.searchParams.delete("collectionId");
  const nextLocation = `${url.pathname}${url.search}`;
  const currentLocation = `${window.location.pathname}${window.location.search}`;
  if (nextLocation !== currentLocation)
    window.history.pushState({}, "", nextLocation);
  emit("location-change", nextLocation);
};
let searchRequestId = 0;
let previewRequestId = 0;
const applyCollection = (
  collection: ManagerProductCollectionResponse | null,
  tab: "products" | "details" | "placements" = "products",
) => {
  searchRequestId += 1;
  previewRequestId += 1;
  searching.value = false;
  previewing.value = false;
  editorTab.value = tab;
  active.value = collection;
  preview.value = null;
  searchResults.value = [];
  error.value = "";
  message.value = "";
  if (!collection) {
    form.value = emptyCollectionForm();
    items.value = [];
    placements.value = defaultPlacements();
    dirty.value = true;
    updateLocation(null);
    return;
  }
  form.value = collectionFormFrom(collection);
  items.value = collectionItemsFrom(collection);
  placements.value = placementPayloads(collection.placements || []);
  dirty.value = false;
  void nextTick(() => {
    dirty.value = false;
  });
  updateLocation(collection);
};
const discardOr = async (next: () => void) => {
  if (saving.value) return;
  if (
    !dirty.value ||
    (await confirmDialog({
      title: "Не сохранять изменения?",
      description: "Несохранённые изменения будут потеряны.",
      confirmText: "Продолжить",
      variant: "danger",
    }))
  )
    next();
};
const selectCollection = (
  collection: ManagerProductCollectionResponse,
  tab: "products" | "details" | "placements" = "products",
) => void discardOr(() => applyCollection(collection, tab));
const newCollection = () => void discardOr(() => applyCollection(null));
const loadCollections = async (selectedId?: number) => {
  loading.value = true;
  error.value = "";
  try {
    const response =
      await ManagerProductCollectionsService.listManagerProductCollections();
    collections.value = response.items || [];
    const target =
      selectedId ||
      Number(new URLSearchParams(window.location.search).get("collectionId"));
    if (target) {
      const selected = collections.value.find((row) => row.id === target);
      if (selected) applyCollection(selected);
    }
  } catch (caught) {
    error.value = getApiErrorMessage(caught);
  } finally {
    loading.value = false;
  }
};
const searchProducts = async (query: string) => {
  const search = query.trim();
  if (!search) return;
  const requestId = ++searchRequestId;
  searching.value = true;
  error.value = "";
  try {
    const response =
      await ManagerProductCollectionsService.searchManagerProductCollectionProducts(
        search,
        30,
      );
    const selected = new Set(items.value.map((item) => item.product_id));
    if (requestId === searchRequestId) {
      searchResults.value = (response.items || []).filter(
        (row) => !selected.has(row.id),
      );
    }
  } catch (caught) {
    if (requestId === searchRequestId) error.value = getApiErrorMessage(caught);
  } finally {
    if (requestId === searchRequestId) searching.value = false;
  }
};
const save = async () => {
  if (saving.value) return;
  saving.value = true;
  error.value = "";
  message.value = "";
  try {
    let saved = active.value;
    if (!saved) {
      saved =
        await ManagerProductCollectionsService.createManagerProductCollection({
          ...safeCollectionPayload(),
          status: "draft",
        });
      active.value = saved;
    }
    const payload: ManagerProductCollectionWorkspacePayload = {
      collection: safeCollectionPayload(),
      items: itemPayloads(items.value),
      placements: placementPayloads(placements.value),
    };
    const result =
      await ManagerProductCollectionsService.saveManagerProductCollectionWorkspace(
        saved.id,
        payload,
      );
    await loadCollections(result.id);
    message.value =
      result.status === "published"
        ? "Изменения опубликованной подборки применены."
        : "Изменения сохранены.";
    dirty.value = false;
  } catch (caught) {
    error.value = getApiErrorMessage(caught);
  } finally {
    saving.value = false;
  }
};
const loadPreview = async (surfaceKey: string, slotKey: string) => {
  if (!active.value?.id || dirty.value) return;
  const collectionId = active.value.id;
  const requestId = ++previewRequestId;
  previewing.value = true;
  preview.value = null;
  error.value = "";
  try {
    const result =
      await ManagerProductCollectionsService.previewManagerProductCollection(
        collectionId,
        surfaceKey,
        slotKey,
      );
    if (
      requestId === previewRequestId &&
      active.value?.id === collectionId &&
      !dirty.value
    ) preview.value = result;
  } catch (caught) {
    if (requestId === previewRequestId) error.value = getApiErrorMessage(caught);
  } finally {
    if (requestId === previewRequestId) previewing.value = false;
  }
};
const duplicate = async () => {
  if (!active.value?.id || saving.value) return;
  try {
    const copy =
      await ManagerProductCollectionsService.duplicateManagerProductCollection(
        active.value.id,
      );
    await loadCollections(copy.id);
    message.value = "Создана черновая копия без размещений.";
  } catch (caught) {
    error.value = getApiErrorMessage(caught);
  }
};
const archive = async () => {
  if (
    saving.value ||
    !active.value?.id ||
    !(await confirmDialog({
      title: "Архивировать подборку?",
      description: "Она исчезнет с сайта, но останется в архиве.",
      confirmText: "Архивировать",
      variant: "danger",
    }))
  )
    return;
  try {
    const archived =
      await ManagerProductCollectionsService.archiveManagerProductCollection(
        active.value.id,
      );
    await loadCollections(archived.id);
    message.value = "Подборка архивирована.";
  } catch (caught) {
    error.value = getApiErrorMessage(caught);
  }
};
const placementGroups = computed(() =>
  collections.value
    .flatMap((collection) =>
      (collection.placements || []).map((placement) => ({
        collection,
        placement,
      })),
    )
    .reduce<Record<string, PlacementOverviewRow[]>>((groups, row) => {
      const key = `${row.placement.surface_key} / ${row.placement.slot_key}`;
      (groups[key] ||= []).push(row);
      return groups;
    }, {}),
);
const beforeUnload = (event: BeforeUnloadEvent) => {
  if (!dirty.value) return;
  event.preventDefault();
  event.returnValue = "";
};
watch(
  form,
  () => {
    dirty.value = true;
    preview.value = null;
  },
  { deep: true },
);
let unregisterNavigationGuard: (() => void) | undefined;
onMounted(async () => {
  window.addEventListener("beforeunload", beforeUnload);
  unregisterNavigationGuard = registerUnsavedNavigationGuard(
    () => {
      if (saving.value) return false;
      return !dirty.value ||
      confirmDialog({
        title: "Не сохранять изменения?",
        description: "Несохранённые изменения будут потеряны.",
        confirmText: "Продолжить",
        variant: "danger",
      });
    },
  );
  await Promise.all([
    loadCollections(),
    ManagerProductCollectionsService.getManagerProductCollectionRuleOptions()
      .then((result) => {
        ruleOptions.value = result;
      })
      .catch((caught) => {
        error.value = getApiErrorMessage(caught);
      }),
  ]);
});
onBeforeUnmount(() => {
  window.removeEventListener("beforeunload", beforeUnload);
  unregisterNavigationGuard?.();
});
</script>

<template>
  <main
    class="mx-auto max-w-[1500px] px-4 pb-8 pt-16 sm:p-6"
    data-testid="product-collections-workspace"
  >
    <div v-if="!isEditing" class="space-y-5">
      <header class="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p class="text-xs font-bold uppercase tracking-wider text-blue-600">
            Контент сайта
          </p>
          <h1 class="text-2xl font-bold text-slate-950 dark:text-white">
            Подборки и размещения
          </h1>
          <p class="mt-1 text-sm text-slate-500">
            Создавайте подборки, задавайте состав и публикуйте их в нужных
            слотах.
          </p>
        </div>
        <div
          class="grid grid-cols-2 rounded-lg bg-slate-100 p-1 dark:bg-slate-800"
        >
          <button
            class="overview-tab"
            :class="overview === 'collections' ? 'overview-tab--active' : ''"
            type="button"
            @click="overview = 'collections'"
          >
            Подборки</button
          ><button
            class="overview-tab"
            :class="overview === 'placements' ? 'overview-tab--active' : ''"
            type="button"
            @click="overview = 'placements'"
          >
            <LayoutPanelTop class="h-4 w-4" /> Размещения
          </button>
        </div>
      </header>
      <p v-if="error" class="notice notice--error">{{ error }}</p>
      <p v-if="message" class="notice notice--success">{{ message }}</p>
      <ProductCollectionsList
        v-if="overview === 'collections'"
        :collections="collections"
        :loading="loading"
        @select="selectCollection"
        @create="newCollection"
        @refresh="loadCollections"
      />
      <section v-else class="space-y-3">
        <div>
          <h2 class="text-lg font-bold">Размещения</h2>
          <p class="text-sm text-slate-500">
            Обзор связей. Изменение открывает конкретную подборку.
          </p>
        </div>
        <div
          v-for="(rows, key) in placementGroups"
          :key="key"
          class="rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900"
        >
          <h3 class="font-bold">{{ key }}</h3>
          <button
            v-for="row in rows"
            :key="`${row.collection.id}-${row.placement.id}`"
            class="mt-2 flex w-full items-center justify-between rounded-lg bg-slate-50 p-3 text-left hover:bg-blue-50 dark:bg-slate-800"
            type="button"
                @click="selectCollection(row.collection, 'placements')"
          >
            <span class="min-w-0"
              ><strong class="block break-words text-sm">{{
                row.collection.internal_name
              }}</strong
              ><span class="text-xs text-slate-500">{{
                row.collection.public_title
              }}</span></span
            ><span
              class="text-xs font-bold"
              :class="
                row.placement.is_enabled ? 'text-emerald-700' : 'text-slate-500'
              "
              >{{ row.placement.is_enabled ? "Включено" : "Выключено" }}</span
            >
          </button>
        </div>
        <p
          v-if="!Object.keys(placementGroups).length"
          class="rounded-xl border border-dashed border-slate-300 p-8 text-center text-sm text-slate-500"
        >
          Размещений пока нет.
        </p>
      </section>
    </div>
    <div v-else class="space-y-3">
      <button
        class="back-button"
        type="button"
        @click="
          discardOr(() => {
            active = null;
            dirty = false;
            updateLocation(null);
          })
        "
      >
        ← К списку подборок
      </button>
      <p v-if="error" class="notice notice--error">{{ error }}</p>
      <p v-if="message" class="notice notice--success">{{ message }}</p>
      <ProductCollectionEditor
        :active="active"
        :initial-tab="editorTab"
        :form="form"
        :items="items"
        :placements="placements"
        :collections="collections"
        :rule-options="ruleOptions"
        :preview="preview"
        :preview-saved="previewSaved"
        :can-manage-platform="canManagePlatform"
        :saving="saving"
        :searching="searching"
        :previewing="previewing"
        :search-results="searchResults"
        @save="save"
        @duplicate="duplicate"
        @archive="archive"
        @preview="loadPreview"
        @search="searchProducts"
        @update:items="
          items = $event;
          dirty = true;
          preview = null;
        "
        @update:placements="
          placements = $event;
          dirty = true;
          preview = null;
        "
      />
    </div>
  </main>
</template>

<style scoped>
.overview-tab {
  display: inline-flex;
  min-height: 34px;
  align-items: center;
  justify-content: center;
  gap: 6px;
  border-radius: 6px;
  padding: 0 10px;
  font-size: 13px;
  font-weight: 700;
  color: rgb(71 85 105);
}
.overview-tab--active {
  background: white;
  color: rgb(30 64 175);
  box-shadow: 0 1px 2px rgb(15 23 42 / 0.12);
}
.notice {
  border-radius: 10px;
  padding: 10px 12px;
  font-size: 14px;
}
.notice--error {
  border: 1px solid rgb(254 202 202);
  background: rgb(254 242 242);
  color: rgb(153 27 27);
}
.notice--success {
  border: 1px solid rgb(167 243 208);
  background: rgb(236 253 245);
  color: rgb(6 95 70);
}
.back-button {
  min-height: 36px;
  color: rgb(30 64 175);
  font-size: 13px;
  font-weight: 700;
}
.back-button:hover {
  text-decoration: underline;
}
</style>
