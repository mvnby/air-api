<script setup lang="ts">
import { ref, onMounted, watch, computed } from 'vue';
import { watchDebounced } from '@vueuse/core';
import { api, type Product } from '../api';
import { Search, RefreshCw, UploadCloud, Edit3, CheckSquare, Square, Images, Settings, ArrowLeft, LayoutGrid, List, Package, Link2, ExternalLink } from 'lucide-vue-next';
import BulkSpecsModal from '../components/BulkSpecsModal.vue';
import BulkCompatibilityModal from '../components/BulkCompatibilityModal.vue';
import ProductEditModal from '../components/ProductEditModal.vue';
import OnlinerImportModal from '../components/OnlinerImportModal.vue';
import { getApiErrorMessage } from '../utils/api-errors';

// Product state
const products = ref<Product[]>([]);
const loading = ref(false);
const showModal = ref(false);
const selectedProduct = ref<Product | null>(null);
const editingProduct = ref<Product | null>(null);
const showEditModal = ref(false);
const modalMode = ref<'single' | 'bulk'>('single');
const imageSearchResults = ref<any[]>([]);
const searchLoading = ref(false);
const imageQuery = ref('');
const cleanupLoading = ref(false);
const cleanupStats = ref<any>(null);
const showCleanupModal = ref(false);
const reuseQuery = ref('');
const reuseResults = ref<any[]>([]);
const activeTab = ref<'search' | 'reuse' | 'upload'>('search');
const uploadDragActive = ref(false);
const fileInput = ref<HTMLInputElement | null>(null);
const toast = ref('');
const showOnlinerImportModal = ref(false);

const setToast = (message: string) => {
    toast.value = message;
    window.setTimeout(() => {
        if (toast.value === message) toast.value = '';
    }, 4000);
};

const getPublicSiteBaseUrl = () => {
    const configured = String(import.meta.env.WEBSITE_URL || '').trim();
    if (configured) {
        return configured.replace(/\/+$/, '');
    }

    const { protocol, hostname, host } = window.location;
    if (hostname === 'localhost' || hostname === '127.0.0.1') {
        return `${protocol}//${hostname}:4321`;
    }
    return `${protocol}//${host}`;
};

const buildPublicProductUrl = (product: Product) => {
    if (!product.slug) return null;
    return `${getPublicSiteBaseUrl()}/product/${product.slug}`;
};

const copyTextToClipboard = async (text: string) => {
    if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(text);
        return;
    }

    const textarea = document.createElement('textarea');
    textarea.value = text;
    textarea.setAttribute('readonly', 'true');
    textarea.style.position = 'absolute';
    textarea.style.left = '-9999px';
    document.body.appendChild(textarea);
    textarea.select();
    document.execCommand('copy');
    document.body.removeChild(textarea);
};

const copyPublicProductLink = async (product: Product) => {
    const url = buildPublicProductUrl(product);
    if (!url) {
        setToast('У товара нет публичного slug');
        return;
    }

    try {
        await copyTextToClipboard(url);
        setToast('Ссылка на сайт скопирована');
    } catch (e) {
        setToast(`Не удалось скопировать ссылку: ${getApiErrorMessage(e)}`);
    }
};

const openPublicProductPage = (product: Product) => {
    const url = buildPublicProductUrl(product);
    if (!url) {
        setToast('У товара нет публичного slug');
        return;
    }
    window.open(url, '_blank', 'noopener,noreferrer');
};

const handleOnlinerImported = async (successCount: number) => {
    setToast(`Импортировано: ${successCount}`);
    await loadProducts();
};

const pendingEditProductId = ref<number | null>(null);
const pendingEditProductQuery = ref('');
const pendingReturnTo = ref('');
const pendingEditHandled = ref(false);

// Bulk Actions
const selectedProductIds = ref<Set<number>>(new Set());
const showBulkSpecsModal = ref(false);
const showBulkCompatibilityModal = ref(false);
const commonGalleryImages = ref<Array<{ url: string; product_count: number }>>([]);
const commonGalleryLoading = ref(false);
const bulkRoundLoading = ref(false);

// Price inline editing
const editingPriceId = ref<number | null>(null);
const priceBuffer = ref<string>('');

// Lazy Loading
const page = ref(1);
const limit = 40;
const hasMore = ref(true);
const loadingMore = ref(false);
const sentinel = ref<HTMLElement | null>(null);

// Filters
const searchQuery = ref('');
const areaMin = ref<number | undefined>();
const areaMax = ref<number | undefined>();
const isInverter = ref<boolean | undefined>();
const viewType = ref<'grid' | 'table'>('grid');
const SMART_SEARCH_LIMIT = 100;
const hasSearchQuery = computed(() => searchQuery.value.trim().length > 0);
const categorySlug = ref<'cat-household' | 'cat-multi' | 'cat-industrial'>('cat-household');
const CATEGORY_FILTER_TABS: Array<{ slug: 'cat-household' | 'cat-multi' | 'cat-industrial'; title: string }> = [
    { slug: 'cat-household', title: 'Бытовые' },
    { slug: 'cat-multi', title: 'Мульти-сплит' },
    { slug: 'cat-industrial', title: 'Полупром' },
];

const applyFilters = () => {
    page.value = 1;
    loadProducts();
};

const setCategoryFilter = (slug: 'cat-household' | 'cat-multi' | 'cat-industrial') => {
    if (categorySlug.value === slug) return;
    categorySlug.value = slug;
    selectedProductIds.value.clear();
    page.value = 1;
    loadProducts();
};


const toggleSelection = (id: number) => {
    if (selectedProductIds.value.has(id)) {
        selectedProductIds.value.delete(id);
    } else {
        selectedProductIds.value.add(id);
    }
};

const allSelected = computed(() => {
    return products.value.length > 0 && selectedProductIds.value.size === products.value.length;
});
const selectedIdsArray = computed(() => Array.from(selectedProductIds.value));
const isBulkMode = computed(() => modalMode.value === 'bulk');

const toggleSelectAll = () => {
    if (allSelected.value) {
        selectedProductIds.value.clear();
    } else {
        products.value.forEach(p => selectedProductIds.value.add(p.id));
    }
};

const openBulkUpdate = () => {
    if (selectedProductIds.value.size === 0) return;
    showBulkSpecsModal.value = true;
};

const openBulkCompatibility = () => {
    if (selectedProductIds.value.size === 0) return;
    showBulkCompatibilityModal.value = true;
};

const selectedProductsForBulkCompatibility = computed(() => {
    const selected = selectedProductIds.value;
    return products.value.filter((product) => selected.has(product.id));
});

const loadCommonGallery = async () => {
    if (selectedIdsArray.value.length === 0) {
        commonGalleryImages.value = [];
        return;
    }
    commonGalleryLoading.value = true;
    try {
        commonGalleryImages.value = await api.getCommonGalleryImages(selectedIdsArray.value);
    } catch (e) {
        commonGalleryImages.value = [];
        console.error(e);
    } finally {
        commonGalleryLoading.value = false;
    }
};

