<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { api, type Product } from './api';
import { Search, RefreshCw } from 'lucide-vue-next';

const products = ref<Product[]>([]);
const loading = ref(false);
const showModal = ref(false);
const selectedProduct = ref<Product | null>(null);
const imageSearchResults = ref<string[]>([]);
const searchLoading = ref(false);
const imageQuery = ref('');

const loadProducts = async () => {
  loading.value = true;
  try {
    const data = await api.getProducts(100);
    products.value = data.items || data; // Adjust based on API structure
  } catch (e) {
    console.error(e);
  } finally {
    loading.value = false;
  }
};

const openSearchModal = (product: Product) => {
  console.log('openSearchModal', product);
  selectedProduct.value = product;
  imageQuery.value = product.title;
  imageSearchResults.value = [];
  showModal.value = true;
  console.log('showModal set to true');
  handleImageSearch(); // Auto search
};

const handleImageSearch = async () => {
    console.log('handleImageSearch called', imageQuery.value);
    if (!imageQuery.value) return;
    searchLoading.value = true;
    try {
        console.log('Calling api.searchImages...');
        const results = await api.searchImages(imageQuery.value);
        console.log('Results:', results);
        imageSearchResults.value = results;
    } catch (e) {
        console.error('Search failed', e);
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

const selectImage = async (url: string) => {
    if (!selectedProduct.value || uploadingImageId.value) return;
    
    uploadingImageId.value = url; // Lock interactions for this image
    
    try {
        const response = await api.uploadImage(selectedProduct.value.id, url);
        // Assuming response contains { url: string, id: number }
        if (response && response.url) {
             // Update local state immediately
             const productIndex = products.value.findIndex(p => p.id === selectedProduct.value?.id);
             if (productIndex !== -1 && products.value[productIndex]) {
                 products.value[productIndex].main_image = response.url;
             }
             if (selectedProduct.value) {
                 selectedProduct.value.main_image = response.url;
             }
             showModal.value = false;
        } else {
             alert('Upload succeeded but no URL returned');
        }
    } catch (e) {
        alert('Upload failed');
    } finally {
        uploadingImageId.value = null; // Unlock
    }
};

onMounted(() => {
  loadProducts();
});
</script>

<template>
  <div class="min-h-screen bg-gray-50 p-8">
    <div class="max-w-7xl mx-auto">
      <header class="mb-8 flex justify-between items-center">
        <h1 class="text-3xl font-bold text-gray-900">Manager Dashboard</h1>
        <button @click="loadProducts" class="p-2 bg-white rounded shadow hover:bg-gray-100">
            <RefreshCw class="w-5 h-5" />
        </button>
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
                        <Search class="w-4 h-4" /> Find Image
                    </button>
                </div>
            </div>
            <div class="p-4">
                <h3 class="font-medium text-gray-900 truncate" :title="product.title">{{ product.title }}</h3>
                <p class="text-gray-500">{{ product.price }} rub.</p>
            </div>
        </div>
      </div>
    </div>
    
    <!-- Search Modal -->
    <div v-if="showModal" class="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4" @click.self="showModal = false">
        <div class="bg-white rounded-xl w-full max-w-4xl max-h-[90vh] flex flex-col">
            <div class="p-4 border-b flex gap-4">
                <input v-model="imageQuery" @keyup.enter="handleImageSearch" class="flex-1 border rounded px-4 py-2" placeholder="Search query..." />
                <button @click="handleImageSearch" class="bg-blue-600 text-white px-6 rounded hover:bg-blue-700">Search</button>
                <button @click="showModal = false" class="text-gray-500 hover:text-gray-700">Close</button>
            </div>
            
            <div class="flex-1 overflow-y-auto p-4 bg-gray-100">
                <div v-if="searchLoading" class="text-center py-10">Searching DuckDuckGo...</div>
                <div v-else class="grid grid-cols-2 md:grid-cols-4 gap-4">
                    <div v-for="url in imageSearchResults" :key="url" class="group aspect-square bg-gray-200 rounded overflow-hidden relative cursor-pointer" @click.prevent="selectImage(url)">
                        <img :src="url" class="w-full h-full object-cover hover:scale-105 transition-transform" loading="lazy" :class="{'opacity-50': uploadingImageId && uploadingImageId !== url}" />
                        
                        <!-- Hover Overlay -->
                        <div v-if="!uploadingImageId" class="absolute inset-0 bg-black/0 group-hover:bg-black/20 transition-colors"></div>
                        
                        <!-- Loading Overlay -->
                        <div v-if="uploadingImageId === url" class="absolute inset-0 bg-black/50 flex items-center justify-center">
                            <RefreshCw class="w-8 h-8 text-white animate-spin" />
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>
  </div>
</template>
