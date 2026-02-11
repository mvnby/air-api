<script setup lang="ts">
import { ref, onMounted, watch, computed } from 'vue';
import { api, type Product } from '../api';
import { Search, RefreshCw, UploadCloud, Edit3, CheckSquare, Square, Images } from 'lucide-vue-next';
import BulkSpecsModal from '../components/BulkSpecsModal.vue';

// Product state
const products = ref<Product[]>([]);
const loading = ref(false);
const showModal = ref(false);
const selectedProduct = ref<Product | null>(null);
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

// Bulk Actions
const selectedProductIds = ref<Set<number>>(new Set());
const showBulkSpecsModal = ref(false);
const commonGalleryImages = ref<Array<{ url: string; product_count: number }>>([]);
const commonGalleryLoading = ref(false);

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

const applyFilters = () => {
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
            alert(`Uploaded ${res.uploaded_links} links`);
            await loadCommonGallery();
        } else {
            const res = await api.uploadLocalImages(selectedProduct.value!.id, files);
            alert(`Uploaded ${res.uploaded} images`);
            refreshSelectedProduct();
        }
        await loadProducts();
    } catch (e) {
        alert('Upload failed');
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
    const data = await api.getManagerProducts(
        1, 
        limit, 
        searchQuery.value || undefined, 
        undefined, // isPublished (not exposed yet)
        areaMin.value,
        areaMax.value,
        isInverter.value
    );
    products.value = data.items ? data.items : (Array.isArray(data) ? data : []);
    hasMore.value = products.value.length >= limit;
  } catch (e) {
    console.error(e);
  } finally {
    loading.value = false;
  }
};

const loadMore = async () => {
    if (loadingMore.value || !hasMore.value) return;
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
            isInverter.value
        );
        const newItems = data.items ? data.items : (Array.isArray(data) ? data : []);
        if (newItems.length < limit) {
            hasMore.value = false;
        }
        products.value.push(...newItems);
    } catch (e) {
        console.error(e);
    } finally {
        loadingMore.value = false;
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

const handleImageSearch = async () => {
    if (!imageQuery.value) return;
    searchLoading.value = true;
    try {
        const results = await api.searchImages(imageQuery.value);
        imageSearchResults.value = results;
    } catch (e) {
        alert('Search failed');
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
            alert('Added to selected products');
        } else {
            await api.linkSearchResult(selectedProduct.value!.id, url);
            await loadProducts();
            refreshSelectedProduct();
            alert('Added to gallery');
        }
    } catch (e) {
        alert('Failed to add');
    } finally {
        uploadingImageId.value = null;
    }
};

const triggerCleanup = async () => {
    cleanupLoading.value = true;
    try {
        const res = await api.cleanupMedia(false);
        cleanupStats.value = res;
    } catch (e) {
        alert('Cleanup failed');
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
            alert('Image reused for selected products');
        } else {
            await api.reuseImage(selectedProduct.value!.id, sourceUrl);
            alert('Image reused');
            await loadProducts();
            refreshSelectedProduct();
        }
    } catch (e) { alert('Failed'); }
};

const setAsMain = async (id: number) => {
    try {
        await api.setMainImage(id);
        alert('Updated');
        await loadProducts();
        refreshSelectedProduct();
    } catch (e) { alert('Failed'); }
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
    } catch (e) { alert('Failed'); }
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
        alert('Failed');
    }
};

const selectImage = async (url: string) => {
    if ((!selectedProduct.value && !isBulkMode.value) || uploadingImageId.value) return;
    
    uploadingImageId.value = url; 
    
    try {
        if (isBulkMode.value) {
            await bulkAddFromUrls([url], true);
            alert('Set as main for selected products');
        } else {
            const response = await api.uploadImage(selectedProduct.value!.id, url);
            if (response && response.url) {
                 await loadProducts();
                 refreshSelectedProduct();
                 showModal.value = false;
            } else {
                 alert('Upload succeeded but no URL returned');
            }
        }
    } catch (e) {
        alert('Upload failed');
    } finally {
        uploadingImageId.value = null;
    }
};

