<script setup lang="ts">
import { ref, onMounted, watch } from 'vue';
import { api, type Product } from './api';
import { Search, RefreshCw, UploadCloud } from 'lucide-vue-next';

// ... (state refs) ...
const products = ref<Product[]>([]);
const loading = ref(false);
const showModal = ref(false);
const selectedProduct = ref<Product | null>(null);
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

// Auth state
const isAuthenticated = ref(false);
const showLoginModal = ref(false);
const loginUsername = ref('');
const loginPassword = ref('');
const loginLoading = ref(false);
const loginError = ref('');

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
    if (!selectedProduct.value) return;
    searchLoading.value = true;
    try {
        const res = await api.uploadLocalImages(selectedProduct.value.id, files);
        alert(`Uploaded ${res.uploaded} images`);
        await loadProducts();
        refreshSelectedProduct();
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
  }
});

const handleLogin = async () => {
    loginLoading.value = true;
    loginError.value = '';
    try {
        await api.login(loginUsername.value, loginPassword.value);
        isAuthenticated.value = true;
        showLoginModal.value = false;
        await loadProducts();
    } catch (e) {
        loginError.value = 'Invalid credentials';
    } finally {
        loginLoading.value = false;
    }
};

const checkAuth = async () => {
    try {
        await api.checkAuth();
        isAuthenticated.value = true;
        // After auth confirmed, load data
        loadProducts();
    } catch (e) {
        isAuthenticated.value = false;
        showLoginModal.value = true;
    }
};

