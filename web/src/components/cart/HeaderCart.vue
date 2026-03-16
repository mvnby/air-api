<script setup>
import { onMounted, ref } from 'vue';
import { useStore } from '@nanostores/vue';
import { cartCount } from '../../store/cart';

const count = useStore(cartCount);
const isHydrated = ref(false);

onMounted(() => {
    isHydrated.value = true;
});
</script>

<template>
  <a href="/cart" class="header-cart-btn" aria-label="Корзина">
    <div class="icon-wrapper">
        <span class="material-icons-round">shopping_cart</span>
        <transition name="pop">
            <span v-if="isHydrated && count > 0" class="badge" key="count">{{ count }}</span>
        </transition>
    </div>
  </a>
</template>

<style scoped>
.header-cart-btn {
    display: flex;
    align-items: center;
    justify-content: center;
    color: var(--text);
    text-decoration: none;
    padding: 0.5rem;
    border-radius: 50%;
    transition: background-color 0.2s, color 0.2s;
}

.header-cart-btn:hover {
    background-color: var(--secondary, #f1f5f9);
    color: var(--primary, #007f80);
}

.icon-wrapper {
    position: relative;
    display: flex;
    align-items: center;
}

.material-icons-round {
    font-size: 1.5rem;
}

.badge {
    position: absolute;
    top: -8px;
    right: -8px;
    background-color: #f97316; /* Orange-500 */
    color: white;
    font-size: 0.7rem;
    font-weight: 700;
    min-width: 18px;
    height: 18px;
    border-radius: 9px;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 0 4px;
    box-shadow: 0 2px 5px rgba(249, 115, 22, 0.4);
    pointer-events: none;
}

/* Pop animation for badge */
.pop-enter-active,
.pop-leave-active {
  transition: transform 0.2s cubic-bezier(0.175, 0.885, 0.32, 1.275);
}

.pop-enter-from,
.pop-leave-to {
  transform: scale(0);
}
</style>
