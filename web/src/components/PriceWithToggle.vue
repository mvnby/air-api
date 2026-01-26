<script setup>
import { ref, computed, onMounted } from 'vue';
import { getInstallationRates, getGlobalConfig } from '../utils/api';

const props = defineProps({
  basePrice: { type: Number, required: true },
  installPrice: { type: Number, default: 600 }, // Fallback/Legacy
  currency: { type: String, default: 'р.' },
  showToggle: { type: Boolean, default: true },
  tags: { type: Array, default: () => [] },
  large: { type: Boolean, default: false }
});

const isInstalled = ref(false);
const rates = ref([]);
const discount = ref(0);
const loading = ref(true);

onMounted(async () => {
    try {
        const [ratesData, configData] = await Promise.all([
            getInstallationRates(),
            getGlobalConfig()
        ]);
        rates.value = ratesData || [];
        if (configData && configData.install_discount) {
            discount.value = parseInt(configData.install_discount, 10) || 0;
        }
    } finally {
        loading.value = false;
    }
});

// Helper to normalize strings for comparison
const normalize = (s) => String(s || '').toLowerCase().trim();

const matchedRate = computed(() => {
    if (!rates.value.length) return null;

    // 1. Identify Product Category
    const knownCategories = ['wall', 'cassette', 'duct', 'ceiling', 'multisplit'];
    const categoryTag = props.tags.find(t => knownCategories.includes(normalize(t.slug)));
    if (!categoryTag) return null;

    const productCategorySlug = normalize(categoryTag.slug);

    // 2. Filter Rates by Category
    const categoryRates = rates.value.filter(r => normalize(r.category) === productCategorySlug);
    if (!categoryRates.length) return null;

    // 3. Find Specific Rate by Power/Area
    for (const rate of categoryRates) {
        const pRange = normalize(rate.power_range);
        if (pRange === 'all') return rate;

        const rateSlugs = pRange.split(',').map(s => s.trim());
        const hasMatchingTag = props.tags.some(t => rateSlugs.includes(normalize(t.slug)));

        if (hasMatchingTag) return rate;
    }

    return null;
});

// Computed logic for display
const effectiveInstallPrice = computed(() => {
    if (matchedRate.value && matchedRate.value.is_fixed) {
        return matchedRate.value.base_price;
    }
    return props.installPrice; 
});

// Price WITH discount applied
const finalInstallPrice = computed(() => {
    return Math.max(0, effectiveInstallPrice.value - discount.value);
});

const shouldShowToogle = computed(() => {
    if (!matchedRate.value) return false;
    if (!matchedRate.value.is_fixed) return false;
    return props.showToggle;
});

const priceDisplay = computed(() => {
    // Case 1: No match or non-fixed -> Just Product Price
    if (!matchedRate.value || !matchedRate.value.is_fixed) {
         return {
             current: format(props.basePrice),
             old: null
         };
    }
    
    // Case 2: Fixed rate but NOT toggled -> Just Product Price
    if (!isInstalled.value) {
        return {
            current: format(props.basePrice),
            old: null
        };
    }

    // Case 3: Fixed rate + Toggled -> Product + Discounted Install
    const total = props.basePrice + finalInstallPrice.value;
    const oldTotal = props.basePrice + effectiveInstallPrice.value;

    return {
        current: format(total),
        old: discount.value > 0 ? format(oldTotal) : null
    };
});

// Force ru-RU to match server side rendering
const format = (num) => num.toLocaleString('ru-RU') + ' ' + props.currency;

const discountPct = computed(() => {
    if (!props.oldPrice || !props.basePrice) return 0;
    const diff = props.oldPrice - props.basePrice;
    return Math.round((diff / props.oldPrice) * 100);
});

const toggle = (e) => {
    e.preventDefault();
    e.stopPropagation();
    isInstalled.value = !isInstalled.value;
}
</script>

<template>
  <div class="price-container" :class="{ 'size-large': large }">
    <!-- Toggle: Only show if allowed (fixed price or default) -->
   
  <div class="price-wrapper">
      <!-- Product Discount Badge (Sale Effect) -->
      <div v-if="props.oldPrice" class="discount-badge squircle sale-badge">
        -{{ discountPct }}%
      </div>
      
      <span v-if="priceDisplay.old" class="old-price">
          {{ priceDisplay.old }}
      </span>
      <span class="final-price" :class="{ pulse: isInstalled }">
        {{ priceDisplay.current }}
      </span>
  </div>
    <div 
      v-if="shouldShowToogle"
      class="installation-toggle" 
      :class="{ active: isInstalled }"
      @click="toggle"
    >
      <div class="toggle-content">
          <div class="toggle-control">
            <div class="toggle-switch" />
            <span>Монтаж</span>
          </div>
          <div class="price-column">
             <span class="inst-price" :class="{ 'line-through text-xs text-muted': discount > 0 }">
                +{{ effectiveInstallPrice }} {{ currency }}
             </span>
             <span v-if="discount > 0" class="discount-price">
                +{{ finalInstallPrice }} {{ currency }}
             </span>
      </div>
    </div>
  </div>

    <!-- Non-fixed rate message (e.g. "from 500 Br") -->
    <div v-if="matchedRate && !matchedRate.is_fixed" class="non-fixed-message">
        Монтаж: <span class="inst-price">от {{ matchedRate.base_price }} {{ currency }}</span>
    </div>

    <div class="p-footer">
       <div class="actions">
           <slot></slot>
       </div>
    </div>
  </div>
