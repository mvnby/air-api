<script setup>
import { ref, onMounted, computed } from 'vue';
import ProductCard from './ProductCard.vue';
import { getCatalog } from '../utils/api';

const props = defineProps({
  initialProducts: {
    type: Array,
    default: () => []
  },
  initialMeta: {
    type: Object,
    default: () => ({ total: 0, page: 1, limit: 12, pages: 1 })
  }
});

const products = ref(props.initialProducts);
const meta = ref(props.initialMeta);
const loading = ref(false);
const activeTags = ref([]);

// --- URL & State Management ---

const getParamsFromUrl = () => {
    if (typeof window === 'undefined') return {};
    const sp = new URLSearchParams(window.location.search);
    const params = {};
    const tags = [];
    
    // Parse tag_slugs properly (comma separated or multiple keys)
    sp.getAll('tag_slugs').forEach(val => {
        val.split(',').forEach(t => {
            if (t.trim()) tags.push(t.trim());
        });
    });
    
    params.tag_slugs = tags;
    params.page = sp.get('page') || 1;
    params.sort = sp.get('sort') || 'newest';
    return params;
};

// Update activeTags from URL
const syncStateFromUrl = () => {
    const params = getParamsFromUrl();
    activeTags.value = params.tag_slugs || [];
};

const fetchProducts = async () => {
    loading.value = true;
    try {
        const params = getParamsFromUrl();
        
        // Ensure 'wall' logic (replicated from catalog.astro)
        // If we are filtering, we assume Wall unless specified otherwise?
        // Let's keep it simple: Just pass what's in URL.
        // But if URL is empty, we must add 'wall' to match default view?
        // Actually, if URL is empty, activeTags is empty.
        // The API call needs 'wall' if no specific type is requested.
        // Let's add 'wall' to the API params if not present, but NOT to the URL (to keep URL clean).
        
        const apiTags = [...(params.tag_slugs || [])];
        if (!apiTags.includes('wall')) {
             apiTags.push('wall');
        }

        const apiParams = {
            tag_slugs: apiTags,
            page: params.page,
            limit: 12,
            sort: params.sort
        };

        const data = await getCatalog(apiParams);
        products.value = data.items || [];
        meta.value = data.meta || { total: 0, page: 1, limit: 12, pages: 1 };
    } catch (e) {
        console.error("Fetch error", e);
    } finally {
        loading.value = false;
    }
};

const updateUrlAndFetch = () => {
    const sp = new URLSearchParams(window.location.search);
    
    // Update tag_slugs
    sp.delete('tag_slugs');
    if (activeTags.value.length > 0) {
        sp.set('tag_slugs', activeTags.value.join(','));
    }
    
    // Reset page on filter change? Yes usually.
    // But if we are just called from toggle, we should reset page.
    // We'll reset page in toggle functions.
    
    const newUrl = `${window.location.pathname}?${sp.toString()}`;
    window.history.pushState({}, '', newUrl);
    fetchProducts();
};

// --- Filter Actions ---

const isTagActive = (slug) => activeTags.value.includes(slug);

const toggleTag = (slug) => {
    if (activeTags.value.includes(slug)) {
        activeTags.value = activeTags.value.filter(t => t !== slug);
    } else {
        activeTags.value.push(slug);
    }
    // Reset page to 1
    const sp = new URLSearchParams(window.location.search);
    sp.set('page', '1');
    const newUrl = `${window.location.pathname}?${sp.toString()}`;
    window.history.replaceState({}, '', newUrl); // update temp URL before main update
    
    updateUrlAndFetch();
};

const toggleMultiTags = (slugs) => {
    // Check if ALL provided slugs are active. If so, deactivate all.
    // Otherwise, activate all (or missing ones).
    const allActive = slugs.every(s => activeTags.value.includes(s));
    
    if (allActive) {
        activeTags.value = activeTags.value.filter(t => !slugs.includes(t));
    } else {
        slugs.forEach(s => {
            if (!activeTags.value.includes(s)) activeTags.value.push(s);
        });
    }
     // Reset page to 1
    const sp = new URLSearchParams(window.location.search);
    sp.set('page', '1');
    const newUrl = `${window.location.pathname}?${sp.toString()}`;
    window.history.replaceState({}, '', newUrl);

    updateUrlAndFetch();
};

const goToPage = (p) => {
    const sp = new URLSearchParams(window.location.search);
    sp.set('page', p);
    const newUrl = `${window.location.pathname}?${sp.toString()}`;
    window.history.pushState({}, '', newUrl);
    fetchProducts();
    window.scrollTo({ top: 0, behavior: 'smooth' });
};

onMounted(() => {
    if (window.location.search) {
        syncStateFromUrl();
        fetchProducts();
    }
});

// Computed active states for complex buttons
const isHeatingActive = computed(() => {
    return activeTags.value.includes('winter-25') || activeTags.value.includes('winter-30');
});

</script>

