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
  },
  forcedTitle: {
    type: String,
    default: ''
  },
  forcedDescription: {
    type: String,
    default: ''
  },
  lockedInitialFilters: {
    type: Object,
    default: null
  }
});

const products = ref(props.initialProducts);
const meta = ref(props.initialMeta);
const loading = ref(false);
const activeTags = ref([]);
const currentIsInverter = ref(null);
const currentHasWifi = ref(null);
const currentHasFreshAir = ref(null);
const currentHeatingMin = ref(null);
const searchQuery = ref('');
let searchDebounceTimeout = null;

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
    params.has_wifi = sp.get('has_wifi') === 'true'
      ? true
      : sp.get('has_wifi') === 'false'
        ? false
        : null;
    params.has_fresh_air = sp.get('has_fresh_air') === 'true'
      ? true
      : sp.get('has_fresh_air') === 'false'
        ? false
        : null;
    params.heating_min = sp.get('heating_min') || null;
    params.is_inverter = sp.get('is_inverter') === 'true'
      ? true
      : sp.get('is_inverter') === 'false'
        ? false
        : null;
    params.q = sp.get('q') || '';
    return params;
};

const currentAreaMin = ref(null);
const currentAreaMax = ref(null);
const lockedFilters = computed(() => props.lockedInitialFilters || null);

const applyLockedState = () => {
    if (!lockedFilters.value) return false;

    const lockedTags = Array.isArray(lockedFilters.value.tag_slugs)
        ? lockedFilters.value.tag_slugs
        : [];
    activeTags.value = [...lockedTags];
    currentAreaMin.value = lockedFilters.value.area_min != null ? String(lockedFilters.value.area_min) : null;
    currentAreaMax.value = lockedFilters.value.area_max != null ? String(lockedFilters.value.area_max) : null;
    currentIsInverter.value = typeof lockedFilters.value.is_inverter === 'boolean' ? lockedFilters.value.is_inverter : null;
    currentHasWifi.value = typeof lockedFilters.value.has_wifi === 'boolean' ? lockedFilters.value.has_wifi : null;
    currentHasFreshAir.value = typeof lockedFilters.value.has_fresh_air === 'boolean' ? lockedFilters.value.has_fresh_air : null;
    currentHeatingMin.value = lockedFilters.value.heating_min != null ? String(lockedFilters.value.heating_min) : null;
    return true;
};

// Update activeTags and Area from URL
const syncStateFromUrl = () => {
    const params = getParamsFromUrl();
    activeTags.value = params.tag_slugs || [];
    currentIsInverter.value = params.is_inverter;
    currentHasWifi.value = params.has_wifi;
    currentHasFreshAir.value = params.has_fresh_air;
    currentHeatingMin.value = params.heating_min;
    searchQuery.value = params.q || '';
    
    // Only update area if they are present in URL, otherwise keep current (to support defaults)
    if (params.area_min || params.area_max) {
        currentAreaMin.value = params.area_min;
        currentAreaMax.value = params.area_max;
    } else if (
        params.tag_slugs.length === 0 &&
        params.is_inverter === null &&
        params.has_wifi === null &&
        params.has_fresh_air === null &&
        params.heating_min === null &&
        !params.q
    ) {
        // If NO filters in URL, try preset state for virtual pages before fallback default.
        if (!applyLockedState()) {
            currentAreaMin.value = null;
            currentAreaMax.value = '29';
        }
    }
};

