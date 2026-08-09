import { computed, ref, type ComputedRef, type Ref, watch } from "vue";
import { ManagerFeaturesService, type ManagerFeatureResponse } from "../client";
import {
  api,
  type ManagerBrand,
  type ManagerBrandSeries,
  type ManagerBrandSeriesCreatePayload,
} from "../api";
import { getApiErrorMessage } from "../utils/api-errors";
import { confirmDialog } from "../services/ui-feedback";
import type { FeatureAssignment } from "../components/brands/SeriesFeatureAssignments.vue";
import type { SeriesForm } from "../components/brands/brand-form-types";
import {
  getChangedSortItems,
  getNextSortOrder,
  moveItemById,
  normalizeContentBlocks,
  normalizeTextList,
  normalizeUrlList,
  withSortOrder,
} from "../components/brands/brand-view-utils";

type UseSeriesWorkspaceOptions = {
  selectedBrandId: Ref<number | null>;
  selectedBrand: ComputedRef<ManagerBrand | null>;
  setToast: (message: string) => void;
};

const emptyForm = (sortOrder: number): SeriesForm => ({
  title: "",
  slug: "",
  tagline: "",
  short_description: "",
  description: "",
  hero_image: "",
  galleryImages: [],
  feature_assignments: [],
  contentBlocks: [],
  footnotesText: "",
  seo_title: "",
  seo_description: "",
  source_url: "",
  sort_order: sortOrder,
  is_published: true,
});

