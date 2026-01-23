<script setup>
import { ref, computed, onMounted } from 'vue';
import { getInstallationRates } from '../utils/api';

const props = defineProps({
  basePrice: { type: Number, required: true },
  installPrice: { type: Number, default: 600 }, // Fallback/Legacy
  currency: { type: String, default: 'Br' },
  showToggle: { type: Boolean, default: true },
  tags: { type: Array, default: () => [] }
});

const isInstalled = ref(false);
const rates = ref([]);
// We might want to expose loading state if crucial, but for now internal is fine
const loading = ref(true);

onMounted(async () => {
    try {
        rates.value = await getInstallationRates() || [];
    } finally {
        loading.value = false;
    }
});

// Helper to normalize strings for comparison
const normalize = (s) => String(s || '').toLowerCase().trim();

const matchedRate = computed(() => {
    if (!rates.value.length) return null;

    // 1. Identify Product Category
    // Known categories corresponding to installation rate types
    const knownCategories = ['wall', 'cassette', 'duct', 'ceiling'];
    
    // Find the category tag in the product tags
    const categoryTag = props.tags.find(t => knownCategories.includes(normalize(t.slug)));
    
    // If product doesn't have a known category tag, we can't determine rate -> return null
    if (!categoryTag) return null;

    const productCategorySlug = normalize(categoryTag.slug);

    // 2. Filter Rates by Category
    // We expect rate.category to match the tag slug (e.g. "wall", "duct")
    const categoryRates = rates.value.filter(r => normalize(r.category) === productCategorySlug);

    if (!categoryRates.length) return null;

    // 3. Find Specific Rate by Power/Area
    // Check for 'all' or specific slug match
    for (const rate of categoryRates) {
        const pRange = normalize(rate.power_range);
        
        // Case A: "all" - matches anything in this category (unless a more specific one is prioritized? Assuming order doesn't matter or 'all' is fallback)
        // Ideally we might want specific matches to take precedence, but for now let's find the first valid match.
        if (pRange === 'all') return rate;

        // Case B: List of slugs (e.g. "area-20, area-25")
        // Check if ANY of the rate's power slugs exist in the product's tags
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
    return props.installPrice; // Fallback (shouldn't happen if hidden)
});

const shouldShowToogle = computed(() => {
    // If no rate matched, HIDE EVERYTHING related to installation
    if (!matchedRate.value) return false;

    // If rate matched but not fixed, HIDE TOGGLE (show text instead)
    if (!matchedRate.value.is_fixed) return false;
    
    return props.showToggle;
});

const priceDisplay = computed(() => {
    // If logic:
    // 1. No match -> Just Base Price
    // 2. Match + Not Fixed -> Just Base Price (Text "from..." is separate)
    // 3. Match + Fixed + Toggled -> Base + Install
    
    if (!matchedRate.value) {
         return format(props.basePrice);
    }

    if (!matchedRate.value.is_fixed) {
        // If not fixed, we just show the base price in the main slot?
        // Prompt says: "вместо итоговой суммы выводить текст 'от [base_price] руб.'" 
        // Wait, "от [base_price] руб." usually refers to the INSTALLATION price or the TOTAL?
        // Context: "Product Card". usually "Price: 50 000". If install is "from 10k", total is "50k + from 10k".
        // Current implementation puts "от X Br" in a separate div `non-fixed-message`.
        // The main price `final-price` should probably stay as the Product Price.
        return format(props.basePrice);
    }
    
    // Fixed rate logic
    const total = props.basePrice + (isInstalled.value ? effectiveInstallPrice.value : 0);
    return format(total);
});

// Force ru-RU to match server side rendering (assuming Node uses system or we can enforce)
// Ideally, pass locale as prop or use a consistent formatter
const format = (num) => num.toLocaleString('ru-RU') + ' ' + props.currency;

const toggle = (e) => {
    e.preventDefault();
    e.stopPropagation();
    isInstalled.value = !isInstalled.value;
}
</script>

<template>
  <div class="price-container">
    <!-- Toggle: Only show if allowed (fixed price or default) -->
    <div 
      v-if="shouldShowToogle"
      class="installation-toggle" 
      :class="{ active: isInstalled }"
      @click="toggle"
    >
      <div class="toggle-control">
        <div class="toggle-switch" />
        <span>Монтаж</span>
      </div>
      <span class="inst-price">+{{ effectiveInstallPrice }} {{ currency }}</span>
    </div>

    <!-- Non-fixed rate message (e.g. "from 500 Br") -->
    <div v-if="matchedRate && !matchedRate.is_fixed" class="non-fixed-message">
        Монтаж: <span class="inst-price">от {{ matchedRate.base_price }} {{ currency }}</span>
    </div>

    <div class="p-footer">
       <span class="final-price" :class="{ pulse: isInstalled }">
         {{ priceDisplay }}
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
  
  .non-fixed-message {
    padding: 0.5rem 0;
    font-size: 0.9rem;
    color: var(--text-muted);
    font-weight: 500;
  }
</style>
