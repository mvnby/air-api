<script setup>
import { computed } from 'vue';
import PriceWithToggle from './PriceWithToggle.vue';
import { resolveImageUrl } from '../utils/api';

const props = defineProps({
  product: {
    type: Object,
    required: true
  },
  variant: {
    type: String,
    default: 'default'
  },
  showInstallation: {
    type: Boolean,
    default: false
  },
  baseInstallationPrice: {
    type: Number,
    default: 360
  }
});

const formatPrice = (price) => price ? price.toLocaleString() + " р." : "";

// --- Logic for Tags & Badges ---

// Helper to check if a tag matches a group slug
const inGroup = (tag, ...slugs) => {
  return tag.group && slugs.includes(tag.group.slug);
};
const toBool = (value) => value === true || value === 'true' || value === 1 || value === '1';
const resolveCompressorLabel = (product) => {
  const raw = String(product?.specs?.compressor_type_norm || '').trim().toLowerCase();
  if (raw === 'full_dc') return 'Full DC Inverter';
  if (raw === 'on_off') return 'On/Off';
  if (raw === 'inverter') return 'Инвертор';
  return product?.is_inverter ? 'Инвертор' : null;
};
const parseMinHeat = (specs = {}) => {
  const fromRange = specs.temp_range_heat;
  if (typeof fromRange === 'string') {
    const m = fromRange.replace(/−|—/g, '-').match(/-\d+/);
    if (m) return Number.parseInt(m[0], 10);
  }
  const fromMin = specs.min_temp_heat;
  if (typeof fromMin === 'string' || typeof fromMin === 'number') {
    const m = String(fromMin).replace(/−|—/g, '-').match(/-\d+/);
    if (m) return Number.parseInt(m[0], 10);
  }
  return null;
};
const formatAreaBadge = (rawArea) => {
  if (rawArea) return `До ${rawArea} м²`;
  return '';
};

// 1. Filter usable tags (Public Tag + Public Group)
const validTags = computed(() => (props.product.tags || []).filter(
  (t) => t.is_public && t.group?.is_public
));

// 2. Extract Specific Badges
const winterTag = computed(() => validTags.value.find((t) => inGroup(t, "winter")));
const featureTags = computed(() => validTags.value.filter((t) => inGroup(t, "features", "design")));
const compressorBadge = computed(() => resolveCompressorLabel(props.product));
const wifiBadgeText = computed(() => {
  const specs = props.product.specs || {};
  if (toBool(specs['wifi-builtin']) || toBool(specs.wifi_ready)) return 'Wi-Fi встроенный';
  if (toBool(specs['wifi-ready']) || specs.wifi_ready === 'ready') return 'Wi-Fi Ready';
  return null;
});
const heatBadgeText = computed(() => {
  const minHeat = parseMinHeat(props.product.specs || {});
  if (typeof minHeat === 'number' && Number.isFinite(minHeat) && minHeat < 0) {
    return `Обогрев до ${minHeat}°C`;
  }
  return winterTag.value?.title || null;
});
const displayFeatureTags = computed(() => {
  const tags = [...featureTags.value];
  if (wifiBadgeText.value && !tags.some((t) => String(t.title || '').toLowerCase().includes('wi-fi'))) {
    tags.push({ id: '__wifi', title: wifiBadgeText.value, slug: 'wifi' });
  }
  return tags;
});

// Fallback for legacy props if no tags present
const showAreaBadge = computed(() => Boolean(props.product.area));
</script>

