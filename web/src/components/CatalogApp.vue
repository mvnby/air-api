<script setup>
import { computed, onMounted, ref } from 'vue';
import ProductCard from './ProductCard.vue';
import { getCatalog, getFiltersConfig } from '../utils/api';
import { getBrandConfig } from '../utils/brands';

const BASE_LIMIT = 20;
const CATEGORY_TABS = [
  { slug: 'cat-household', title: 'Бытовые' },
  { slug: 'cat-multi', title: 'Мульти-сплит' },
  { slug: 'cat-industrial', title: 'Полупромышленные' },
];
const POWER_PRESETS = [
  { key: 'area-20', title: 'до 20 м²', min: null, max: 20 },
  { key: 'area-25', title: 'до 25 м²', min: null, max: 25 },
  { key: 'area-35', title: 'до 35 м²', min: null, max: 35 },
  { key: 'area-50', title: 'до 50 м²', min: null, max: 50 },
  { key: 'area-70', title: 'до 70 м²', min: null, max: 70 },
];
const INDUSTRIAL_TYPE_OPTIONS = [
  { value: 'duct', title: 'Канальные' },
  { value: 'cassette', title: 'Кассетные' },
  { value: 'floor_ceiling', title: 'Напольно-потолочные' },
  { value: 'column', title: 'Колонные' },
];
const CATEGORY_SLUGS = new Set(CATEGORY_TABS.map((tab) => tab.slug));