const openBulkImageModal = async () => {
    if (selectedProductIds.value.size === 0) return;
    modalMode.value = 'bulk';
    selectedProduct.value = null;
    imageQuery.value = '';
    imageSearchResults.value = [];
    reuseQuery.value = '';
    reuseResults.value = [];
    activeTab.value = 'search';
    showModal.value = true;
    await loadCommonGallery();
};

const handleBulkSuccess = async () => {
    await loadProducts();
    selectedProductIds.value.clear();
};

const handleFileSelect = async (e: Event) => {
    const input = e.target as HTMLInputElement;
    if (input.files && input.files.length > 0) {
        await uploadFiles(input.files);
    }
};

const handleDrop = async (e: DragEvent) => {
    uploadDragActive.value = false;
    if (e.dataTransfer?.files && e.dataTransfer.files.length > 0) {
        await uploadFiles(e.dataTransfer.files);
    }
};

const uploadFiles = async (files: FileList) => {
    if (!selectedProduct.value && !isBulkMode.value) return;
    searchLoading.value = true;
    try {
        if (isBulkMode.value) {
            const res = await api.bulkUploadLocalImages(selectedIdsArray.value, files);
            setToast(`Загружено ссылок: ${res.uploaded_links}`);
            await loadCommonGallery();
        } else {
            const res = await api.uploadLocalImages(selectedProduct.value!.id, files);
            setToast(`Загружено изображений: ${res.uploaded}`);
            refreshSelectedProduct();
        }
        await loadProducts();
    } catch (e) {
        setToast(`Ошибка загрузки: ${getApiErrorMessage(e)}`);
        console.error(e);
    } finally {
        searchLoading.value = false;
    }
};

// Scroll lock
watch(showModal, (val) => {
  if (val) {
    document.body.style.overflow = 'hidden';
  } else {
    document.body.style.overflow = '';
    confirmDeleteUrl.value = null;
  }
});

const loadProducts = async () => {
  loading.value = true;
  page.value = 1;
  try {
    if (hasSearchQuery.value) {
      const smartResults = await api.smartSearchProducts(
          searchQuery.value.trim(),
          SMART_SEARCH_LIMIT,
          undefined,
          undefined,
          categorySlug.value,
      );
      const filtered = smartResults.filter((product) => {
        if (areaMin.value !== undefined && product.area < areaMin.value) return false;
        if (areaMax.value !== undefined && product.area > areaMax.value) return false;
        if (isInverter.value !== undefined && product.is_inverter !== isInverter.value) return false;
        return true;
      });
      products.value = filtered;
      hasMore.value = false;
    } else {
      const data = await api.getManagerProducts(
          1,
          limit,
          undefined,
          undefined, // isPublished (not exposed yet)
          areaMin.value,
          areaMax.value,
          isInverter.value,
          categorySlug.value,
      );
      products.value = data.items ? data.items : (Array.isArray(data) ? data : []);
      hasMore.value = products.value.length >= limit;
    }
    if (pendingEditProductId.value && !pendingEditHandled.value) {
      const target = products.value.find((p) => p.id === pendingEditProductId.value)
        || (pendingEditProductQuery.value
          ? products.value.find((p) => p.title.toLowerCase().includes(pendingEditProductQuery.value.toLowerCase()))
          : null);
      if (target) {
        pendingEditHandled.value = true;
        openEditModal(target);
      } else if (searchQuery.value.trim()) {
        pendingEditHandled.value = true;
        setToast(`Товар #${pendingEditProductId.value} не найден`);
      }
    }
  } catch (e) {
    setToast(`Ошибка загрузки товаров: ${getApiErrorMessage(e)}`);
    console.error(e);
  } finally {
    loading.value = false;
  }
};

const loadMore = async () => {
    if (loadingMore.value || !hasMore.value || hasSearchQuery.value) return;
    loadingMore.value = true;
    page.value++;
    try {
        const data = await api.getManagerProducts(
            page.value, 
            limit, 
            searchQuery.value || undefined, 
            undefined, 
            areaMin.value, 
            areaMax.value, 
            isInverter.value,
            categorySlug.value,
        );
        const newItems = data.items ? data.items : (Array.isArray(data) ? data : []);
        if (newItems.length < limit) {
            hasMore.value = false;
        }
        products.value.push(...newItems);
    } catch (e) {
        setToast(`Ошибка догрузки товаров: ${getApiErrorMessage(e)}`);
        console.error(e);
    } finally {
        loadingMore.value = false;
    }
};

const startEditingPrice = (product: Product) => {
    editingPriceId.value = product.id;
    priceBuffer.value = String(product.price);
};

const cancelEditingPrice = () => {
    editingPriceId.value = null;
    priceBuffer.value = '';
};

const savePrice = async (product: Product) => {
    const newPrice = parseInt(priceBuffer.value);
    if (isNaN(newPrice)) {
        setToast('Некорректная цена');
        return;
    }
    if (newPrice === product.price) {
        cancelEditingPrice();
        return;
    }

    try {
        await api.updateProduct(product.id, { price: newPrice });
        product.price = newPrice;
        cancelEditingPrice();
    } catch (e) {
        setToast(`Ошибка при сохранении цены: ${getApiErrorMessage(e)}`);
        console.error(e);
    }
};

const confirmingRound = ref(false);

const handleBulkRoundPrices = async () => {
    if (selectedProductIds.value.size === 0) return;
    
    if (!confirmingRound.value) {
        confirmingRound.value = true;
        // Auto-cancel after 4 seconds
        setTimeout(() => { confirmingRound.value = false; }, 4000);
        return;
    }
    
    confirmingRound.value = false;
    bulkRoundLoading.value = true;
    try {
        await api.bulkRoundPrices(selectedIdsArray.value);
        await loadProducts();
        selectedProductIds.value.clear();
        setToast('Цены округлены');
    } catch (e) {
        setToast(`Ошибка при округлении: ${getApiErrorMessage(e)}`);
        console.error(e);
    } finally {
        bulkRoundLoading.value = false;
    }
};

const refreshSelectedProduct = () => {
    if (selectedProduct.value) {
        const fresh = products.value.find(p => p.id === selectedProduct.value!.id);
        if (fresh) {
            selectedProduct.value = fresh;
        }
    }
};

const openSearchModal = (product: Product) => {
  modalMode.value = 'single';
  selectedProduct.value = product;
  imageQuery.value = product.title;
  imageSearchResults.value = [];
  showModal.value = true;
  handleImageSearch();
};

const openEditModal = (product: Product) => {
    editingProduct.value = product;
    showEditModal.value = true;
};

const navigateBackFromProducts = () => {
    if (!pendingReturnTo.value) return;
    window.history.pushState({}, '', pendingReturnTo.value);
    window.dispatchEvent(new PopStateEvent('popstate'));
};

const handleEditSuccess = async () => {
    await loadProducts();
};

