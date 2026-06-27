<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';
import { api, type ManagerBrand, type ManagerBrandSeries } from '../api';
import MediaField from '../components/MediaField.vue';
import { getApiErrorMessage } from '../utils/api-errors';

type BrandForm = {
    title: string;
    slug: string;
    logo_url: string;
    description: string;
    sort_order: number;
    is_published: boolean;
};

type SeriesForm = {
    title: string;
    slug: string;
    tagline: string;
    short_description: string;
    description: string;
    hero_image: string;
    galleryImages: string[];
    featuresText: string;
    featureBlocks: SeriesFeatureBlockForm[];
    contentBlocks: SeriesContentBlockForm[];
    footnotesText: string;
    seo_title: string;
    seo_description: string;
    source_url: string;
    sort_order: number;
    is_published: boolean;
};

type SeriesFeatureBlockForm = {
    title: string;
    text: string;
    image_url: string;
    icon: string;
    footnote: string;
};

type SeriesContentBlockForm = {
    kind: 'text' | 'image_text' | 'media';
    title: string;
    text: string;
    image_url: string;
    layout: 'text_left' | 'text_right' | 'full';
};

const brands = ref<ManagerBrand[]>([]);
const loading = ref(true);
const saving = ref(false);
const query = ref('');
const error = ref('');
const toast = ref('');
const modalOpen = ref(false);
const editingBrand = ref<ManagerBrand | null>(null);
const selectedBrandId = ref<number | null>(null);
const seriesItems = ref<ManagerBrandSeries[]>([]);
const seriesLoading = ref(false);
const seriesSaving = ref(false);
const seriesError = ref('');
const seriesModalOpen = ref(false);
const editingSeries = ref<ManagerBrandSeries | null>(null);
const reorderingBrands = ref(false);
const reorderingSeries = ref(false);
const draggedBrandId = ref<number | null>(null);
const brandDropTargetId = ref<number | null>(null);
const draggedSeriesId = ref<number | null>(null);
const seriesDropTargetId = ref<number | null>(null);
const expandedSeriesIds = ref<Set<number>>(new Set());
const form = ref<BrandForm>({
    title: '',
    slug: '',
    logo_url: '',
    description: '',
    sort_order: 0,
    is_published: true,
});
const seriesForm = ref<SeriesForm>({
    title: '',
    slug: '',
    tagline: '',
    short_description: '',
    description: '',
    hero_image: '',
    galleryImages: [],
    featuresText: '',
    featureBlocks: [],
    contentBlocks: [],
    footnotesText: '',
    seo_title: '',
    seo_description: '',
    source_url: '',
    sort_order: 0,
    is_published: true,
});
const pendingGalleryImage = ref('');

const filteredBrands = computed(() => {
    const q = query.value.trim().toLowerCase();
    if (!q) return brands.value;
    return brands.value.filter((item) => {
        return (
            String(item.title || '').toLowerCase().includes(q)
            || String(item.slug || '').toLowerCase().includes(q)
        );
    });
});

const selectedBrand = computed(() => {
    if (!selectedBrandId.value) return null;
    return brands.value.find((item) => item.id === selectedBrandId.value) || null;
});

const isBrandSearchActive = computed(() => query.value.trim().length > 0);
const isBrandReorderDisabled = computed(() => (
    loading.value
    || saving.value
    || reorderingBrands.value
    || isBrandSearchActive.value
));
const isSeriesReorderDisabled = computed(() => (
    !selectedBrandId.value
    || seriesLoading.value
    || seriesSaving.value
    || reorderingSeries.value
));

const SORT_ORDER_STEP = 10;

const getNextSortOrder = <T extends { sort_order?: number | null }>(items: T[]) => {
    const maxOrder = items.reduce((max, item) => Math.max(max, Number(item.sort_order || 0)), 0);
    return maxOrder + SORT_ORDER_STEP;
};

const moveItemById = <T extends { id: number }>(items: T[], draggedId: number, targetId: number) => {
    const sourceIndex = items.findIndex((item) => item.id === draggedId);
    const targetIndex = items.findIndex((item) => item.id === targetId);
    if (sourceIndex < 0 || targetIndex < 0 || sourceIndex === targetIndex) return items;

    const next = [...items];
    const [moved] = next.splice(sourceIndex, 1);
    if (!moved) return items;
    next.splice(targetIndex, 0, moved);
    return next;
};

const isSeriesExpanded = (seriesId: number) => expandedSeriesIds.value.has(seriesId);

const hasSeriesDetails = (series: ManagerBrandSeries) => Boolean(
    series.tagline
    || series.short_description
    || series.description
    || series.hero_image
    || series.gallery_images?.length
    || series.features?.length
    || series.feature_blocks?.length
    || series.content_blocks?.length
    || series.footnotes?.length
    || series.seo_title
    || series.seo_description
    || series.source_url
);

const toggleSeriesExpanded = (seriesId: number) => {
    const next = new Set(expandedSeriesIds.value);
    if (next.has(seriesId)) {
        next.delete(seriesId);
    } else {
        next.add(seriesId);
    }
    expandedSeriesIds.value = next;
};

const toggleSeriesExpandedFromCard = (series: ManagerBrandSeries) => {
    if (!hasSeriesDetails(series)) return;
    if (window.matchMedia('(min-width: 1024px)').matches) return;
    toggleSeriesExpanded(series.id);
};

const withSortOrder = <T extends { sort_order: number }>(items: T[]) => (
    items.map((item, index) => ({
        ...item,
        sort_order: (index + 1) * SORT_ORDER_STEP,
    }))
);

const getChangedSortItems = <T extends { id: number; sort_order: number }>(previous: T[], next: T[]) => {
    const previousOrder = new Map(previous.map((item) => [item.id, Number(item.sort_order || 0)]));
    return next.filter((item) => Number(item.sort_order || 0) !== previousOrder.get(item.id));
};

const resetForm = () => {
    form.value = {
        title: '',
        slug: '',
        logo_url: '',
        description: '',
        sort_order: getNextSortOrder(brands.value),
        is_published: true,
    };
};

const resetSeriesForm = () => {
    pendingGalleryImage.value = '';
    seriesForm.value = {
        title: '',
        slug: '',
        tagline: '',
        short_description: '',
        description: '',
        hero_image: '',
        galleryImages: [],
        featuresText: '',
        featureBlocks: [],
        contentBlocks: [],
        footnotesText: '',
        seo_title: '',
        seo_description: '',
        source_url: '',
        sort_order: getNextSortOrder(seriesItems.value),
        is_published: true,
    };
};

const setToast = (message: string) => {
    toast.value = message;
    window.setTimeout(() => {
        if (toast.value === message) toast.value = '';
    }, 3000);
};

const fetchBrands = async () => {
    loading.value = true;
    error.value = '';
    try {
        const res = await api.listManagerBrands();
        brands.value = [...(res.items || [])];
        if (selectedBrandId.value && !brands.value.some((item) => item.id === selectedBrandId.value)) {
            selectedBrandId.value = null;
        }
        if (!selectedBrandId.value && brands.value.length > 0) {
            selectedBrandId.value = brands.value[0]?.id || null;
        }
    } catch (err) {
        error.value = getApiErrorMessage(err);
    } finally {
        loading.value = false;
    }
};

