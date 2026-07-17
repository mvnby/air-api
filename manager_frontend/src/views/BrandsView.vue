<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';
import { api, type ManagerBrand, type ManagerBrandFeature, type ManagerBrandSeries } from '../api';
import IconPicker from '../components/IconPicker.vue';
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
    brandFeatureIds: number[];
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

type BrandFeatureDraft = {
    title: string;
    text: string;
    image_url: string;
    icon: string;
    source_url: string;
    aliasesText: string;
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
const brandFeatures = ref<ManagerBrandFeature[]>([]);
const seriesLoading = ref(false);
const brandFeaturesLoading = ref(false);
const seriesSaving = ref(false);
const featureSaving = ref(false);
const editingBrandFeatureId = ref<number | null>(null);
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
    brandFeatureIds: [],
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
const seoPromptPreview = ref('');
const featureDraft = ref<BrandFeatureDraft>({
    title: '',
    text: '',
    image_url: '',
    icon: '',
    source_url: '',
    aliasesText: '',
});

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
const selectedBrandFeatureCount = computed(() => seriesForm.value.brandFeatureIds.length);
const isEditingBrandFeature = computed(() => editingBrandFeatureId.value !== null);

const SORT_ORDER_STEP = 10;
const featureIconOptions = [
    { value: '', icon: 'hide_image', label: 'Без' },
    { value: 'air', icon: 'air', label: 'Воздух' },
    { value: 'ac_unit', icon: 'ac_unit', label: 'Холод' },
    { value: 'thermostat', icon: 'thermostat', label: 'Климат' },
    { value: 'eco', icon: 'eco', label: 'ECO' },
    { value: 'energy_savings_leaf', icon: 'energy_savings_leaf', label: 'Энергия' },
    { value: 'bolt', icon: 'bolt', label: 'Мощность' },
    { value: 'wifi', icon: 'wifi', label: 'Wi-Fi' },
    { value: 'self_cleaning', icon: 'self_cleaning', label: 'Самооч.' },
    { value: 'cleaning_services', icon: 'cleaning_services', label: 'Очистка' },
    { value: 'filter_alt', icon: 'filter_alt', label: 'Фильтр' },
    { value: 'water_drop', icon: 'water_drop', label: 'Осуш.' },
    { value: 'waves', icon: 'waves', label: 'Поток' },
    { value: 'volume_down', icon: 'volume_down', label: 'Тишина' },
    { value: 'shield', icon: 'shield', label: 'Защита' },
    { value: 'auto_awesome', icon: 'auto_awesome', label: 'AI' },
    { value: 'settings_suggest', icon: 'settings_suggest', label: 'Авто' },
];

const getNextSortOrder = <T extends { sort_order?: number | null }>(items: T[]) => {
    const maxOrder = items.reduce((max, item) => Math.max(max, Number(item.sort_order || 0)), 0);
    return maxOrder + SORT_ORDER_STEP;
};

const sortBrandFeatures = (items: ManagerBrandFeature[]) => (
    [...items].sort((a, b) => (
        Number(a.sort_order || 0) - Number(b.sort_order || 0)
        || String(a.title || '').localeCompare(String(b.title || ''))
    ))
);

const compactText = (value: string, maxLength = 160) => {
    const text = String(value || '').replace(/\s+/g, ' ').trim();
    if (text.length <= maxLength) return text;
    return `${text.slice(0, maxLength - 1).trim()}…`;
};

const getSelectedBrandFeatureTitles = () => {
    const selectedIds = new Set(seriesForm.value.brandFeatureIds);
    return brandFeatures.value
        .filter((feature) => selectedIds.has(feature.id))
        .map((feature) => String(feature.title || '').trim())
        .filter(Boolean);
};

const suggestedSeriesFeatureTitles = computed(() => {
    const titles = [
        ...getSelectedBrandFeatureTitles(),
        ...seriesForm.value.featureBlocks.map((block) => String(block.title || '').trim()),
        ...seriesForm.value.contentBlocks.map((block) => String(block.title || '').trim()),
    ];
    return normalizeTextList(titles.join('\n'));
});

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
    || series.brand_features?.length
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
    seoPromptPreview.value = '';
    seriesForm.value = {
        title: '',
        slug: '',
        tagline: '',
        short_description: '',
        description: '',
        hero_image: '',
        galleryImages: [],
        featuresText: '',
        brandFeatureIds: [],
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

const fetchBrandFeatures = async () => {
    if (!selectedBrandId.value) {
        brandFeatures.value = [];
        return;
    }

    brandFeaturesLoading.value = true;
    seriesError.value = '';
    try {
        const res = await api.listManagerBrandFeatures(selectedBrandId.value);
        brandFeatures.value = sortBrandFeatures(res.items || []);
    } catch (err) {
        seriesError.value = getApiErrorMessage(err);
    } finally {
        brandFeaturesLoading.value = false;
    }
};

const selectBrand = (brand: ManagerBrand) => {
    if (selectedBrandId.value === brand.id) {
        selectedBrandId.value = null;
        seriesError.value = '';
        return;
    }
    selectedBrandId.value = brand.id;
};

const openSeriesProducts = (series: ManagerBrandSeries) => {
    const params = new URLSearchParams({
        seriesId: String(series.id),
        seriesTitle: String(series.title || ''),
        returnTo: '/manager/brands',
    });
    if (selectedBrand.value?.slug) params.set('brand', selectedBrand.value.slug);
    window.location.href = `/manager/products?${params.toString()}`;
};

const formatProductCount = (count: number | undefined) => {
    const value = Math.max(0, Number(count) || 0);
    const mod100 = value % 100;
    const mod10 = value % 10;
    const noun = mod100 >= 11 && mod100 <= 14
        ? 'товаров'
        : mod10 === 1
            ? 'товар'
            : mod10 >= 2 && mod10 <= 4
                ? 'товара'
                : 'товаров';
    return `${value} ${noun}`;
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
    seoPromptPreview.value = '';
    seriesForm.value = {
        title: String(series.title || ''),
        slug: String(series.slug || ''),
        tagline: String(series.tagline || ''),
        short_description: String(series.short_description || ''),
        description: String(series.description || ''),
        hero_image: String(series.hero_image || ''),
        galleryImages: [...(series.gallery_images || [])],
        featuresText: (series.features || []).join('\n'),
        brandFeatureIds: [...(series.brand_feature_ids || (series.brand_features || []).map((feature) => feature.id))],
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

const syncSeriesFeaturesFromStructuredBlocks = () => {
    const suggestions = suggestedSeriesFeatureTitles.value;
    if (suggestions.length === 0) {
        seriesError.value = 'Сначала добавьте фичи бренда, блоки преимуществ или контентные секции.';
        return;
    }
    const existing = normalizeTextList(seriesForm.value.featuresText);
    seriesForm.value.featuresText = normalizeTextList([...existing, ...suggestions].join('\n')).join('\n');
    setToast('Фичи серии собраны из блоков');
};

const buildSeriesSeoDescriptionSource = () => {
    const selectedFeatureDescriptions = brandFeatures.value
        .filter((feature) => seriesForm.value.brandFeatureIds.includes(feature.id))
        .map((feature) => [feature.title, feature.text].filter(Boolean).join(': '));
    return normalizeTextList([
        seriesForm.value.tagline,
        seriesForm.value.short_description,
        seriesForm.value.description,
        ...selectedFeatureDescriptions,
        ...seriesForm.value.featureBlocks.map((block) => [block.title, block.text].filter(Boolean).join(': ')),
        ...seriesForm.value.contentBlocks.map((block) => [block.title, block.text].filter(Boolean).join(': ')),
    ].join('\n'));
};

const generateSeriesSeoDraft = () => {
    const brandTitle = selectedBrand.value?.title || '';
    const seriesTitle = String(seriesForm.value.title || '').trim();
    if (!seriesTitle && !brandTitle) {
        seriesError.value = 'Заполните название серии или бренд, чтобы собрать SEO.';
        return;
    }

    const titleBase = [brandTitle, seriesTitle].filter(Boolean).join(' ');
    const titleTail = String(seriesForm.value.tagline || seriesForm.value.short_description || '').trim();
    seriesForm.value.seo_title = compactText([titleBase, titleTail].filter(Boolean).join(' — '), 68);

    const descriptionParts = buildSeriesSeoDescriptionSource();
    const fallbackFeatures = suggestedSeriesFeatureTitles.value.slice(0, 4).join(', ');
    const description = descriptionParts.length
        ? descriptionParts.join(' ')
        : [titleBase, fallbackFeatures].filter(Boolean).join(': ');
    seriesForm.value.seo_description = compactText(description, 158);
    setToast('SEO-черновик собран из описаний');
};

const buildSeriesSeoPrompt = () => {
    const payload = {
        brand: selectedBrand.value?.title || '',
        series: seriesForm.value.title,
        tagline: seriesForm.value.tagline,
        short_description: seriesForm.value.short_description,
        description: seriesForm.value.description,
        reusable_features: brandFeatures.value
            .filter((feature) => seriesForm.value.brandFeatureIds.includes(feature.id))
            .map((feature) => ({ title: feature.title, text: feature.text || '' })),
        feature_blocks: seriesForm.value.featureBlocks.map((block) => ({
            title: block.title,
            text: block.text,
        })),
        content_blocks: seriesForm.value.contentBlocks.map((block) => ({
            title: block.title,
            text: block.text,
        })),
        current_seo_title: seriesForm.value.seo_title,
        current_seo_description: seriesForm.value.seo_description,
    };
    return [
        'Ты SEO-редактор интернет-магазина климатической техники.',
        'Составь SEO title и SEO description для страницы серии кондиционеров на русском языке.',
        'Правила:',
        '- Верни только JSON без markdown: {"seo_title":"...","seo_description":"..."}',
        '- seo_title: до 68 символов, без кликбейта, бренд и серия должны быть в начале.',
        '- seo_description: до 158 символов, живая польза серии, без выдуманных характеристик.',
        '- Используй только факты из входных данных.',
        '- Не перечисляй все фичи, выбери 2-3 самые сильные.',
        '',
        'Входные данные:',
        JSON.stringify(payload, null, 2),
    ].join('\n');
};

const prepareSeriesSeoPrompt = async () => {
    const prompt = buildSeriesSeoPrompt();
    seoPromptPreview.value = prompt;
    try {
        await navigator.clipboard.writeText(prompt);
        setToast('Промпт для AI скопирован');
    } catch {
        setToast('Промпт подготовлен ниже');
    }
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

const isBrandFeatureSelected = (featureId: number) => seriesForm.value.brandFeatureIds.includes(featureId);

const toggleBrandFeature = (featureId: number) => {
    const current = new Set(seriesForm.value.brandFeatureIds);
    if (current.has(featureId)) {
        current.delete(featureId);
    } else {
        current.add(featureId);
    }
    seriesForm.value.brandFeatureIds = [...current];
};

const resetFeatureDraft = () => {
    editingBrandFeatureId.value = null;
    featureDraft.value = {
        title: '',
        text: '',
        image_url: '',
        icon: '',
        source_url: '',
        aliasesText: '',
    };
};

const startEditBrandFeature = (feature: ManagerBrandFeature) => {
    editingBrandFeatureId.value = feature.id;
    featureDraft.value = {
        title: String(feature.title || ''),
        text: String(feature.text || ''),
        image_url: String(feature.image_url || ''),
        icon: String(feature.icon || ''),
        source_url: String(feature.source_url || ''),
        aliasesText: (feature.aliases || []).join('\n'),
    };
};

const saveBrandFeatureFromDraft = async () => {
    if (!selectedBrandId.value) return;
    const title = String(featureDraft.value.title || '').trim();
    if (!title) {
        seriesError.value = 'Название фичи обязательно.';
        return;
    }

    featureSaving.value = true;
    seriesError.value = '';
    try {
        const existingFeature = brandFeatures.value.find((feature) => feature.id === editingBrandFeatureId.value);
        const payload = {
            title,
            text: String(featureDraft.value.text || '').trim() || undefined,
            image_url: String(featureDraft.value.image_url || '').trim() || undefined,
            icon: String(featureDraft.value.icon || '').trim() || undefined,
            source_url: String(featureDraft.value.source_url || '').trim() || undefined,
            aliases: normalizeTextList(featureDraft.value.aliasesText),
            is_published: true,
            sort_order: existingFeature ? Number(existingFeature.sort_order || 0) : getNextSortOrder(brandFeatures.value),
        };

        if (editingBrandFeatureId.value) {
            const updated = await api.updateManagerBrandFeature(
                selectedBrandId.value,
                editingBrandFeatureId.value,
                payload,
            );
            brandFeatures.value = sortBrandFeatures(
                brandFeatures.value.map((feature) => (feature.id === updated.id ? updated : feature)),
            );
            setToast('Фича обновлена');
        } else {
            const created = await api.createManagerBrandFeature(selectedBrandId.value, payload);
            brandFeatures.value = sortBrandFeatures([...brandFeatures.value, created]);
            if (created.id && !seriesForm.value.brandFeatureIds.includes(created.id)) {
                seriesForm.value.brandFeatureIds.push(created.id);
            }
            setToast('Фича добавлена в библиотеку');
        }
        resetFeatureDraft();
    } catch (err) {
        seriesError.value = getApiErrorMessage(err);
    } finally {
        featureSaving.value = false;
    }
};

const deleteBrandFeature = async (feature: ManagerBrandFeature) => {
    if (!selectedBrandId.value) return;
    if (Number(feature.series_count || 0) > 0) {
        seriesError.value = `Фича "${feature.title}" используется в сериях. Сначала отвяжите ее от серий, затем удалите.`;
        return;
    }
    if (!confirm(`Удалить фичу "${feature.title}" из библиотеки бренда?`)) return;

    featureSaving.value = true;
    seriesError.value = '';
    try {
        await api.deleteManagerBrandFeature(selectedBrandId.value, feature.id);
        brandFeatures.value = brandFeatures.value.filter((item) => item.id !== feature.id);
        seriesForm.value.brandFeatureIds = seriesForm.value.brandFeatureIds.filter((id) => id !== feature.id);
        if (editingBrandFeatureId.value === feature.id) {
            resetFeatureDraft();
        }
        setToast('Фича удалена');
    } catch (err) {
        seriesError.value = getApiErrorMessage(err);
    } finally {
        featureSaving.value = false;
    }
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
            brand_feature_ids: [...seriesForm.value.brandFeatureIds],
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
        await fetchBrandFeatures();
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
    fetchBrandFeatures();
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
                                <div class="inline-flex items-center justify-end gap-1">
                                    <button
                                        type="button"
                                        class="inline-flex h-8 w-8 items-center justify-center rounded-lg border border-gray-200 text-gray-600 transition-colors hover:bg-gray-50 hover:text-teal-700 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-700 dark:hover:text-teal-200"
                                        title="Изменить бренд"
                                        aria-label="Изменить бренд"
                                        @click.stop="openEdit(brand)"
                                    >
                                        <span class="material-icons-round text-[18px]">edit</span>
                                    </button>
                                    <button
                                        type="button"
                                        class="inline-flex h-8 w-8 items-center justify-center rounded-lg border border-red-200 text-red-500 transition-colors hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-40 dark:border-red-900/50 dark:text-red-300 dark:hover:bg-red-950/30"
                                        :disabled="(brand.products_count ?? 0) > 0"
                                        :title="(brand.products_count ?? 0) > 0 ? 'Нельзя удалить бренд с товарами' : 'Удалить бренд'"
                                        aria-label="Удалить бренд"
                                        @click.stop="deleteBrand(brand)"
                                    >
                                        <span class="material-icons-round text-[18px]">delete</span>
                                    </button>
                                </div>
                            </td>
                        </tr>
                        <tr v-if="selectedBrandId === brand.id" class="border-b border-teal-100 bg-teal-50/50 dark:border-teal-900/40 dark:bg-teal-950/10">
                            <td colspan="6" class="p-0">
                                <div class="mx-3 my-3 rounded-2xl border border-teal-100 bg-white p-4 shadow-sm dark:border-teal-900/60 dark:bg-slate-900">
                                    <div class="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                                        <div class="min-w-0">
                                            <p class="text-xs uppercase tracking-[0.18em] font-bold text-teal-600 dark:text-teal-300">Серии бренда</p>
                                            <h2 class="text-lg font-bold text-gray-900 dark:text-white">{{ brand.title }}</h2>
                                            <p v-if="brand.description" class="mt-1 max-w-4xl text-sm text-gray-500 dark:text-slate-400">
                                                {{ brand.description }}
                                            </p>
                                            <p class="mt-1 text-xs text-gray-500 dark:text-slate-400">
                                                Описания и фичи попадут на брендовые страницы и в блок связанных моделей. Порядок меняется перетаскиванием карточек.
                                            </p>
                                        </div>
                                        <div class="flex shrink-0 flex-wrap items-center gap-2">
                                            <div v-if="reorderingSeries" class="text-xs font-semibold text-teal-600 dark:text-teal-300">
                                                Сохраняем порядок...
                                            </div>
                                            <button
                                                type="button"
                                                class="inline-flex items-center justify-center gap-2 rounded-lg bg-teal-600 px-4 py-2 text-sm font-medium text-white transition-all hover:bg-teal-500"
                                                @click.stop="openSeriesCreate"
                                            >
                                                <span class="material-icons-round text-[18px]">add</span>
                                                Новая серия
                                            </button>
                                        </div>
                                    </div>

                                    <div v-if="seriesError" class="mt-3 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-900/40 dark:bg-red-900/20 dark:text-red-300">
                                        {{ seriesError }}
                                    </div>

                                    <div v-if="seriesLoading" class="py-6 text-sm text-gray-500 dark:text-slate-400">
                                        Загрузка серий...
                                    </div>
                                    <div v-else-if="seriesItems.length === 0" class="mt-3 rounded-xl border border-dashed border-gray-300 px-4 py-8 text-sm text-gray-500 dark:border-slate-700 dark:text-slate-400">
                                        У бренда пока нет серий. Можно добавить первую вручную.
                                    </div>
                                    <div v-else class="mt-3 space-y-2">
                                        <article
                                            v-for="series in seriesItems"
                                            :key="series.id"
                                            class="relative rounded-xl border border-gray-200 bg-slate-50 px-3 py-2.5 pr-20 transition-shadow dark:border-slate-700 dark:bg-slate-900/50 lg:pr-3"
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
                                                        class="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-gray-200 text-gray-400 transition-colors dark:border-slate-700 dark:text-slate-500"
                                                        :class="isSeriesReorderDisabled ? 'cursor-not-allowed opacity-40' : 'cursor-grab hover:bg-white hover:text-teal-600 active:cursor-grabbing dark:hover:bg-slate-800 dark:hover:text-teal-300'"
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
                                                        class="h-10 w-10 shrink-0 rounded-lg border border-gray-200 bg-white object-cover dark:border-slate-700"
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
                                                            <button
                                                                type="button"
                                                                class="inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-xs font-semibold text-teal-700 transition-colors hover:bg-teal-50 hover:text-teal-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500 dark:text-teal-300 dark:hover:bg-teal-950/40 dark:hover:text-teal-100"
                                                                :title="`Показать товары серии ${series.title}`"
                                                                @click.stop="openSeriesProducts(series)"
                                                            >
                                                                {{ formatProductCount(series.products_count) }}
                                                                <span class="material-icons-round text-[14px]">arrow_outward</span>
                                                            </button>
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
                                                        class="rounded-full border border-teal-200 bg-teal-50 px-2 py-0.5 text-xs font-semibold text-teal-700 dark:border-teal-900/60 dark:bg-teal-950/30 dark:text-teal-200"
                                                    >
                                                        {{ feature }}
                                                    </span>
                                                    <span
                                                        v-if="series.features.length > 3"
                                                        class="rounded-full border border-gray-200 px-2 py-0.5 text-xs font-semibold text-gray-500 dark:border-slate-700 dark:text-slate-400"
                                                    >
                                                        +{{ series.features.length - 3 }}
                                                    </span>
                                                </div>
                                                <div class="hidden shrink-0 items-center gap-1 lg:inline-flex">
                                                    <button
                                                        v-if="hasSeriesDetails(series)"
                                                        type="button"
                                                        class="inline-flex items-center gap-1 rounded border border-gray-200 px-2.5 py-1 text-xs font-semibold hover:bg-white dark:border-slate-700 dark:hover:bg-slate-800"
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
                                                        class="rounded border border-gray-200 px-2.5 py-1 text-xs font-semibold hover:bg-white dark:border-slate-700 dark:hover:bg-slate-800"
                                                        @click.stop="openSeriesEdit(series)"
                                                    >
                                                        Изменить
                                                    </button>
                                                    <button
                                                        type="button"
                                                        class="rounded border border-red-200 px-2.5 py-1 text-xs font-semibold text-red-600 hover:bg-red-50 disabled:opacity-50"
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
                                                    v-if="series.brand_features?.length"
                                                    class="rounded-full bg-indigo-50 px-2 py-0.5 text-indigo-700 dark:bg-indigo-950/30 dark:text-indigo-200"
                                                >
                                                    из библиотеки {{ series.brand_features.length }}
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
                                                class="mt-2 border-t border-gray-200 pt-2 text-sm text-gray-600 dark:border-slate-700 dark:text-slate-300"
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
                                                        class="rounded-full border border-teal-200 bg-teal-50 px-2 py-0.5 text-xs font-semibold text-teal-700 dark:border-teal-900/60 dark:bg-teal-950/30 dark:text-teal-200"
                                                    >
                                                        {{ feature }}
                                                    </span>
                                                </div>
                                                <div v-if="series.brand_features?.length" class="mt-2 grid gap-1.5 sm:grid-cols-2">
                                                    <div
                                                        v-for="feature in series.brand_features"
                                                        :key="`${series.id}-brand-feature-${feature.id}`"
                                                        class="rounded-lg border border-indigo-100 bg-indigo-50/60 px-2 py-1.5 text-xs dark:border-indigo-900/60 dark:bg-indigo-950/20"
                                                    >
                                                        <span class="font-semibold text-indigo-800 dark:text-indigo-100">{{ feature.title }}</span>
                                                        <p v-if="feature.text" class="mt-0.5 line-clamp-2 text-indigo-700/70 dark:text-indigo-200/70">{{ feature.text }}</p>
                                                    </div>
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
                            </td>
                        </tr>
                        </template>
                    </tbody>
                </table>
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
                        <div class="rounded-2xl border border-indigo-100 bg-indigo-50/40 p-3 dark:border-indigo-900/60 dark:bg-indigo-950/20">
                            <div class="mb-3 flex flex-wrap items-start justify-between gap-2">
                                <div>
                                    <h4 class="text-sm font-semibold text-gray-800 dark:text-slate-100">Библиотека фич бренда</h4>
                                    <p class="text-xs text-gray-500 dark:text-slate-400">
                                        Переиспользуемые блоки для нескольких серий. Выбрано: {{ selectedBrandFeatureCount }}.
                                    </p>
                                </div>
                                <span v-if="brandFeaturesLoading" class="text-xs font-semibold text-indigo-700 dark:text-indigo-200">Загрузка...</span>
                            </div>
                            <div v-if="brandFeatures.length" class="grid gap-2 md:grid-cols-2">
                                <article
                                    v-for="feature in brandFeatures"
                                    :key="feature.id"
                                    class="min-h-[88px] rounded-xl border px-3 py-2 transition"
                                    :class="isBrandFeatureSelected(feature.id)
                                        ? 'border-indigo-300 bg-white shadow-sm dark:border-indigo-700 dark:bg-slate-900'
                                        : 'border-white/70 bg-white/70 hover:border-indigo-200 dark:border-slate-800 dark:bg-slate-900/50 dark:hover:border-indigo-800'"
                                >
                                    <div class="flex items-start gap-2">
                                        <button
                                            type="button"
                                            class="mt-0.5 inline-flex h-6 w-6 shrink-0 items-center justify-center rounded border text-[14px]"
                                            :class="isBrandFeatureSelected(feature.id)
                                                ? 'border-indigo-500 bg-indigo-600 text-white'
                                                : 'border-gray-300 text-transparent hover:border-indigo-300 dark:border-slate-600'"
                                            :aria-pressed="isBrandFeatureSelected(feature.id)"
                                            @click="toggleBrandFeature(feature.id)"
                                        >
                                            <span class="material-icons-round text-[15px]">check</span>
                                        </button>
                                        <span
                                            v-if="feature.icon"
                                            class="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-indigo-100 text-indigo-700 dark:bg-indigo-950 dark:text-indigo-200"
                                            :title="feature.icon"
                                        >
                                            <span class="material-icons-round text-[18px]">{{ feature.icon }}</span>
                                        </span>
                                        <button type="button" class="min-w-0 flex-1 text-left" @click="toggleBrandFeature(feature.id)">
                                            <span class="block truncate text-sm font-semibold text-gray-900 dark:text-slate-100">{{ feature.title }}</span>
                                            <span v-if="feature.text" class="mt-0.5 line-clamp-2 text-xs text-gray-500 dark:text-slate-400">{{ feature.text }}</span>
                                            <span v-if="feature.aliases?.length" class="mt-1 block truncate text-[11px] text-indigo-700/70 dark:text-indigo-200/70">
                                                {{ feature.aliases.join(', ') }}
                                            </span>
                                            <span v-if="Number(feature.series_count || 0) > 0" class="mt-1 block text-[11px] font-semibold text-gray-500 dark:text-slate-400">
                                                Используется в сериях: {{ feature.series_count }}
                                            </span>
                                        </button>
                                        <div class="flex shrink-0 items-center gap-1">
                                            <button
                                                type="button"
                                                class="inline-flex h-8 w-8 items-center justify-center rounded-lg text-gray-500 hover:bg-indigo-50 hover:text-indigo-700 dark:text-slate-400 dark:hover:bg-indigo-950/40 dark:hover:text-indigo-200"
                                                title="Редактировать фичу"
                                                @click.stop="startEditBrandFeature(feature)"
                                            >
                                                <span class="material-icons-round text-[17px]">edit</span>
                                            </button>
                                            <button
                                                type="button"
                                                class="inline-flex h-8 w-8 items-center justify-center rounded-lg text-gray-500 hover:bg-red-50 hover:text-red-600 disabled:cursor-not-allowed disabled:opacity-40 dark:text-slate-400 dark:hover:bg-red-950/30 dark:hover:text-red-300"
                                                :disabled="featureSaving || Number(feature.series_count || 0) > 0"
                                                :title="Number(feature.series_count || 0) > 0 ? 'Сначала отвяжите фичу от серий' : 'Удалить фичу'"
                                                @click.stop="deleteBrandFeature(feature)"
                                            >
                                                <span class="material-icons-round text-[17px]">delete</span>
                                            </button>
                                        </div>
                                    </div>
                                </article>
                            </div>
                            <p v-else class="rounded-xl border border-dashed border-indigo-200 px-3 py-3 text-sm text-gray-500 dark:border-indigo-900/60 dark:text-slate-400">
                                У бренда пока нет reusable-фич.
                            </p>
                            <div class="mt-3 border-t border-indigo-100 pt-3 dark:border-indigo-900/60">
                                <div class="mb-2 flex flex-wrap items-center justify-between gap-2">
                                    <div>
                                        <h5 class="text-xs font-bold uppercase tracking-[0.14em] text-indigo-800 dark:text-indigo-200">
                                            {{ isEditingBrandFeature ? 'Редактирование фичи' : 'Новая фича бренда' }}
                                        </h5>
                                        <p class="text-[11px] text-gray-500 dark:text-slate-400">
                                            Иконка выбирается из Material Icons, это не ссылка и не файл.
                                        </p>
                                    </div>
                                    <button
                                        v-if="isEditingBrandFeature"
                                        type="button"
                                        class="inline-flex items-center gap-1 rounded-lg border border-gray-200 px-3 py-1.5 text-xs font-semibold text-gray-600 hover:bg-white dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-900"
                                        :disabled="featureSaving"
                                        @click="resetFeatureDraft"
                                    >
                                        <span class="material-icons-round text-[16px]">close</span>
                                        Отменить
                                    </button>
                                </div>
                                <div class="grid gap-2 lg:grid-cols-[1fr_1fr_auto]">
                                <input
                                    v-model="featureDraft.title"
                                    type="text"
                                    class="rounded-lg border border-indigo-100 bg-white px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-900"
                                    placeholder="Фича: Gentle Breeze"
                                />
                                <input
                                    v-model="featureDraft.text"
                                    type="text"
                                    class="rounded-lg border border-indigo-100 bg-white px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-900"
                                    placeholder="Короткое описание"
                                />
                                <button
                                    type="button"
                                    class="inline-flex items-center justify-center gap-1 rounded-lg bg-indigo-600 px-3 py-2 text-sm font-semibold text-white hover:bg-indigo-700 disabled:opacity-50"
                                    :disabled="featureSaving"
                                    @click="saveBrandFeatureFromDraft"
                                >
                                    <span class="material-icons-round text-[16px]">{{ isEditingBrandFeature ? 'save' : 'library_add' }}</span>
                                    {{ featureSaving ? 'Сохраняем...' : (isEditingBrandFeature ? 'Сохранить' : 'Создать') }}
                                </button>
                                <MediaField
                                    v-model="featureDraft.image_url"
                                    label="Изображение фичи"
                                    kind="brand"
                                    :tags="['brand-feature']"
                                    accept="image/png,image/jpeg,image/webp,image/svg+xml,.svg"
                                    placeholder="/media/library/original/brand-feature.webp"
                                />
                                <IconPicker
                                    v-model="featureDraft.icon"
                                    class="lg:col-span-3"
                                    :options="featureIconOptions"
                                    label="Иконка"
                                    tone="indigo"
                                />
                                <label class="lg:col-span-3 rounded-lg border border-indigo-100 bg-white px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-900">
                                    <span class="mb-1 block text-[11px] font-semibold uppercase tracking-[0.12em] text-gray-400 dark:text-slate-500">Источник</span>
                                    <input
                                        v-model="featureDraft.source_url"
                                        type="url"
                                        class="w-full bg-transparent text-sm outline-none"
                                        placeholder="URL страницы производителя или материала"
                                    />
                                    <span class="mt-1 block text-[11px] text-gray-500 dark:text-slate-400">
                                        Служебная ссылка на первоисточник фичи: откуда взяли описание, цифры или картинку. На сайте не выводится.
                                    </span>
                                </label>
                                <textarea
                                    v-model="featureDraft.aliasesText"
                                    rows="2"
                                    class="lg:col-span-3 rounded-lg border border-indigo-100 bg-white px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-900"
                                    placeholder="Синонимы, по одному на строку"
                                />
                                </div>
                            </div>
                        </div>
                        <label class="text-sm space-y-1 block">
                            <span class="flex flex-wrap items-center justify-between gap-2">
                                <span>
                                    <span class="block text-gray-600 dark:text-slate-300 font-medium">Фичи серии</span>
                                    <span class="block text-xs text-gray-500 dark:text-slate-400">
                                        Короткие legacy-чипсы для карточек. Можно собрать из выбранных фич бренда, преимуществ и контентных секций.
                                    </span>
                                </span>
                                <button
                                    type="button"
                                    class="inline-flex items-center gap-1 rounded-lg border border-indigo-200 px-3 py-1.5 text-xs font-semibold text-indigo-700 hover:bg-indigo-50 disabled:opacity-40 dark:border-indigo-900/60 dark:text-indigo-200 dark:hover:bg-indigo-950/30"
                                    :disabled="suggestedSeriesFeatureTitles.length === 0"
                                    @click="syncSeriesFeaturesFromStructuredBlocks"
                                >
                                    <span class="material-icons-round text-[15px]">auto_fix_high</span>
                                    Собрать из блоков
                                </button>
                            </span>
                            <textarea v-model="seriesForm.featuresText" rows="3" class="w-full px-3 py-2 rounded-lg border border-gray-200 dark:border-slate-700 bg-slate-100 dark:bg-slate-900" placeholder="Одна фича на строку" />
                            <span v-if="suggestedSeriesFeatureTitles.length" class="flex flex-wrap gap-1.5">
                                <span
                                    v-for="title in suggestedSeriesFeatureTitles"
                                    :key="`suggested-feature-${title}`"
                                    class="rounded-full bg-indigo-50 px-2 py-0.5 text-[11px] font-semibold text-indigo-700 dark:bg-indigo-950/30 dark:text-indigo-200"
                                >
                                    {{ title }}
                                </span>
                            </span>
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
                                    <div class="text-sm space-y-1 md:col-span-2">
                                        <span class="text-gray-600 dark:text-slate-300 font-medium">Иконка</span>
                                        <IconPicker
                                            v-model="block.icon"
                                            :options="featureIconOptions"
                                            label="Иконка блока"
                                            tone="teal"
                                        />
                                    </div>
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
                            <span class="block text-xs text-gray-500 dark:text-slate-400">
                                Мелкие примечания внизу страницы серии: условия сравнения, ограничения функций, ссылки на испытания. Одна сноска на строку.
                            </span>
                            <textarea v-model="seriesForm.footnotesText" rows="4" class="w-full px-3 py-2 rounded-lg border border-gray-200 dark:border-slate-700 bg-slate-100 dark:bg-slate-900" placeholder="Одна сноска на строку" />
                        </label>
                        <div class="space-y-3">
                            <div class="flex flex-wrap items-center justify-between gap-2">
                                <div>
                                    <h3 class="text-sm font-semibold text-gray-700 dark:text-slate-200">SEO</h3>
                                    <p class="text-xs text-gray-500 dark:text-slate-400">Черновик можно собрать из описания и фич, а промпт отдать DeepSeek.</p>
                                </div>
                                <div class="flex flex-wrap gap-2">
                                    <button
                                        type="button"
                                        class="inline-flex items-center gap-1 rounded-lg border border-teal-200 px-3 py-1.5 text-xs font-semibold text-teal-700 hover:bg-teal-50 dark:border-teal-900/60 dark:text-teal-200 dark:hover:bg-teal-950/30"
                                        @click="generateSeriesSeoDraft"
                                    >
                                        <span class="material-icons-round text-[15px]">auto_awesome</span>
                                        SEO из контента
                                    </button>
                                    <button
                                        type="button"
                                        class="inline-flex items-center gap-1 rounded-lg border border-indigo-200 px-3 py-1.5 text-xs font-semibold text-indigo-700 hover:bg-indigo-50 dark:border-indigo-900/60 dark:text-indigo-200 dark:hover:bg-indigo-950/30"
                                        @click="prepareSeriesSeoPrompt"
                                    >
                                        <span class="material-icons-round text-[15px]">content_copy</span>
                                        Промпт для AI
                                    </button>
                                </div>
                            </div>
                            <label class="text-sm space-y-1 block">
                                <span class="text-gray-600 dark:text-slate-300 font-medium">SEO title</span>
                                <input v-model="seriesForm.seo_title" type="text" class="w-full px-3 py-2 rounded-lg border border-gray-200 dark:border-slate-700 bg-slate-100 dark:bg-slate-900" />
                            </label>
                            <label class="text-sm space-y-1 block">
                                <span class="text-gray-600 dark:text-slate-300 font-medium">SEO description</span>
                                <textarea v-model="seriesForm.seo_description" rows="3" class="w-full px-3 py-2 rounded-lg border border-gray-200 dark:border-slate-700 bg-slate-100 dark:bg-slate-900" />
                            </label>
                            <label v-if="seoPromptPreview" class="text-sm space-y-1 block">
                                <span class="text-gray-600 dark:text-slate-300 font-medium">Промпт для DeepSeek</span>
                                <textarea
                                    v-model="seoPromptPreview"
                                    rows="5"
                                    class="w-full px-3 py-2 rounded-lg border border-indigo-100 dark:border-indigo-900/60 bg-indigo-50/40 dark:bg-indigo-950/20 text-xs"
                                    readonly
                                />
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