<template>
  <div>
    <!-- Filters Bar -->
    <div class="filters-bar">
        <!-- Inverter -->
        <button 
            class="filter-btn" 
            :class="{ active: isTagActive('inverter') }"
            @click="toggleTag('inverter')"
        >
            <span class="material-icons-round icon">equalizer</span>
            Инвертор
        </button>

        <!-- Area 25m -->
        <button 
            class="filter-btn" 
            :class="{ active: isTagActive('area-25') }"
            @click="toggleTag('area-25')"
        >
            <span class="material-icons-round icon">straighten</span>
            До 25 кв.м
        </button>

        <!-- Calculator Link -->
        <a 
            href="/kak-vybrat-konditsioner"
            class="filter-btn"
            style="border-color: var(--primary); color: var(--primary);"
        >
            <span class="material-icons-round icon">calculate</span>
            Подбор
        </a>

        <!-- Heating -25/-30 -->
        <button 
            class="filter-btn" 
            :class="{ active: isHeatingActive }"
            @click="toggleMultiTags(['winter-25', 'winter-30'])"
        >
            <span class="material-icons-round icon">ac_unit</span>
            Обогрев в мороз
        </button>

        <!-- WiFi -->
        <button 
            class="filter-btn" 
            :class="{ active: isTagActive('wifi-builtin') }"
            @click="toggleTag('wifi-builtin')"
        >
            <span class="material-icons-round icon">wifi</span>
            Wi-Fi модуль
        </button>

        <!-- Quiet -->
        <button 
            class="filter-btn" 
            :class="{ active: isTagActive('noise-silent') }"
            @click="toggleTag('noise-silent')"
        >
            <span class="material-icons-round icon">volume_off</span>
            Тихий режим
        </button>
    </div>

    <!-- Grid -->
    <div v-if="loading" class="loading-state">
        <span class="material-icons-round spin">refresh</span>
        Загрузка...
    </div>
    
    <div v-else-if="products.length > 0" class="products-area">
        <div class="grid">
             <ProductCard 
                v-for="product in products" 
                :key="product.id" 
                :product="product" 
                :showInstallation="true"
             />
        </div>
    </div>
    
    <div v-else class="empty-status card">
        <span class="material-icons-round large">search_off</span>
        <h3>Товары не найдены</h3>
        <p>Попробуйте изменить параметры поиска.</p>
    </div>

    <!-- Pagination -->
    <div v-if="meta.pages > 1 && !loading" class="pagination">
        <button 
            v-for="p in meta.pages" 
            :key="p"
            @click="goToPage(p)"
            class="page-link"
            :class="{ active: Number(meta.page) === p }"
        >
            {{ p }}
        </button>
    </div>
  </div>
</template>

<style scoped>
    /* Filters Bar */
    .filters-bar {
        display: flex;
        align-items: center;
        gap: 1rem;
        margin-bottom: 2rem;
        overflow-x: auto;
        padding-bottom: 0.5rem;
        scrollbar-width: thin;
    }

    .filter-btn {
        display: inline-flex;
        align-items: center;
        gap: 0.5rem;
        padding: 0.6rem 1.25rem;
        background: var(--surface);
        border: 1px solid var(--border);
        border-radius: 99px;
        font-weight: 600;
        font-size: 0.95rem;
        color: var(--text);
        white-space: nowrap;
        transition: all 0.2s;
        cursor: pointer;
        text-decoration: none;
        font-family: inherit;
    }

    .filter-btn:hover {
        border-color: var(--primary);
        color: var(--primary);
        background: rgba(0, 127, 128, 0.05);
    }

    .filter-btn.active {
        background: var(--primary);
        color: white;
        border-color: var(--primary);
    }

    .icon {
        font-size: 1.2rem;
    }

    /* Grid */
    .products-area {
        width: 100%;
    }

    .grid {
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
        gap: 2rem;
    }
    
    .loading-state {
        text-align: center;
        padding: 4rem;
        color: var(--text-muted);
        font-size: 1.2rem;
        display: flex;
        flex-direction: column;
        align-items: center;
        gap: 1rem;
    }
    .spin {
        animation: spin 1s linear infinite;
        font-size: 2rem;
    }
    @keyframes spin { 100% { -webkit-transform: rotate(360deg); transform:rotate(360deg); } }

    .empty-status {
        text-align: center;
        padding: 5rem;
        display: flex;
        flex-direction: column;
        align-items: center;
        gap: 1rem;
    }
    .large {
        font-size: 4rem;
        color: var(--text-muted);
        opacity: 0.5;
    }

    .pagination {
        display: flex;
        justify-content: center;
        gap: 0.75rem;
        margin-top: 5rem;
    }
    .page-link {
        width: 48px;
        height: 48px;
        display: flex;
        align-items: center;
        justify-content: center;
        border-radius: 12px;
        background: var(--surface);
        border: 1px solid var(--border);
        font-weight: 700;
        transition: all 0.2s;
        cursor: pointer;
        font-family: inherit;
        font-size: 1rem;
    }
    .page-link:hover {
        border-color: var(--primary);
        color: var(--primary);
        transform: translateY(-2px);
    }
    .page-link.active {
        background: var(--primary);
        color: white;
        border-color: var(--primary);
        box-shadow: 0 10px 15px -3px rgba(0, 127, 128, 0.3);
    }
    
    @media (max-width: 768px) {
        .filters-bar {
            padding-bottom: 1rem;
        }
    }
</style>