// Intersection Observer for infinite scroll
onMounted(() => {
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
</script>

<template>
  <div class="p-6">
    <!-- Header -->
    <header class="mb-6 flex justify-between items-center">
      <div class="flex items-center gap-4">
          <h1 class="text-2xl font-bold text-gray-900">Товары</h1>
          <div v-if="selectedProductIds.size > 0" class="flex items-center gap-2 bg-teal-50 px-4 py-2 rounded-lg border border-teal-100">
              <span class="text-sm font-medium text-teal-800">{{ selectedProductIds.size }} выбрано</span>
              <button @click="openBulkImageModal" class="flex items-center gap-1 bg-slate-700 text-white px-3 py-1.5 rounded-md text-sm hover:bg-slate-800 transition-colors">
                  <Images class="w-3.5 h-3.5" /> Изображения
              </button>
              <button @click="openBulkUpdate" class="flex items-center gap-1 bg-teal-600 text-white px-3 py-1.5 rounded-md text-sm hover:bg-teal-700 transition-colors">
                  <Edit3 class="w-3.5 h-3.5" /> Характеристики
              </button>
              <button @click="selectedProductIds.clear()" class="text-xs text-teal-600 hover:text-teal-800 underline ml-1">Сбросить</button>
          </div>
      </div>
      <div class="flex gap-2">
          <button @click="toggleSelectAll" class="px-3 py-2 bg-white border border-gray-200 rounded-lg hover:bg-gray-50 flex items-center gap-2 text-gray-700 text-sm transition-colors">
              <CheckSquare v-if="allSelected" class="w-4 h-4 text-teal-600" />
              <Square v-else class="w-4 h-4 text-gray-400" />
              Выбрать все
          </button>
          <button @click="showCleanupModal = true" class="px-3 py-2 bg-red-50 text-red-600 rounded-lg hover:bg-red-100 text-sm transition-colors">
              Очистка медиа
          </button>
          <button @click="loadProducts" class="p-2 bg-white rounded-lg border border-gray-200 shadow-sm hover:bg-gray-50 transition-colors">
              <RefreshCw class="w-4 h-4 text-gray-600" />
          </button>
      </div>
    </header>

    <!-- Filters -->
    <div class="bg-white p-4 rounded-xl shadow-sm border border-gray-200 mb-6 flex flex-wrap gap-4 items-end">
        <div class="flex-1 min-w-[200px]">
            <label class="block text-xs font-medium text-gray-500 mb-1">Поиск по модели</label>
            <div class="relative">
                <Search class="w-4 h-4 text-gray-400 absolute left-3 top-1/2 -translate-y-1/2" />
                <input 
                    v-model="searchQuery" 
                    @keyup.enter="applyFilters"
                    placeholder="Например: ARTCOOL..." 
                    class="w-full pl-9 pr-4 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-teal-500 focus:border-transparent outline-none"
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
                    class="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-teal-500 outline-none"
                 />
                 <span class="text-gray-400">-</span>
                 <input 
                    v-model.number="areaMax"
                    type="number" 
                    placeholder="До" 
                    class="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-teal-500 outline-none"
                 />
             </div>
        </div>

        <div class="flex items-center gap-2 pb-2">
            <label class="flex items-center gap-2 cursor-pointer bg-gray-50 px-3 py-2 rounded-lg border border-gray-200 hover:bg-gray-100 transition-colors select-none">
                <input type="checkbox" v-model="isInverter" class="w-4 h-4 text-teal-600 rounded focus:ring-teal-500" />
                <span class="text-sm text-gray-700">Только инвертор</span>
            </label>
        </div>

        <button 
            @click="applyFilters"
            class="px-6 py-2 bg-teal-600 text-white rounded-lg hover:bg-teal-700 font-medium text-sm transition-colors shadow-sm"
        >
            Применить
        </button>
    </div>
    
    <!-- Product Grid -->
    <div v-if="loading" class="text-center py-20 text-gray-500">Загрузка...</div>
    
    <div v-else>
      <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-5 gap-5">
        <div v-for="product in products" :key="product.id" 
             class="bg-white rounded-xl shadow-sm overflow-hidden group border-2 transition-all hover:shadow-md relative"
             :class="selectedProductIds.has(product.id) ? 'border-teal-500 ring-2 ring-teal-100' : 'border-transparent'"
        >
             <!-- Selection Checkbox Overlay -->
             <div class="absolute top-2.5 left-2.5 z-10">
                 <button @click.stop="toggleSelection(product.id)" class="bg-white/90 backdrop-blur-sm rounded-md shadow-sm hover:bg-white p-1 transition-colors">
                     <CheckSquare v-if="selectedProductIds.has(product.id)" class="w-5 h-5 text-teal-600" />
                     <Square v-else class="w-5 h-5 text-gray-400" />
                 </button>
             </div>
            <div class="aspect-video bg-gray-100 relative">
                <img v-if="product.main_image" :src="getImageUrl(product.main_image)" class="w-full h-full object-cover" />
                <div v-else class="w-full h-full flex items-center justify-center text-gray-300">
                    <Package class="w-10 h-10" />
                </div>
                
                <!-- Overlay Actions -->
                <div class="absolute inset-0 bg-black/50 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center">
                    <button @click="openSearchModal(product)" class="bg-teal-600 text-white px-4 py-2 rounded-full flex items-center gap-2 hover:bg-teal-700 text-sm font-medium transition-colors">
                        <Search class="w-4 h-4" /> Управление
                    </button>
                </div>
            </div>
            <div class="p-3.5">
                <h3 class="font-medium text-gray-900 text-sm truncate" :title="product.title">{{ product.title }}</h3>
                <p class="text-teal-700 font-semibold text-sm mt-0.5">{{ product.price }} руб.</p>
                <!-- Mini Gallery Preview -->
                <div class="flex gap-1 mt-2 overflow-hidden h-7" v-if="product.gallery_images && product.gallery_images.length">
                    <img v-for="img in product.gallery_images.slice(0, 6)" :key="img.id" :src="getImageUrl(img.url)" class="w-7 h-7 object-cover rounded" />
                    <span v-if="product.gallery_images.length > 6" class="w-7 h-7 bg-gray-100 rounded flex items-center justify-center text-[10px] text-gray-500">+{{ product.gallery_images.length - 6 }}</span>
                </div>
            </div>
        </div>
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
                                       <button @click="addToGallery(r.image)" class="w-full bg-slate-600 text-white text-xs py-1.5 rounded-md hover:bg-slate-700 transition-colors">
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
</template>
