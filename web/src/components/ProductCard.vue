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

// 1. Filter usable tags (Public Tag + Public Group)
const validTags = computed(() => (props.product.tags || []).filter(
  (t) => t.is_public && t.group?.is_public
));

// 2. Extract Specific Badges
const inverterTag = computed(() => validTags.value.find((t) => inGroup(t, "compressor-type")));
const areaTag = computed(() => validTags.value.find((t) => inGroup(t, "area")));
const winterTag = computed(() => validTags.value.find((t) => inGroup(t, "winter")));
const featureTags = computed(() => validTags.value.filter((t) => inGroup(t, "features", "design")));

// Fallback for legacy props if no tags present
const showLegacyInverter = computed(() => !inverterTag.value && props.product.is_inverter);
const showLegacyArea = computed(() => !areaTag.value && props.product.area);
</script>

<template>
  <a v-if="variant === 'default'" :href="`/product/${product.slug}`" class="product-item card group">
    <div class="p-img-box">
      <img :src="resolveImageUrl(product.main_image)" :alt="product.title" />

      <!-- Top Left: Functionality Badges + Inverter -->
      <div class="p-badge-list">
        <span v-if="inverterTag" class="badge inverter-badge">{{ inverterTag.title }}</span>
        <span v-else-if="showLegacyInverter" class="badge small">Инвертор</span>
        
        <template v-if="!product.tags && product.badges">
            <span v-for="b in product.badges" :key="b.text" :class="['p-tag', b.class]">{{ b.text }}</span>
        </template>
      </div>

      <!-- Top Right: Area -->
      <div v-if="areaTag || showLegacyArea" class="p-top-right-badge">
        {{ areaTag ? areaTag.title : `${product.area} м²` }}
      </div>

      <!-- Bottom: Winter/Heat -->
      <div v-if="winterTag" class="p-bottom-badge heat">
        <span class="material-icons-round" style="font-size: 14px; margin-right: 4px;">wb_sunny</span>
        {{ winterTag.title }}
      </div>
    </div>
    <div class="p-info">
      <!-- Only show legacy area info if we DON'T have a top-right badge for it -->
      <span v-if="!areaTag && showLegacyArea" class="p-area-info">{{ `${product.area} м²` }}</span>

      <h4>{{ product.title }}</h4>

      <!-- Feature Tags -->
      <div v-if="featureTags.length > 0" class="p-features-list">
        <span v-for="tag in featureTags" :key="tag.id" :class="['feature-tag', tag.slug]">{{ tag.title }}</span>
      </div>

      <PriceWithToggle
        :basePrice="product.price"
        :installPrice="baseInstallationPrice"
        currency="Br"
        :showToggle="showInstallation"
        :tags="product.tags"
      />
    </div>
  </a>

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
    gap: 0.5rem;
    margin-bottom: 1.5rem;
    margin-top: -0.5rem;
  }

  .feature-tag {
    font-size: 0.8rem;
    color: var(--text-muted);
    background: var(--secondary);
    padding: 0.2rem 0.6rem;
    border-radius: 6px;
    white-space: nowrap;
  }

  .p-info {
    padding: 1.5rem;
    flex: 1;
    display: flex;
    flex-direction: column;
  }
  .p-area-info {
    font-size: 0.8rem;
    font-weight: 700;
    color: var(--primary);
    text-transform: uppercase;
    margin-bottom: 0.5rem;
    display: block;
  }
  .p-info h4 {
    font-size: 1.125rem;
    margin-bottom: 1.5rem;
    line-height: 1.4;
    flex: 1;
  }
</style>