const props = defineProps({
  initialProducts: {
    type: Array,
    default: () => []
  },
  initialMeta: {
    type: Object,
    default: () => ({ total: 0, page: 1, limit: BASE_LIMIT, pages: 1 })
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

const products = ref(props.initialProducts || []);
const meta = ref(props.initialMeta || { total: 0, page: 1, limit: BASE_LIMIT, pages: 1 });

const loadingInitial = ref(false);
const loadingMore = ref(false);
const loadingBrands = ref(false);

const activeTags = ref([]);
const searchQuery = ref('');
const sort = ref('newest');
const mobileSearchOpen = ref(false);
const advancedFiltersOpen = ref(false);

const currentAreaMin = ref(null);
const currentAreaMax = ref(null);
const currentIsInverter = ref(null);
const currentHasWifi = ref(null);
const currentHasFreshAir = ref(null);
const currentHeatingMin = ref(null);
const currentIndoorTypes = ref([]);

const availableBrands = ref([]);
let searchDebounceTimeout = null;

const lockedFilters = computed(() => props.lockedInitialFilters || null);
const knownBrandSlugs = computed(() => new Set(availableBrands.value.map((brand) => brand.slug)));
const activeCategorySlug = computed(() => activeTags.value.find((slug) => CATEGORY_SLUGS.has(slug)) || null);
const activeBrandSlug = computed(() => activeTags.value.find((slug) => knownBrandSlugs.value.has(slug)) || null);
const isHouseholdCategory = computed(() => activeCategorySlug.value === 'cat-household');
const isIndustrialCategory = computed(() => activeCategorySlug.value === 'cat-industrial');

const activePowerPresetKey = computed(() => {
  const min = currentAreaMin.value === null || currentAreaMin.value === undefined || currentAreaMin.value === ''
    ? null
    : Number(currentAreaMin.value);
  const max = currentAreaMax.value === null || currentAreaMax.value === undefined || currentAreaMax.value === ''
    ? null
    : Number(currentAreaMax.value);
  const found = POWER_PRESETS.find((preset) => preset.min === min && preset.max === max);
  return found?.key || null;
});

const hasActiveAdvancedFilters = computed(() => (
  sort.value !== 'newest'
  || currentIsInverter.value !== null
  || currentHasWifi.value !== null
  || currentHasFreshAir.value !== null
  || currentHeatingMin.value !== null
));

const pageTitle = computed(() => {
  if (props.forcedTitle) return props.forcedTitle;
  if (activeCategorySlug.value === 'cat-multi') return 'Мульти-сплит системы';
  if (activeCategorySlug.value === 'cat-industrial') return 'Полупромышленные кондиционеры';
  return 'Бытовые кондиционеры';
});

const pageDescription = computed(() => {
  if (props.forcedDescription) return props.forcedDescription;
  if (activeCategorySlug.value === 'cat-multi') {
    return 'Системы с одним наружным блоком и несколькими внутренними для гибкого зонирования.';
  }
  if (activeCategorySlug.value === 'cat-industrial') {
    return 'Кассетные, канальные и напольно-потолочные решения для коммерческих и сложных объектов.';
  }
  return 'Настенные сплит-системы для квартиры и дома с удобной фильтрацией по брендам.';
});

const semiGuideUrl = '/blog/polupromyshlennye-kondicionery-tipy-i-vybor';

const hasMore = computed(() => {
  const currentPage = Number(meta.value?.page || 1);
  const totalPages = Number(meta.value?.pages || 1);
  return currentPage < totalPages;
});

const getParamsFromUrl = () => {
  if (typeof window === 'undefined') return null;
  const sp = new URLSearchParams(window.location.search);

  const tags = [];
  sp.getAll('tag_slugs').forEach((value) => {
    value.split(',').forEach((tag) => {
      const clean = tag.trim();
      if (clean) tags.push(clean);
    });
  });

  return {
    page: Number.parseInt(sp.get('page') || '1', 10) || 1,
    sort: sp.get('sort') || 'newest',
    q: sp.get('q') || '',
    tag_slugs: tags,
    area_min: sp.get('area_min') || null,
    area_max: sp.get('area_max') || null,
    is_inverter: sp.get('is_inverter') === 'true'
      ? true
      : sp.get('is_inverter') === 'false'
        ? false
        : null,
    has_wifi: sp.get('has_wifi') === 'true'
      ? true
      : sp.get('has_wifi') === 'false'
        ? false
        : null,
    has_fresh_air: sp.get('has_fresh_air') === 'true'
      ? true
      : sp.get('has_fresh_air') === 'false'
        ? false
        : null,
    indoor_types: sp.getAll('indoor_types').flatMap((value) => value.split(',')).map((v) => v.trim()).filter(Boolean),
    heating_min: sp.get('heating_min') || null,
  };
};

const applyLockedFilters = (params) => {
  if (!lockedFilters.value) return params;

  const merged = { ...params };
  const lockedTagSlugs = Array.isArray(lockedFilters.value.tag_slugs)
    ? lockedFilters.value.tag_slugs
    : [];

  merged.tag_slugs = [...new Set([...(params.tag_slugs || []), ...lockedTagSlugs])];

  const scalarKeys = [
    'area_min',
    'area_max',
    'is_inverter',
    'has_wifi',
    'has_fresh_air',
    'heating_min',
    'sort',
  ];

  scalarKeys.forEach((key) => {
    if (lockedFilters.value[key] !== undefined && lockedFilters.value[key] !== null) {
      merged[key] = lockedFilters.value[key];
    }
  });

  return merged;
};

const syncStateFromUrl = () => {
  const params = getParamsFromUrl();
  if (!params) return;

  activeTags.value = [...params.tag_slugs];
  searchQuery.value = params.q;
  sort.value = params.sort;

  currentAreaMin.value = params.area_min;
  currentAreaMax.value = params.area_max;
  currentIsInverter.value = params.is_inverter;
  currentHasWifi.value = params.has_wifi;
  currentHasFreshAir.value = params.has_fresh_air;
  currentIndoorTypes.value = [...params.indoor_types];
  currentHeatingMin.value = params.heating_min;

  if (!activeTags.value.some((slug) => CATEGORY_SLUGS.has(slug))) {
    const lockedCategory = (Array.isArray(lockedFilters.value?.tag_slugs)
      ? lockedFilters.value.tag_slugs
      : []
    ).find((slug) => CATEGORY_SLUGS.has(slug));

    activeTags.value.push(lockedCategory || 'cat-household');
  }
};

const buildApiParams = (page = 1) => {
  const base = {
    page,
    limit: BASE_LIMIT,
    sort: sort.value,
    tag_slugs: [...activeTags.value],
    q: searchQuery.value.trim() || undefined,
    area_min: currentAreaMin.value || undefined,
    area_max: currentAreaMax.value || undefined,
    is_inverter: currentIsInverter.value,
    has_wifi: currentHasWifi.value,
    has_fresh_air: currentHasFreshAir.value,
    indoor_types: isIndustrialCategory.value ? [...currentIndoorTypes.value] : undefined,
    heating_min: currentHeatingMin.value || undefined,
  };

  return applyLockedFilters(base);
};

const syncUrlFromState = (page = 1, { replace = false } = {}) => {
  if (typeof window === 'undefined') return;

  const params = buildApiParams(page);
  const sp = new URLSearchParams();

  if (params.tag_slugs && params.tag_slugs.length > 0) {
    sp.set('tag_slugs', params.tag_slugs.join(','));
  }
  if (page > 1) sp.set('page', String(page));
  if (params.sort && params.sort !== 'newest') sp.set('sort', params.sort);
  if (params.q) sp.set('q', params.q);

  if (params.area_min !== undefined) sp.set('area_min', String(params.area_min));
  if (params.area_max !== undefined) sp.set('area_max', String(params.area_max));
  if (params.is_inverter !== null && params.is_inverter !== undefined) sp.set('is_inverter', String(params.is_inverter));
  if (params.has_wifi !== null && params.has_wifi !== undefined) sp.set('has_wifi', String(params.has_wifi));
  if (params.has_fresh_air !== null && params.has_fresh_air !== undefined) sp.set('has_fresh_air', String(params.has_fresh_air));
  if (params.indoor_types && params.indoor_types.length > 0) {
    params.indoor_types.forEach((value) => sp.append('indoor_types', value));
  }
  if (params.heating_min !== undefined) sp.set('heating_min', String(params.heating_min));

  const query = sp.toString();
  const newUrl = query ? `${window.location.pathname}?${query}` : window.location.pathname;
  if (replace) {
    window.history.replaceState({}, '', newUrl);
  } else {
    window.history.pushState({}, '', newUrl);
  }
};

const fetchProducts = async ({ page = 1, append = false } = {}) => {
  if (append) {
    loadingMore.value = true;
  } else {
    loadingInitial.value = true;
  }

  try {
    const apiParams = buildApiParams(page);
    const data = await getCatalog(apiParams);

    const incomingItems = data.items || [];
    if (append) {
      const seen = new Set(products.value.map((item) => item.id));
      const merged = [...products.value];
      incomingItems.forEach((item) => {
        if (!seen.has(item.id)) {
          merged.push(item);
          seen.add(item.id);
        }
      });
      products.value = merged;
    } else {
      products.value = incomingItems;
    }

    meta.value = data.meta || { total: 0, page: 1, limit: BASE_LIMIT, pages: 1 };
  } catch (error) {
    console.error('Fetch catalog failed', error);
  } finally {
    loadingInitial.value = false;
    loadingMore.value = false;
  }
};

const updateBrandsFallbackFromProducts = () => {
  if (availableBrands.value.length > 0) return;

  const acc = new Map();
  products.value.forEach((product) => {
    const brandTag = (product.tags || []).find((tag) =>
      (tag.group?.slug === 'brand' || tag.group_slug === 'brand') && tag.slug
    );
    if (!brandTag) return;

    if (!acc.has(brandTag.slug)) {
      acc.set(brandTag.slug, {
        slug: brandTag.slug,
        title: brandTag.title,
        sort_order: brandTag.sort_order ?? 999,
      });
    }
  });

  availableBrands.value = [...acc.values()].sort((a, b) => {
    if ((a.sort_order ?? 999) !== (b.sort_order ?? 999)) {
      return (a.sort_order ?? 999) - (b.sort_order ?? 999);
    }
    return (a.title || '').localeCompare(b.title || '');
  });
};

const loadBrands = async () => {
  loadingBrands.value = true;
  try {
    const filters = await getFiltersConfig();
    availableBrands.value = (filters?.brands || []).map((brand) => ({
      ...brand,
      sort_order: brand.sort_order ?? 999,
    }));
  } catch (error) {
    console.error('Failed to load brands', error);
  } finally {
    loadingBrands.value = false;
    updateBrandsFallbackFromProducts();
  }
};

const setCategory = async (categorySlug) => {
  activeTags.value = activeTags.value.filter((slug) => !CATEGORY_SLUGS.has(slug));
  activeTags.value.push(categorySlug);
  if (categorySlug !== 'cat-household') {
    currentAreaMin.value = null;
    currentAreaMax.value = null;
  }
  if (categorySlug !== 'cat-industrial') {
    currentIndoorTypes.value = [];
  }

  syncUrlFromState(1);
  await fetchProducts({ page: 1, append: false });
};

const toggleIndustrialType = async (value) => {
  if (!isIndustrialCategory.value) return;
  const set = new Set(currentIndoorTypes.value);
  if (set.has(value)) {
    set.delete(value);
  } else {
    set.add(value);
  }
  currentIndoorTypes.value = [...set];
  syncUrlFromState(1);
  await fetchProducts({ page: 1, append: false });
};

const clearIndustrialTypes = async () => {
  currentIndoorTypes.value = [];
  syncUrlFromState(1);
  await fetchProducts({ page: 1, append: false });
};

const toggleBrand = async (brandSlug) => {
  const brandSet = knownBrandSlugs.value;
  if (brandSlug === '__all__') {
    activeTags.value = activeTags.value.filter((slug) => !brandSet.has(slug));
    syncUrlFromState(1);
    await fetchProducts({ page: 1, append: false });
    return;
  }

  const isActive = activeBrandSlug.value === brandSlug;

  activeTags.value = activeTags.value.filter((slug) => !brandSet.has(slug));
  if (!isActive) {
    activeTags.value.push(brandSlug);
  }

  syncUrlFromState(1);
  await fetchProducts({ page: 1, append: false });
};

const loadMore = async () => {
  if (!hasMore.value || loadingMore.value) return;
  const nextPage = Number(meta.value?.page || 1) + 1;
  syncUrlFromState(nextPage);
  await fetchProducts({ page: nextPage, append: true });
};

const setPowerPreset = async (preset) => {
  if (activePowerPresetKey.value === preset.key) {
    currentAreaMin.value = null;
    currentAreaMax.value = null;
  } else {
    currentAreaMin.value = preset.min;
    currentAreaMax.value = preset.max;
  }

  syncUrlFromState(1);
  await fetchProducts({ page: 1, append: false });
};

const toggleBooleanFilter = async (key, value) => {
  const map = {
    is_inverter: currentIsInverter,
    has_wifi: currentHasWifi,
    has_fresh_air: currentHasFreshAir,
  };
  const target = map[key];
  if (!target) return;

  target.value = target.value === value ? null : value;
  syncUrlFromState(1);
  await fetchProducts({ page: 1, append: false });
};

const setHeatingMin = async (value) => {
  currentHeatingMin.value = currentHeatingMin.value === value ? null : value;
  syncUrlFromState(1);
  await fetchProducts({ page: 1, append: false });
};

const resetAdvancedFilters = async () => {
  sort.value = 'newest';
  currentIsInverter.value = null;
  currentHasWifi.value = null;
  currentHasFreshAir.value = null;
  currentIndoorTypes.value = [];
  currentHeatingMin.value = null;
  if (!isHouseholdCategory.value) {
    currentAreaMin.value = null;
    currentAreaMax.value = null;
  }
  syncUrlFromState(1);
  await fetchProducts({ page: 1, append: false });
};

const onSortChange = async () => {
  syncUrlFromState(1);
  await fetchProducts({ page: 1, append: false });
};

const onSearchInput = () => {
  if (searchDebounceTimeout) clearTimeout(searchDebounceTimeout);
  searchDebounceTimeout = setTimeout(async () => {
    syncUrlFromState(1, { replace: true });
    await fetchProducts({ page: 1, append: false });
  }, 450);
};

onMounted(async () => {
  syncStateFromUrl();
  await loadBrands();

  const currentMetaLimit = Number(props.initialMeta?.limit || BASE_LIMIT);
  const urlPage = Number(getParamsFromUrl()?.page || 1);

  if (!props.initialProducts?.length || currentMetaLimit !== BASE_LIMIT || urlPage > 1) {
    await fetchProducts({ page: Math.max(1, urlPage), append: false });
  }
});
</script>

<template>
  <div class="catalog-shell">
    <header class="catalog-header">
      <div class="header-top">
        <div class="breadcrumb">
          <a href="/">Главная</a>
          <span class="sep">/</span>
          <span>Каталог</span>
        </div>

        <div class="search-input-wrapper header-search catalog-desktop-only">
          <span class="material-icons-round search-icon">search</span>
          <input
            v-model="searchQuery"
            type="text"
            class="search-input"
            placeholder="Поиск по модели, бренду, характеристике"
            @input="onSearchInput"
          />
        </div>

        <button
          class="search-toggle catalog-mobile-only"
          :class="{ active: mobileSearchOpen }"
          @click="mobileSearchOpen = !mobileSearchOpen"
          aria-label="Открыть поиск"
          type="button"
        >
          <span class="material-icons-round">{{ mobileSearchOpen ? 'close' : 'search' }}</span>
        </button>
      </div>

      <div v-if="mobileSearchOpen" class="search-input-wrapper header-search catalog-mobile-only mobile-search">
        <span class="material-icons-round search-icon">search</span>
        <input
          v-model="searchQuery"
          type="text"
          class="search-input"
          placeholder="Поиск по модели, бренду, характеристике"
          @input="onSearchInput"
        />
      </div>

      <h1 class="gradient-text">{{ pageTitle }}</h1>
      <p class="header-description">{{ pageDescription }}</p>
      <a
        v-if="isIndustrialCategory"
        :href="semiGuideUrl"
        class="semi-guide-link"
      >
        Как выбрать тип полупромышленного кондиционера
      </a>
    </header>

    <section class="glass-panel category-panel">
      <div class="section-label">Категория</div>
      <div class="category-tabs">
        <button
          v-for="tab in CATEGORY_TABS"
          :key="tab.slug"
          class="category-tab"
          :class="{ active: activeCategorySlug === tab.slug }"
          @click="setCategory(tab.slug)"
        >
          {{ tab.title }}
        </button>
      </div>
    </section>

    <section class="glass-panel brand-panel">
      <div class="section-head">
        <div class="section-label">Бренд</div>
        <div v-if="loadingBrands" class="label-hint">Обновляем список...</div>
      </div>
      <div class="brand-strip">
        <button
          class="brand-pill"
          :class="{ active: activeBrandSlug === null }"
          @click="toggleBrand('__all__')"
        >
          Все бренды
        </button>

        <button
          v-for="brand in availableBrands"
          :key="brand.slug"
          class="brand-pill"
          :class="{ active: activeBrandSlug === brand.slug }"
          @click="toggleBrand(brand.slug)"
        >
          <img
            v-if="getBrandConfig(brand.slug).logo"
            :src="getBrandConfig(brand.slug).logo"
            :alt="brand.title"
            class="brand-pill-logo"
          />
          <span>{{ brand.title }}</span>
        </button>
      </div>
    </section>

    <section v-if="isHouseholdCategory" class="glass-panel quick-power-panel">
      <div class="section-label">Мощность</div>
      <div class="quick-chip-row">
        <button
          class="quick-chip"
          :class="{ active: activePowerPresetKey === null }"
          @click="setPowerPreset({ key: '__all__', min: null, max: null })"
        >
          Любая
        </button>
        <button
          v-for="preset in POWER_PRESETS"
          :key="preset.key"
          class="quick-chip"
          :class="{ active: activePowerPresetKey === preset.key }"
          @click="setPowerPreset(preset)"
        >
          {{ preset.title }}
        </button>
      </div>
    </section>

    <section v-if="isIndustrialCategory" class="glass-panel quick-power-panel">
      <div class="section-label">Тип внутреннего блока</div>
      <div class="quick-chip-row">
        <button
          class="quick-chip"
          :class="{ active: currentIndoorTypes.length === 0 }"
          @click="clearIndustrialTypes"
        >
          Все типы
        </button>
        <button
          v-for="item in INDUSTRIAL_TYPE_OPTIONS"
          :key="item.value"
          class="quick-chip"
          :class="{ active: currentIndoorTypes.includes(item.value) }"
          @click="toggleIndustrialType(item.value)"
        >
          {{ item.title }}
        </button>
      </div>
    </section>

    <section class="filters-toolbar">
      <button class="filters-toggle-btn" type="button" @click="advancedFiltersOpen = !advancedFiltersOpen">
        <span class="material-icons-round">tune</span>
        <span>{{ advancedFiltersOpen ? 'Скрыть фильтры' : 'Фильтры' }}</span>
      </button>
      <button
        v-if="hasActiveAdvancedFilters"
        type="button"
        class="filters-reset-btn"
        @click="resetAdvancedFilters"
      >
        Сбросить
      </button>
    </section>

    <transition name="fade-up">
      <section v-if="advancedFiltersOpen" class="glass-panel advanced-panel">
        <div class="advanced-row">
          <label class="control-label" for="catalog-sort">Сортировка</label>
          <select id="catalog-sort" v-model="sort" class="filters-select" @change="onSortChange">
            <option value="newest">Сначала новые</option>
            <option value="price_asc">Сначала дешевле</option>
            <option value="price_desc">Сначала дороже</option>
          </select>
        </div>

        <div class="advanced-row">
          <div class="control-label">Тип компрессора</div>
          <div class="quick-chip-row">
            <button
              class="quick-chip"
              :class="{ active: currentIsInverter === true }"
              @click="toggleBooleanFilter('is_inverter', true)"
            >
              Инвертор
            </button>
            <button
              class="quick-chip"
              :class="{ active: currentIsInverter === false }"
              @click="toggleBooleanFilter('is_inverter', false)"
            >
              On/Off
            </button>
          </div>
        </div>

        <div class="advanced-row">
          <div class="control-label">Дополнительно</div>
          <div class="quick-chip-row">
            <button
              class="quick-chip"
              :class="{ active: currentHasWifi === true }"
              @click="toggleBooleanFilter('has_wifi', true)"
            >
              Wi-Fi
            </button>
            <button
              class="quick-chip"
              :class="{ active: currentHasFreshAir === true }"
              @click="toggleBooleanFilter('has_fresh_air', true)"
            >
              Приток воздуха
            </button>
          </div>
        </div>

        <div class="advanced-row">
          <div class="control-label">Обогрев</div>
          <div class="quick-chip-row">
            <button class="quick-chip" :class="{ active: currentHeatingMin === '-15' }" @click="setHeatingMin('-15')">
              до -15°C
            </button>
            <button class="quick-chip" :class="{ active: currentHeatingMin === '-20' }" @click="setHeatingMin('-20')">
              до -20°C
            </button>
            <button class="quick-chip" :class="{ active: currentHeatingMin === '-25' }" @click="setHeatingMin('-25')">
              до -25°C
            </button>
            <button class="quick-chip" :class="{ active: currentHeatingMin === '-30' }" @click="setHeatingMin('-30')">
              до -30°C
            </button>
          </div>
        </div>
      </section>
    </transition>

    <div v-if="loadingInitial" class="grid skeleton-grid">
      <div v-for="i in 8" :key="`skeleton-${i}`" class="skeleton-card" />
    </div>

    <div v-else-if="products.length > 0" class="catalog-content">
      <transition-group name="fade-up" tag="div" class="grid">
        <ProductCard
          v-for="product in products"
          :key="product.id"
          :product="product"
          :showInstallation="true"
        />
      </transition-group>

      <div v-if="loadingMore" class="grid skeleton-grid skeleton-grid-more">
        <div v-for="i in 4" :key="`skeleton-more-${i}`" class="skeleton-card" />
      </div>

      <div v-if="hasMore" class="load-more-wrap">
        <button class="load-more-btn" :disabled="loadingMore" @click="loadMore">
          {{ loadingMore ? 'Загружаем...' : 'Показать еще' }}
        </button>
      </div>
    </div>

    <div v-else class="empty-status card">
      <span class="material-icons-round large">search_off</span>
      <h3>Товары не найдены</h3>
      <p>Попробуйте выбрать другой бренд или категорию.</p>
    </div>
  </div>
</template>

<style scoped>
.catalog-header {
  margin-bottom: 1.5rem;
}

.header-top {
  display: flex;
  align-items: center;
  gap: 0.9rem;
  margin-bottom: 1rem;
}

.breadcrumb {
  font-size: 0.9rem;
  color: var(--text-muted);
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-weight: 500;
  min-width: 0;
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

.catalog-desktop-only {
  display: flex !important;
}

.catalog-mobile-only {
  display: none !important;
}

.header-search {
  width: min(620px, 58vw);
  margin-left: auto;
}

.search-toggle {
  width: 42px;
  height: 42px;
  border-radius: 12px;
  border: 1px solid var(--panel-chip-border);
  background: var(--panel-pill-bg);
  color: var(--text);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: border-color 0.2s ease, transform 0.2s ease;
}

.search-toggle.active {
  border-color: rgba(0, 127, 128, 0.8);
}

.mobile-search {
  width: 100%;
  margin-bottom: 0.85rem;
}

.catalog-header h1 {
  font-size: clamp(2rem, 4vw, 2.7rem);
  margin: 0 0 0.5rem;
  line-height: 1.12;
}

.header-description {
  max-width: 760px;
  color: var(--text-muted);
  margin: 0;
}

.semi-guide-link {
  display: inline-flex;
  margin-top: 0.7rem;
  font-size: 0.92rem;
  font-weight: 700;
  color: var(--primary);
  text-decoration: none;
}

.semi-guide-link:hover {
  text-decoration: underline;
}

.glass-panel {
  background: var(--panel-glass-bg);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  border: 1px solid var(--panel-glass-border);
  border-radius: 18px;
  box-shadow: var(--panel-glass-shadow);
  padding: 1rem;
  margin-bottom: 1rem;
}

.section-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 1rem;
}

.section-label {
  font-size: 0.8rem;
  font-weight: 800;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--text-muted);
  margin-bottom: 0.75rem;
}

.label-hint {
  font-size: 0.8rem;
  color: var(--text-muted);
}

.category-tabs {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 0.65rem;
}

.category-tab {
  border: 1px solid var(--panel-chip-border);
  background: var(--panel-chip-bg);
  color: var(--text);
  border-radius: 14px;
  padding: 0.82rem 1rem;
  font-size: 0.92rem;
  font-weight: 700;
  cursor: pointer;
  transition: transform 0.2s ease, box-shadow 0.2s ease, border-color 0.2s ease;
}

.category-tab:hover {
  transform: translateY(-1px);
  border-color: var(--panel-chip-hover-border);
}

.category-tab.active {
  color: var(--panel-active-text);
  border-color: transparent;
  background: var(--panel-active-gradient);
  box-shadow: 0 12px 25px -18px rgba(10, 102, 89, 0.9);
}

.brand-strip {
  display: flex;
  gap: 0.6rem;
  overflow-x: auto;
  padding-bottom: 0.25rem;
  scrollbar-width: thin;
}

.brand-pill {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  border: 1px solid var(--panel-chip-border);
  background: var(--panel-pill-bg);
  border-radius: 999px;
  padding: 0.52rem 0.95rem;
  font-size: 0.9rem;
  font-weight: 600;
  color: var(--text);
  cursor: pointer;
  white-space: nowrap;
  transition: all 0.2s ease;
}

.brand-pill:hover {
  border-color: var(--panel-chip-hover-border);
  transform: translateY(-1px);
}

.brand-pill.active {
  color: var(--panel-active-text);
  border-color: transparent;
  background: var(--panel-active-gradient-alt);
  box-shadow: 0 10px 24px -16px rgba(18, 90, 145, 0.85);
}

.brand-pill-logo {
  width: 22px;
  height: 22px;
  object-fit: contain;
  display: block;
}

.search-container {
  margin: 1rem 0 1.6rem;
  max-width: 680px;
}

.search-input-wrapper {
  position: relative;
  display: flex;
  align-items: center;
}

.search-icon {
  position: absolute;
  left: 0.9rem;
  color: var(--text-muted);
}

.search-input {
  width: 100%;
  border: 1px solid var(--panel-input-border);
  border-radius: 14px;
  background: var(--panel-input-bg);
  color: var(--text);
  font-size: 0.96rem;
  padding: 0.8rem 1rem 0.8rem 2.85rem;
  transition: box-shadow 0.2s ease, border-color 0.2s ease;
  font-family: inherit;
}

.search-input::placeholder {
  color: var(--text-muted);
}

.search-input:focus {
  outline: none;
  border-color: rgba(0, 127, 128, 0.65);
  box-shadow: 0 0 0 4px rgba(0, 127, 128, 0.12);
}

.quick-power-panel {
  margin-top: -0.1rem;
}

.quick-chip-row {
  display: flex;
  gap: 0.55rem;
  flex-wrap: wrap;
}

.quick-chip {
  border: 1px solid var(--panel-chip-border);
  background: var(--panel-chip-bg);
  color: var(--text);
  border-radius: 999px;
  padding: 0.48rem 0.9rem;
  font-size: 0.88rem;
  font-weight: 700;
  cursor: pointer;
  transition: transform 0.18s ease, border-color 0.2s ease, background 0.2s ease;
}

.quick-chip:hover {
  transform: translateY(-1px);
  border-color: var(--panel-chip-hover-border);
}

.quick-chip.active {
  color: var(--panel-active-text);
  border-color: transparent;
  background: var(--panel-active-gradient-alt);
}

.filters-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  margin: 0.3rem 0 1rem;
}

.filters-toggle-btn,
.filters-reset-btn {
  border: 1px solid var(--panel-chip-border);
  background: var(--panel-pill-bg);
  color: var(--text);
  border-radius: 999px;
  padding: 0.52rem 0.92rem;
  font-size: 0.88rem;
  font-weight: 700;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
}

.filters-reset-btn {
  color: var(--text-muted);
}

.advanced-panel {
  margin-top: -0.2rem;
}

.advanced-row {
  display: flex;
  flex-direction: column;
  gap: 0.55rem;
}

.advanced-row + .advanced-row {
  margin-top: 0.9rem;
}

.control-label {
  font-size: 0.78rem;
  font-weight: 800;
  letter-spacing: 0.06em;
  color: var(--text-muted);
  text-transform: uppercase;
}

.filters-select {
  width: 100%;
  max-width: 280px;
  border: 1px solid var(--panel-input-border);
  border-radius: 12px;
  background: var(--panel-input-bg);
  color: var(--text);
  font-size: 0.9rem;
  padding: 0.6rem 0.7rem;
}

.catalog-content {
  display: flex;
  flex-direction: column;
  gap: 1.4rem;
}

.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 1.3rem;
}