const handleImageSearch = async () => {
    if (!imageQuery.value) return;
    searchLoading.value = true;
    try {
        const results = await api.searchImages(imageQuery.value);
        imageSearchResults.value = results;
    } catch (e) {
        setToast(`Ошибка поиска: ${getApiErrorMessage(e)}`);
    } finally {
        searchLoading.value = false;
    }
};

const getImageUrl = (path: string) => {
    if (!path) return '';
    if (path.startsWith('http')) return path;
    if (path.startsWith('/')) return path;
    return '/' + path;
};

const uploadingImageId = ref<string | null>(null);

const bulkAddFromUrls = async (urls: string[], setMain: boolean) => {
    if (!isBulkMode.value || urls.length === 0) return;
    await api.bulkAddGalleryImages(selectedIdsArray.value, urls, setMain, true, false);
    await loadProducts();
    await loadCommonGallery();
};

const addToGallery = async (url: string) => {
    if (!selectedProduct.value && !isBulkMode.value) return;
    uploadingImageId.value = url;
    try {
        if (isBulkMode.value) {
            await bulkAddFromUrls([url], false);
            setToast('Изображение добавлено выбранным товарам');
        } else {
            await api.linkSearchResult(selectedProduct.value!.id, url);
            await loadProducts();
            refreshSelectedProduct();
            setToast('Изображение добавлено в галерею');
        }
    } catch (e) {
        setToast(`Ошибка добавления: ${getApiErrorMessage(e)}`);
    } finally {
        uploadingImageId.value = null;
    }
};

const triggerCleanup = async () => {
    cleanupLoading.value = true;
    try {
        const res = await api.cleanupMedia(false);
        cleanupStats.value = res;
        setToast('Очистка завершена');
    } catch (e) {
        setToast(`Ошибка очистки: ${getApiErrorMessage(e)}`);
    } finally {
        cleanupLoading.value = false;
    }
};

const handleReuseSearch = async () => {
    if (!reuseQuery.value) return;
    searchLoading.value = true;
    try {
        reuseResults.value = await api.reuseSearch(reuseQuery.value);
    } catch (e) { console.error(e); }
    finally { searchLoading.value = false; }
};

const reuseImage = async (sourceUrl: string) => {
    if (!selectedProduct.value && !isBulkMode.value) return;
    try {
        if (isBulkMode.value) {
            await bulkAddFromUrls([sourceUrl], false);
            setToast('Изображение применено к выбранным товарам');
        } else {
            await api.reuseImage(selectedProduct.value!.id, sourceUrl);
            setToast('Изображение применено');
            await loadProducts();
            refreshSelectedProduct();
        }
    } catch (e) {
        setToast(`Ошибка повторного использования: ${getApiErrorMessage(e)}`);
    }
};

const setAsMain = async (id: number) => {
    try {
        await api.setMainImage(id);
        setToast('Главное изображение обновлено');
        await loadProducts();
        refreshSelectedProduct();
    } catch (e) {
        setToast(`Ошибка обновления: ${getApiErrorMessage(e)}`);
    }
};

const confirmDeleteId = ref<number | null>(null);
const confirmDeleteUrl = ref<string | null>(null);

const removeFromGallery = async (id: number) => {
    if (confirmDeleteId.value !== id) {
        confirmDeleteId.value = id;
        setTimeout(() => { if(confirmDeleteId.value === id) confirmDeleteId.value = null; }, 3000);
        return;
    }
    
    confirmDeleteId.value = null;
    try {
        await api.deleteGalleryImage(id);
        await loadProducts();
        refreshSelectedProduct();
        setToast('Изображение удалено');
    } catch (e) {
        setToast(`Ошибка удаления: ${getApiErrorMessage(e)}`);
    }
};

const removeCommonImage = async (url: string) => {
    if (!isBulkMode.value) return;
    if (confirmDeleteUrl.value !== url) {
        confirmDeleteUrl.value = url;
        setTimeout(() => {
            if (confirmDeleteUrl.value === url) confirmDeleteUrl.value = null;
        }, 3000);
        return;
    }

    confirmDeleteUrl.value = null;
    try {
        await api.bulkDeleteCommonImages(selectedIdsArray.value, [url], true);
        await loadProducts();
        await loadCommonGallery();
    } catch (e) {
        setToast(`Ошибка удаления: ${getApiErrorMessage(e)}`);
    }
};

const selectImage = async (url: string) => {
    if ((!selectedProduct.value && !isBulkMode.value) || uploadingImageId.value) return;
    
    uploadingImageId.value = url; 
    
    try {
        if (isBulkMode.value) {
            await bulkAddFromUrls([url], true);
            setToast('Главное изображение обновлено для выбранных товаров');
        } else {
            const response = await api.uploadImage(selectedProduct.value!.id, url);
            if (response && response.url) {
                 await loadProducts();
                 refreshSelectedProduct();
                 showModal.value = false;
            } else {
                 setToast('Изображение загружено, но URL не вернулся');
            }
        }
    } catch (e) {
        setToast(`Ошибка загрузки: ${getApiErrorMessage(e)}`);
    } finally {
        uploadingImageId.value = null;
    }
};

// Intersection Observer for infinite scroll
onMounted(() => {
    const params = new URLSearchParams(window.location.search);
    const editProductIdRaw = params.get('editProductId');
    const parsedEditProductId = editProductIdRaw ? Number(editProductIdRaw) : NaN;
    pendingEditProductId.value = Number.isFinite(parsedEditProductId) && parsedEditProductId > 0 ? parsedEditProductId : null;
    pendingEditProductQuery.value = params.get('editProductQuery') || '';
    pendingReturnTo.value = params.get('returnTo') || '';
    if (!searchQuery.value) {
        if (pendingEditProductQuery.value) {
            searchQuery.value = pendingEditProductQuery.value;
        } else if (pendingEditProductId.value) {
            searchQuery.value = String(pendingEditProductId.value);
        }
    }
    loadProducts();

    const observer = new IntersectionObserver((entries) => {
        if (entries[0]?.isIntersecting && hasMore.value && !loadingMore.value) {
            loadMore();
        }
    }, { threshold: 0.1 });

    // Watch for sentinel element
    watch(sentinel, (el) => {
        if (el) observer.observe(el);
    });
});

const isDeletingProduct = ref<number | null>(null);
const deleteProduct = async (product: Product) => {
    const proceed = window.confirm(`Вы уверены, что хотите удалить товар "${product.title}"? Если товар используется в заказах, удаление будет отклонено.`);
    if (!proceed) return;

    isDeletingProduct.value = product.id;
    try {
        await api.deleteProduct(product.id);
        setToast('Товар успешно удален');
        await loadProducts();
        
        // Remove from selection if deleted
        if (selectedProductIds.value.has(product.id)) {
            selectedProductIds.value.delete(product.id);
        }
    } catch (e: any) {
        setToast(getApiErrorMessage(e));
    } finally {
        isDeletingProduct.value = null;
    }
};

watchDebounced(
    searchQuery,
    () => {
        page.value = 1;
        loadProducts();
    },
    { debounce: 400, maxWait: 1200 },
);
</script>