const loadProducts = async () => {
  loading.value = true;
  try {
    const data = await api.getProducts(100);
    // Handle { items: [...], meta: ... } response
    products.value = data.items ? data.items : (Array.isArray(data) ? data : []);
  } catch (e) {
    console.error(e);
  } finally {
    loading.value = false;
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
  console.log('openSearchModal', product);
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

const addToGallery = async (url: string) => {
    if (!selectedProduct.value) return;
    uploadingImageId.value = url;
    try {
        await api.linkSearchResult(selectedProduct.value.id, url);
        await loadProducts();
        refreshSelectedProduct();
        alert('Added to gallery');
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
    if (!selectedProduct.value) return;
    try {
        await api.reuseImage(selectedProduct.value.id, sourceUrl);
        alert('Image reused');
        await loadProducts();
        refreshSelectedProduct();
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

const removeFromGallery = async (id: number) => {
    if (confirmDeleteId.value !== id) {
        confirmDeleteId.value = id;
        setTimeout(() => { if(confirmDeleteId.value === id) confirmDeleteId.value = null; }, 3000); // Reset after 3s
        return;
    }
    
    confirmDeleteId.value = null;
    try {
        await api.deleteGalleryImage(id);
        await loadProducts();
        refreshSelectedProduct();
    } catch (e) { alert('Failed'); }
};

// ... existing selectImage ...

// In template:
// Change max-h-[90vh] to h-[90vh]
// Change h-full to flex-1 min-h-0


const selectImage = async (url: string) => {
    if (!selectedProduct.value || uploadingImageId.value) return;
    
    uploadingImageId.value = url; 
    
    try {
        const response = await api.uploadImage(selectedProduct.value.id, url);
        if (response && response.url) {
             await loadProducts();
             refreshSelectedProduct();
             showModal.value = false;
        } else {
             alert('Upload succeeded but no URL returned');
        }
    } catch (e) {
        alert('Upload failed');
    } finally {
        uploadingImageId.value = null;
    }
};

onMounted(() => {
  checkAuth();
});
</script>

<template>
  <!-- Login Modal -->
  <div v-if="showLoginModal" class="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
    <div class="bg-white rounded-xl p-8 max-w-md w-full mx-4">
      <h2 class="text-2xl font-bold mb-6 text-center">Manager Login</h2>
      <form @submit.prevent="handleLogin" class="space-y-4">
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">Username</label>
          <input 
            v-model="loginUsername" 
            type="text" 
            required
            class="w-full border rounded px-4 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
            placeholder="Enter username"
          />
        </div>
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">Password</label>
          <input 
            v-model="loginPassword" 
            type="password" 
            required
            class="w-full border rounded px-4 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
            placeholder="Enter password"
          />
        </div>
        <div v-if="loginError" class="text-red-600 text-sm">{{ loginError }}</div>
        <button 
          type="submit" 
          :disabled="loginLoading"
          class="w-full bg-blue-600 text-white py-2 rounded hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {{ loginLoading ? 'Logging in...' : 'Login' }}
        </button>
      </form>
    </div>
  </div>

  <div class="min-h-screen bg-gray-50 p-8">
    <div class="max-w-7xl mx-auto">
      <header class="mb-8 flex justify-between items-center">
        <h1 class="text-3xl font-bold text-gray-900">Manager Dashboard</h1>
        <div class="flex gap-2">
            <button @click="showCleanupModal = true" class="px-4 py-2 bg-red-100 text-red-700 rounded hover:bg-red-200">
                Cleanup Media
            </button>
            <button @click="loadProducts" class="p-2 bg-white rounded shadow hover:bg-gray-100">
                <RefreshCw class="w-5 h-5" />
            </button>
        </div>
      </header>
      
      <!-- Product Grid -->
      <div v-if="loading" class="text-center py-20">Loading...</div>
      
      <div v-else class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
        <div v-for="product in products" :key="product.id" class="bg-white rounded-lg shadow overflow-hidden group">
            <div class="aspect-video bg-gray-200 relative">
                <img v-if="product.main_image" :src="getImageUrl(product.main_image)" class="w-full h-full object-cover" />
                <div v-else class="w-full h-full flex items-center justify-center text-gray-400">
                    No Image
                </div>
                
                <!-- Overlay Actions -->
                <div class="absolute inset-0 bg-black/50 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center">
                    <button @click="openSearchModal(product)" class="bg-blue-600 text-white px-4 py-2 rounded-full flex items-center gap-2 hover:bg-blue-700">
                        <Search class="w-4 h-4" /> Manage Images
                    </button>
                </div>
            </div>
            <div class="p-4">
                <h3 class="font-medium text-gray-900 truncate" :title="product.title">{{ product.title }}</h3>
                <p class="text-gray-500">{{ product.price }} rub.</p>
                <!-- Mini Gallery Preview -->
                <div class="flex gap-1 mt-2 overflow-hidden h-8" v-if="product.gallery_images && product.gallery_images.length">
                    <img v-for="img in product.gallery_images" :src="getImageUrl(img.url)" class="w-8 h-8 object-cover rounded" />
                </div>
            </div>
        </div>
      </div>
    </div>
    
    <!-- Cleanup Modal -->
    <div v-if="showCleanupModal" class="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
        <div class="bg-white rounded-xl p-6 max-w-lg w-full">
            <h2 class="text-xl font-bold mb-4">Cleanup Unused Media</h2>
            <p class="mb-4 text-gray-600">This will scan for files not referenced in the database and delete them.</p>
            
            <div v-if="cleanupStats" class="bg-gray-100 p-4 rounded mb-4 text-sm">
                <p>Deleted: {{ cleanupStats.deleted_count }} files</p>
                <p>Reclaimed: {{ (cleanupStats.reclaimed_bytes / 1024 / 1024).toFixed(2) }} MB</p>
                <ul class="mt-2 list-disc list-inside text-gray-500 h-32 overflow-y-auto">
                    <li v-for="f in cleanupStats.files" :key="f">{{ f }}</li>
                </ul>
            </div>
            
            <div class="flex justify-end gap-2">
                <button @click="showCleanupModal = false" class="px-4 py-2 text-gray-500">Close</button>
                <button @click="triggerCleanup" :disabled="cleanupLoading" class="px-4 py-2 bg-red-600 text-white rounded hover:bg-red-700 disabled:opacity-50">
                    {{ cleanupLoading ? 'Cleaning...' : 'Run Cleanup' }}
                </button>
            </div>
        </div>
    </div>
    
    <!-- Search / Manage Modal -->
    <div v-if="showModal" class="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4" @click.self="showModal = false">
        <div class="bg-white rounded-xl w-full max-w-6xl h-[90vh] flex flex-col">
            <!-- Tabs -->
            <div class="flex border-b bg-gray-50 rounded-t-xl">
                 <button 
                    @click="activeTab = 'search'" 
                    class="px-6 py-3 font-medium border-b-2"
                    :class="activeTab === 'search' ? 'border-blue-600 text-blue-600' : 'border-transparent text-gray-500'"
                 >Search Images</button>
                 <button 
                    @click="activeTab = 'reuse'" 
                    class="px-6 py-3 font-medium border-b-2"
                    :class="activeTab === 'reuse' ? 'border-blue-600 text-blue-600' : 'border-transparent text-gray-500'"
                 >Reuse from Catalog</button>
                 <button 
                    @click="activeTab = 'upload'" 
                    class="px-6 py-3 font-medium border-b-2"
                    :class="activeTab === 'upload' ? 'border-blue-600 text-blue-600' : 'border-transparent text-gray-500'"
                 >Upload Image</button>
                 <div class="flex-1 flex justify-end items-center px-4">
                     <button @click="showModal = false" class="text-gray-500 hover:text-gray-700">Close</button>
                 </div>
            </div>

            <!-- Tab Content -->
            <div class="flex-1 overflow-hidden flex flex-col min-h-0">
                <!-- SEARCH TAB -->
                <div v-if="activeTab === 'search'" class="flex flex-col flex-1 min-h-0">
                     <div class="p-4 border-b flex gap-4 bg-white">
                        <input v-model="imageQuery" @keyup.enter="handleImageSearch" class="flex-1 border rounded px-4 py-2" placeholder="Search query..." />
                        <button @click="handleImageSearch" class="bg-blue-600 text-white px-6 rounded hover:bg-blue-700">Search</button>
                    </div>
                    
                    <div class="flex-1 overflow-y-auto p-4 bg-gray-100">
                        <div v-if="searchLoading" class="text-center py-10">Searching DuckDuckGo...</div>
                        <div v-else class="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-5 gap-4">
                             <!-- Search Results -->
                             <div v-for="(r, idx) in imageSearchResults" :key="idx" class="group relative bg-white rounded shadow hover:shadow-lg transition-all">
                                <div class="aspect-square bg-gray-200 relative overflow-hidden">
                                     <img :src="r.thumbnail || r.image" class="w-full h-full object-contain p-2" loading="lazy" />
                                     <!-- Hover Actions -->
                                     <div class="absolute inset-0 bg-black/60 opacity-0 group-hover:opacity-100 transition-opacity flex flex-col items-center justify-center gap-2 p-2">
                                         <button @click="selectImage(r.image)" class="w-full bg-blue-600 text-white text-xs py-1 rounded hover:bg-blue-700">
                                             Set as MAIN
                                         </button>
                                         <button @click="addToGallery(r.image)" class="w-full bg-slate-600 text-white text-xs py-1 rounded hover:bg-slate-700">
                                             Add to Gallery
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
                        <input v-model="reuseQuery" @keyup.enter="handleReuseSearch" class="flex-1 border rounded px-4 py-2" placeholder="Search product model (e.g. Forest 09)..." />
                        <button @click="handleReuseSearch" class="bg-blue-600 text-white px-6 rounded hover:bg-blue-700">Find</button>
                    </div>
                    <div class="flex-1 overflow-y-auto p-4 bg-gray-100">
                        <div class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
                            <div v-for="p in reuseResults" :key="p.id" class="bg-white rounded shadow overflow-hidden group">
                                <div class="aspect-video bg-gray-200 relative">
                                    <img v-if="p.main_image" :src="getImageUrl(p.main_image)" class="w-full h-full object-cover" />
                                    <div v-else class="w-full h-full flex items-center justify-center text-gray-400 text-xs">No Image</div>
                                    
                                     <div class="absolute inset-0 bg-black/40 opacity-0 group-hover:opacity-100 flex items-center justify-center">
                                         <button @click="reuseImage(p.main_image)" class="text-white text-sm bg-blue-600 px-3 py-2 rounded">Copy Image</button>
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
                        :class="uploadDragActive ? 'border-blue-500 bg-blue-50' : 'border-gray-300 hover:border-gray-400 bg-white'"
                        @dragenter.prevent="uploadDragActive = true"
                        @dragleave.prevent="uploadDragActive = false"
                        @dragover.prevent
                        @drop.prevent="handleDrop"
                        @click="fileInput?.click()"
                    >
                        <input type="file" ref="fileInput" multiple accept="image/*" class="hidden" @change="handleFileSelect" />
                        <UploadCloud class="w-16 h-16 text-gray-400 mb-4" :class="{ 'text-blue-500': uploadDragActive }" />
                        <h3 class="text-xl font-medium text-gray-700 mb-2">
                            {{ uploadDragActive ? 'Drop files here' : 'Drag & Drop images here' }}
                        </h3>
                        <p class="text-gray-500 mb-6">or click to browse local files</p>
                        
                        <div v-if="searchLoading" class="flex items-center gap-2 text-blue-600 font-medium">
                            <div class="w-4 h-4 border-2 border-blue-600 border-t-transparent rounded-full animate-spin"></div>
                            Uploading...
                        </div>
                    </div>
                </div>
            </div>
            
            <!-- Current Product Gallery Preview (Footer) -->
            <div class="h-48 bg-white border-t p-4 overflow-x-auto flex gap-4 shrink-0">
                <div class="w-64 shrink-0 flex items-center justify-center text-gray-400 border-r pr-4">
                    Current Gallery
                </div>
                 <!-- Main Image -->
                 <div v-if="selectedProduct?.main_image" class="relative group w-32 shrink-0 border-2 border-green-500 rounded overflow-hidden">
                    <img :src="getImageUrl(selectedProduct.main_image)" class="w-full h-full object-cover" />
                    <span class="absolute top-0 left-0 bg-green-500 text-white text-[10px] px-1">MAIN</span>
                 </div>
                 
                 <!-- Gallery Items -->
                 <div v-if="selectedProduct?.gallery_images" v-for="img in selectedProduct.gallery_images.filter(i => !i.is_installation_photo)" :key="img.id" class="relative group w-32 shrink-0 border rounded overflow-hidden">
                    <img :src="getImageUrl(img.url)" class="w-full h-full object-cover" />
                    <!-- Actions -->
                    <div class="absolute inset-0 bg-black/50 opacity-0 group-hover:opacity-100 flex flex-col items-center justify-center gap-1 p-2">
                         <button @click="setAsMain(img.id)" class="text-[10px] bg-white text-black px-2 py-1 rounded hover:bg-gray-200 w-full">Make Main</button>
                         <button 
                            @click="removeFromGallery(img.id)" 
                            class="text-[10px] text-white px-2 py-1 rounded w-full transition-colors"
                            :class="confirmDeleteId === img.id ? 'bg-red-800 font-bold' : 'bg-red-600 hover:bg-red-700'"
                         >
                            {{ confirmDeleteId === img.id ? 'Confirm?' : 'Delete' }}
                         </button>
                    </div>
                 </div>
            </div>
        </div>
    </div>
  </div>
</template>
