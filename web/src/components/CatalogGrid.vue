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

// Helper to parse URL params
const getParamsFromUrl = () => {
  const sp = new URLSearchParams(window.location.search);
  const params = {};
  for (const [key, value] of sp.entries()) {
      if (key === 'tag_slugs') {
          // URLSearchParams might have multiple entries for same key, or comma separated
          // get() returns first. getAll returns all.
          // Our api.js builds it as tag_slugs=a&tag_slugs=b
          const all = sp.getAll('tag_slugs');
          // Start with parsing commas if any
          let slugs = [];
          all.forEach(s => slugs.push(...s.split(',')));
          params[key] = slugs;
      } else {
          params[key] = value;
      }
  }
  return params;
};

const fetchProducts = async () => {
  loading.value = true;
  try {
    const params = getParamsFromUrl();
    
    // Enforce logic from catalog.astro: Ensure 'wall' tag is present unless specific override?
    // Actually, let's just use what's in URL. But if URL is empty, we might want default.
    // However, initialProducts were fetched with 'wall'.
    // If I filter by 'area-25', I should verify if I need 'wall'.
    // The previous logic was: if (!tag_slugs.includes("wall")) tag_slugs.push("wall");
    // We replicate it here.
    
    let tags = params.tag_slugs || [];
    if (!Array.isArray(tags)) tags = [tags];
    
    if (!tags.includes('wall')) {
        tags.push('wall');
    }
    
    // Clean up params for API call
    const apiParams = {
        ...params,
        tag_slugs: tags,
        page: params.page || 1,
        limit: 12,
        sort: params.sort || 'newest'
    };
    
    // Remove legacy params if they exist in URL but handled via tags now
    // (Though URL shouldn't have them as per my Astro change)
    
    const data = await getCatalog(apiParams);
    products.value = data.items || [];
    meta.value = data.meta || { total: 0, page: 1, limit: 12, pages: 1 };
    
  } catch (e) {
    console.error("Failed to fetch products", e);
  } finally {
    loading.value = false;
  }
};

onMounted(() => {
  // If there are search params (that change the result from default), fetch.
  // Default is /catalog (no params).
  // If /catalog has query params, fetch dynamic result instead of SSR default list.
  if (window.location.search) {
      fetchProducts();
  }
});

// Navigation Helper
const updateUrl = (newParams) => {
    const sp = new URLSearchParams(window.location.search);
    Object.entries(newParams).forEach(([k, v]) => {
        if (v === null) sp.delete(k);
        else sp.set(k, v);
    });
    const newUrl = `${window.location.pathname}?${sp.toString()}`;
    window.history.pushState({}, '', newUrl);
    fetchProducts();
    window.scrollTo({ top: 0, behavior: 'smooth' });
};

const goToPage = (p) => updateUrl({ page: p });

</script>

<template>
  <div>
    <div v-if="loading" class="loading-state">
        <span class="material-icons-round spin">refresh</span>
        Загрузка...
    </div>
    
    <div v-else-if="products.length > 0" class="grid">
      <ProductCard 
        v-for="product in products" 
        :key="product.id" 
        :product="product" 
        :showInstallation="true"
      />
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
</style>
