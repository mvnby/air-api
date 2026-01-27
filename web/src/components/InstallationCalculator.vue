<script setup>
import { ref, computed, onMounted, watch } from 'vue';
import { getInstallationRates, getGlobalConfig, createOrder } from '../utils/api';

const rates = ref([]);
const loading = ref(true);
const error = ref(null);
const discount = ref(0);

const selectedCategory = ref('');
const selectedRateId = ref(null);
const currentMeters = ref(3);

// CONSTANTS
const BASE_PIPE_LENGTH = 3;

// Frontend Localization Maps
const CATEGORY_MAP = {
  'Wall': 'Настенный',
  'Cassette/Ceiling': 'Кассетный/Потолочный',
  'Cassette': 'Кассетный',
  'Ceiling': 'Напольно-потолочный',
  'Duct': 'Канальный',
  'Multisplit': 'Мульти-сплит'
};

const RANGE_MAP = {
  '07-12': '07-12 (до 35 м²)',
  '18-24': '18-24 (до 70 м²)',
  '30-36': '30-36 (до 100 м²)',
  'area-20, area-25, area-35': '07-12 (до 35 м²)',
  'area-50, area-70': '18-24 (до 70 м²)',
  'area-80, area-100': '30-36 (до 100 м²)',
  'All': 'Любая мощность'
};

onMounted(async () => {
  try {
    const [data, config] = await Promise.all([
        getInstallationRates(),
        getGlobalConfig()
    ]);
    
    if (!data) {
       throw new Error('Не удалось загрузить тарифы');
    }
    rates.value = data;
    
    if (config && config.install_discount) {
        discount.value = parseInt(config.install_discount, 10) || 0;
    }
    
    // Select first category by default if available
    if (rates.value.length > 0) {
      const categories = [...new Set(rates.value.map(r => r.category))];
      if (categories.length > 0) {
        selectedCategory.value = categories[0];
      }
    }
  } catch (err) {
    error.value = err.message;
  } finally {
    loading.value = false;
  }
});

// Computed: Unique Categories
const categories = computed(() => {
  return [...new Set(rates.value.map(r => r.category))];
});

// Computed: Rates for selected category
const categoryRates = computed(() => {
  if (!selectedCategory.value) return [];
  return rates.value.filter(r => r.category === selectedCategory.value);
});

// Computed: The currently active rate object
const activeRate = computed(() => {
  if (!selectedCategory.value) return null;
  // If user selected a specific rate ID, find it
  if (selectedRateId.value) {
    return categoryRates.value.find(r => r.id === selectedRateId.value) || categoryRates.value[0];
  }
  // Default to first one
  return categoryRates.value[0];
});

// Helper to translate
const tCategory = (cat) => CATEGORY_MAP[cat] || cat;
const tRange = (range) => {
    // Try exact match first
    if (RANGE_MAP[range]) return RANGE_MAP[range];
    // If range contains one of the keys (partial match logic for flexibility)
    for (const [key, val] of Object.entries(RANGE_MAP)) {
        if (range.includes(key)) return val;
    }
    return range;
};

// Watch for category change to reset selection or auto-select
watch(selectedCategory, (newVal) => {
  const available = rates.value.filter(r => r.category === newVal);
  if (available.length > 0) {
    selectedRateId.value = available[0].id;
  } else {
    selectedRateId.value = null;
  }
});

// Calculation Logic
const calculatedPrice = computed(() => {
  const rate = activeRate.value;
  if (!rate) return 0;
  
  if (!rate.is_fixed) return rate.base_price;

  const extraMeters = Math.max(0, currentMeters.value - rate.included_pipe_meters);
  return rate.base_price + (extraMeters * rate.extra_pipe_price);
});

const isFixedPrice = computed(() => activeRate.value?.is_fixed ?? true);
const priceComment = computed(() => activeRate.value?.comment);

// --- ORDER LOGIC ---
const showModal = ref(false);
const submitting = ref(false);
const success = ref(false);
const form = ref({
    name: '',
    phone: ''
});

const openOrderModal = () => {
    showModal.value = true;
    success.value = false;
};