.skeleton-grid {
  margin-top: 0.2rem;
}

.skeleton-grid-more {
  margin-top: 0.8rem;
}

.skeleton-card {
  border-radius: 14px;
  min-height: 390px;
  background: var(--panel-skeleton);
  background-size: 220% 100%;
  animation: shimmer 1.25s infinite linear;
}

@keyframes shimmer {
  to {
    background-position-x: -220%;
  }
}

.load-more-wrap {
  display: flex;
  justify-content: center;
  margin-top: 0.4rem;
}

.load-more-btn {
  border: none;
  border-radius: 999px;
  padding: 0.82rem 1.5rem;
  font-size: 0.95rem;
  font-weight: 700;
  color: var(--panel-active-text);
  background: var(--panel-active-gradient);
  box-shadow: 0 14px 28px -20px rgba(17, 122, 142, 1);
  cursor: pointer;
  transition: transform 0.2s ease, opacity 0.2s ease;
}

.load-more-btn:hover {
  transform: translateY(-1px);
}

.load-more-btn:disabled {
  cursor: not-allowed;
  opacity: 0.7;
}

.fade-up-enter-active,
.fade-up-leave-active {
  transition: all 0.26s ease;
}

.fade-up-enter-from,
.fade-up-leave-to {
  opacity: 0;
  transform: translateY(8px);
}

.empty-status {
  text-align: center;
  padding: 4rem 1rem;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.75rem;
}

.large {
  font-size: 4rem;
  color: var(--text-muted);
  opacity: 0.55;
}

@media (max-width: 980px) {
  .category-tabs {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 768px) {
  .header-top {
    align-items: center;
    margin-bottom: 0.8rem;
  }

  .catalog-desktop-only {
    display: none !important;
  }

  .catalog-mobile-only {
    display: flex !important;
  }

  .breadcrumb {
    font-size: 0.85rem;
    gap: 0.4rem;
    margin-right: auto;
  }

  .glass-panel {
    border-radius: 16px;
    padding: 0.9rem;
  }

  .brand-pill {
    padding: 0.5rem 0.84rem;
  }

  .grid {
    grid-template-columns: 1fr;
  }

  .filters-toolbar {
    margin-top: 0;
  }
}
</style>
