<template>
  <div class="sticky-bar" :class="{ visible: isVisible }">
    <div class="bar-content">
      <div class="price-info">
        <span class="label">Итого:</span>
        <span class="price-val">{{ formattedPrice }}</span>
      </div>
      <button class="btn btn-primary btn-sm" @click="scrollToBuy">
        <span class="material-icons-round">shopping_cart</span>
        В корзину
      </button>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue';

const props = defineProps({
  price: { type: Number, required: true },
  currency: { type: String, default: 'Br' }
});

const isVisible = ref(false);

const formattedPrice = computed(() => {
  return props.price.toLocaleString('ru-RU') + ' ' + props.currency;
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
}

@media (max-width: 768px) {
    .sticky-bar {
        display: block;
    }
}
</style>
