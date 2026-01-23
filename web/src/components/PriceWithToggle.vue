<script setup>
import { ref, computed } from 'vue';

const props = defineProps({
  basePrice: { type: Number, required: true },
  installPrice: { type: Number, default: 360 },
  currency: { type: String, default: 'Br' },
  showToggle: { type: Boolean, default: true }
});

const isInstalled = ref(false);

const totalPrice = computed(() => {
  return props.basePrice + (isInstalled.value ? props.installPrice : 0);
});

const format = (num) => num.toLocaleString() + ' ' + props.currency;

const toggle = (e) => {
    // Prevent navigation if inside an <a> tag
    e.preventDefault();
    e.stopPropagation();
    isInstalled.value = !isInstalled.value;
}
</script>

<template>
  <div class="price-container">
    <div 
      v-if="showToggle"
      class="installation-toggle" 
      :class="{ active: isInstalled }"
      @click="toggle"
    >
      <div class="toggle-control">
        <div class="toggle-switch" />
        <span>Монтаж</span>
      </div>
      <span class="inst-price">+{{ installPrice }} {{ currency }}</span>
    </div>

    <div class="p-footer">
       <span class="final-price" :class="{ pulse: isInstalled }">
         {{ format(totalPrice) }}
       </span>
       <div class="actions">
           <slot></slot>
       </div>
    </div>
  </div>
</template>

<style scoped>
  .installation-toggle {
    background: var(--secondary, #f1f5f9);
    padding: 0.75rem 1rem;
    border-radius: 1rem;
    display: flex;
    justify-content: space-between;
    align-items: center;
    cursor: pointer;
    margin-bottom: 1.5rem;
    transition: background 0.2s;
  }
  .installation-toggle:hover {
    background: rgba(0, 127, 128, 0.15);
  }
  .toggle-control {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    font-weight: 600;
    font-size: 0.9rem;
  }
  .toggle-switch {
    width: 36px;
    height: 20px;
    border-radius: 20px;
    background: #cbd5e1;
    position: relative;
    transition: background 0.3s;
  }
  .toggle-switch::after {
    content: "";
    position: absolute;
    width: 14px;
    height: 14px;
    background: white;
    border-radius: 50%;
    top: 3px;
    left: 3px;
    transition: all 0.3s;
  }
  .installation-toggle.active {
    background: rgba(0, 127, 128, 0.2);
  }
  .installation-toggle.active .toggle-switch {
    background: var(--primary);
  }
  .installation-toggle.active .toggle-switch::after {
    left: 19px;
  }
  .inst-price {
    color: var(--primary);
    font-weight: 700;
    font-size: 0.9rem;
  }

  .p-footer {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-top: auto;
  }
  .final-price {
    font-size: 1.25rem;
    font-weight: 800;
    transition: transform 0.2s;
  }
  .pulse {
    transform: scale(1.1);
    color: var(--primary);
  }
  .actions {
      display: flex;
  }
</style>
