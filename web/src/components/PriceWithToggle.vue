<script setup>
import { ref, computed, onMounted } from 'vue';
import { getInstallationRates, getGlobalConfig, getProductById } from '../utils/api';
import { addItem } from '../store/cart';
import { addToast } from '../store/toast';

const props = defineProps({
  basePrice: { type: Number, required: true },
  oldPrice: { type: Number, default: 0 },
  installPrice: { type: Number, default: 600 }, // Fallback/Legacy
  currency: { type: String, default: 'р.' },
  showToggle: { type: Boolean, default: true },
  tags: { type: Array, default: () => [] },
  large: { type: Boolean, default: false },
  // Data for Cart
  id: { type: String, default: '' },
  productId: { default: 0 },
  title: { type: String, default: '' },
  image: { type: String, default: '' }
});

const isInstalled = ref(false);
const rates = ref([]);
const discount = ref(0);
const loading = ref(true);
const buttonState = ref('default');

const liveBasePrice = ref(props.basePrice);
const liveOldPrice = ref(props.oldPrice);

onMounted(async () => {
    try {
        const [ratesData, configData, freshProduct] = await Promise.all([
            getInstallationRates(),
            getGlobalConfig(),
            props.productId ? getProductById(props.productId) : Promise.resolve(null)
        ]);
        rates.value = ratesData || [];
        if (configData && configData.install_discount) {
            discount.value = parseInt(configData.install_discount, 10) || 0;
        }
        if (freshProduct && freshProduct.price !== undefined) {
            liveBasePrice.value = freshProduct.price;
            liveOldPrice.value = freshProduct.old_price || 0;
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

const shouldShowToggle = computed(() => {
    if (!matchedRate.value) return false;
    if (!matchedRate.value.is_fixed) return false;
    return props.showToggle;
});

// Force ru-RU to match server side rendering
const format = (num) => num.toLocaleString('ru-RU') + ' ' + props.currency;

const priceDisplay = computed(() => {
    // Case 1: No match or non-fixed -> Just Product Price
    if (!matchedRate.value || !matchedRate.value.is_fixed) {
         return {
             current: format(liveBasePrice.value),
             old: null
         };
    }
    
    // Case 2: Fixed rate but NOT toggled -> Just Product Price
    if (!isInstalled.value) {
        return {
            current: format(liveBasePrice.value),
            old: null
        };
    }

    // Case 3: Fixed rate + Toggled -> Product + Discounted Install
    const total = liveBasePrice.value + finalInstallPrice.value;
    const oldTotal = liveBasePrice.value + effectiveInstallPrice.value;

    return {
        current: format(total),
        old: discount.value > 0 ? format(oldTotal) : null
    };
});

const discountPct = computed(() => {
    if (!liveOldPrice.value || !liveBasePrice.value) return 0;
    const diff = liveOldPrice.value - liveBasePrice.value;
    return Math.round((diff / liveOldPrice.value) * 100);
});

const toggle = (e) => {
    e.preventDefault();
    e.stopPropagation();
    isInstalled.value = !isInstalled.value;
}

const addToCart = () => {
    if (!props.id) return;
    
    addItem({
        id: props.id,
        name: props.title,
        price: liveBasePrice.value,
        image: props.image,
        productId: props.productId,
        withInstallation: isInstalled.value,
        installationPrice: finalInstallPrice.value, // Use discounted price
        // We could infer category from tags if needed, or pass it
    });
    
    // Feedback: Toast + Button State
    addToast(`Добавлено в корзину: ${props.title}`);
    
    buttonState.value = 'success';
    setTimeout(() => {
        buttonState.value = 'default';
    }, 2000);
}
</script>

<template>
  <div class="price-container" :class="{ 'size-large': large }">
    <!-- Price Display -->
    <div class="price-wrapper">
        <!-- Sale Badge -->
        <div v-if="liveOldPrice" class="discount-badge sale-badge">
          -{{ discountPct }}%
        </div>
        
        <span v-if="priceDisplay.old" class="old-price">
            {{ priceDisplay.old }}
        </span>
        <span class="final-price" :class="{ 'pulse-primary': isInstalled }">
          {{ priceDisplay.current }}
        </span>
    </div>

    <!-- Toggle -->
    <div 
      v-if="shouldShowToggle"
      class="installation-toggle" 
      :class="{ active: isInstalled }"
      @click="toggle"
    >
      <div class="toggle-content">
          <div class="toggle-control">
            <div class="toggle-switch"></div>
            <span>Монтаж</span>
          </div>
          <div class="price-column">
             <div v-if="discount > 0" class="price-row-stack">
                <span class="inst-price line-through text-muted small">
                  {{ effectiveInstallPrice }}
                </span>
                <span class="discount-price">
                  +{{ finalInstallPrice }} {{ currency }}
                </span>
             </div>
             <span v-else class="inst-price">
                +{{ effectiveInstallPrice }} {{ currency }}
             </span>
          </div>
      </div>
    </div>

    <!-- Non-fixed rate message -->
    <div v-if="matchedRate && !matchedRate.is_fixed" class="non-fixed-message">
        Монтаж: <span class="inst-price">от {{ matchedRate.base_price }} {{ currency }}</span>
    </div>

    <!-- Actions (Centered) -->
    <div class="actions-container">
        <button 
            class="btn-action primary js-track-cart" 
            :class="{ success: buttonState === 'success' }"
            @click.stop="addToCart"
        >
            <span class="material-icons-round">{{ buttonState === 'success' ? 'check' : 'shopping_cart' }}</span>
            {{ buttonState === 'success' ? 'Добавлено' : 'В корзину' }}
        </button>
        <!-- "Buy in 1 click" removed for micro cards, kept for large if requested? 
             User specifically said remove quick order from thumbnails. 
             In large view (product page) it might be useful, but user said "it doesn't work".
             Removing from everywhere to be safe and clean.
        -->
    </div>
  </div>
</template>

<style scoped>
  .price-container {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: .5rem;
    width: 100%;
  }

  /* Price Display */
  .price-wrapper {
      display: flex;
      flex-direction: column;
      align-items: center;
      position: relative;
      margin-bottom: 0.5rem;
  }
  
  .old-price {
      font-size: 0.95rem;
      color: var(--text-muted);
      text-decoration: line-through;
      margin-bottom: -2px;
  }

  .final-price {
    white-space: nowrap;
    font-size: 1.75rem;
    font-weight: 800;
    color: var(--text);
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  }

  .pulse-primary {
    color: var(--primary);
    transform: scale(1.05);
  }

  /* Discount Badge (Orange) */
  .discount-badge {
    position: absolute;
    top: -12px;
    right: -24px;
    background: #f97316; /* Orange 500 */
    color: white;
    font-size: 0.75rem;
    font-weight: 800;
    padding: 2px 8px;
    border-radius: 6px;
    box-shadow: 0 4px 12px rgba(249, 115, 22, 0.3);
    z-index: 5;
    transform: rotate(6deg);
  }
  
  .sale-badge {
      right: auto;
      left: -28px;
      transform: rotate(-6deg);
  }

  /* Toggle Row */
  .installation-toggle {
    width: 100%;
    max-width: 320px;
    background: var(--surface);
    border: 1px solid var(--border);
    padding: 0.75rem 1rem;
    border-radius: 1rem;
    cursor: pointer;
    transition: all 0.2s;
  }
  
  .installation-toggle:hover {
    border-color: var(--primary);
    background: rgba(var(--primary-rgb), 0.05);
  }

  .installation-toggle.active {
    background: var(--primary-bg);
    border-color: var(--primary);
  }

  .toggle-content {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 1rem;
  }

  .toggle-control {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    font-weight: 700;
    font-size: 0.95rem;
    color: var(--text);
  }

  .toggle-switch {
    width: 36px;
    height: 20px;
    border-radius: 20px;
    background: var(--border);
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

  .active .toggle-switch {
    background: var(--primary);
  }
  .active .toggle-switch::after {
    left: 19px;
  }

  .price-column {
      display: flex;
      flex-direction: column;
      align-items: flex-end;
      line-height: 1.2;
  }

  .price-row-stack {
      display: flex;
      flex-direction: column;
      align-items: flex-end;
  }

  .inst-price {
    color: var(--text-muted);
    font-weight: 600;
    font-size: 0.85rem;
  }

  .inst-price.small {
      font-size: 0.75rem;
      margin-bottom: -2px;
  }

  .discount-price {
      color: var(--primary);
      font-weight: 800;
      font-size: 0.95rem;
  }

  .line-through { text-decoration: line-through; }
  .text-muted { color: var(--text-muted); }

  /* Actions Container */
  .actions-container {
      width: 100%;
      display: flex;
      justify-content: center;
  }

  .btn-action {
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 0.5rem;
      padding: 0.8rem 2rem;
      border-radius: 12px;
      font-weight: 700;
      font-size: 1rem;
      cursor: pointer;
      transition: all 0.2s;
      border: none;
      font-family: inherit;
      width: 100%;
      max-width: 240px;
  }

  .btn-action.primary {
      background: var(--primary);
      color: white;
      box-shadow: 0 4px 15px rgba(var(--primary-rgb), 0.3);
  }

  .btn-action.primary:hover {
      background: var(--primary-dark);
      transform: translateY(-2px);
      box-shadow: 0 6px 20px rgba(var(--primary-rgb), 0.4);
  }

  .btn-action.primary.success {
      background: #10b981; /* Emerald 500 */
      box-shadow: 0 4px 15px rgba(16, 185, 129, 0.4);
      pointer-events: none;
  }

  .btn-action.primary:active {
      transform: translateY(0);
  }

  /* Non-fixed message */
  .non-fixed-message {
    font-size: 0.9rem;
    color: var(--text-muted);
    font-weight: 600;
  }

  /* Large View (Product Page) */
  .size-large {
    gap: 2rem;
  }

  .size-large .final-price {
    font-size: 3.5rem;
  }

  .size-large .btn-action {
    max-width: 300px;
    padding: 1.1rem 2.5rem;
    font-size: 1.1rem;
    border-radius: 16px;
  }

  .size-large .installation-toggle {
    max-width: 400px;
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

  @media (max-width: 640px) {
    .size-large .final-price {
        font-size: 2.5rem;
    }
  }
</style>