const fetchProducts = async () => {
    loading.value = true;
    try {
        const params = getParamsFromUrl();

        const apiParams = {
            tag_slugs: params.tag_slugs,
            page: params.page,
            limit: 100,
            sort: params.sort,
            area_min: params.area_min,
            area_max: params.area_max,
            is_inverter: params.is_inverter,
            has_wifi: params.has_wifi,
            has_fresh_air: params.has_fresh_air,
            heating_min: params.heating_min,
            q: params.q,
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

    // Update JSONB/column filters
    sp.delete('is_inverter');
    sp.delete('has_wifi');
    sp.delete('has_fresh_air');
    sp.delete('heating_min');
    if (currentIsInverter.value !== null) sp.set('is_inverter', String(currentIsInverter.value));
    if (currentHasWifi.value !== null) sp.set('has_wifi', String(currentHasWifi.value));
    if (currentHasFreshAir.value !== null) sp.set('has_fresh_air', String(currentHasFreshAir.value));
    if (currentHeatingMin.value !== null) sp.set('heating_min', String(currentHeatingMin.value));
    
    sp.delete('q');
    if (searchQuery.value.trim()) sp.set('q', searchQuery.value.trim());
    
    const newUrl = `${window.location.pathname}?${sp.toString()}`;
    window.history.pushState({}, '', newUrl);
    fetchProducts();
};

const onSearchInput = () => {
    // If user is typing, clear other filters
    if (searchQuery.value && searchQuery.value.trim().length > 0) {
        currentAreaMin.value = null;
        currentAreaMax.value = null;
        activeTags.value = [];
        currentIsInverter.value = null;
        currentHasWifi.value = null;
        currentHasFreshAir.value = null;
        currentHeatingMin.value = null;
    }

    if (searchDebounceTimeout) clearTimeout(searchDebounceTimeout);
    searchDebounceTimeout = setTimeout(() => {
        const currentSp = new URLSearchParams(window.location.search);
        currentSp.set('page', '1');
        const newUrl = `${window.location.pathname}?${currentSp.toString()}`;
        window.history.replaceState({}, '', newUrl);
        
        updateUrlAndFetch();
    }, 500);
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

const toggleBooleanFilter = (key) => {
    if (key === 'is_inverter') {
        currentIsInverter.value = currentIsInverter.value === true ? null : true;
    } else if (key === 'has_wifi') {
        currentHasWifi.value = currentHasWifi.value === true ? null : true;
    } else if (key === 'has_fresh_air') {
        currentHasFreshAir.value = currentHasFreshAir.value === true ? null : true;
    }

    const sp = new URLSearchParams(window.location.search);
    sp.set('page', '1');
    const newUrl = `${window.location.pathname}?${sp.toString()}`;
    window.history.replaceState({}, '', newUrl);
    updateUrlAndFetch();
};

const toggleHeatingFilter = () => {
    currentHeatingMin.value = currentHeatingMin.value ? null : '-20';
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
    const hasFilters = sp.has('tag_slugs') || sp.has('area_min') || sp.has('area_max') || sp.has('is_inverter') || sp.has('has_wifi') || sp.has('has_fresh_air') || sp.has('heating_min');
    
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
    return currentHeatingMin.value !== null;
});

const isInverterActive = computed(() => currentIsInverter.value === true);
const isWifiActive = computed(() => currentHasWifi.value === true);
const isFreshAirActive = computed(() => currentHasFreshAir.value === true);

const isAreaActive = (min, max) => {
    return currentAreaMin.value == min && currentAreaMax.value == max;
};

const pageTitle = computed(() => {
    if (props.forcedTitle) return props.forcedTitle;
    if (isAreaActive(null, '29')) return "Кондиционеры для небольших помещений (до 25 м²)";
    if (isAreaActive('30', '39')) return "Кондиционеры для средних помещений (до 35 м²)";
    if (isAreaActive('40', '59')) return "Кондиционеры для больших помещений (до 50 м²)";
    if (isAreaActive('60', null)) return "Мощные кондиционеры (от 60 м²)";
    return "Каталог кондиционеров в Витебске";
});

const pageDescription = computed(() => {
    if (props.forcedDescription) return props.forcedDescription;
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

    <!-- Search Bar -->
    <div class="search-container">
        <div class="search-input-wrapper">
             <span class="material-icons-round search-icon">search</span>
             <input 
                type="text" 
                v-model="searchQuery" 
                @input="onSearchInput"
                placeholder="Поиск (например: LG, инвертор, 25 м²)"
                class="search-input"
             />
             <button v-if="searchQuery" @click="searchQuery = ''; onSearchInput()" class="clear-search">
                <span class="material-icons-round">close</span>
             </button>
        </div>
    </div>

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
            :class="{ active: isInverterActive }"
            @click="toggleBooleanFilter('is_inverter')"
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
            @click="toggleHeatingFilter"
        >
            <span class="material-icons-round icon">ac_unit</span>
            Обогрев в мороз
        </button>

        <!-- WiFi -->
        <button 
            class="filter-btn" 
            :class="{ active: isWifiActive }"
            @click="toggleBooleanFilter('has_wifi')"
        >
            <span class="material-icons-round icon">wifi</span>
            Wi-Fi модуль
        </button>

        <!-- Fresh Air -->
        <button 
            class="filter-btn" 
            :class="{ active: isFreshAirActive }"
            @click="toggleBooleanFilter('has_fresh_air')"
        >
            <span class="material-icons-round icon">air</span>
            Приток свежего воздуха
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

    /* Search Bar Styles */
    .search-container {
        margin-bottom: 2rem;
        max-width: 600px;
    }
    .search-input-wrapper {
        position: relative;
        display: flex;
        align-items: center;
    }
    .search-input {
        width: 100%;
        padding: 0.8rem 1rem 0.8rem 2.8rem;
        border: 2px solid var(--border);
        border-radius: 12px;
        background: var(--surface);
        font-size: 1rem;
        transition: all 0.2s;
        font-family: inherit;
    }
    .search-input:focus {
        border-color: var(--primary);
        outline: none;
        box-shadow: 0 0 0 3px rgba(0, 127, 128, 0.1);
    }
    .search-icon {
        position: absolute;
        left: 0.8rem;
        color: var(--text-muted);
        pointer-events: none;
    }
    .clear-search {
        position: absolute;
        right: 0.5rem;
        background: none;
        border: none;
        color: var(--text-muted);
        cursor: pointer;
        padding: 0.2rem;
        display: flex;
        align-items: center;
        border-radius: 50%;
    }
    .clear-search:hover {
        background: rgba(0,0,0,0.05);
        color: var(--text);
    }
</style>
