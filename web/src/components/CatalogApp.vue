<script setup>
import { ref, onMounted, computed } from 'vue';
import ProductCard from './ProductCard.vue';
import { getCatalog } from '../utils/api';
import { getBrandConfig } from '../utils/brands';

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
    params.area_min = sp.get('area_min') || null;
    params.area_max = sp.get('area_max') || null;
    return params;
};

const currentAreaMin = ref(null);
const currentAreaMax = ref(null);

// Update activeTags and Area from URL
const syncStateFromUrl = () => {
    const params = getParamsFromUrl();
    activeTags.value = params.tag_slugs || [];
    
    // Only update area if they are present in URL, otherwise keep current (to support defaults)
    if (params.area_min || params.area_max) {
        currentAreaMin.value = params.area_min;
        currentAreaMax.value = params.area_max;
    } else if (params.tag_slugs.length === 0) {
        // If NO filters at all, apply default
        currentAreaMin.value = null;
        currentAreaMax.value = '29';
    }
};

const fetchProducts = async () => {
    loading.value = true;
    try {
        const params = getParamsFromUrl();
        
        const apiTags = [...(params.tag_slugs || [])];
        if (!apiTags.includes('wall')) {
             apiTags.push('wall');
        }

        const apiParams = {
            tag_slugs: apiTags,
            page: params.page,
            limit: 100,
            sort: params.sort,
            area_min: params.area_min,
            area_max: params.area_max
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

    // Update area
    sp.delete('area_min');
    sp.delete('area_max');
    if (currentAreaMin.value) sp.set('area_min', currentAreaMin.value);
    if (currentAreaMax.value) sp.set('area_max', currentAreaMax.value);
    
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

const setAreaFilter = (min, max) => {
    currentAreaMin.value = min;
    currentAreaMax.value = max;
    
    const sp = new URLSearchParams(window.location.search);
    sp.set('page', '1');
    const newUrl = `${window.location.pathname}?${sp.toString()}`;
    window.history.replaceState({}, '', newUrl);

    updateUrlAndFetch();
};

onMounted(() => {
    const sp = new URLSearchParams(window.location.search);
    const hasFilters = sp.has('tag_slugs') || sp.has('area_min') || sp.has('area_max') || sp.has('is_inverter');
    
    syncStateFromUrl();
    
    if (window.location.search && hasFilters) {
        fetchProducts();
    } else if (!hasFilters) {
        // If no filters, we already set the default in syncStateFromUrl.
        // But we might need to fetch if Astro didn't.
        // Actually, Astro SHOULD have fetched with area_max=29.
        // Let's verify by fetching if products are empty or if we want to be sure.
        // But to avoid double fetch on landing, we can skip it if initialProducts is present.
    }
});

// Computed active states for complex buttons
const isHeatingActive = computed(() => {
    return activeTags.value.includes('winter-25') || activeTags.value.includes('winter-30');
});

const isAreaActive = (min, max) => {
    return currentAreaMin.value == min && currentAreaMax.value == max;
};

const pageTitle = computed(() => {
    if (isAreaActive(null, '29')) return "Кондиционеры для небольших помещений (до 25 м²)";
    if (isAreaActive('30', '39')) return "Кондиционеры для средних помещений (до 35 м²)";
    if (isAreaActive('40', '59')) return "Кондиционеры для больших помещений (до 50 м²)";
    if (isAreaActive('60', null)) return "Мощные кондиционеры (от 60 м²)";
    return "Каталог кондиционеров в Витебске";
});

const pageDescription = computed(() => {
    if (isAreaActive(null, '29')) return "Тихие и энергоэффективные модели, идеально подходящие для спален и детских комнат.";
    if (isAreaActive('40', '59')) return "Производительные сплит-системы для просторных гостиных и офисов.";
    return "Современные системы кондиционирования для идеального климата в вашем доме и офисе.";
});

const groupedProducts = computed(() => {
    const groups = {};
    
    products.value.forEach(product => {
        // Find brand tag
        const brandTag = product.tags?.find(t => 
            t.group?.slug === 'brand' || t.group_slug === 'brand'
        );
        
        const brandName = brandTag ? brandTag.title : 'Другие бренды';
        const brandSlug = brandTag ? brandTag.slug : 'other';
        const brandSortOrder = brandTag ? (brandTag.sort_order ?? 999) : 1000;
        
        if (!groups[brandName]) {
            groups[brandName] = {
                brandName,
                brandSlug,
                brandSortOrder,
                config: getBrandConfig(brandSlug),
                items: []
            };
        }
        groups[brandName].items.push(product);
    });
    
    // Sort products inside each brand by price
    Object.values(groups).forEach(group => {
        group.items.sort((a, b) => (a.price || 0) - (b.price || 0));
    });
    
    // Sort brands by sort_order, then by name
    return Object.values(groups).sort((a, b) => {
        if (a.brandSortOrder !== b.brandSortOrder) {
            return a.brandSortOrder - b.brandSortOrder;
        }
        return a.brandName.localeCompare(b.brandName);
    });
});

</script>

<template>
  <div>
    <!-- Dynamic Header -->
    <header class="catalog-header">
        <div class="breadcrumb">
            <a href="/">Главная</a>
            <span class="sep">/</span>
            <span>Каталог</span>
        </div>
        <h1 class="gradient-text">{{ pageTitle }}</h1>
        <p style="max-width: 700px; color: var(--text-muted); min-height: 3em;">
            {{ pageDescription }}
        </p>
    </header>

    <!-- Area Selection (Primary Filter Row) -->
    <div class="area-filters">
        <div class="filter-label">Площадь помещения:</div>
        <div class="chips-row">
            <button 
                class="chip" 
                :class="{ active: isAreaActive(null, '29') }"
                @click="setAreaFilter(null, '29')"
            >
                До 25 м²
            </button>
            <button 
                class="chip" 
                :class="{ active: isAreaActive('30', '39') }"
                @click="setAreaFilter('30', '39')"
            >
                До 35 м²
            </button>
            <button 
                class="chip" 
                :class="{ active: isAreaActive('40', '59') }"
                @click="setAreaFilter('40', '59')"
            >
                До 50 м²
            </button>
            <button 
                class="chip" 
                :class="{ active: isAreaActive('60', null) }"
                @click="setAreaFilter('60', null)"
            >
                60+ м²
            </button>
            <button 
                class="chip" 
                :class="{ active: isAreaActive(null, null) }"
                @click="setAreaFilter(null, null)"
            >
                Все
            </button>
        </div>
    </div>

    <!-- Secondary Filters Bar -->
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

        <!-- Removed generic Area 25m as it's now in main row -->

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
    
    <div v-else-if="groupedProducts.length > 0" class="catalog-content">
        <section v-for="group in groupedProducts" :key="group.brandName" class="brand-section">
            <div class="brand-header-wrapper">
                <div class="brand-header-container">
                    <img 
                        v-if="group.config.logo" 
                        :src="group.config.logo" 
                        :alt="group.brandName"
                        class="brand-logo"
                    />
                    <h2 v-else class="brand-title" :class="group.config.color">
                        {{ group.brandName }}
                    </h2>
                </div>
            </div>
            <div class="grid">
                 <ProductCard 
                    v-for="product in group.items" 
                    :key="product.id" 
                    :product="product" 
                    :showInstallation="true"
                 />
            </div>
        </section>
    </div>
    
    <div v-else class="empty-status card">
        <span class="material-icons-round large">search_off</span>
        <h3>Товары не найдены</h3>
        <p>Попробуйте изменить параметры поиска.</p>
    </div>

  </div>
</template>

<style scoped>
    /* Catalog Header (moved from Astro) */
    .catalog-header {
        margin-bottom: 2rem;
    }
    .breadcrumb {
        font-size: 0.9rem;
        color: var(--text-muted);
        margin-bottom: 1rem;
        display: flex;
        align-items: center;
        gap: 0.5rem;
        font-weight: 500;
    }
    .breadcrumb a {
        color: inherit;
        text-decoration: none;
    }
    .breadcrumb a:hover {
        color: var(--primary);
    }
    .sep {
        opacity: 0.5;
    }
    .catalog-header h1 {
        font-size: 2.5rem;
        margin-bottom: 0.5rem;
        font-weight: 800;
        line-height: 1.1;
    }

    /* Area Filters */
    .area-filters {
        margin-bottom: 1.5rem;
    }
    .filter-label {
        font-size: 0.9rem;
        font-weight: 700;
        color: var(--text-muted);
        text-transform: uppercase;
        letter-spacing: 0.05em;
        margin-bottom: 0.75rem;
    }
    .chips-row {
        display: flex;
        flex-wrap: wrap;
        gap: 0.75rem;
    }
    .chip {
        padding: 0.5rem 1.25rem;
        border-radius: 12px;
        background: var(--surface);
        border: 2px solid var(--border);
        font-weight: 700;
        font-size: 0.95rem;
        cursor: pointer;
        transition: all 0.2s;
        color: var(--text);
        font-family: inherit;
    }
    .chip:hover {
        border-color: var(--primary);
        color: var(--primary);
    }
    .chip.active {
        background: var(--primary);
        color: white;
        border-color: var(--primary);
        box-shadow: 0 4px 12px rgba(0, 127, 128, 0.2);
    }

    /* Filters Bar */
    .filters-bar {
        display: flex;
        align-items: center;
        gap: 1rem;
        margin-bottom: 2.5rem;
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

    /* Grid & Catalog Content */
    .catalog-content {
        width: 100%;
        display: flex;
        flex-direction: column;
        gap: 4rem;
    }

    .brand-section {
        position: relative;
    }

    .brand-header-wrapper {
        position: sticky;
        top: 0;
        z-index: 10;
        background: rgba(255, 255, 255, 0.9);
        backdrop-filter: blur(10px);
        -webkit-backdrop-filter: blur(10px);
        border-bottom: 1px solid var(--border);
        margin: 2rem 0;
        transition: all 0.3s ease;
    }

    .brand-header-container {
        display: flex;
        align-items: center;
        padding: 1rem 0;
    }

    .brand-logo {
        height: 2.5rem;
        object-fit: contain;
        display: block;
    }

    .brand-title {
        font-size: 2rem;
        font-weight: 800;
        color: var(--text);
        margin: 0;
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