<template>
  <div v-if="variant === 'default'" class="product-item card group">
    <a :href="`/product/${product.slug}`" class="product-link">
      <div class="p-img-box">
        <img :src="resolveImageUrl(product.main_image)" :alt="product.title" />

        <!-- Top Left: Functionality Badges + Inverter -->
        <div class="p-badge-list">
          <span v-if="compressorBadge" class="badge inverter-badge">{{ compressorBadge }}</span>
          
          <template v-if="!product.tags && product.badges">
              <span v-for="b in product.badges" :key="b.text" :class="['p-tag', b.class]">{{ b.text }}</span>
          </template>
        </div>

        <!-- Top Right: Area -->
        <div v-if="showAreaBadge" class="p-top-right-badge">
          {{ formatAreaBadge(product.area) }}
        </div>

        <!-- Bottom: Winter/Heat -->
        <div v-if="heatBadgeText" class="p-bottom-badge heat">
          <span class="material-icons-round" style="font-size: 14px; margin-right: 4px;">wb_sunny</span>
          {{ heatBadgeText }}
        </div>
      </div>
      <div class="p-info">
        <h4>{{ product.title }}</h4>

        <!-- Feature Tags -->
        <div v-if="displayFeatureTags.length > 0" class="p-features-list">
          <span v-for="tag in displayFeatureTags" :key="tag.id" :class="['feature-tag', tag.slug]">{{ tag.title }}</span>
        </div>
      </div>
    </a>

    <div class="p-actions">
        <PriceWithToggle
          :basePrice="product.price"
          :installPrice="baseInstallationPrice"
          currency="р."
          :showToggle="showInstallation"
          :tags="product.tags"
          :id="product.slug"
          :productId="product.id"
          :title="product.title"
          :image="resolveImageUrl(product.main_image)"
        />
    </div>
  </div>

  <!-- Implement minimal/hero variants only if needed by Catalog (Catalog mostly uses default) -->
</template>

<style scoped>
  /* Base Card Styles ported from Astro */
  .product-item {
    padding: 0;
    overflow: hidden;
    display: flex;
    flex-direction: column;
    text-decoration: none;
    color: inherit;
    transition: transform 0.2s;
  }
  .product-item:hover {
    transform: translateY(-4px);
  }

  .p-img-box {
    height: 200px;
    background: var(--bg);
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 1.5rem;
    position: relative;
    border-bottom: 1px solid var(--border);
  }
  .p-img-box img {
    max-width: 100%;
    max-height: 100%;
    object-fit: contain;
    transition: transform 0.4s;
  }
  .product-item:hover .p-img-box img {
    transform: scale(1.1);
  }
  .p-badge-list {
    position: absolute;
    top: 1rem;
    left: 1rem;
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
    z-index: 2;
  }

  .p-top-right-badge {
    position: absolute;
    top: 1rem;
    right: 1rem;
    background: var(--surface);
    backdrop-filter: blur(4px);
    padding: 0.25rem 0.6rem;
    border-radius: 8px;
    font-size: 0.75rem;
    font-weight: 700;
    color: var(--text);
    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);
    z-index: 2;
    border: 1px solid var(--border);
  }

  .p-bottom-badge {
    position: absolute;
    bottom: 0;
    left: 0;
    right: 0;
    padding: 0.4rem 1rem;
    font-size: 0.75rem;
    font-weight: 600;
    display: flex;
    align-items: center;
    justify-content: center;
    background: rgba(var(--surface-rgb), 0.95);
    z-index: 2;
  }

  .p-bottom-badge.heat {
    background: var(--warning-bg);
    color: var(--warning-text);
    border-top: 1px solid var(--warning);
    width: fit-content;
    box-shadow: 2px -1px 1px -1px var(--warning);
    border-radius: 0 10px 0 0;
  }

  .inverter-badge {
    background: var(--primary);
    color: white;
    padding: 0.25rem 0.6rem;
    border-radius: 6px;
    font-size: 0.7rem;
    font-weight: 600;
  }

  .p-tag.feature {
    background: var(--surface);
    border: 1px solid var(--border);
    color: var(--text-muted);
  }

  .p-features-list {
    display: flex;
    flex-wrap: wrap;
    gap: 0.375rem;
    margin-top: 0.25rem;
  }

  .feature-tag {
    font-size: 0.8rem;
    color: var(--text-muted);
    background: var(--secondary);
    padding: 0.2rem 0.6rem;
    border-radius: 6px;
    white-space: nowrap;
  }

  .product-link {
    text-decoration: none;
    color: inherit;
    flex: 1;
    display: flex;
    flex-direction: column;
  }
  .p-actions {
    padding: 0 1.5rem 1.5rem;
  }
  .p-info {
    padding: .75rem 1.5rem 0.5rem;
    flex: 1;
    display: flex;
    flex-direction: column;
  }
</style>
