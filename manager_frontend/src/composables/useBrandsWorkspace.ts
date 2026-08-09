import { computed, onMounted, ref } from "vue";
import { api, type ManagerBrand } from "../api";
import { getApiErrorMessage } from "../utils/api-errors";
import { confirmDialog } from "../services/ui-feedback";
import type { BrandForm } from "../components/brands/brand-form-types";
import {
  getChangedSortItems,
  getNextSortOrder,
  moveItemById,
  withSortOrder,
} from "../components/brands/brand-view-utils";
import { useSeriesWorkspace } from "./useSeriesWorkspace";

const emptyBrandForm = (sortOrder: number): BrandForm => ({
  title: "",
  slug: "",
  logo_url: "",
  short_description: "",
  description: "",
  sort_order: sortOrder,
  is_published: true,
});

export const useBrandsWorkspace = () => {
  const brands = ref<ManagerBrand[]>([]);
  const loading = ref(true);
  const saving = ref(false);
  const query = ref("");
  const error = ref("");
  const toast = ref("");
  const modalOpen = ref(false);
  const editingBrand = ref<ManagerBrand | null>(null);
  const selectedBrandId = ref<number | null>(null);
  const reorderingBrands = ref(false);
  const draggedBrandId = ref<number | null>(null);
  const brandDropTargetId = ref<number | null>(null);
  const form = ref<BrandForm>(emptyBrandForm(0));

  const filteredBrands = computed(() => {
    const needle = query.value.trim().toLowerCase();
    if (!needle) return brands.value;
    return brands.value.filter(
      (item) =>
        String(item.title || "")
          .toLowerCase()
          .includes(needle) ||
        String(item.slug || "")
          .toLowerCase()
          .includes(needle),
    );
  });
  const selectedBrand = computed(
    () =>
      brands.value.find((item) => item.id === selectedBrandId.value) || null,
  );
  const isBrandReorderDisabled = computed(
    () =>
      loading.value ||
      saving.value ||
      reorderingBrands.value ||
      Boolean(query.value.trim()),
  );

  const setToast = (message: string) => {
    toast.value = message;
    window.setTimeout(() => {
      if (toast.value === message) toast.value = "";
    }, 3000);
  };

  const series = useSeriesWorkspace({
    selectedBrandId,
    selectedBrand,
    setToast,
  });

  const resetForm = () => {
    form.value = emptyBrandForm(getNextSortOrder(brands.value));
  };

  const fetchBrands = async () => {
    loading.value = true;
    error.value = "";
    try {
      const response = await api.listManagerBrands();
      brands.value = [...(response.items || [])];
      if (
        selectedBrandId.value &&
        !brands.value.some((item) => item.id === selectedBrandId.value)
      ) {
        selectedBrandId.value = null;
      }
    } catch (cause) {
      error.value = getApiErrorMessage(cause);
    } finally {
      loading.value = false;
    }
  };

  const selectBrand = (brand: ManagerBrand) => {
    if (selectedBrandId.value === brand.id) {
      selectedBrandId.value = null;
      series.seriesError.value = "";
      return;
    }
    selectedBrandId.value = brand.id;
  };

  const openCreate = () => {
    editingBrand.value = null;
    resetForm();
    modalOpen.value = true;
    error.value = "";
  };

  const openEdit = (brand: ManagerBrand) => {
    editingBrand.value = brand;
    form.value = {
      title: String(brand.title || ""),
      slug: String(brand.slug || ""),
      logo_url: String(brand.logo_url || ""),
      short_description: String(brand.short_description || ""),
      description: String(brand.description || ""),
      sort_order: Number(brand.sort_order || 0),
      is_published: Boolean(brand.is_published),
    };
    modalOpen.value = true;
    error.value = "";
  };

  const closeModal = () => {
    modalOpen.value = false;
    editingBrand.value = null;
    resetForm();
  };

  const saveBrand = async () => {
    const title = String(form.value.title || "").trim();
    if (!title) {
      error.value = "Название бренда обязательно.";
      return;
    }

    saving.value = true;
    error.value = "";
    try {
      const wasEditing = Boolean(editingBrand.value?.id);
      const payload = {
        title,
        slug: String(form.value.slug || "").trim() || undefined,
        logo_url: String(form.value.logo_url || "").trim() || undefined,
        short_description:
          String(form.value.short_description || "").trim() || undefined,
        description: String(form.value.description || "").trim() || undefined,
        sort_order: wasEditing
          ? Number(form.value.sort_order || 0)
          : getNextSortOrder(brands.value),
        is_published: Boolean(form.value.is_published),
      };
      if (editingBrand.value?.id) {
        await api.updateManagerBrand(editingBrand.value.id, payload);
      } else {
        await api.createManagerBrand(payload);
      }
      await fetchBrands();
      closeModal();
      setToast(wasEditing ? "Бренд обновлен" : "Бренд создан");
    } catch (cause) {
      error.value = getApiErrorMessage(cause);
    } finally {
      saving.value = false;
    }
  };

  const resetBrandDragState = () => {
    draggedBrandId.value = null;
    brandDropTargetId.value = null;
  };

  const onBrandDragStart = (event: DragEvent, brand: ManagerBrand) => {
    if (isBrandReorderDisabled.value) return;
    draggedBrandId.value = brand.id;
    event.dataTransfer?.setData("text/plain", String(brand.id));
    if (event.dataTransfer) event.dataTransfer.effectAllowed = "move";
  };

  const onBrandDragOver = (event: DragEvent, brand: ManagerBrand) => {
    if (
      isBrandReorderDisabled.value ||
      !draggedBrandId.value ||
      draggedBrandId.value === brand.id
    )
      return;
    event.preventDefault();
    brandDropTargetId.value = brand.id;
    if (event.dataTransfer) event.dataTransfer.dropEffect = "move";
  };

  const clearBrandDropTarget = (brandId: number) => {
    if (brandDropTargetId.value === brandId) brandDropTargetId.value = null;
  };

  const onBrandDrop = async (brand: ManagerBrand) => {
    const sourceId = draggedBrandId.value;
    resetBrandDragState();
    if (!sourceId || sourceId === brand.id || isBrandReorderDisabled.value)
      return;

    const previous = [...brands.value];
    const next = withSortOrder(moveItemById(brands.value, sourceId, brand.id));
    const changed = getChangedSortItems(previous, next);
    if (!changed.length) return;

    brands.value = next;
    reorderingBrands.value = true;
    error.value = "";
    try {
      await Promise.all(
        changed.map((item) =>
          api.updateManagerBrand(item.id, { sort_order: item.sort_order }),
        ),
      );
      setToast("Порядок брендов сохранен");
      await fetchBrands();
    } catch (cause) {
      brands.value = previous;
      error.value = `Не удалось сохранить порядок брендов: ${getApiErrorMessage(cause)}`;
      await fetchBrands();
    } finally {
      reorderingBrands.value = false;
    }
  };

  const deleteBrand = async (brand: ManagerBrand) => {
    const confirmed = await confirmDialog({
      title: "Удалить бренд?",
      description: brand.title,
      confirmText: "Удалить",
      variant: "danger",
    });
    if (!confirmed) return;

    error.value = "";
    try {
      await api.deleteManagerBrand(brand.id);
      await fetchBrands();
      setToast("Бренд удален");
    } catch (cause) {
      error.value = getApiErrorMessage(cause);
    }
  };

  onMounted(() => {
    void fetchBrands();
  });

  return {
    ...series,
    brandDropTargetId,
    brands,
    clearBrandDropTarget,
    closeModal,
    deleteBrand,
    draggedBrandId,
    editingBrand,
    error,
    filteredBrands,
    form,
    isBrandReorderDisabled,
    loading,
    modalOpen,
    onBrandDragOver,
    onBrandDragStart,
    onBrandDrop,
    openCreate,
    openEdit,
    query,
    reorderingBrands,
    resetBrandDragState,
    saveBrand,
    saving,
    selectBrand,
    selectedBrand,
    selectedBrandId,
    setToast,
    toast,
  };
};