export const useSeriesWorkspace = ({
  selectedBrandId,
  selectedBrand,
  setToast,
}: UseSeriesWorkspaceOptions) => {
  const seriesItems = ref<ManagerBrandSeries[]>([]);
  const catalogFeatures = ref<ManagerFeatureResponse[]>([]);
  const seriesLoading = ref(false);
  const catalogFeaturesLoading = ref(false);
  const seriesSaving = ref(false);
  const seriesGalleryApplying = ref(false);
  const seriesError = ref("");
  const seriesModalOpen = ref(false);
  const editingSeries = ref<ManagerBrandSeries | null>(null);
  const reorderingSeries = ref(false);
  const draggedSeriesId = ref<number | null>(null);
  const seriesDropTargetId = ref<number | null>(null);
  const featuredSeriesId = ref<number | null>(null);
  const expandedSeriesIds = ref<Set<number>>(new Set());
  const seriesForm = ref<SeriesForm>(emptyForm(0));

  const isSeriesReorderDisabled = computed(
    () =>
      !selectedBrandId.value ||
      seriesLoading.value ||
      seriesSaving.value ||
      featuredSeriesId.value !== null ||
      reorderingSeries.value,
  );
  const availableCatalogFeatures = computed(() =>
    catalogFeatures.value.filter(
      (feature) =>
        feature.scope_type === "universal" ||
        (feature.scope_type === "brand" &&
          feature.brand_id === selectedBrandId.value),
    ),
  );

  const resetSeriesForm = () => {
    seriesForm.value = emptyForm(getNextSortOrder(seriesItems.value));
  };

  const fetchSeries = async () => {
    if (!selectedBrandId.value) {
      seriesItems.value = [];
      return;
    }

    seriesLoading.value = true;
    seriesError.value = "";
    try {
      const response = await api.listManagerBrandSeries(selectedBrandId.value);
      seriesItems.value = [...(response.items || [])];
      const existingIds = new Set(seriesItems.value.map((item) => item.id));
      expandedSeriesIds.value = new Set(
        [...expandedSeriesIds.value].filter((id) => existingIds.has(id)),
      );
    } catch (cause) {
      seriesError.value = getApiErrorMessage(cause);
    } finally {
      seriesLoading.value = false;
    }
  };

  const fetchCatalogFeatures = async () => {
    if (!selectedBrandId.value) return;

    catalogFeaturesLoading.value = true;
    seriesError.value = "";
    try {
      const response = await ManagerFeaturesService.listManagerFeatures(
        undefined,
        undefined,
        undefined,
        undefined,
        undefined,
        true,
      );
      catalogFeatures.value = response.items || [];
    } catch (cause) {
      seriesError.value = getApiErrorMessage(cause);
    } finally {
      catalogFeaturesLoading.value = false;
    }
  };

  const openSeriesProducts = (series: ManagerBrandSeries) => {
    const params = new URLSearchParams({
      seriesId: String(series.id),
      seriesTitle: String(series.title || ""),
      returnTo: "/manager/brands",
    });
    if (selectedBrand.value?.slug)
      params.set("brand", selectedBrand.value.slug);
    window.location.href = `/manager/products?${params.toString()}`;
  };

  const toggleSeriesExpanded = (seriesId: number) => {
    const next = new Set(expandedSeriesIds.value);
    if (next.has(seriesId)) next.delete(seriesId);
    else next.add(seriesId);
    expandedSeriesIds.value = next;
  };

  const toggleSeriesExpandedFromCard = (series: ManagerBrandSeries) => {
    if (!window.matchMedia("(min-width: 1024px)").matches) {
      toggleSeriesExpanded(series.id);
    }
  };

  const openSeriesCreate = () => {
    editingSeries.value = null;
    resetSeriesForm();
    void fetchCatalogFeatures();
    seriesModalOpen.value = true;
    seriesError.value = "";
  };

  const assignmentFallback = (
    series: ManagerBrandSeries,
  ): FeatureAssignment[] => {
    const responseAssignments = series.feature_assignments;
    if (responseAssignments) {
      return responseAssignments.map((assignment) => ({
        feature_id: assignment.feature_id,
        is_featured: Boolean(assignment.is_featured),
      }));
    }

    const featureIds =
      series.brand_feature_ids ||
      (series.brand_features || []).map((feature) => feature.id);
    return featureIds.map((feature_id) => ({ feature_id, is_featured: false }));
  };

  const openSeriesEdit = (series: ManagerBrandSeries) => {
    editingSeries.value = series;
    seriesForm.value = {
      title: String(series.title || ""),
      slug: String(series.slug || ""),
      tagline: String(series.tagline || ""),
      short_description: String(series.short_description || ""),
      description: String(series.description || ""),
      hero_image: String(series.hero_image || ""),
      galleryImages: [...(series.gallery_images || [])],
      feature_assignments: assignmentFallback(series),
      contentBlocks: (series.content_blocks || []).map((block) => ({
        kind: block.kind || "text",
        title: String(block.title || ""),
        text: String(block.text || ""),
        image_url: String(block.image_url || ""),
        layout: block.layout || "text_left",
      })),
      footnotesText: (series.footnotes || []).join("\n"),
      seo_title: String(series.seo_title || ""),
      seo_description: String(series.seo_description || ""),
      source_url: String(series.source_url || ""),
      sort_order: Number(series.sort_order || 0),
      is_published: Boolean(series.is_published),
    };
    void fetchCatalogFeatures();
    seriesModalOpen.value = true;
    seriesError.value = "";
  };

  const closeSeriesModal = () => {
    seriesModalOpen.value = false;
    editingSeries.value = null;
    resetSeriesForm();
  };

  const addContentBlock = () => {
    seriesForm.value.contentBlocks.push({
      kind: "text",
      title: "",
      text: "",
      image_url: "",
      layout: "text_left",
    });
  };

  const removeContentBlock = (index: number) => {
    seriesForm.value.contentBlocks.splice(index, 1);
  };

  const addGalleryImage = (url: string) => {
    const normalized = String(url || "").trim();
    if (!normalized) return;
    const alreadyAdded = seriesForm.value.galleryImages.some(
      (item) => item.trim().toLowerCase() === normalized.toLowerCase(),
    );
    if (!alreadyAdded) seriesForm.value.galleryImages.push(normalized);
  };

  const removeGalleryImage = (index: number) => {
    seriesForm.value.galleryImages.splice(index, 1);
  };

  const applySeriesGalleryToProducts = async () => {
    if (
      !selectedBrandId.value ||
      !editingSeries.value?.id ||
      seriesGalleryApplying.value
    )
      return;

    const galleryUrls = normalizeUrlList(seriesForm.value.galleryImages);
    if (!galleryUrls.length) {
      seriesError.value = "Добавьте хотя бы одно изображение в галерею.";
      return;
    }

    seriesGalleryApplying.value = true;
    seriesError.value = "";
    try {
      const result = await api.applyManagerSeriesGalleryToProducts(
        selectedBrandId.value,
        editingSeries.value.id,
        galleryUrls,
      );
      seriesForm.value.galleryImages = galleryUrls;
      await fetchSeries();
      setToast(
        `Добавлено товарам: ${result.added_links}, уже было: ${result.skipped_existing}`,
      );
    } catch (cause) {
      seriesError.value = getApiErrorMessage(cause);
    } finally {
      seriesGalleryApplying.value = false;
    }
  };

  const saveSeries = async () => {
    if (!selectedBrandId.value) return;
    const title = String(seriesForm.value.title || "").trim();
    if (!title) {
      seriesError.value = "Название серии обязательно.";
      return;
    }

    seriesSaving.value = true;
    seriesError.value = "";
    try {
      const wasEditing = Boolean(editingSeries.value?.id);
      const payload: ManagerBrandSeriesCreatePayload = {
        title,
        slug: String(seriesForm.value.slug || "").trim() || undefined,
        tagline: String(seriesForm.value.tagline || "").trim() || undefined,
        short_description:
          String(seriesForm.value.short_description || "").trim() || undefined,
        description:
          String(seriesForm.value.description || "").trim() || undefined,
        hero_image:
          String(seriesForm.value.hero_image || "").trim() || undefined,
        gallery_images: normalizeUrlList(seriesForm.value.galleryImages),
        feature_assignments: seriesForm.value.feature_assignments,
        content_blocks: normalizeContentBlocks(seriesForm.value.contentBlocks),
        footnotes: normalizeTextList(seriesForm.value.footnotesText),
        seo_title: String(seriesForm.value.seo_title || "").trim() || undefined,
        seo_description:
          String(seriesForm.value.seo_description || "").trim() || undefined,
        source_url:
          String(seriesForm.value.source_url || "").trim() || undefined,
        sort_order: wasEditing
          ? Number(seriesForm.value.sort_order || 0)
          : getNextSortOrder(seriesItems.value),
        is_published: Boolean(seriesForm.value.is_published),
      };
      if (editingSeries.value?.id) {
        await api.updateManagerBrandSeries(
          selectedBrandId.value,
          editingSeries.value.id,
          payload,
        );
      } else {
        await api.createManagerBrandSeries(selectedBrandId.value, payload);
      }
      await fetchSeries();
      await fetchCatalogFeatures();
      closeSeriesModal();
      setToast(wasEditing ? "Серия обновлена" : "Серия создана");
    } catch (cause) {
      seriesError.value = getApiErrorMessage(cause);
    } finally {
      seriesSaving.value = false;
    }
  };

  const resetSeriesDragState = () => {
    draggedSeriesId.value = null;
    seriesDropTargetId.value = null;
  };

  const onSeriesDragStart = (event: DragEvent, series: ManagerBrandSeries) => {
    if (isSeriesReorderDisabled.value) return;
    draggedSeriesId.value = series.id;
    event.dataTransfer?.setData("text/plain", String(series.id));
    if (event.dataTransfer) event.dataTransfer.effectAllowed = "move";
  };

  const onSeriesDragOver = (event: DragEvent, series: ManagerBrandSeries) => {
    if (
      isSeriesReorderDisabled.value ||
      !draggedSeriesId.value ||
      draggedSeriesId.value === series.id
    )
      return;
    event.preventDefault();
    seriesDropTargetId.value = series.id;
    if (event.dataTransfer) event.dataTransfer.dropEffect = "move";
  };

  const onSeriesDrop = async (series: ManagerBrandSeries) => {
    const brandId = selectedBrandId.value;
    const sourceId = draggedSeriesId.value;
    resetSeriesDragState();
    if (
      !brandId ||
      !sourceId ||
      sourceId === series.id ||
      isSeriesReorderDisabled.value
    )
      return;

    const previous = [...seriesItems.value];
    const next = withSortOrder(
      moveItemById(seriesItems.value, sourceId, series.id),
    );
    const changed = getChangedSortItems(previous, next);
    if (!changed.length) return;

    seriesItems.value = next;
    reorderingSeries.value = true;
    seriesError.value = "";
    try {
      await Promise.all(
        changed.map((item) =>
          api.updateManagerBrandSeries(brandId, item.id, {
            sort_order: item.sort_order,
          }),
        ),
      );
      setToast("Порядок серий сохранен");
      await fetchSeries();
    } catch (cause) {
      seriesItems.value = previous;
      seriesError.value = `Не удалось сохранить порядок серий: ${getApiErrorMessage(cause)}`;
      await fetchSeries();
    } finally {
      reorderingSeries.value = false;
    }
  };

  const deleteSeries = async (series: ManagerBrandSeries) => {
    if (!selectedBrandId.value) return;
    const confirmed = await confirmDialog({
      title: "Удалить серию?",
      description: series.title,
      confirmText: "Удалить",
      variant: "danger",
    });
    if (!confirmed) return;

    seriesError.value = "";
    try {
      await api.deleteManagerBrandSeries(selectedBrandId.value, series.id);
      await fetchSeries();
      setToast("Серия удалена");
    } catch (cause) {
      seriesError.value = getApiErrorMessage(cause);
    }
  };

  const toggleSeriesFeatured = async (series: ManagerBrandSeries) => {
    if (
      !selectedBrandId.value ||
      featuredSeriesId.value !== null ||
      (!series.is_published && !series.is_featured)
    )
      return;

    const wasFeatured = Boolean(series.is_featured);
    featuredSeriesId.value = series.id;
    seriesError.value = "";
    try {
      const payload = { is_featured: !wasFeatured };
      await api.updateManagerBrandSeries(
        selectedBrandId.value,
        series.id,
        payload,
      );
      await fetchSeries();
      setToast(
        wasFeatured ? "Серия убрана из подборки" : "Серия добавлена в подборку",
      );
    } catch (cause) {
      seriesError.value = getApiErrorMessage(cause);
    } finally {
      featuredSeriesId.value = null;
    }
  };

  watch(selectedBrandId, () => {
    void fetchSeries();
    void fetchCatalogFeatures();
  });

  return {
    addContentBlock,
    addGalleryImage,
    applySeriesGalleryToProducts,
    availableCatalogFeatures,
    catalogFeaturesLoading,
    closeSeriesModal,
    deleteSeries,
    editingSeries,
    expandedSeriesIds,
    featuredSeriesId,
    isSeriesReorderDisabled,
    onSeriesDragOver,
    onSeriesDragStart,
    onSeriesDrop,
    openSeriesCreate,
    openSeriesEdit,
    openSeriesProducts,
    removeContentBlock,
    removeGalleryImage,
    reorderingSeries,
    resetSeriesDragState,
    saveSeries,
    seriesDropTargetId,
    seriesError,
    seriesForm,
    seriesGalleryApplying,
    seriesItems,
    seriesLoading,
    seriesModalOpen,
    seriesSaving,
    draggedSeriesId,
    toggleSeriesExpanded,
    toggleSeriesExpandedFromCard,
    toggleSeriesFeatured,
  };
};