const submitOrder = async () => {
    if (!form.value.name || !form.value.phone) return;
    
    submitting.value = true;
    
    // Construct payload
    const payload = {
        customer: {
            name: form.value.name,
            phone: form.value.phone,
        },
        items: [{
            product_id: null,
            quantity: 1,
            with_installation: true,
            installation_price: calculatedPrice.value,
            installation_meta: {
                source: "calculator_page",
                type: tCategory(selectedCategory.value),
                meters: currentMeters.value,
                power_range: activeRate.value?.power_range || "Standard"
            }
        }],
        comment: `Заказ на монтаж из калькулятора. ${currentMeters.value}м трассы.`
    };

    const res = await createOrder(payload);
    
    submitting.value = false;
    if (res) {
        success.value = true;
        form.value = { name: '', phone: '' };
        setTimeout(() => {
            showModal.value = false;
        }, 3000);
    } else {
        alert('Ошибка при отправке заказа. Попробуйте позже.');
    }
};

</script>

<template>
  <div class="calculator-card glass p-8 rounded-3xl" v-if="!loading && !error">
    <h3 class="text-2xl font-bold mb-6 text-teal-900">Калькулятор монтажа</h3>

    <!-- Category Selection -->
    <div class="control-group">
      <label class="label">Тип оборудования</label>
      <div class="category-list">
        <button 
          v-for="cat in categories" 
          :key="cat"
          @click="selectedCategory = cat"
          class="cat-btn"
          :class="{ active: selectedCategory === cat }"
        >
          {{ tCategory(cat) }}
        </button>
      </div>
    </div>

    <!-- Power Range Selection (if multiple) -->
    <div class="control-group" v-if="categoryRates.length > 1">
      <label class="label">Мощность (BTU / кВт)</label>
      <div class="select-wrapper">
        <select v-model="selectedRateId" class="custom-select">
          <option v-for="rate in categoryRates" :key="rate.id" :value="rate.id">
            {{ tRange(rate.power_range || 'Стандарт') }}
          </option>
        </select>
        <span class="material-icons-round select-icon">expand_more</span>
      </div>
    </div>

    <!-- Length Slider -->
    <div class="control-group" v-if="isFixedPrice">
      <div class="range-header">
        <label class="label">Длина трассы</label>
        <div class="range-value">
          {{ currentMeters }} <span>м</span>
        </div>
      </div>
      
      <div class="range-container">
        <input 
            type="range" 
            v-model.number="currentMeters" 
            min="1" 
            max="15" 
            step="0.5"
            class="range-input"
        >
        <div class="range-labels">
            <span>1 м</span>
            <span>15 м</span>
        </div>
      </div>
      
      <p class="helper-text">
        В базовый монтаж включено <strong>{{ activeRate?.included_pipe_meters || 3 }} метра</strong>. 
        Дополнительный метр: <strong>{{ activeRate?.extra_pipe_price }} BYN</strong>
      </p>
    </div>

    <div class="divider"></div>

    <!-- Total Price -->
    <div class="total-section">
      <p class="total-label">Итоговая стоимость</p>
      
      <transition mode="out-in" name="fade-slide">
        <div :key="calculatedPrice" class="price-display">
          <div class="price-value">
             <span v-if="!isFixedPrice" class="price-prefix">от</span>
             {{ calculatedPrice }} 
             <span class="currency">BYN</span>
          </div>
          <p v-if="priceComment" class="price-comment">
             {{ priceComment }}
          </p>
        </div>
      </transition>

      <!-- Promo Banner -->
      <div v-if="discount > 0" class="promo-banner squircle">
        <span class="material-icons-round promo-icon">info</span>
        <p>
          Купите кондиционер у нас и получите скидку <strong>{{ discount }} BYN</strong> на этот монтаж!
        </p>
      </div>

      <button class="action-btn" @click="openOrderModal">
        Заказать монтаж
      </button>
    </div>

    <!-- Modal Portal -->
    <div v-if="showModal" class="modal-overlay" @click.self="showModal = false">
        <div class="modal-card glass">
            <button class="close-btn" @click="showModal = false">
                <span class="material-icons-round">close</span>
            </button>
            
            <div v-if="!success">
                <h3 class="modal-title">Заказать монтаж</h3>
                <p class="modal-desc">Оставьте контакты, и мы свяжемся для уточнения деталей.</p>
                
                <form @submit.prevent="submitOrder" class="order-form">
                    <div class="form-group">
                        <label>Ваше имя</label>
                        <input type="text" v-model="form.name" required placeholder="Иван" class="form-input" />
                    </div>
                    <div class="form-group">
                        <label>Телефон</label>
                        <input type="tel" v-model="form.phone" required placeholder="+375 29 000 00 00" class="form-input" />
                    </div>
                    
                    <button type="submit" class="submit-btn" :disabled="submitting">
                        <span v-if="submitting">Отправка...</span>
                        <span v-else>Отправить заявку</span>
                    </button>
                </form>
            </div>
            
            <div v-else class="success-state">
                <div class="success-icon">
                    <span class="material-icons-round">check_circle</span>
                </div>
                <h3>Заявка принята!</h3>
                <p>Менеджер свяжется с вами в ближайшее время.</p>
            </div>
        </div>
    </div>

  </div>
  
  <div v-else-if="loading" class="calculator-card glass loading">
    Loading...
  </div>

  <div v-else class="error-msg">
    Ошибка загрузки тарифов
  </div>
