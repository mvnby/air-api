<script setup lang="ts">
import BrandEditorModal from "../components/brands/BrandEditorModal.vue";
import BrandsList from "../components/brands/BrandsList.vue";
import SeriesEditorModal from "../components/brands/SeriesEditorModal.vue";
import { useBrandsWorkspace } from "../composables/useBrandsWorkspace";

const {
  addContentBlock,
  addGalleryImage,
  applySeriesGalleryToProducts,
  availableCatalogFeatures,
  brandDropTargetId,
  catalogFeaturesLoading,
  clearBrandDropTarget,
  closeModal,
  closeSeriesModal,
  deleteBrand,
  deleteSeries,
  draggedBrandId,
  draggedSeriesId,
  editingBrand,
  editingSeries,
  error,
  expandedSeriesIds,
  filteredBrands,
  form,
  isBrandReorderDisabled,
  isSeriesReorderDisabled,
  loading,
  modalOpen,
  onBrandDragOver,
  onBrandDragStart,
  onBrandDrop,
  onSeriesDragOver,
  onSeriesDragStart,
  onSeriesDrop,
  openCreate,
  openEdit,
  openSeriesCreate,
  openSeriesEdit,
  openSeriesProducts,
  query,
  removeContentBlock,
  removeGalleryImage,
  reorderingBrands,
  reorderingSeries,
  resetBrandDragState,
  resetSeriesDragState,
  saveBrand,
  saveSeries,
  saving,
  selectBrand,
  selectedBrand,
  selectedBrandId,
  seriesDropTargetId,
  seriesError,
  seriesForm,
  seriesGalleryApplying,
  seriesItems,
  seriesLoading,
  seriesModalOpen,
  seriesSaving,
  toast,
  toggleSeriesExpanded,
  toggleSeriesExpandedFromCard,
} = useBrandsWorkspace();

const clearSeriesDropTarget = (seriesId: number) => {
  if (seriesDropTargetId.value === seriesId) seriesDropTargetId.value = null;
};
</script>

<template>
  <div class="space-y-5">
    <Transition name="fade">
      <div
        v-if="toast"
        class="fixed right-6 top-6 z-[100] rounded-xl bg-teal-600 px-6 py-3 font-medium text-white shadow-2xl"
      >
        {{ toast }}
      </div>
    </Transition>

    <div class="flex items-center justify-between">
      <h1
        class="text-2xl font-bold tracking-tight text-gray-900 dark:text-white"
      >
        Бренды
      </h1>
      <button
        type="button"
        class="inline-flex items-center justify-center gap-2 rounded-lg bg-teal-600 px-4 py-2 text-sm font-medium text-white transition-all hover:bg-teal-500"
        @click="openCreate"
      >
        <span class="material-icons-round text-[18px]">add</span>
        Новый бренд
      </button>
    </div>

    <BrandsList
      :brands="filteredBrands"
      :loading="loading"
      :query="query"
      :error="error"
      :selected-brand-id="selectedBrandId"
      :reordering="reorderingBrands"
      :reorder-disabled="isBrandReorderDisabled"
      :dragged-brand-id="draggedBrandId"
      :drop-target-id="brandDropTargetId"
      :series-items="seriesItems"
      :series-loading="seriesLoading"
      :series-error="seriesError"
      :series-reordering="reorderingSeries"
      :series-reorder-disabled="isSeriesReorderDisabled"
      :dragged-series-id="draggedSeriesId"
      :series-drop-target-id="seriesDropTargetId"
      :expanded-series-ids="expandedSeriesIds"
      @update:query="query = $event"
      @select="selectBrand"
      @edit="openEdit"
      @delete="deleteBrand"
      @brand-drag-start="onBrandDragStart"
      @brand-drag-over="onBrandDragOver"
      @brand-drag-leave="clearBrandDropTarget"
      @brand-drop="onBrandDrop"
      @brand-drag-end="resetBrandDragState"
      @create-series="openSeriesCreate"
      @edit-series="openSeriesEdit"
      @delete-series="deleteSeries"
      @open-series-products="openSeriesProducts"
      @toggle-series-expanded="toggleSeriesExpanded"
      @toggle-series-from-card="toggleSeriesExpandedFromCard"
      @series-drag-start="onSeriesDragStart"
      @series-drag-over="onSeriesDragOver"
      @series-drag-leave="clearSeriesDropTarget"
      @series-drop="onSeriesDrop"
      @series-drag-end="resetSeriesDragState"
    />

    <BrandEditorModal
      :open="modalOpen"
      :form="form"
      :editing="Boolean(editingBrand)"
      :saving="saving"
      @close="closeModal"
      @save="saveBrand"
    />

    <SeriesEditorModal
      :open="seriesModalOpen"
      :form="seriesForm"
      :editing="Boolean(editingSeries)"
      :brand-name="selectedBrand?.title"
      :features="availableCatalogFeatures"
      :features-loading="catalogFeaturesLoading"
      :saving="seriesSaving"
      :gallery-applying="seriesGalleryApplying"
      @close="closeSeriesModal"
      @save="saveSeries"
      @apply-gallery="applySeriesGalleryToProducts"
      @add-gallery="addGalleryImage"
      @remove-gallery="removeGalleryImage"
      @add-content-block="addContentBlock"
      @remove-content-block="removeContentBlock"
    />
  </div>
</template>