</template>

<style scoped>
  .price-container {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: .25rem;
  }

  .installation-toggle {
    background: var(--secondary, #f1f5f9);
    padding: 0.75rem 1rem;
    border-radius: 1rem;
    position: relative; /* For badge absolute positioning */
    cursor: pointer;
    margin-bottom: 1.5rem;
    transition: background 0.2s;
    border: 2px solid transparent;
  }
  .installation-toggle:hover {
    background: rgba(0, 127, 128, 0.1);
  }
  
  .toggle-content {
    display: flex;
    justify-content: space-between;
    align-items: center;
    width: 100%;
    gap: 1.25rem;
  }

  .toggle-control {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    font-weight: 600;
    font-size: 0.95rem;
  }
  .toggle-switch {
    width: 40px;
    height: 22px;
    border-radius: 20px;
    background: #cbd5e1;
    position: relative;
    transition: background 0.3s;
  }
  .toggle-switch::after {
    content: "";
    position: absolute;
    width: 16px;
    height: 16px;
    background: white;
    border-radius: 50%;
    top: 3px;
    left: 3px;
    transition: all 0.3s;
    box-shadow: 0 1px 2px rgba(0,0,0,0.2);
  }
  .installation-toggle.active {
    background: rgba(0, 127, 128, 0.05);
    border-color: rgba(0, 127, 128, 0.2);
  }
  .installation-toggle.active .toggle-switch {
    background: var(--primary);
  }
  .installation-toggle.active .toggle-switch::after {
    left: 21px;
  }
  
  .price-column {
      display: flex;
      flex-direction: column;
      align-items: flex-end;
      line-height: 1.1;
  }
  .inst-price {
    color: var(--text-muted);
    font-weight: 500;
    font-size: 0.9rem;
  }
  .discount-price {
      color: #0d9488; /* Teal-600 */
      font-weight: 700;
      font-size: 0.95rem;
  }
  .text-xs { font-size: 0.75rem; }
  .text-muted { color: #94a3b8; }
  .line-through { text-decoration: line-through; }

  /* Badge */
  .discount-badge {
    position: absolute;
    top: -10px;
    right: -5px;
    background: #f97316; /* Orange-500 */
    color: white;
    font-size: 0.65rem;
    font-weight: 700;
    text-transform: uppercase;
    padding: 2px 8px;
    border-radius: 8px; /* Squircle aprox */
    box-shadow: 0 2px 5px rgba(249, 115, 22, 0.4);
    transform: rotate(3deg);
    animation: bounce 2s infinite;
  }
  .squircle {
       border-radius: 6px; /* Smooth corners */
  }

  @keyframes bounce {
      0%, 20%, 50%, 80%, 100% {transform: translateY(0) rotate(3deg);}
      40% {transform: translateY(-3px) rotate(3deg);}
      60% {transform: translateY(-2px) rotate(3deg);}
  }

  .p-footer {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-top: auto;
  }
  
  /* Price Wrapper for old/new stacking */
  .price-wrapper {
      display: flex;
      flex-direction: column;
      align-items: center;
      position: relative;
  }
  
  .old-price {
      font-size: 0.9rem;
      color: var(--text-muted);
      text-decoration: line-through;
      margin-bottom: -4px;
      padding-top: 10px; /* Make space for badge */
  }

  .sale-badge {
      top: -5px;
      left: -5px;
      right: auto;
      transform: rotate(-3deg);
  }

  .final-price {
    white-space: nowrap;
    font-size: 1.5rem;
    font-weight: 800;
    transition: transform 0.2s;
    color: var(--text);
  }
  .size-large .final-price {
    font-size: 3.5rem;
  }
  .size-large .installation-toggle {
    padding: 1rem 1.5rem;
  }
  .size-large .toggle-control {
    font-size: 1.1rem;
  }
  .size-large .inst-price {
    font-size: 1rem;
  }
  .size-large .discount-price {
    font-size: 1.1rem;
  }
  .pulse {
    transform: scale(1.02);
    color: var(--primary);
  }
  .actions {
      display: flex;
      width: 100%;
      justify-content: center ;
  }
  .actions-slot {
    width: 100%;
  }
  
  .non-fixed-message {
    padding: 0.5rem 0;
    font-size: 0.9rem;
    color: var(--text-muted);
    font-weight: 500;
  }
</style>