</template>

<style scoped>
.calculator-card {
    padding: 2rem;
    border-radius: 1.5rem;
    margin-bottom: 2rem;
}

.title {
    font-size: 1.5rem;
    font-weight: 700;
    margin-bottom: 1.5rem;
    color: var(--primary-dark);
}

.control-group {
    margin-bottom: 1.5rem;
}

.label {
    display: block;
    font-size: 0.9rem;
    font-weight: 500;
    color: var(--text-muted);
    margin-bottom: 0.5rem;
}

/* Category Buttons */
.category-list {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
}

.cat-btn {
    padding: 0.5rem 1rem;
    border-radius: 9999px;
    border: 1px solid transparent;
    background: rgba(255, 255, 255, 0.5);
    color: var(--text-muted);
    font-size: 0.9rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.2s;
}

.cat-btn:hover {
    background: rgba(255, 255, 255, 0.8);
    color: var(--text);
}

.cat-btn.active {
    background: var(--primary);
    color: white;
    box-shadow: 0 4px 12px rgba(0, 127, 128, 0.3);
}

/* Custom Select */
.select-wrapper {
    position: relative;
    width: 100%;
}

.custom-select {
    width: 100%;
    appearance: none;
    background: rgba(255, 255, 255, 0.5);
    border: 1px solid var(--border);
    border-radius: 0.75rem;
    padding: 0.75rem 1rem;
    font-size: 1rem;
    color: var(--text);
    cursor: pointer;
    transition: all 0.2s;
}

.custom-select:focus {
    outline: none;
    border-color: var(--primary);
    box-shadow: 0 0 0 3px rgba(0, 127, 128, 0.1);
}

.select-icon {
    position: absolute;
    right: 1rem;
    top: 50%;
    transform: translateY(-50%);
    pointer-events: none;
    color: var(--text-muted);
}

/* Slider */
.range-header {
    display: flex;
    justify-content: space-between;
    align-items: flex-end;
    margin-bottom: 0.5rem;
}

.range-value {
    font-size: 2rem;
    font-weight: 700;
    color: var(--primary);
    line-height: 1;
}

.range-value span {
    font-size: 1rem;
    font-weight: 400;
    color: var(--text-muted);
}

.range-container {
    padding: 0.5rem 0;
}

.range-input {
    width: 100%;
    height: 8px;
    background: #e5e7eb;
    border-radius: 4px;
    appearance: none;
    cursor: pointer;
}

.range-input::-webkit-slider-thumb {
    appearance: none;
    width: 24px;
    height: 24px;
    background: var(--primary);
    border-radius: 50%;
    cursor: pointer;
    box-shadow: 0 2px 6px rgba(0, 0, 0, 0.2);
    transition: transform 0.1s;
}

.range-input::-webkit-slider-thumb:hover {
    transform: scale(1.1);
}

.range-labels {
    display: flex;
    justify-content: space-between;
    font-size: 0.75rem;
    color: var(--text-muted);
    margin-top: 0.25rem;
}

.helper-text {
    font-size: 0.875rem;
    color: var(--text-muted);
    margin-top: 1rem;
    line-height: 1.5;
}

.helper-text strong {
    color: var(--text);
    font-weight: 600;
}

.divider {
    height: 1px;
    background: rgba(0, 0, 0, 0.05); /* very subtle */
    margin: 2rem 0;
}

/* Total Section */
.total-section {
    text-align: center;
}

.total-label {
    font-size: 0.9rem;
    color: var(--text-muted);
    margin-bottom: 0.5rem;
}

.price-value {
    font-size: 3rem;
    font-weight: 800;
    color: var(--primary);
    line-height: 1;
    margin-bottom: 0.5rem;
    letter-spacing: -0.02em;
}

.price-prefix {
    font-size: 1.5rem;
    vertical-align: top;
    margin-right: 0.25rem;
    font-weight: 500;
}