const fetchSeries = async () => {
    if (!selectedBrandId.value) {
        seriesItems.value = [];
        return;
    }

    seriesLoading.value = true;
    seriesError.value = '';
    try {
        const res = await api.listManagerBrandSeries(selectedBrandId.value);
        seriesItems.value = [...(res.items || [])];
        const existingIds = new Set(seriesItems.value.map((item) => item.id));
        expandedSeriesIds.value = new Set([...expandedSeriesIds.value].filter((id) => existingIds.has(id)));
    } catch (err) {
        seriesError.value = getApiErrorMessage(err);
    } finally {
        seriesLoading.value = false;
    }
};

const selectBrand = (brand: ManagerBrand) => {
    selectedBrandId.value = brand.id;
};

const openCreate = () => {
    editingBrand.value = null;
    resetForm();
    modalOpen.value = true;
    error.value = '';
};

const openEdit = (brand: ManagerBrand) => {
    editingBrand.value = brand;
    form.value = {
        title: String(brand.title || ''),
        slug: String(brand.slug || ''),
        logo_url: String(brand.logo_url || ''),
        description: String(brand.description || ''),
        sort_order: Number(brand.sort_order || 0),
        is_published: Boolean(brand.is_published),
    };
    modalOpen.value = true;
    error.value = '';
};

const closeModal = () => {
    modalOpen.value = false;
    editingBrand.value = null;
    resetForm();
};

const openSeriesCreate = () => {
    editingSeries.value = null;
    resetSeriesForm();
    seriesModalOpen.value = true;
    seriesError.value = '';
};

const openSeriesEdit = (series: ManagerBrandSeries) => {
    editingSeries.value = series;
    seriesForm.value = {
        title: String(series.title || ''),
        slug: String(series.slug || ''),
        tagline: String(series.tagline || ''),
        short_description: String(series.short_description || ''),
        description: String(series.description || ''),
        hero_image: String(series.hero_image || ''),
        galleryImages: [...(series.gallery_images || [])],
        featuresText: (series.features || []).join('\n'),
        featureBlocks: (series.feature_blocks || []).map((block) => ({
            title: String(block.title || ''),
            text: String(block.text || ''),
            image_url: String(block.image_url || ''),
            icon: String(block.icon || ''),
            footnote: String(block.footnote || ''),
        })),
        contentBlocks: (series.content_blocks || []).map((block) => ({
            kind: block.kind || 'text',
            title: String(block.title || ''),
            text: String(block.text || ''),
            image_url: String(block.image_url || ''),
            layout: block.layout || 'text_left',
        })),
        footnotesText: (series.footnotes || []).join('\n'),
        seo_title: String(series.seo_title || ''),
        seo_description: String(series.seo_description || ''),
        source_url: String(series.source_url || ''),
        sort_order: Number(series.sort_order || 0),
        is_published: Boolean(series.is_published),
    };
    seriesModalOpen.value = true;
    seriesError.value = '';
};

const closeSeriesModal = () => {
    seriesModalOpen.value = false;
    editingSeries.value = null;
    resetSeriesForm();
};

const normalizeFeatures = (value: string) => {
    return normalizeTextList(value);
};

const normalizeTextList = (value: string) => {
    const seen = new Set<string>();
    return String(value || '')
        .split('\n')
        .map((item) => item.trim())
        .filter((item) => {
            if (!item) return false;
            const key = item.toLowerCase();
            if (seen.has(key)) return false;
            seen.add(key);
            return true;
        });
};

const normalizeUrlList = (value: string[]) => {
    const seen = new Set<string>();
    return value
        .map((item) => String(item || '').trim())
        .filter((item) => {
            if (!item) return false;
            const key = item.toLowerCase();
            if (seen.has(key)) return false;
            seen.add(key);
            return true;
        });
};

const normalizeFeatureBlocks = (blocks: SeriesFeatureBlockForm[]) => (
    blocks
        .map((block) => ({
            title: String(block.title || '').trim(),
            text: String(block.text || '').trim() || undefined,
            image_url: String(block.image_url || '').trim() || undefined,
            icon: String(block.icon || '').trim() || undefined,
            footnote: String(block.footnote || '').trim() || undefined,
        }))
        .filter((block) => block.title)
);

const normalizeContentBlocks = (blocks: SeriesContentBlockForm[]) => (
    blocks
        .map((block) => ({
            kind: block.kind || 'text',
            title: String(block.title || '').trim() || undefined,
            text: String(block.text || '').trim() || undefined,
            image_url: String(block.image_url || '').trim() || undefined,
            layout: block.layout || 'text_left',
        }))
        .filter((block) => block.title || block.text || block.image_url)
);

const addFeatureBlock = () => {
    seriesForm.value.featureBlocks.push({
        title: '',
        text: '',
        image_url: '',
        icon: '',
        footnote: '',
    });
};

const removeFeatureBlock = (index: number) => {
    seriesForm.value.featureBlocks.splice(index, 1);
};

const addContentBlock = () => {
    seriesForm.value.contentBlocks.push({
        kind: 'text',
        title: '',
        text: '',
        image_url: '',
        layout: 'text_left',
    });
};

const removeContentBlock = (index: number) => {
    seriesForm.value.contentBlocks.splice(index, 1);
};

const addGalleryImage = (url = pendingGalleryImage.value) => {
    const normalized = String(url || '').trim();
    if (!normalized) return;
    const exists = seriesForm.value.galleryImages.some((item) => item.trim().toLowerCase() === normalized.toLowerCase());
    if (!exists) {
        seriesForm.value.galleryImages.push(normalized);
    }
    pendingGalleryImage.value = '';
};

const removeGalleryImage = (index: number) => {
    seriesForm.value.galleryImages.splice(index, 1);
};

