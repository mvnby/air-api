<template>
  <div class="sticky-bar" :class="{ visible: isVisible }">
    <div class="bar-content">
      <div class="price-info">
        <span class="label">Итого:</span>
        <span class="price-val">{{ formattedPrice }} <span v-if="hasKnownPrice" class="price-byn"></span></span>
        <span v-if="shouldInquire" class="stock-note">{{ stockNote }}</span>
      </div>
      <button
        class="btn btn-primary btn-sm js-track-cart"
        :class="{ notify: shouldInquire }"
        @click="scrollToBuy"
      >
        <span class="material-icons-round">{{ actionIcon }}</span>
        {{ actionLabel }}
      </button>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue';
import {
    formatProductPrice,
    getProductAvailabilityDisplay,
    hasKnownProductPrice,
} from '../../utils/product-display';

const props = defineProps({
  price: { type: [Number, String], default: 0 },
  currency: { type: String, default: 'Br' },
  vitebskQty: { type: Number, default: 0 },
  minskQty: { type: Number, default: 0 },
  availabilityStatus: { type: String, default: null }
});

const isVisible = ref(false);

const formattedPrice = computed(() => {
  return formatProductPrice(props.price);
});

const hasKnownPrice = computed(() => hasKnownProductPrice(props.price));

const availabilityState = computed(() => {
  return getProductAvailabilityDisplay({
    vitebskQty: props.vitebskQty,
    minskQty: props.minskQty,
    availabilityStatus: props.availabilityStatus,
  });
});

const shouldInquire = computed(() => {
  return !hasKnownPrice.value || !availabilityState.value.canOrder;
});

const stockNote = computed(() => availabilityState.value.message);

const actionLabel = computed(() => {
  if (!hasKnownPrice.value && availabilityState.value.isUnknown) return 'Уточнить';
  if (!hasKnownPrice.value) return 'Уточнить цену';
  if (availabilityState.value.isExplicitOutOfStock) return 'Сообщить';
  if (!availabilityState.value.canOrder) return 'Уточнить наличие';
  return 'В корзину';
});

const actionIcon = computed(() => {
  if (availabilityState.value.isExplicitOutOfStock) return 'notifications_active';
  if (shouldInquire.value) return 'support_agent';
  return 'shopping_cart';
});

const handleScroll = () => {
    // Show bar only after scrolling down a bit (e.g. 300px)
    isVisible.value = window.scrollY > 300;
};

const scrollToBuy = () => {
    const buyBlock = document.querySelector('.price-section');
    if (buyBlock) {
        buyBlock.scrollIntoView({ behavior: 'smooth', block: 'center' });
        // Optional: Highlight the block
        buyBlock.classList.add('highlight-pulse');
        setTimeout(() => buyBlock.classList.remove('highlight-pulse'), 1000);
    }
};

onMounted(() => {
    window.addEventListener('scroll', handleScroll);
});

onUnmounted(() => {
    window.removeEventListener('scroll', handleScroll);
});
</script>

<style scoped>
.sticky-bar {
    position: fixed;
    bottom: 0;
    left: 0;
    right: 0;
    background: white;
    padding: 1rem;
    box-shadow: 0 -4px 20px rgba(0,0,0,0.1);
    z-index: 100;
    transform: translateY(100%);
    transition: transform 0.3s ease;
    display: none; /* Hidden by default, shown via media query */
}

.sticky-bar.visible {
    transform: translateY(0);
}

.bar-content {
    display: flex;
    justify-content: space-between;
    align-items: center;
    max-width: 600px;
    margin: 0 auto;
}

.price-info {
    display: flex;
    flex-direction: column;
}

.stock-note {
    font-size: 0.75rem;
    color: #475569;
    font-weight: 600;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: fit-content;
    margin-top: 0.25rem;
    padding: 0.18rem 0.55rem;
    border-radius: 999px;
    background: rgba(148, 163, 184, 0.12);
    border: 1px solid rgba(100, 116, 139, 0.22);
}

:global(.dark) .stock-note {
    color: rgba(241, 245, 249, 0.82);
    background: rgba(148, 163, 184, 0.14);
    border-color: rgba(148, 163, 184, 0.24);
}

.label {
    font-size: 0.75rem;
    color: #64748b;
}

.price-val {
    font-weight: 700;
    font-size: 1.1rem;
    color: #0f172a;
}

.btn-sm {
    padding: 0.5rem 1rem;
    font-size: 0.9rem;
    border-radius: 12px;
    display: flex;
    align-items: center;
    gap: 0.5rem;
    background: #007f80;
    color: white;
    border: none;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.2s ease;
}

.btn-sm:hover {
    opacity: 0.92;
}

.btn-sm:active {
    transform: translateY(1px);
}

.sticky-bar .btn-sm .material-icons-round {
    font-size: 1.1rem;
}

.btn-sm.notify {
    background: #fff7ed;
    color: #b45309;
    border: 1px solid #fdba74;
}

@media (max-width: 768px) {
    .sticky-bar {
        display: block;
    }
}
</style>