.currency {
    font-size: 1.5rem;
    vertical-align: top;
    color: var(--text-muted);
    font-weight: 400;
}

.price-comment {
    display: inline-block;
    padding: 0.25rem 0.75rem;
    background: #fff7ed;
    color: #c2410c;
    border-radius: 0.5rem;
    font-size: 0.875rem;
    font-weight: 500;
}

/* Promo Banner */
.promo-banner {
    margin-top: 1.5rem;
    background: #f0fdfa; /* Teal-50 */
    border: 1px solid #99f6e4; /* Teal-200 */
    padding: 1rem;
    display: flex;
    align-items: center;
    gap: 0.75rem;
    text-align: left;
    color: #0f766e; /* Teal-700 */
    box-shadow: 0 4px 12px rgba(13, 148, 136, 0.1);
}

.promo-banner p {
    font-size: 0.9rem;
    line-height: 1.4;
    margin: 0;
}

.promo-banner strong {
    color: var(--primary);
    font-weight: 700;
}

.promo-icon {
    color: var(--primary);
    font-size: 1.25rem;
}

.squircle {
    border-radius: 12px;
}

/* Animations */
.fade-slide-enter-active,
.fade-slide-leave-active {
  transition: all 0.3s ease;
}

.fade-slide-enter-from {
  opacity: 0;
  transform: translateY(10px);
}

.fade-slide-leave-to {
  opacity: 0;
  transform: translateY(-10px);
}

.error-msg {
    text-align: center;
    color: #ef4444;
    padding: 2rem;
}

/* Modal Styles */
.action-btn {
    margin-top: 1.5rem;
    width: 100%;
    padding: 1rem;
    border: none;
    border-radius: 12px;
    background: var(--primary);
    color: white;
    font-size: 1.1rem;
    font-weight: 700;
    cursor: pointer;
    transition: background 0.2s, transform 0.1s;
    box-shadow: 0 4px 12px rgba(0, 127, 128, 0.4);
}
.action-btn:hover {
    background: #006b6c;
    transform: translateY(-2px);
}
.action-btn:active {
    transform: translateY(0);
}

.modal-overlay {
    position: fixed;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    background: rgba(0,0,0,0.5);
    backdrop-filter: blur(4px);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 9999;
    padding: 1rem;
}

.modal-card {
    background: white; /* Fallback */
    background: rgba(255, 255, 255, 0.95);
    width: 100%;
    max-width: 400px;
    padding: 2rem;
    border-radius: 1.5rem;
    position: relative;
    box-shadow: 0 20px 40px rgba(0,0,0,0.2);
    animation: slideUp 0.3s ease-out;
}

@keyframes slideUp {
    from { transform: translateY(20px); opacity: 0; }
    to { transform: translateY(0); opacity: 1; }
}

.close-btn {
    position: absolute;
    top: 1rem;
    right: 1rem;
    background: none;
    border: none;
    cursor: pointer;
    color: var(--text-muted);
}

.modal-title {
    font-size: 1.5rem;
    font-weight: 700;
    margin-bottom: 0.5rem;
    color: var(--primary-dark);
}
.modal-desc {
    color: var(--text-muted);
    font-size: 0.9rem;
    margin-bottom: 1.5rem;
}

.form-group {
    margin-bottom: 1rem;
}
.form-group label {
    display: block;
    margin-bottom: 0.5rem;
    font-weight: 500;
    font-size: 0.9rem;
    color: var(--text);
}
.form-input {
    width: 100%;
    padding: 0.75rem 1rem;
    border: 1px solid var(--border);
    border-radius: 0.75rem;
    font-size: 1rem;
    transition: all 0.2s;
}
.form-input:focus {
    outline: none;
    border-color: var(--primary);
    box-shadow: 0 0 0 3px rgba(0, 127, 128, 0.1);
}

.submit-btn {
    width: 100%;
    padding: 1rem;
    margin-top: 1rem;
    background: var(--primary);
    color: white;
    font-weight: 700;
    border: none;
    border-radius: 0.75rem;
    cursor: pointer;
    transition: background 0.2s;
}
.submit-btn:disabled {
    background: #ccc;
    cursor: not-allowed;
}

.success-state {
    text-align: center;
    padding: 1rem 0;
}
.success-icon {
    font-size: 4rem;
    color: var(--primary);
    margin-bottom: 1rem;
}
.success-icon .material-icons-round {
    font-size: 4rem;
}
</style>