const saveBrand = async () => {
    const title = String(form.value.title || '').trim();
    if (!title) {
        error.value = 'Название бренда обязательно.';
        return;
    }

    saving.value = true;
    error.value = '';
    try {
        const wasEditing = Boolean(editingBrand.value?.id);
        const payload = {
            title,
            slug: String(form.value.slug || '').trim() || undefined,
            logo_url: String(form.value.logo_url || '').trim() || undefined,
            description: String(form.value.description || '').trim() || undefined,
            sort_order: wasEditing ? Number(form.value.sort_order || 0) : getNextSortOrder(brands.value),
            is_published: Boolean(form.value.is_published),
        };
        if (editingBrand.value?.id) {
            await api.updateManagerBrand(editingBrand.value.id, payload);
        } else {
            await api.createManagerBrand(payload);
        }
        await fetchBrands();
        closeModal();
        setToast(wasEditing ? 'Бренд обновлен' : 'Бренд создан');
    } catch (err) {
        error.value = getApiErrorMessage(err);
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
    event.dataTransfer?.setData('text/plain', String(brand.id));
    if (event.dataTransfer) {
        event.dataTransfer.effectAllowed = 'move';
    }
};

const onBrandDragOver = (event: DragEvent, brand: ManagerBrand) => {
    if (isBrandReorderDisabled.value || !draggedBrandId.value || draggedBrandId.value === brand.id) return;
    event.preventDefault();
    brandDropTargetId.value = brand.id;
    if (event.dataTransfer) {
        event.dataTransfer.dropEffect = 'move';
    }
};

const onBrandDrop = async (brand: ManagerBrand) => {
    const sourceId = draggedBrandId.value;
    resetBrandDragState();
    if (!sourceId || sourceId === brand.id || isBrandReorderDisabled.value) return;

    const previous = [...brands.value];
    const reordered = moveItemById(brands.value, sourceId, brand.id);
    const next = withSortOrder(reordered);
    const changed = getChangedSortItems(previous, next);
    if (changed.length === 0) return;

    brands.value = next;
    reorderingBrands.value = true;
    error.value = '';
    try {
        await Promise.all(changed.map((item) => api.updateManagerBrand(item.id, { sort_order: item.sort_order })));
        setToast('Порядок брендов сохранен');
        await fetchBrands();
    } catch (err) {
        brands.value = previous;
        error.value = `Не удалось сохранить порядок брендов: ${getApiErrorMessage(err)}`;
        await fetchBrands();
    } finally {
        reorderingBrands.value = false;
    }
};

const deleteBrand = async (brand: ManagerBrand) => {
    if (!confirm(`Удалить бренд "${brand.title}"?`)) return;
    error.value = '';
    try {
        await api.deleteManagerBrand(brand.id);
        await fetchBrands();
        setToast('Бренд удален');
    } catch (err) {
        error.value = getApiErrorMessage(err);
    }
};

const saveSeries = async () => {
    if (!selectedBrandId.value) return;

    const title = String(seriesForm.value.title || '').trim();
    if (!title) {
        seriesError.value = 'Название серии обязательно.';
        return;
    }

    seriesSaving.value = true;
    seriesError.value = '';
    try {
        const wasEditing = Boolean(editingSeries.value?.id);
        const payload = {
            title,
            slug: String(seriesForm.value.slug || '').trim() || undefined,
            tagline: String(seriesForm.value.tagline || '').trim() || undefined,
            short_description: String(seriesForm.value.short_description || '').trim() || undefined,
            description: String(seriesForm.value.description || '').trim() || undefined,
            hero_image: String(seriesForm.value.hero_image || '').trim() || undefined,
            gallery_images: normalizeUrlList(seriesForm.value.galleryImages),
            features: normalizeFeatures(seriesForm.value.featuresText),
            feature_blocks: normalizeFeatureBlocks(seriesForm.value.featureBlocks),
            content_blocks: normalizeContentBlocks(seriesForm.value.contentBlocks),
            footnotes: normalizeTextList(seriesForm.value.footnotesText),
            seo_title: String(seriesForm.value.seo_title || '').trim() || undefined,
            seo_description: String(seriesForm.value.seo_description || '').trim() || undefined,
            source_url: String(seriesForm.value.source_url || '').trim() || undefined,
            sort_order: wasEditing ? Number(seriesForm.value.sort_order || 0) : getNextSortOrder(seriesItems.value),
            is_published: Boolean(seriesForm.value.is_published),
        };
        if (editingSeries.value?.id) {
            await api.updateManagerBrandSeries(selectedBrandId.value, editingSeries.value.id, payload);
        } else {
            await api.createManagerBrandSeries(selectedBrandId.value, payload);
        }
        await fetchSeries();
        closeSeriesModal();
        setToast(wasEditing ? 'Серия обновлена' : 'Серия создана');
    } catch (err) {
        seriesError.value = getApiErrorMessage(err);
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
    event.dataTransfer?.setData('text/plain', String(series.id));
    if (event.dataTransfer) {
        event.dataTransfer.effectAllowed = 'move';
    }
};

const onSeriesDragOver = (event: DragEvent, series: ManagerBrandSeries) => {
    if (isSeriesReorderDisabled.value || !draggedSeriesId.value || draggedSeriesId.value === series.id) return;
    event.preventDefault();
    seriesDropTargetId.value = series.id;
    if (event.dataTransfer) {
        event.dataTransfer.dropEffect = 'move';
    }
};

const onSeriesDrop = async (series: ManagerBrandSeries) => {
    const brandId = selectedBrandId.value;
    const sourceId = draggedSeriesId.value;
    resetSeriesDragState();
    if (!brandId || !sourceId || sourceId === series.id || isSeriesReorderDisabled.value) return;

    const previous = [...seriesItems.value];
    const reordered = moveItemById(seriesItems.value, sourceId, series.id);
    const next = withSortOrder(reordered);
    const changed = getChangedSortItems(previous, next);
    if (changed.length === 0) return;

    seriesItems.value = next;
    reorderingSeries.value = true;
    seriesError.value = '';
    try {
        await Promise.all(changed.map((item) => (
            api.updateManagerBrandSeries(brandId, item.id, { sort_order: item.sort_order })
        )));
        setToast('Порядок серий сохранен');
        await fetchSeries();
    } catch (err) {
        seriesItems.value = previous;
        seriesError.value = `Не удалось сохранить порядок серий: ${getApiErrorMessage(err)}`;
        await fetchSeries();
    } finally {
        reorderingSeries.value = false;
    }
};

const deleteSeries = async (series: ManagerBrandSeries) => {
    if (!selectedBrandId.value) return;
    if (!confirm(`Удалить серию "${series.title}"?`)) return;

    seriesError.value = '';
    try {
        await api.deleteManagerBrandSeries(selectedBrandId.value, series.id);
        await fetchSeries();
        setToast('Серия удалена');
    } catch (err) {
        seriesError.value = getApiErrorMessage(err);
    }
};

watch(selectedBrandId, () => {
    fetchSeries();
});

onMounted(() => {
    fetchBrands();
});
</script>

<template>
    <div class="space-y-5">
        <Transition name="fade">
            <div v-if="toast" class="fixed top-6 right-6 z-[100] rounded-xl bg-teal-600 px-6 py-3 font-medium text-white shadow-2xl">
                {{ toast }}
            </div>
        </Transition>

        <div class="flex items-center justify-between">
            <h1 class="text-2xl font-bold text-gray-900 dark:text-white tracking-tight">Бренды</h1>
            <button
                type="button"
                class="inline-flex items-center justify-center gap-2 rounded-lg bg-teal-600 px-4 py-2 text-sm font-medium text-white hover:bg-teal-500 transition-all"
                @click="openCreate"
            >
                <span class="material-icons-round text-[18px]">add</span>
                Новый бренд
            </button>
        </div>

        <div class="rounded-xl border border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-800/70 p-4 space-y-4">
            <div class="flex flex-col sm:flex-row gap-3 sm:items-center sm:justify-between">
                <input
                    v-model="query"
                    type="text"
                    placeholder="Поиск по названию или slug"
                    class="w-full sm:max-w-sm px-3 py-2 bg-slate-100 dark:bg-slate-900 border border-gray-200 dark:border-slate-700 rounded-lg text-sm"
                />
                <div class="text-xs text-gray-500 dark:text-slate-400">
                    <span v-if="reorderingBrands" class="font-semibold text-teal-600 dark:text-teal-300">Сохраняем порядок...</span>
                    <span v-else-if="isBrandSearchActive">Перетаскивание доступно после очистки поиска.</span>
                    <span v-else>Всего: {{ filteredBrands.length }} · порядок меняется перетаскиванием</span>
                </div>
            </div>

            <div v-if="error" class="rounded-lg border border-red-200 dark:border-red-900/40 bg-red-50 dark:bg-red-900/20 px-3 py-2 text-sm text-red-700 dark:text-red-300">
                {{ error }}
            </div>

            <div v-if="loading" class="py-6 text-sm text-gray-500 dark:text-slate-400">Загрузка брендов...</div>
            <div v-else-if="filteredBrands.length === 0" class="py-6 text-sm text-gray-500 dark:text-slate-400">Бренды не найдены.</div>

            <div v-else class="overflow-x-auto">
                <table class="min-w-full text-sm">
                    <thead>
                        <tr class="text-left text-gray-500 dark:text-slate-400 border-b border-gray-100 dark:border-slate-700">
                            <th class="py-2 pr-3 font-semibold w-12">Порядок</th>
                            <th class="py-2 pr-3 font-semibold">Бренд</th>
                            <th class="py-2 pr-3 font-semibold">Slug</th>
                            <th class="py-2 pr-3 font-semibold">Товаров</th>
                            <th class="py-2 pr-3 font-semibold">Статус</th>
                            <th class="py-2 text-right font-semibold">Действия</th>
                        </tr>
                    </thead>
                    <tbody>
                        <template v-for="brand in filteredBrands" :key="brand.id">
                        <tr v-if="brandDropTargetId === brand.id" aria-hidden="true">
                            <td colspan="6" class="p-0">
                                <div class="mx-3 h-1 rounded-full bg-teal-400 shadow-[0_0_18px_rgba(20,184,166,0.75)] dark:bg-teal-300"></div>
                            </td>
                        </tr>
                        <tr
                            class="border-b border-gray-100 dark:border-slate-800/80 cursor-pointer transition-colors"
                            :class="[
                                selectedBrandId === brand.id ? 'bg-teal-50/80 dark:bg-teal-900/20' : 'hover:bg-gray-50 dark:hover:bg-slate-800',
                                draggedBrandId === brand.id ? 'opacity-50' : '',
                            ]"
                            :draggable="!isBrandReorderDisabled"
                            @dragstart="onBrandDragStart($event, brand)"
                            @dragover="onBrandDragOver($event, brand)"
                            @dragleave="brandDropTargetId = brandDropTargetId === brand.id ? null : brandDropTargetId"
                            @drop.prevent="onBrandDrop(brand)"
                            @dragend="resetBrandDragState"
                            @click="selectBrand(brand)"
                        >
                            <td class="py-2 pr-3">
                                <button
                                    type="button"
                                    class="inline-flex h-8 w-8 items-center justify-center rounded-lg border border-gray-200 dark:border-slate-700 text-gray-400 dark:text-slate-500 transition-colors"
                                    :class="isBrandReorderDisabled ? 'cursor-not-allowed opacity-40' : 'cursor-grab hover:bg-gray-50 hover:text-teal-600 dark:hover:bg-slate-700 dark:hover:text-teal-300 active:cursor-grabbing'"
                                    :disabled="isBrandReorderDisabled"
                                    title="Перетащите бренд выше или ниже"
                                    @click.stop
                                >
                                    <span class="material-icons-round text-[20px]">drag_indicator</span>
                                </button>
                            </td>
                            <td class="py-2 pr-3">
                                <div class="flex items-center gap-2 min-w-[220px]">
                                    <img
                                        v-if="brand.logo_url"
                                        :src="brand.logo_url"
                                        :alt="brand.title"
                                        class="w-7 h-7 rounded bg-white object-contain border border-gray-200"
                                    />
                                    <div>
                                        <div class="font-semibold text-gray-800 dark:text-slate-200">{{ brand.title }}</div>
                                        <div v-if="brand.description" class="text-xs text-gray-500 dark:text-slate-400 truncate max-w-[360px]">
                                            {{ brand.description }}
                                        </div>
                                    </div>
                                </div>
                            </td>
                            <td class="py-2 pr-3 text-gray-600 dark:text-slate-300 font-mono">{{ brand.slug }}</td>
                            <td class="py-2 pr-3 text-gray-700 dark:text-slate-200">{{ brand.products_count }}</td>
                            <td class="py-2 pr-3">
                                <span
                                    class="inline-flex items-center rounded-full px-2 py-0.5 text-xs font-semibold"
                                    :class="brand.is_published ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300' : 'bg-gray-100 text-gray-600 dark:bg-slate-700 dark:text-slate-300'"
                                >
                                    {{ brand.is_published ? 'Публичный' : 'Скрыт' }}
                                </span>
                            </td>
                            <td class="py-2 text-right">
                                <div class="inline-flex items-center gap-1">
                                    <button
                                        type="button"
                                        class="px-2.5 py-1 rounded border border-gray-200 dark:border-slate-700 text-xs font-semibold hover:bg-gray-50 dark:hover:bg-slate-700"
                                        @click.stop="selectBrand(brand)"
                                    >
                                        Серии
                                    </button>
                                    <button
                                        type="button"
                                        class="px-2.5 py-1 rounded border border-gray-200 dark:border-slate-700 text-xs font-semibold hover:bg-gray-50 dark:hover:bg-slate-700"
                                        @click.stop="openEdit(brand)"
                                    >
                                        Изменить
                                    </button>
                                    <button
                                        type="button"
                                        class="px-2.5 py-1 rounded border border-red-200 text-red-600 text-xs font-semibold hover:bg-red-50 disabled:opacity-50"
                                        :disabled="(brand.products_count ?? 0) > 0"
                                        @click.stop="deleteBrand(brand)"
                                    >
                                        Удалить
                                    </button>
                                </div>
                            </td>
                        </tr>
                        </template>
                    </tbody>
                </table>
            </div>
        </div>

        <div class="rounded-xl border border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-800/70 p-4 space-y-4">
            <div class="flex flex-col sm:flex-row gap-3 sm:items-center sm:justify-between">
                <div>
                    <p class="text-xs uppercase tracking-[0.18em] font-bold text-teal-600 dark:text-teal-300">Серии бренда</p>
                    <h2 class="text-lg font-bold text-gray-900 dark:text-white">
                        {{ selectedBrand ? selectedBrand.title : 'Выберите бренд' }}
                    </h2>
                    <p class="text-sm text-gray-500 dark:text-slate-400">
                        Описания и фичи попадут на брендовые страницы и в блок связанных моделей. Порядок меняется перетаскиванием карточек.
                    </p>
                </div>
                <div v-if="reorderingSeries" class="text-xs font-semibold text-teal-600 dark:text-teal-300">
                    Сохраняем порядок серий...
                </div>
                <button
                    type="button"
                    class="inline-flex items-center justify-center gap-2 rounded-lg bg-teal-600 px-4 py-2 text-sm font-medium text-white hover:bg-teal-500 transition-all disabled:opacity-50"
                    :disabled="!selectedBrand"
                    @click="openSeriesCreate"
                >
                    <span class="material-icons-round text-[18px]">add</span>
                    Новая серия
                </button>
            </div>

            <div v-if="seriesError" class="rounded-lg border border-red-200 dark:border-red-900/40 bg-red-50 dark:bg-red-900/20 px-3 py-2 text-sm text-red-700 dark:text-red-300">
                {{ seriesError }}
            </div>

            <div v-if="!selectedBrand" class="py-6 text-sm text-gray-500 dark:text-slate-400">
                Выберите бренд в таблице выше.
            </div>
            <div v-else-if="seriesLoading" class="py-6 text-sm text-gray-500 dark:text-slate-400">
                Загрузка серий...
            </div>
            <div v-else-if="seriesItems.length === 0" class="rounded-xl border border-dashed border-gray-300 dark:border-slate-700 px-4 py-8 text-sm text-gray-500 dark:text-slate-400">
                У бренда пока нет серий. Можно добавить первую вручную.
            </div>
            <div v-else class="space-y-2">
                <article
                    v-for="series in seriesItems"
                    :key="series.id"
                    class="relative rounded-xl border border-gray-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/50 px-3 py-2.5 pr-20 transition-shadow lg:pr-3"
                    :class="[
                        draggedSeriesId === series.id ? 'opacity-50' : '',
                        hasSeriesDetails(series) ? 'cursor-pointer lg:cursor-default' : '',
                    ]"
                    :draggable="!isSeriesReorderDisabled"
                    @click="toggleSeriesExpandedFromCard(series)"
                    @dragstart="onSeriesDragStart($event, series)"
                    @dragover="onSeriesDragOver($event, series)"
                    @dragleave="seriesDropTargetId = seriesDropTargetId === series.id ? null : seriesDropTargetId"
                    @drop.prevent="onSeriesDrop(series)"
                    @dragend="resetSeriesDragState"
                >
                    <span
                        v-if="seriesDropTargetId === series.id"
                        aria-hidden="true"
                        class="pointer-events-none absolute -top-2 left-3 right-3 h-1 rounded-full bg-teal-400 shadow-[0_0_18px_rgba(20,184,166,0.75)] dark:bg-teal-300"
                    />
                    <div class="absolute right-2 top-2 z-10 inline-flex items-center gap-1 lg:hidden" @click.stop>
                        <button
                            type="button"
                            class="inline-flex h-8 w-8 items-center justify-center rounded-lg border border-gray-200 bg-white/85 text-gray-600 shadow-sm backdrop-blur hover:text-teal-700 dark:border-slate-700 dark:bg-slate-900/85 dark:text-slate-300 dark:hover:text-teal-200"
                            title="Изменить серию"
                            aria-label="Изменить серию"
                            @click.stop="openSeriesEdit(series)"
                        >
                            <span class="material-icons-round text-[18px]">edit</span>
                        </button>
                        <button
                            type="button"
                            class="inline-flex h-8 w-8 items-center justify-center rounded-lg border border-red-200 bg-white/85 text-red-500 shadow-sm backdrop-blur hover:bg-red-50 disabled:opacity-40 dark:border-red-900/60 dark:bg-slate-900/85 dark:hover:bg-red-950/30"
                            :disabled="(series.products_count ?? 0) > 0"
                            title="Удалить серию"
                            aria-label="Удалить серию"
                            @click.stop="deleteSeries(series)"
                        >
                            <span class="material-icons-round text-[18px]">delete</span>
                        </button>
                    </div>
                    <div class="flex flex-col gap-2 lg:flex-row lg:items-center lg:gap-3">
                        <div class="flex min-w-0 flex-1 items-start gap-2">
                            <button
                                type="button"
                                class="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-gray-200 dark:border-slate-700 text-gray-400 dark:text-slate-500 transition-colors"
                                :class="isSeriesReorderDisabled ? 'cursor-not-allowed opacity-40' : 'cursor-grab hover:bg-white hover:text-teal-600 dark:hover:bg-slate-800 dark:hover:text-teal-300 active:cursor-grabbing'"
                                :disabled="isSeriesReorderDisabled"
                                title="Перетащите серию выше или ниже"
                                @click.stop
                            >
                                <span class="material-icons-round text-[22px]">drag_indicator</span>
                            </button>
                            <img
                                v-if="series.hero_image"
                                :src="series.hero_image"
                                :alt="series.title"
                                class="h-10 w-10 shrink-0 rounded-lg object-cover border border-gray-200 dark:border-slate-700 bg-white"
                            />
                            <div class="min-w-0 flex-1">
                                <div class="flex flex-wrap items-center gap-x-2 gap-y-1">
                                    <h3 class="min-w-0 break-words font-bold leading-tight text-gray-900 dark:text-slate-100">{{ series.title }}</h3>
                                    <span
                                        class="inline-flex items-center rounded-full px-2 py-0.5 text-xs font-semibold"
                                        :class="series.is_published ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300' : 'bg-gray-100 text-gray-600 dark:bg-slate-700 dark:text-slate-300'"
                                    >
                                        {{ series.is_published ? 'Публичная' : 'Скрыта' }}
                                    </span>
                                    <span class="text-xs text-gray-500 dark:text-slate-400">{{ series.products_count }} товаров</span>
                                </div>
                                <p class="text-xs font-mono text-gray-500 dark:text-slate-400">{{ series.slug }}</p>
                                <p v-if="series.tagline" class="mt-0.5 text-sm font-semibold text-gray-700 dark:text-slate-200">
                                    {{ series.tagline }}
                                </p>
                                <p v-else-if="series.short_description" class="mt-0.5 line-clamp-2 text-sm text-gray-500 dark:text-slate-400">
                                    {{ series.short_description }}
                                </p>
                            </div>
                        </div>
                        <div v-if="series.features?.length && !isSeriesExpanded(series.id)" class="flex min-w-0 flex-1 flex-wrap gap-1.5 lg:max-w-[34%]">
                            <span
                                v-for="feature in series.features.slice(0, 3)"
                                :key="feature"
                                class="rounded-full border border-teal-200 dark:border-teal-900/60 bg-teal-50 dark:bg-teal-950/30 px-2 py-0.5 text-xs font-semibold text-teal-700 dark:text-teal-200"
                            >
                                {{ feature }}
                            </span>
                            <span
                                v-if="series.features.length > 3"
                                class="rounded-full border border-gray-200 dark:border-slate-700 px-2 py-0.5 text-xs font-semibold text-gray-500 dark:text-slate-400"
                            >
                                +{{ series.features.length - 3 }}
                            </span>
                        </div>
                        <div class="hidden shrink-0 items-center gap-1 lg:inline-flex">
                            <button
                                v-if="hasSeriesDetails(series)"
                                type="button"
                                class="inline-flex items-center gap-1 px-2.5 py-1 rounded border border-gray-200 dark:border-slate-700 text-xs font-semibold hover:bg-white dark:hover:bg-slate-800"
                                :aria-expanded="isSeriesExpanded(series.id)"
                                @click.stop="toggleSeriesExpanded(series.id)"
                            >
                                <span class="material-icons-round text-[16px]">
                                    {{ isSeriesExpanded(series.id) ? 'expand_less' : 'expand_more' }}
                                </span>
                                Детали
                            </button>
                            <button
                                type="button"
                                class="px-2.5 py-1 rounded border border-gray-200 dark:border-slate-700 text-xs font-semibold hover:bg-white dark:hover:bg-slate-800"
                                @click.stop="openSeriesEdit(series)"
                            >
                                Изменить
                            </button>
                            <button
                                type="button"
                                class="px-2.5 py-1 rounded border border-red-200 text-red-600 text-xs font-semibold hover:bg-red-50 disabled:opacity-50"
                                :disabled="(series.products_count ?? 0) > 0"
                                @click.stop="deleteSeries(series)"
                            >
                                Удалить
                            </button>
                        </div>
                    </div>
                    <div
                        v-if="!isSeriesExpanded(series.id)"
                        class="mt-2 flex flex-wrap gap-1.5 text-[11px] font-semibold"
                    >
                        <span
                            v-if="series.gallery_images?.length"
                            class="rounded-full bg-blue-50 px-2 py-0.5 text-blue-700 dark:bg-blue-950/30 dark:text-blue-200"
                        >
                            галерея {{ series.gallery_images.length }}
                        </span>
                        <span
                            v-if="series.feature_blocks?.length"
                            class="rounded-full bg-purple-50 px-2 py-0.5 text-purple-700 dark:bg-purple-950/30 dark:text-purple-200"
                        >
                            преимущества {{ series.feature_blocks.length }}
                        </span>
                        <span
                            v-if="series.content_blocks?.length"
                            class="rounded-full bg-amber-50 px-2 py-0.5 text-amber-700 dark:bg-amber-950/30 dark:text-amber-200"
                        >
                            контент {{ series.content_blocks.length }}
                        </span>
                        <span
                            v-if="series.seo_title || series.seo_description"
                            class="rounded-full bg-emerald-50 px-2 py-0.5 text-emerald-700 dark:bg-emerald-950/30 dark:text-emerald-200"
                        >
                            SEO
                        </span>
                    </div>
                    <div
                        v-if="isSeriesExpanded(series.id)"
                        class="mt-2 border-t border-gray-200 dark:border-slate-700 pt-2 text-sm text-gray-600 dark:text-slate-300"
                    >
                        <p v-if="series.tagline" class="font-semibold text-gray-800 dark:text-slate-100">
                            {{ series.tagline }}
                        </p>
                        <p v-if="series.short_description" class="mt-1">
                            {{ series.short_description }}
                        </p>
                        <p v-if="series.description">
                            {{ series.description }}
                        </p>
                        <div v-if="series.features?.length" class="mt-2 flex flex-wrap gap-1.5">
                            <span
                                v-for="feature in series.features"
                                :key="feature"
                                class="rounded-full border border-teal-200 dark:border-teal-900/60 bg-teal-50 dark:bg-teal-950/30 px-2 py-0.5 text-xs font-semibold text-teal-700 dark:text-teal-200"
                            >
                                {{ feature }}
                            </span>
                        </div>
                        <div v-if="series.feature_blocks?.length" class="mt-2 grid gap-1.5 sm:grid-cols-2">
                            <div
                                v-for="block in series.feature_blocks"
                                :key="`${series.id}-${block.title}`"
                                class="rounded-lg border border-gray-200 bg-white px-2 py-1.5 text-xs dark:border-slate-700 dark:bg-slate-900"
                            >
                                <span class="font-semibold text-gray-800 dark:text-slate-100">{{ block.title }}</span>
                                <p v-if="block.text" class="mt-0.5 text-gray-500 dark:text-slate-400">{{ block.text }}</p>
                            </div>
                        </div>
                    </div>
                </article>
            </div>
        </div>

        <div
            v-if="modalOpen"
            class="fixed inset-0 z-[70] bg-black/50 backdrop-blur-sm flex items-center justify-center p-4"
            @click.self="closeModal"
        >
            <div class="w-full max-w-2xl rounded-2xl border border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-900 shadow-2xl overflow-hidden">
                <header class="px-5 py-4 border-b border-gray-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800/60">
                    <h2 class="text-lg font-bold text-gray-900 dark:text-slate-100">
                        {{ editingBrand ? 'Редактирование бренда' : 'Новый бренд' }}
                    </h2>
                </header>
                <div class="p-5 space-y-3">
                    <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
                        <label class="text-sm space-y-1">
                            <span class="text-gray-600 dark:text-slate-300 font-medium">Название</span>
                            <input v-model="form.title" type="text" class="w-full px-3 py-2 rounded-lg border border-gray-200 dark:border-slate-700 bg-slate-100 dark:bg-slate-900" />
                        </label>
                        <label class="text-sm space-y-1">
                            <span class="text-gray-600 dark:text-slate-300 font-medium">Slug</span>
                            <input v-model="form.slug" type="text" class="w-full px-3 py-2 rounded-lg border border-gray-200 dark:border-slate-700 bg-slate-100 dark:bg-slate-900" />
                        </label>
                    </div>
                    <MediaField
                        v-model="form.logo_url"
                        label="Логотип"
                        kind="brand"
                        :tags="['logo', 'brand']"
                        accept="image/svg+xml,image/png,image/jpeg,image/webp,.svg"
                        placeholder="/media/library/original/logo.svg"
                    />
                    <label class="text-sm space-y-1 block">
                        <span class="text-gray-600 dark:text-slate-300 font-medium">Описание</span>
                        <textarea v-model="form.description" rows="4" class="w-full px-3 py-2 rounded-lg border border-gray-200 dark:border-slate-700 bg-slate-100 dark:bg-slate-900" />
                        <span class="block text-xs text-gray-500 dark:text-slate-400">
                            Можно использовать Markdown: абзацы, списки, ссылки, **жирный**, *курсив*.
                        </span>
                    </label>
                    <label class="text-sm flex items-center gap-2">
                        <input v-model="form.is_published" type="checkbox" class="rounded border-gray-300 dark:border-slate-700" />
                        <span class="text-gray-600 dark:text-slate-300 font-medium">Публиковать бренд</span>
                    </label>
                </div>
                <footer class="px-5 py-4 border-t border-gray-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800/60 flex items-center justify-end gap-2">
                    <button type="button" class="px-4 py-2 rounded-lg text-sm font-medium text-gray-600 dark:text-slate-300 hover:bg-gray-100 dark:hover:bg-slate-700" @click="closeModal">
                        Отмена
                    </button>
                    <button type="button" class="px-4 py-2 rounded-lg text-sm font-semibold text-white bg-teal-600 hover:bg-teal-700 disabled:opacity-50" :disabled="saving" @click="saveBrand">
                        {{ saving ? 'Сохранение...' : 'Сохранить' }}
                    </button>
                </footer>
            </div>
        </div>

        <div
            v-if="seriesModalOpen"
            class="fixed inset-0 z-[70] bg-black/50 backdrop-blur-sm flex items-center justify-center p-4"
            @click.self="closeSeriesModal"
        >
            <div class="w-full max-w-5xl rounded-2xl border border-gray-200 dark:border-slate-700 bg-white dark:bg-slate-900 shadow-2xl overflow-hidden">
                <header class="px-5 py-4 border-b border-gray-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800/60">
                    <h2 class="text-lg font-bold text-gray-900 dark:text-slate-100">
                        {{ editingSeries ? 'Редактирование серии' : 'Новая серия' }}
                    </h2>
                    <p v-if="selectedBrand" class="text-sm text-gray-500 dark:text-slate-400">{{ selectedBrand.title }}</p>
                </header>
                <div class="max-h-[72vh] overflow-y-auto p-5 space-y-5">
                    <section class="space-y-3">
                        <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
                            <label class="text-sm space-y-1">
                                <span class="text-gray-600 dark:text-slate-300 font-medium">Название</span>
                                <input v-model="seriesForm.title" type="text" class="w-full px-3 py-2 rounded-lg border border-gray-200 dark:border-slate-700 bg-slate-100 dark:bg-slate-900" />
                            </label>
                            <label class="text-sm space-y-1">
                                <span class="text-gray-600 dark:text-slate-300 font-medium">Slug</span>
                                <input v-model="seriesForm.slug" type="text" class="w-full px-3 py-2 rounded-lg border border-gray-200 dark:border-slate-700 bg-slate-100 dark:bg-slate-900" />
                            </label>
                        </div>
                        <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
                            <label class="text-sm space-y-1">
                                <span class="text-gray-600 dark:text-slate-300 font-medium">Слоган</span>
                                <input v-model="seriesForm.tagline" type="text" class="w-full px-3 py-2 rounded-lg border border-gray-200 dark:border-slate-700 bg-slate-100 dark:bg-slate-900" placeholder="Охлаждение без прямого потока" />
                            </label>
                            <label class="text-sm space-y-1">
                                <span class="text-gray-600 dark:text-slate-300 font-medium">Источник</span>
                                <input v-model="seriesForm.source_url" type="url" class="w-full px-3 py-2 rounded-lg border border-gray-200 dark:border-slate-700 bg-slate-100 dark:bg-slate-900" placeholder="https://..." />
                            </label>
                        </div>
                        <div class="grid grid-cols-1 lg:grid-cols-2 gap-3">
                            <label class="text-sm space-y-1 block">
                                <span class="text-gray-600 dark:text-slate-300 font-medium">Короткое описание</span>
                                <textarea v-model="seriesForm.short_description" rows="3" class="w-full px-3 py-2 rounded-lg border border-gray-200 dark:border-slate-700 bg-slate-100 dark:bg-slate-900" />
                            </label>
                            <label class="text-sm space-y-1 block">
                                <span class="text-gray-600 dark:text-slate-300 font-medium">Описание серии</span>
                                <textarea v-model="seriesForm.description" rows="3" class="w-full px-3 py-2 rounded-lg border border-gray-200 dark:border-slate-700 bg-slate-100 dark:bg-slate-900" />
                            </label>
                        </div>
                    </section>

                    <section class="space-y-4 border-t border-gray-200 pt-4 dark:border-slate-700">
                        <div class="max-w-2xl">
                            <MediaField
                                v-model="seriesForm.hero_image"
                                label="Hero image"
                                kind="brand"
                                :tags="['series', 'hero']"
                                accept="image/png,image/jpeg,image/webp,image/svg+xml,.svg"
                                placeholder="/media/library/original/series.webp"
                            />
                        </div>
                        <div class="space-y-3">
                            <div>
                                <h3 class="text-sm font-medium text-gray-600 dark:text-slate-300">Галерея</h3>
                                <p class="mt-1 text-xs text-gray-500 dark:text-slate-400">Изображения серии для лендингов, карточек и промо-блоков.</p>
                            </div>
                            <div v-if="seriesForm.galleryImages.length" class="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                                <div
                                    v-for="(_, index) in seriesForm.galleryImages"
                                    :key="`gallery-${index}`"
                                    class="rounded-xl border border-gray-200 p-3 dark:border-slate-700"
                                >
                                    <div class="mb-2 flex items-center justify-between gap-3">
                                        <span class="text-xs font-bold uppercase tracking-[0.14em] text-gray-500 dark:text-slate-400">Изображение {{ index + 1 }}</span>
                                        <button
                                            type="button"
                                            class="inline-flex h-8 w-8 items-center justify-center rounded-lg text-red-500 hover:bg-red-50 dark:hover:bg-red-950/30"
                                            title="Удалить из галереи"
                                            aria-label="Удалить из галереи"
                                            @click="removeGalleryImage(index)"
                                        >
                                            <span class="material-icons-round text-[18px]">delete</span>
                                        </button>
                                    </div>
                                    <MediaField
                                        v-model="seriesForm.galleryImages[index]"
                                        :label="`URL ${index + 1}`"
                                        kind="brand"
                                        :tags="['series', 'gallery']"
                                        accept="image/png,image/jpeg,image/webp,image/svg+xml,.svg"
                                        placeholder="/media/library/original/series-gallery.webp"
                                    />
                                </div>
                            </div>
                            <p v-else class="rounded-xl border border-dashed border-gray-300 px-3 py-3 text-sm text-gray-500 dark:border-slate-700 dark:text-slate-400">
                                Галерея пока пустая.
                            </p>
                            <div class="rounded-xl border border-teal-100 bg-teal-50/40 p-3 dark:border-teal-900/60 dark:bg-teal-950/20">
                                <MediaField
                                    v-model="pendingGalleryImage"
                                    label="Добавить изображение"
                                    kind="brand"
                                    :tags="['series', 'gallery']"
                                    accept="image/png,image/jpeg,image/webp,image/svg+xml,.svg"
                                    placeholder="/media/library/original/series-gallery.webp"
                                    @picked="addGalleryImage"
                                />
                                <button
                                    v-if="pendingGalleryImage"
                                    type="button"
                                    class="mt-3 inline-flex items-center gap-1 rounded-lg bg-teal-600 px-3 py-2 text-xs font-semibold text-white hover:bg-teal-700"
                                    @click="addGalleryImage()"
                                >
                                    <span class="material-icons-round text-[16px]">add</span>
                                    Добавить в галерею
                                </button>
                            </div>
                        </div>
                    </section>

                    <section class="space-y-3 border-t border-gray-200 pt-4 dark:border-slate-700">
                        <div class="flex items-center justify-between gap-3">
                            <div>
                                <h3 class="text-sm font-bold uppercase tracking-[0.16em] text-gray-500 dark:text-slate-400">Преимущества</h3>
                                <p class="text-xs text-gray-500 dark:text-slate-400">Короткие фичи идут чипсами, блоки можно раскрыть на сайте подробнее.</p>
                            </div>
                            <button type="button" class="inline-flex items-center gap-1 rounded-lg border border-teal-200 px-3 py-1.5 text-xs font-semibold text-teal-700 hover:bg-teal-50 dark:border-teal-900/60 dark:text-teal-200 dark:hover:bg-teal-950/30" @click="addFeatureBlock">
                                <span class="material-icons-round text-[16px]">add</span>
                                Блок
                            </button>
                        </div>
                        <label class="text-sm space-y-1 block">
                            <span class="text-gray-600 dark:text-slate-300 font-medium">Фичи серии</span>
                            <textarea v-model="seriesForm.featuresText" rows="3" class="w-full px-3 py-2 rounded-lg border border-gray-200 dark:border-slate-700 bg-slate-100 dark:bg-slate-900" placeholder="Одна фича на строку" />
                        </label>
                        <div v-if="seriesForm.featureBlocks.length" class="space-y-3">
                            <div
                                v-for="(block, index) in seriesForm.featureBlocks"
                                :key="`feature-${index}`"
                                class="rounded-xl border border-gray-200 p-3 dark:border-slate-700"
                            >
                                <div class="mb-3 flex items-center justify-between gap-3">
                                    <span class="text-xs font-bold uppercase tracking-[0.14em] text-gray-500 dark:text-slate-400">Преимущество {{ index + 1 }}</span>
                                    <button type="button" class="inline-flex h-8 w-8 items-center justify-center rounded-lg text-red-500 hover:bg-red-50 dark:hover:bg-red-950/30" @click="removeFeatureBlock(index)">
                                        <span class="material-icons-round text-[18px]">delete</span>
                                    </button>
                                </div>
                                <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
                                    <label class="text-sm space-y-1">
                                        <span class="text-gray-600 dark:text-slate-300 font-medium">Заголовок</span>
                                        <input v-model="block.title" type="text" class="w-full px-3 py-2 rounded-lg border border-gray-200 dark:border-slate-700 bg-slate-100 dark:bg-slate-900" />
                                    </label>
                                    <label class="text-sm space-y-1">
                                        <span class="text-gray-600 dark:text-slate-300 font-medium">Иконка</span>
                                        <input v-model="block.icon" type="text" class="w-full px-3 py-2 rounded-lg border border-gray-200 dark:border-slate-700 bg-slate-100 dark:bg-slate-900" placeholder="air / bolt / self_cleaning" />
                                    </label>
                                    <MediaField
                                        v-model="block.image_url"
                                        label="Изображение"
                                        kind="brand"
                                        :tags="['series', 'feature']"
                                        accept="image/png,image/jpeg,image/webp,image/svg+xml,.svg"
                                        placeholder="/media/library/original/feature.webp"
                                    />
                                    <label class="text-sm space-y-1">
                                        <span class="text-gray-600 dark:text-slate-300 font-medium">Сноска</span>
                                        <input v-model="block.footnote" type="text" class="w-full px-3 py-2 rounded-lg border border-gray-200 dark:border-slate-700 bg-slate-100 dark:bg-slate-900" />
                                    </label>
                                </div>
                                <label class="mt-3 block text-sm space-y-1">
                                    <span class="text-gray-600 dark:text-slate-300 font-medium">Описание</span>
                                    <textarea v-model="block.text" rows="3" class="w-full px-3 py-2 rounded-lg border border-gray-200 dark:border-slate-700 bg-slate-100 dark:bg-slate-900" />
                                </label>
                            </div>
                        </div>
                    </section>

                    <section class="space-y-3 border-t border-gray-200 pt-4 dark:border-slate-700">
                        <div class="flex items-center justify-between gap-3">
                            <div>
                                <h3 class="text-sm font-bold uppercase tracking-[0.16em] text-gray-500 dark:text-slate-400">Контентные блоки</h3>
                                <p class="text-xs text-gray-500 dark:text-slate-400">Основа для будущих секций серии как на фирменных страницах.</p>
                            </div>
                            <button type="button" class="inline-flex items-center gap-1 rounded-lg border border-teal-200 px-3 py-1.5 text-xs font-semibold text-teal-700 hover:bg-teal-50 dark:border-teal-900/60 dark:text-teal-200 dark:hover:bg-teal-950/30" @click="addContentBlock">
                                <span class="material-icons-round text-[16px]">add</span>
                                Секция
                            </button>
                        </div>
                        <div v-if="seriesForm.contentBlocks.length" class="space-y-3">
                            <div
                                v-for="(block, index) in seriesForm.contentBlocks"
                                :key="`content-${index}`"
                                class="rounded-xl border border-gray-200 p-3 dark:border-slate-700"
                            >
                                <div class="mb-3 flex items-center justify-between gap-3">
                                    <span class="text-xs font-bold uppercase tracking-[0.14em] text-gray-500 dark:text-slate-400">Секция {{ index + 1 }}</span>
                                    <button type="button" class="inline-flex h-8 w-8 items-center justify-center rounded-lg text-red-500 hover:bg-red-50 dark:hover:bg-red-950/30" @click="removeContentBlock(index)">
                                        <span class="material-icons-round text-[18px]">delete</span>
                                    </button>
                                </div>
                                <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
                                    <label class="text-sm space-y-1">
                                        <span class="text-gray-600 dark:text-slate-300 font-medium">Тип</span>
                                        <select v-model="block.kind" class="w-full px-3 py-2 rounded-lg border border-gray-200 dark:border-slate-700 bg-slate-100 dark:bg-slate-900">
                                            <option value="text">Текст</option>
                                            <option value="image_text">Текст + изображение</option>
                                            <option value="media">Медиа</option>
                                        </select>
                                    </label>
                                    <label class="text-sm space-y-1">
                                        <span class="text-gray-600 dark:text-slate-300 font-medium">Макет</span>
                                        <select v-model="block.layout" class="w-full px-3 py-2 rounded-lg border border-gray-200 dark:border-slate-700 bg-slate-100 dark:bg-slate-900">
                                            <option value="text_left">Текст слева</option>
                                            <option value="text_right">Текст справа</option>
                                            <option value="full">На всю ширину</option>
                                        </select>
                                    </label>
                                    <label class="text-sm space-y-1">
                                        <span class="text-gray-600 dark:text-slate-300 font-medium">Заголовок</span>
                                        <input v-model="block.title" type="text" class="w-full px-3 py-2 rounded-lg border border-gray-200 dark:border-slate-700 bg-slate-100 dark:bg-slate-900" />
                                    </label>
                                    <MediaField
                                        v-model="block.image_url"
                                        label="Изображение"
                                        kind="brand"
                                        :tags="['series', 'content']"
                                        accept="image/png,image/jpeg,image/webp,image/svg+xml,.svg"
                                        placeholder="/media/library/original/series-content.webp"
                                    />
                                </div>
                                <label class="mt-3 block text-sm space-y-1">
                                    <span class="text-gray-600 dark:text-slate-300 font-medium">Текст</span>
                                    <textarea v-model="block.text" rows="4" class="w-full px-3 py-2 rounded-lg border border-gray-200 dark:border-slate-700 bg-slate-100 dark:bg-slate-900" />
                                </label>
                            </div>
                        </div>
                        <p v-else class="rounded-xl border border-dashed border-gray-300 px-3 py-3 text-sm text-gray-500 dark:border-slate-700 dark:text-slate-400">
                            Контентных секций пока нет.
                        </p>
                    </section>

                    <section class="grid grid-cols-1 lg:grid-cols-2 gap-4 border-t border-gray-200 pt-4 dark:border-slate-700">
                        <label class="text-sm space-y-1 block">
                            <span class="text-gray-600 dark:text-slate-300 font-medium">Сноски</span>
                            <textarea v-model="seriesForm.footnotesText" rows="4" class="w-full px-3 py-2 rounded-lg border border-gray-200 dark:border-slate-700 bg-slate-100 dark:bg-slate-900" placeholder="Одна сноска на строку" />
                        </label>
                        <div class="space-y-3">
                            <label class="text-sm space-y-1 block">
                                <span class="text-gray-600 dark:text-slate-300 font-medium">SEO title</span>
                                <input v-model="seriesForm.seo_title" type="text" class="w-full px-3 py-2 rounded-lg border border-gray-200 dark:border-slate-700 bg-slate-100 dark:bg-slate-900" />
                            </label>
                            <label class="text-sm space-y-1 block">
                                <span class="text-gray-600 dark:text-slate-300 font-medium">SEO description</span>
                                <textarea v-model="seriesForm.seo_description" rows="3" class="w-full px-3 py-2 rounded-lg border border-gray-200 dark:border-slate-700 bg-slate-100 dark:bg-slate-900" />
                            </label>
                        </div>
                    </section>

                    <label class="text-sm flex items-center gap-2 border-t border-gray-200 pt-4 dark:border-slate-700">
                        <input v-model="seriesForm.is_published" type="checkbox" class="rounded border-gray-300 dark:border-slate-700" />
                        <span class="text-gray-600 dark:text-slate-300 font-medium">Публиковать серию</span>
                    </label>
                </div>
                <footer class="px-5 py-4 border-t border-gray-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800/60 flex items-center justify-end gap-2">
                    <button type="button" class="px-4 py-2 rounded-lg text-sm font-medium text-gray-600 dark:text-slate-300 hover:bg-gray-100 dark:hover:bg-slate-700" @click="closeSeriesModal">
                        Отмена
                    </button>
                    <button type="button" class="px-4 py-2 rounded-lg text-sm font-semibold text-white bg-teal-600 hover:bg-teal-700 disabled:opacity-50" :disabled="seriesSaving" @click="saveSeries">
                        {{ seriesSaving ? 'Сохранение...' : 'Сохранить' }}
                    </button>
                </footer>
            </div>
        </div>
    </div>
</template>