<template>
  <div class="p-6">
    <!-- Header -->
    <header class="mb-6 flex justify-between items-center">
      <div class="flex items-center gap-4">
          <button
            v-if="pendingReturnTo"
            @click="navigateBackFromProducts"
            class="px-3 py-2 bg-white dark:bg-slate-800 border border-gray-200 dark:border-slate-700 rounded-lg hover:bg-gray-50 dark:hover:bg-slate-700 flex items-center gap-2 text-gray-700 dark:text-slate-200 text-sm transition-colors"
          >
            <ArrowLeft class="w-4 h-4" />
            Назад
          </button>
          <h1 class="text-2xl font-bold text-gray-900 dark:text-white tracking-tight flex items-center gap-3">
            <span class="material-icons-round text-teal-600 dark:text-teal-400">inventory_2</span>
            Товары
          </h1>
          
          <div class="flex bg-gray-100 dark:bg-slate-800 p-1 rounded-lg ml-2">
            <button 
                @click="viewType = 'grid'"
                class="p-1.5 rounded-md transition-all"
                :class="viewType === 'grid' ? 'bg-white dark:bg-slate-700 text-teal-700 dark:text-teal-400 shadow-sm' : 'text-gray-500 hover:text-gray-700 dark:hover:text-slate-300'"
                title="Сетка"
            >
              <LayoutGrid class="w-4 h-4" />
            </button>
            <button 
                @click="viewType = 'table'"
                class="p-1.5 rounded-md transition-all"
                :class="viewType === 'table' ? 'bg-white dark:bg-slate-700 text-teal-700 dark:text-teal-400 shadow-sm' : 'text-gray-500 hover:text-gray-700 dark:hover:text-slate-300'"
                title="Таблица"
            >
              <List class="w-4 h-4" />
            </button>
          </div>

          <div v-if="selectedProductIds.size > 0" class="flex items-center gap-2 bg-teal-50 dark:bg-teal-900/20 px-4 py-2 rounded-lg border border-teal-100 dark:border-teal-900/30">
              <span class="text-sm font-medium text-teal-800 dark:text-teal-300">{{ selectedProductIds.size }} выбрано</span>
              <button @click="openBulkImageModal" class="flex items-center gap-1 bg-gray-700 text-white px-3 py-1.5 rounded-md text-sm hover:bg-gray-800 transition-colors">
                  <Images class="w-3.5 h-3.5" /> Изображения
              </button>
              <button @click="openBulkUpdate" class="flex items-center gap-1 bg-teal-600 text-white px-3 py-1.5 rounded-md text-sm hover:bg-teal-700 transition-colors">
                  <Edit3 class="w-3.5 h-3.5" /> Характеристики
              </button>
              <button @click="openBulkCompatibility" class="flex items-center gap-1 bg-indigo-600 text-white px-3 py-1.5 rounded-md text-sm hover:bg-indigo-700 transition-colors">
                  <Link2 class="w-3.5 h-3.5" /> Совместимость
              </button>
              <button 
                @click="handleBulkRoundPrices" 
                :disabled="bulkRoundLoading"
                class="flex items-center gap-1 px-3 py-1.5 rounded-md text-sm transition-all disabled:opacity-50"
                :class="confirmingRound ? 'bg-red-600 hover:bg-red-700 text-white animate-pulse ring-2 ring-red-300' : 'bg-amber-600 hover:bg-amber-700 text-white'"
              >
                  <RefreshCw class="w-3.5 h-3.5" :class="{ 'animate-spin': bulkRoundLoading }" />
                  {{ confirmingRound ? 'Подтвердить?' : 'Округлить цены' }}
              </button>
              <button @click="selectedProductIds.clear()" class="text-xs text-teal-600 hover:text-teal-800 underline ml-1">Сбросить</button>
          </div>
      </div>
      <div class="flex gap-2">
          <button @click="toggleSelectAll" class="px-3 py-2 bg-white dark:bg-slate-800 border border-gray-200 dark:border-slate-700 rounded-lg hover:bg-gray-50 dark:hover:bg-slate-700 flex items-center gap-2 text-gray-700 dark:text-slate-200 text-sm transition-colors">
              <CheckSquare v-if="allSelected" class="w-4 h-4 text-teal-600" />
              <Square v-else class="w-4 h-4 text-gray-400" />
              Выбрать все
          </button>
          <button @click="showCleanupModal = true" class="px-3 py-2 bg-red-50 text-red-600 rounded-lg hover:bg-red-100 text-sm transition-colors">
              Очистка медиа
          </button>
          <button
            @click="showOnlinerImportModal = true"
            class="flex items-center gap-1.5 px-3 py-2 bg-teal-600 hover:bg-teal-500 text-white rounded-lg text-sm font-medium transition-colors shadow-sm"
            title="Импорт из Onliner"
          >
            <span class="material-icons-round text-base leading-none">cloud_download</span>
            Onliner
          </button>
          <button @click="loadProducts" class="p-2 bg-white dark:bg-slate-800 rounded-lg border border-gray-200 dark:border-slate-700 shadow-sm hover:bg-gray-50 dark:hover:bg-slate-700 transition-colors" title="Обновить">
              <RefreshCw class="w-4 h-4 text-gray-600 dark:text-slate-400" />
          </button>
      </div>
    </header>
      <!-- Toast -->
      <Transition name="fade">
        <div v-if="toast" class="fixed top-6 right-6 z-[100] bg-teal-600 text-white px-6 py-3 rounded-xl shadow-2xl font-medium animate-in slide-in-from-top-4 duration-300">
          {{ toast }}
        </div>
      </Transition>

    <!-- Filters -->
    <div class="bg-white dark:bg-slate-800 p-4 rounded-xl shadow-sm border border-gray-200 dark:border-slate-700 mb-6 flex flex-wrap gap-4 items-end">
        <div class="w-full">
            <label class="block text-xs font-medium text-gray-500 mb-1">Категория каталога</label>
            <div class="flex flex-wrap gap-2">
                <button
                    v-for="tab in CATEGORY_FILTER_TABS"
                    :key="tab.slug"
                    type="button"
                    class="px-3 py-1.5 rounded-lg border text-sm font-medium transition-colors"
                    :class="categorySlug === tab.slug
                        ? 'bg-teal-600 text-white border-teal-600'
                        : 'bg-white dark:bg-slate-800 text-gray-700 dark:text-slate-200 border-gray-300 dark:border-slate-700 hover:bg-gray-50 dark:hover:bg-slate-700'"
                    @click="setCategoryFilter(tab.slug)"
                >
                    {{ tab.title }}
                </button>
            </div>
        </div>

        <div class="flex-1 min-w-[200px]">
            <label class="block text-xs font-medium text-gray-500 mb-1">Поиск по модели</label>
            <div class="relative">
                <Search class="w-4 h-4 text-gray-400 dark:text-slate-500 absolute left-3 top-1/2 -translate-y-1/2" />
                <input 
                    v-model="searchQuery" 
                    @keyup.enter="applyFilters"
                    placeholder="Например: ARTCOOL..." 
                    class="w-full pl-9 pr-4 py-2 border border-gray-300 dark:border-slate-700 bg-slate-100 dark:bg-slate-900 text-gray-900 dark:text-slate-100 dark:placeholder-slate-500 rounded-lg text-sm focus:ring-2 focus:ring-teal-500 focus:border-transparent outline-none shadow-inner"
                />
            </div>
        </div>

        <div class="w-[180px]">
             <label class="block text-xs font-medium text-gray-500 mb-1">Площадь (м²)</label>
             <div class="flex gap-2 items-center">
                 <input 
                    v-model.number="areaMin"
                    type="number" 
                    placeholder="От" 
                    class="w-full px-3 py-2 border border-gray-300 dark:border-slate-700 bg-slate-100 dark:bg-slate-900 text-gray-900 dark:text-slate-100 dark:placeholder-slate-500 rounded-lg text-sm focus:ring-2 focus:ring-teal-500 outline-none shadow-inner"
                 />
                 <span class="text-gray-400">-</span>
                 <input 
                    v-model.number="areaMax"
                    type="number" 
                    placeholder="До" 
                    class="w-full px-3 py-2 border border-gray-300 dark:border-slate-700 bg-slate-100 dark:bg-slate-900 text-gray-900 dark:text-slate-100 dark:placeholder-slate-500 rounded-lg text-sm focus:ring-2 focus:ring-teal-500 outline-none shadow-inner"
                 />
             </div>
        </div>

        <div class="flex items-center gap-2 pb-2">
            <label class="flex items-center gap-2 cursor-pointer bg-slate-100 dark:bg-slate-800 px-3 py-2 rounded-lg border border-gray-200 dark:border-slate-700 hover:bg-gray-100 dark:hover:bg-slate-700 transition-colors select-none">
                <input type="checkbox" v-model="isInverter" class="w-4 h-4 text-teal-600 dark:text-teal-500 bg-white dark:bg-slate-900 border-gray-300 dark:border-slate-700 rounded focus:ring-teal-500" />
                <span class="text-sm text-gray-700 dark:text-slate-300">Только инвертор</span>
            </label>
        </div>

        <button 
            @click="applyFilters"
            class="px-6 py-2 bg-teal-600 dark:bg-teal-600 text-white rounded-lg hover:bg-teal-700 dark:hover:bg-teal-700 font-medium text-sm transition-colors shadow-sm"
        >
            Применить
        </button>
    </div>
    
    <!-- Product Grid -->
    <div v-if="loading" class="py-20">
      <div class="flex items-center justify-center gap-3 text-gray-500">
        <div class="h-6 w-6 rounded-full border-2 border-[#007f80] border-t-transparent animate-spin"></div>
        <span>Загрузка товаров...</span>
      </div>
    </div>
    
    <div v-else>
      <!-- Grid View -->
      <div v-if="viewType === 'grid'" class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-5 gap-5">
        <div v-for="product in products" :key="product.id" 
             class="bg-white dark:bg-slate-800 rounded-xl shadow-sm overflow-hidden group border-2 transition-all hover:shadow-md relative"
             :class="selectedProductIds.has(product.id) ? 'border-teal-500 ring-2 ring-teal-100 dark:ring-teal-900/50' : 'border-transparent'"
        >
             <!-- Selection Checkbox Overlay -->
             <div class="absolute top-2.5 left-2.5 z-10">
                 <button @click.stop="toggleSelection(product.id)" class="bg-white/90 dark:bg-slate-800/90 backdrop-blur-sm rounded-md shadow-sm hover:bg-white dark:hover:bg-slate-700 p-1 transition-colors">
                     <CheckSquare v-if="selectedProductIds.has(product.id)" class="w-5 h-5 text-teal-600" />
                     <Square v-else class="w-5 h-5 text-gray-400" />
                 </button>
             </div>
            <div class="aspect-video bg-gray-100 dark:bg-slate-700 relative">
                <img v-if="product.main_image" :src="getImageUrl(product.main_image)" class="w-full h-full object-cover" />
                <div v-else class="w-full h-full flex items-center justify-center text-gray-300">
                    <Package class="w-10 h-10" />
                </div>
                
                <!-- Overlay Actions -->
                <div class="absolute inset-0 bg-black/50 opacity-0 group-hover:opacity-100 transition-opacity flex flex-col items-center justify-center gap-2">
                    <button
                      @click.stop="deleteProduct(product)"
                      :disabled="isDeletingProduct === product.id"
                      class="absolute top-2.5 right-2.5 flex h-7 w-7 items-center justify-center rounded-full bg-red-600/90 text-white shadow-sm transition-colors hover:bg-red-700 disabled:opacity-50"
                      title="Удалить"
                    >
                      <span class="material-icons-round text-[16px] leading-none">close</span>
                    </button>
                    <button @click="openSearchModal(product)" class="bg-teal-600 text-white px-4 py-2 rounded-full flex items-center gap-2 hover:bg-teal-700 text-sm font-medium transition-colors w-36 justify-center">
                        <Images class="w-4 h-4" /> Фото
                    </button>
                    <button @click="openEditModal(product)" class="bg-white text-gray-900 px-4 py-2 rounded-full flex items-center gap-2 hover:bg-gray-100 text-sm font-medium transition-colors w-36 justify-center">
                        <Settings class="w-4 h-4 text-teal-600" /> Изменить
                    </button>
                    <button @click="copyPublicProductLink(product)" class="bg-white text-gray-900 px-4 py-2 rounded-full flex items-center gap-2 hover:bg-gray-100 text-sm font-medium transition-colors w-36 justify-center">
                        <Link2 class="w-4 h-4 text-teal-600" /> Ссылка
                    </button>
                </div>
            </div>
            <div class="p-3.5">
                <h3 class="font-medium text-gray-900 dark:text-slate-200 text-sm truncate" :title="product.title">{{ product.title }}</h3>
                <div class="mt-0.5 flex items-center justify-between gap-3 min-h-6">
                    <template v-if="editingPriceId === product.id">
                        <input 
                            v-model="priceBuffer"
                            type="number"
                            @blur="savePrice(product)"
                            @keyup.enter="savePrice(product)"
                            @keyup.esc="cancelEditingPrice"
                            class="w-24 px-1 py-0.5 border border-teal-500 dark:border-teal-400 rounded text-sm outline-none bg-teal-50 dark:bg-teal-900/30 text-gray-900 dark:text-slate-200"
                            auto-focus
                        />
                        <span class="text-xs text-teal-600 dark:text-teal-400 ml-1">руб.</span>
                    </template>
                    <p 
                        v-else 
                        @click.stop="startEditingPrice(product)"
                        class="text-teal-700 dark:text-teal-400 font-semibold text-sm cursor-pointer hover:bg-teal-50 dark:hover:bg-teal-900/40 rounded px-1 -ml-1 transition-colors"
                        title="Нажмите, чтобы изменить цену"
                    >
                        {{ product.price }} руб.
                    </p>
                    <button
                        @click="openPublicProductPage(product)"
                        class="inline-flex items-center gap-1 rounded-full px-2 py-1 text-[11px] font-medium text-teal-700 dark:text-teal-300 bg-teal-50 dark:bg-teal-900/30 hover:bg-teal-100 dark:hover:bg-teal-900/40 transition-colors disabled:opacity-45 disabled:cursor-not-allowed disabled:hover:bg-teal-50 dark:disabled:hover:bg-teal-900/30"
                        :disabled="!product.slug"
                        :title="product.slug ? 'Открыть карточку товара на сайте' : 'У товара нет публичного slug'"
                    >
                        <ExternalLink class="w-3.5 h-3.5" />
                        сайт
                    </button>
                </div>
                <div class="mt-1 space-y-0.5 text-[11px] text-gray-500 dark:text-slate-400">
                    <div>Себестоимость: {{ product.min_cost_byn != null ? `${product.min_cost_byn.toFixed(2)} BYN` : '—' }}</div>
                    <div>РРЦ: {{ product.recommended_price_byn != null ? `${product.recommended_price_byn.toFixed(2)} BYN` : '—' }}</div>
                    <div>Маржа: {{ product.margin_abs_preview != null ? `${product.margin_abs_preview.toFixed(2)} BYN` : '—' }}</div>
                </div>
                <div class="mt-2 flex items-center gap-1.5 text-[10px]">
                    <span class="px-1.5 py-0.5 rounded bg-emerald-50 text-emerald-700 border border-emerald-200">Витебск: {{ product.vitebsk_qty || 0 }}</span>
                    <span class="px-1.5 py-0.5 rounded bg-sky-50 text-sky-700 border border-sky-200">Минск: {{ product.minsk_qty || 0 }}</span>
                    <span
                        class="px-1.5 py-0.5 rounded border"
                        :class="product.availability_status === 'in_stock_now'
                            ? 'bg-emerald-100 text-emerald-700 border-emerald-200'
                            : product.availability_status === 'available_2_3_days'
                                ? 'bg-amber-100 text-amber-800 border-amber-200'
                                : product.availability_status === 'check_availability'
                                    ? 'bg-blue-100 text-blue-800 border-blue-200'
                                : 'bg-gray-100 text-gray-600 border-gray-200'"
                    >
                        {{ product.availability_status === 'in_stock_now'
                            ? 'Сейчас'
                            : (product.availability_status === 'available_2_3_days'
                                ? '2-3 дня'
                                : (product.availability_status === 'check_availability' ? 'Уточнить' : 'Нет')) }}
                    </span>
                </div>
                <!-- Mini Gallery Preview -->
                <div class="flex gap-1 mt-2 overflow-hidden h-7" v-if="product.gallery_images && product.gallery_images.length">
                    <img v-for="img in product.gallery_images.slice(0, 6)" :key="img.id" :src="getImageUrl(img.url)" class="w-7 h-7 object-cover rounded" />
                    <span v-if="product.gallery_images.length > 6" class="w-7 h-7 bg-gray-100 rounded flex items-center justify-center text-[10px] text-gray-500">+{{ product.gallery_images.length - 6 }}</span>
                </div>
            </div>
        </div>
      </div>

      <!-- Table View -->
      <div v-else-if="viewType === 'table'" class="bg-white dark:bg-slate-800 rounded-xl shadow-sm border border-gray-200 dark:border-slate-700 overflow-hidden">
        <table class="w-full text-left border-collapse text-gray-900 dark:text-slate-200">
          <thead class="bg-gray-50 dark:bg-slate-900/50 text-gray-500 dark:text-slate-400">
            <tr>
              <th class="p-4 w-12">
                <button @click="toggleSelectAll" class="text-gray-400 hover:text-gray-600 dark:hover:text-slate-300">
                  <CheckSquare v-if="allSelected" class="w-5 h-5 text-teal-600" />
                  <Square v-else class="w-5 h-5" />
                </button>
              </th>
              <th class="p-4 text-xs font-semibold uppercase tracking-wider">Фото</th>
              <th class="p-4 text-xs font-semibold uppercase tracking-wider">Название</th>
              <th class="p-4 text-xs font-semibold uppercase tracking-wider">Цена</th>
              <th class="p-4 text-xs font-semibold uppercase tracking-wider">Supply</th>
              <th class="p-4 text-xs font-semibold uppercase tracking-wider text-right">Действия</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-100 dark:divide-slate-700">
            <tr v-for="product in products" :key="product.id" 
                class="hover:bg-gray-50 dark:hover:bg-slate-700/50 transition-colors"
                :class="{ 'bg-teal-50/50 dark:bg-teal-900/20': selectedProductIds.has(product.id) }"
            >
              <td class="p-4">
                <button @click="toggleSelection(product.id)" class="text-gray-400 hover:text-gray-600 dark:hover:text-slate-300">
                  <CheckSquare v-if="selectedProductIds.has(product.id)" class="w-5 h-5 text-teal-600" />
                  <Square v-else class="w-5 h-5" />
                </button>
              </td>
              <td class="p-4">
                <div class="w-16 h-10 bg-gray-100 dark:bg-slate-700 rounded overflow-hidden shadow-sm relative group/thumb cursor-pointer" @click="openEditModal(product)">
                    <img v-if="product.main_image" :src="getImageUrl(product.main_image)" class="w-full h-full object-cover" />
                    <div v-else class="w-full h-full flex items-center justify-center text-gray-300">
                      <Package class="w-5 h-5" />
                    </div>
                </div>
              </td>
              <td class="p-4">
                <div class="text-sm font-medium max-w-xl truncate" :title="product.title">
                  {{ product.title }}
                </div>
              </td>
              <td class="p-4">
                <div class="text-sm font-semibold text-teal-700 dark:text-teal-400">
                   {{ product.price }} руб.
                </div>
              </td>
              <td class="p-4 text-xs text-gray-600 dark:text-slate-400">
                <div>Себест: {{ product.min_cost_byn != null ? `${product.min_cost_byn.toFixed(2)}` : '—' }}</div>
                <div>РРЦ: {{ product.recommended_price_byn != null ? `${product.recommended_price_byn.toFixed(2)}` : '—' }}</div>
                <div>V: {{ product.vitebsk_qty || 0 }} / M: {{ product.minsk_qty || 0 }}</div>
              </td>
              <td class="p-4 text-right">
                <div class="flex justify-end gap-2 text-gray-400">
                  <button @click="copyPublicProductLink(product)" class="p-2 hover:text-teal-600 dark:hover:text-teal-400 transition-colors" :title="product.slug ? 'Скопировать ссылку на сайт' : 'У товара нет публичного slug'" :disabled="!product.slug">
                    <Link2 class="w-4 h-4" />
                  </button>
                  <button @click="openPublicProductPage(product)" class="p-2 hover:text-teal-600 dark:hover:text-teal-400 transition-colors" :title="product.slug ? 'Открыть сайт' : 'У товара нет публичного slug'" :disabled="!product.slug">
                    <ExternalLink class="w-4 h-4" />
                  </button>
                  <button @click="openSearchModal(product)" class="p-2 hover:text-teal-600 dark:hover:text-teal-400 transition-colors" title="Фото">
                    <Images class="w-4 h-4" />
                  </button>
                  <button @click="openEditModal(product)" class="p-2 hover:text-teal-600 dark:hover:text-teal-400 transition-colors" title="Изменить">
                    <Settings class="w-4 h-4" />
                  </button>
                  <button @click.stop="deleteProduct(product)" :disabled="isDeletingProduct === product.id" class="p-2 hover:text-red-600 transition-colors" title="Удалить">
                    <span class="material-icons-round text-[18px]">delete</span>
                  </button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- Lazy Load Sentinel -->
      <div ref="sentinel" class="py-8 text-center">
        <div v-if="loadingMore" class="flex items-center justify-center gap-2 text-gray-500">
          <div class="w-5 h-5 border-2 border-teal-600 border-t-transparent rounded-full animate-spin"></div>
          Загрузка...
        </div>
        <p v-else-if="!hasMore && products.length > 0" class="text-gray-400 text-sm">Все товары загружены ({{ products.length }})</p>
      </div>
    </div>
  </div>
  
  <!-- Cleanup Modal -->
  <div v-if="showCleanupModal" class="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div class="bg-white rounded-xl p-6 max-w-lg w-full shadow-2xl">
          <h2 class="text-xl font-bold mb-4">Очистка неиспользуемых медиа</h2>
          <p class="mb-4 text-gray-600">Сканирование файлов, не связанных с базой данных, и их удаление.</p>
          
          <div v-if="cleanupStats" class="bg-gray-50 p-4 rounded-lg mb-4 text-sm">
              <p>Удалено: {{ cleanupStats.deleted_count }} файлов</p>
              <p>Освобождено: {{ (cleanupStats.reclaimed_bytes / 1024 / 1024).toFixed(2) }} MB</p>
              <ul class="mt-2 list-disc list-inside text-gray-500 h-32 overflow-y-auto">
                  <li v-for="f in cleanupStats.files" :key="f">{{ f }}</li>
              </ul>
          </div>
          
          <div class="flex justify-end gap-2">
              <button @click="showCleanupModal = false" class="px-4 py-2 text-gray-500 hover:text-gray-700">Закрыть</button>
              <button @click="triggerCleanup" :disabled="cleanupLoading" class="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 disabled:opacity-50 transition-colors">
                  {{ cleanupLoading ? 'Очистка...' : 'Запустить' }}
              </button>
          </div>
      </div>
  </div>
  
  <!-- Search / Manage Modal -->
  <div v-if="showModal" class="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4" @click.self="showModal = false">
      <div class="bg-white rounded-xl w-full max-w-6xl h-[90vh] flex flex-col shadow-2xl">
          <!-- Tabs -->
          <div class="flex border-b bg-gray-50 rounded-t-xl">
               <button 
                  @click="activeTab = 'search'" 
                  class="px-6 py-3 font-medium border-b-2 text-sm transition-colors"
                  :class="activeTab === 'search' ? 'border-teal-600 text-teal-700' : 'border-transparent text-gray-500 hover:text-gray-700'"
               >Поиск изображений</button>
               <button 
                  @click="activeTab = 'reuse'" 
                  class="px-6 py-3 font-medium border-b-2 text-sm transition-colors"
                  :class="activeTab === 'reuse' ? 'border-teal-600 text-teal-700' : 'border-transparent text-gray-500 hover:text-gray-700'"
               >Из каталога</button>
               <button 
                  @click="activeTab = 'upload'" 
                  class="px-6 py-3 font-medium border-b-2 text-sm transition-colors"
                  :class="activeTab === 'upload' ? 'border-teal-600 text-teal-700' : 'border-transparent text-gray-500 hover:text-gray-700'"
               >Загрузить</button>
               <div v-if="isBulkMode" class="flex items-center text-sm text-teal-700 font-medium px-3">
                  {{ selectedIdsArray.length }} товаров
               </div>
               <div class="flex-1 flex justify-end items-center px-4">
                   <button @click="showModal = false" class="text-gray-400 hover:text-gray-600 text-sm transition-colors">Закрыть</button>
               </div>
          </div>

          <!-- Tab Content -->
          <div class="flex-1 overflow-hidden flex flex-col min-h-0">
              <!-- SEARCH TAB -->
              <div v-if="activeTab === 'search'" class="flex flex-col flex-1 min-h-0">
                   <div class="p-4 border-b flex gap-4 bg-white">
                      <input v-model="imageQuery" @keyup.enter="handleImageSearch" class="flex-1 border border-gray-300 rounded-lg px-4 py-2 focus:outline-none focus:ring-2 focus:ring-teal-500 focus:border-transparent" placeholder="Поисковый запрос..." />
                      <button @click="handleImageSearch" class="bg-teal-600 text-white px-6 rounded-lg hover:bg-teal-700 transition-colors font-medium">Поиск</button>
                  </div>
                  
                  <div class="flex-1 overflow-y-auto p-4 bg-gray-50">
                      <div v-if="searchLoading" class="text-center py-10 text-gray-500">Поиск DuckDuckGo...</div>
                      <div v-else class="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-5 gap-4">
                           <div v-for="(r, idx) in imageSearchResults" :key="idx" class="group relative bg-white rounded-lg shadow-sm hover:shadow-md transition-all">
                              <div class="aspect-square bg-gray-100 relative overflow-hidden rounded-t-lg">
                                   <img :src="r.thumbnail || r.image" class="w-full h-full object-contain p-2" loading="lazy" />
                                   <div class="absolute inset-0 bg-black/60 opacity-0 group-hover:opacity-100 transition-opacity flex flex-col items-center justify-center gap-2 p-2">
                                       <button @click="selectImage(r.image)" class="w-full bg-teal-600 text-white text-xs py-1.5 rounded-md hover:bg-teal-700 transition-colors">
                                           {{ isBulkMode ? 'Главное для всех' : 'Сделать главным' }}
                                       </button>
                                       <button @click="addToGallery(r.image)" class="w-full bg-gray-600 text-white text-xs py-1.5 rounded-md hover:bg-gray-700 transition-colors">
                                           {{ isBulkMode ? 'Добавить всем' : 'В галерею' }}
                                       </button>
                                   </div>
                              </div>
                              <div class="p-2 text-xs text-gray-500 border-t flex justify-between">
                                  <span>{{ r.width }}x{{ r.height }}</span>
                                  <span class="truncate max-w-[100px]">{{ r.source }}</span>
                              </div>
                          </div>
                      </div>
                  </div>
              </div>
              
              <!-- REUSE TAB -->
              <div v-if="activeTab === 'reuse'" class="flex flex-col flex-1 min-h-0">
                   <div class="p-4 border-b flex gap-4 bg-white">
                      <input v-model="reuseQuery" @keyup.enter="handleReuseSearch" class="flex-1 border border-gray-300 rounded-lg px-4 py-2 focus:outline-none focus:ring-2 focus:ring-teal-500 focus:border-transparent" placeholder="Найти модель (напр. Forest 09)..." />
                      <button @click="handleReuseSearch" class="bg-teal-600 text-white px-6 rounded-lg hover:bg-teal-700 transition-colors font-medium">Найти</button>
                  </div>
                  <div class="flex-1 overflow-y-auto p-4 bg-gray-50">
                      <div class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
                          <div v-for="p in reuseResults" :key="p.id" class="bg-white rounded-lg shadow-sm overflow-hidden group hover:shadow-md transition-all">
                              <div class="aspect-video bg-gray-100 relative">
                                  <img v-if="p.main_image" :src="getImageUrl(p.main_image)" class="w-full h-full object-cover" />
                                  <div v-else class="w-full h-full flex items-center justify-center text-gray-300 text-xs">Нет фото</div>
                                  
                                   <div class="absolute inset-0 bg-black/40 opacity-0 group-hover:opacity-100 flex items-center justify-center transition-opacity">
                                       <button @click="reuseImage(p.main_image)" class="text-white text-sm bg-teal-600 px-3 py-2 rounded-lg hover:bg-teal-700 transition-colors">
                                          {{ isBulkMode ? 'Копировать всем' : 'Копировать' }}
                                       </button>
                                  </div>
                              </div>
                              <div class="p-2 text-sm font-medium truncate" :title="p.title">{{ p.title }}</div>
                          </div>
                      </div>
                  </div>
              </div>

              <!-- UPLOAD TAB -->
              <div v-if="activeTab === 'upload'" class="flex flex-col flex-1 min-h-0 p-8 items-center justify-center bg-gray-50">
                  <div 
                      class="w-full max-w-2xl border-4 border-dashed rounded-xl p-12 flex flex-col items-center justify-center transition-colors cursor-pointer"
                      :class="uploadDragActive ? 'border-teal-500 bg-teal-50' : 'border-gray-300 hover:border-gray-400 bg-white'"
                      @dragenter.prevent="uploadDragActive = true"
                      @dragleave.prevent="uploadDragActive = false"
                      @dragover.prevent
                      @drop.prevent="handleDrop"
                      @click="fileInput?.click()"
                  >
                      <input type="file" ref="fileInput" multiple accept="image/*" class="hidden" @change="handleFileSelect" />
                      <UploadCloud class="w-16 h-16 text-gray-400 mb-4" :class="{ 'text-teal-500': uploadDragActive }" />
                      <h3 class="text-xl font-medium text-gray-700 mb-2">
                          {{ uploadDragActive ? 'Отпустите файлы' : 'Перетащите изображения сюда' }}
                      </h3>
                      <p class="text-gray-500 mb-6">или нажмите для выбора файлов</p>
                      
                      <div v-if="searchLoading" class="flex items-center gap-2 text-teal-600 font-medium">
                          <div class="w-4 h-4 border-2 border-teal-600 border-t-transparent rounded-full animate-spin"></div>
                          Загрузка...
                      </div>
                  </div>
              </div>
          </div>
          
          <!-- Current Product Gallery Preview (Footer) -->
          <div class="h-44 bg-white border-t p-4 overflow-x-auto flex gap-4 shrink-0">
              <div class="w-56 shrink-0 flex items-center justify-center text-gray-400 border-r pr-4 text-sm">
                  {{ isBulkMode ? 'Общая галерея (все выбранные)' : 'Текущая галерея' }}
              </div>
              <template v-if="isBulkMode">
                  <div v-if="commonGalleryLoading" class="text-sm text-gray-500 flex items-center">
                      Загрузка общих изображений...
                  </div>
                  <div
                      v-for="img in commonGalleryImages"
                      :key="img.url"
                      class="relative group w-32 shrink-0 border rounded-lg overflow-hidden"
                  >
                      <img :src="getImageUrl(img.url)" class="w-full h-full object-cover" />
                      <div class="absolute inset-0 bg-black/50 opacity-0 group-hover:opacity-100 flex flex-col items-center justify-center gap-1 p-2 transition-opacity">
                          <button
                              @click="removeCommonImage(img.url)"
                              class="text-[10px] text-white px-2 py-1 rounded w-full transition-colors"
                              :class="confirmDeleteUrl === img.url ? 'bg-red-800 font-bold' : 'bg-red-600 hover:bg-red-700'"
                          >
                              {{ confirmDeleteUrl === img.url ? 'Подтвердить?' : 'Удалить у всех' }}
                          </button>
                      </div>
                  </div>
              </template>
              <template v-else>
                  <!-- Main Image -->
                  <div v-if="selectedProduct?.main_image" class="relative group w-32 shrink-0 border-2 border-teal-500 rounded-lg overflow-hidden">
                      <img :src="getImageUrl(selectedProduct.main_image)" class="w-full h-full object-cover" />
                      <span class="absolute top-0 left-0 bg-teal-500 text-white text-[10px] px-1.5 py-0.5 rounded-br-md">Главное</span>
                  </div>

                  <!-- Gallery Items -->
                  <div v-if="selectedProduct?.gallery_images" v-for="img in selectedProduct.gallery_images.filter(i => !i.is_installation_photo)" :key="img.id" class="relative group w-32 shrink-0 border rounded-lg overflow-hidden">
                      <img :src="getImageUrl(img.url)" class="w-full h-full object-cover" />
                      <div class="absolute inset-0 bg-black/50 opacity-0 group-hover:opacity-100 flex flex-col items-center justify-center gap-1 p-2 transition-opacity">
                           <button @click="setAsMain(img.id)" class="text-[10px] bg-white text-black px-2 py-1 rounded hover:bg-gray-200 w-full">Сделать главным</button>
                           <button
                              @click="removeFromGallery(img.id)"
                              class="text-[10px] text-white px-2 py-1 rounded w-full transition-colors"
                              :class="confirmDeleteId === img.id ? 'bg-red-800 font-bold' : 'bg-red-600 hover:bg-red-700'"
                           >
                              {{ confirmDeleteId === img.id ? 'Подтвердить?' : 'Удалить' }}
                           </button>
                      </div>
                  </div>
              </template>
          </div>
      </div>
  </div>
    <!-- Bulk Specs Modal -->
    <BulkSpecsModal 
        v-model="showBulkSpecsModal"
        :selected-product-ids="Array.from(selectedProductIds)"
        @success="handleBulkSuccess"
    />
    <BulkCompatibilityModal
        v-model="showBulkCompatibilityModal"
        :selected-products="selectedProductsForBulkCompatibility"
        @success="handleBulkSuccess"
    />

    <!-- Individual Edit Modal -->
    <ProductEditModal 
        v-model="showEditModal"
        :product="editingProduct"
        @success="handleEditSuccess"
    />

    <!-- Onliner Import Modal -->
    <OnlinerImportModal
        v-if="showOnlinerImportModal"
        @close="showOnlinerImportModal = false"
        @imported="handleOnlinerImported"
    />
</template>
