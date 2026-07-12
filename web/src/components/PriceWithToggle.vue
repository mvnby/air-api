<script setup>
import { ref, computed, onMounted, watch, nextTick } from 'vue';
import { getInstallationRates, getGlobalConfig, getProductById, submitProductAvailabilityLead } from '../utils/api';
import { addItem } from '../store/cart';
import { addToast } from '../store/toast';
import { formatPhoneForDisplay, validateRequiredBelarusPhone } from '../utils/validation';
import {
    formatProductPrice,
    hasKnownProductPrice,
    resolveProductAvailability,
} from '../utils/product-display';
import {
    calculateInstallationPrice,
    matchProductInstallationRate,
} from '../utils/installation-pricing';

const props = defineProps({
  basePrice: { type: [Number, String], default: 0 },
  oldPrice: { type: [Number, String], default: 0 },
  installPrice: { type: Number, default: 600 }, // Fallback/Legacy
  currency: { type: String, default: 'р.' },
  showToggle: { type: Boolean, default: true },
  tags: { type: Array, default: () => [] },
  large: { type: Boolean, default: false },
  // Data for Cart
  id: { type: String, default: '' },
  productId: { default: 0 },
  title: { type: String, default: '' },
  image: { type: String, default: '' },
  area: { type: Number, default: 0 },
  vitebskQty: { type: Number, default: 0 },
  minskQty: { type: Number, default: 0 },
  availabilityStatus: { type: String, default: null },
  installationRates: { type: Array, default: null },
  installDiscount: { type: Number, default: null },
  refreshProductOnMount: { type: Boolean, default: true }
});

const isInstalled = ref(false);
const rates = ref([]);
const discount = ref(0);
const loading = ref(true);
const buttonState = ref('default');
const showNotifyModal = ref(false);
const notifySubmitting = ref(false);
const notifySuccess = ref(false);
const notifyPhoneError = ref('');
const notifyForm = ref({
    name: '',
    phone: '',
});
const notifyPhoneInputRef = ref(null);

const liveBasePrice = ref(Number(props.basePrice) || 0);
const liveOldPrice = ref(Number(props.oldPrice) || 0);
const liveVitebskQty = ref(Number(props.vitebskQty) || 0);
const liveMinskQty = ref(Number(props.minskQty) || 0);
const liveAvailabilityStatus = ref(props.availabilityStatus);

onMounted(async () => {
    try {
        const shouldUseProvidedRates = Array.isArray(props.installationRates) && props.installationRates.length > 0;
        const shouldUseProvidedDiscount = props.installDiscount !== null && props.installDiscount !== undefined;
        const [ratesData, configData, freshProduct] = await Promise.all([
            shouldUseProvidedRates ? Promise.resolve(props.installationRates) : getInstallationRates(),
            shouldUseProvidedDiscount ? Promise.resolve(null) : getGlobalConfig(),
            props.refreshProductOnMount && props.productId ? getProductById(props.productId) : Promise.resolve(null)
        ]);
        rates.value = ratesData || [];
        if (shouldUseProvidedDiscount) {
            discount.value = Number(props.installDiscount) || 0;
        } else if (configData && configData.install_discount) {
            discount.value = parseInt(configData.install_discount, 10) || 0;
        }
        if (freshProduct && freshProduct.price !== undefined) {
            liveBasePrice.value = Number(freshProduct.price) || 0;
            liveOldPrice.value = Number(freshProduct.old_price) || 0;
            liveVitebskQty.value = Number(freshProduct.vitebsk_qty) || 0;
            liveMinskQty.value = Number(freshProduct.minsk_qty) || 0;
            liveAvailabilityStatus.value = freshProduct.availability_status;
        }
    } finally {
        loading.value = false;
    }
});

watch(showNotifyModal, async (isOpen) => {
    if (isOpen) {
        await nextTick();
        if (notifyPhoneInputRef.value) {
            notifyPhoneInputRef.value.onfocus = () => {
                if (!notifyForm.value.phone.trim()) notifyForm.value.phone = '+375 ';
                notifyPhoneError.value = '';
            };
        }
        return;
    }

    notifyPhoneError.value = '';
});

const matchedRate = computed(() => {
    return matchProductInstallationRate({
        rates: rates.value,
        tags: props.tags,
        area: props.area,
    });
});

// Computed logic for display
const effectiveInstallPrice = computed(() => {
    if (matchedRate.value && matchedRate.value.is_fixed) {
        return matchedRate.value.base_price;
    }
    return props.installPrice; 
});

const installationQuote = computed(() => calculateInstallationPrice({
    rate: matchedRate.value,
    meters: 3,
    bundleDiscount: discount.value,
    applyBundleDiscount: true,
}));

// Price WITH discount applied
const finalInstallPrice = computed(() => {
    if (installationQuote.value.status === 'fixed') {
        return installationQuote.value.total;
    }
    return props.installPrice;
});

const hasKnownPrice = computed(() => hasKnownProductPrice(liveBasePrice.value));

const availabilityState = computed(() => {
    return resolveProductAvailability({
        vitebskQty: liveVitebskQty.value,
        minskQty: liveMinskQty.value,
        availabilityStatus: liveAvailabilityStatus.value,
    });
});

const availabilityMessage = computed(() => {
    return availabilityState.value.message;
});

const availabilityTone = computed(() => {
    return availabilityState.value.tone;
});

const isExplicitOutOfStock = computed(() => {
    return availabilityState.value.isExplicitOutOfStock;
});

const shouldOpenInquiry = computed(() => {
    return !hasKnownPrice.value || !availabilityState.value.canOrder;
});

const canAddToCart = computed(() => {
    return hasKnownPrice.value && availabilityState.value.canOrder;
});

const shouldShowToggle = computed(() => {
    if (!canAddToCart.value) return false;
    if (!matchedRate.value) return false;
    if (!matchedRate.value.is_fixed) return false;
    return props.showToggle;
});

// Force ru-RU to match server side rendering
const format = (num) => Number(num).toLocaleString('ru-RU');

const priceDisplay = computed(() => {
    if (!hasKnownPrice.value) {
        return {
            current: formatProductPrice(liveBasePrice.value),
            old: null,
            showCurrency: false,
            isInquiry: true,
        };
    }

    // Case 1: No match or non-fixed -> Just Product Price
    if (!matchedRate.value || !matchedRate.value.is_fixed) {
         return {
             current: format(liveBasePrice.value),
             old: null,
             showCurrency: true,
             isInquiry: false,
         };
    }
    
    // Case 2: Fixed rate but NOT toggled -> Just Product Price
    if (!isInstalled.value) {
        return {
            current: format(liveBasePrice.value),
            old: null,
            showCurrency: true,
            isInquiry: false,
        };
    }

    // Case 3: Fixed rate + Toggled -> Product + Discounted Install
    const total = Number(liveBasePrice.value) + Number(finalInstallPrice.value);
    const oldTotal = Number(liveBasePrice.value) + Number(effectiveInstallPrice.value);

    return {
        current: format(total),
        old: discount.value > 0 ? format(oldTotal) : null,
        showCurrency: true,
        isInquiry: false,
    };
});

const discountPct = computed(() => {
    if (!liveOldPrice.value || !hasKnownPrice.value) return 0;
    const diff = liveOldPrice.value - liveBasePrice.value;
    return diff > 0 ? Math.round((diff / liveOldPrice.value) * 100) : 0;
});

const toggle = (e) => {
    e.preventDefault();
    e.stopPropagation();
    isInstalled.value = !isInstalled.value;
}

const addToCart = () => {
    if (!canAddToCart.value) return;
    if (!props.id) return;
    
    const added = addItem({
        id: props.id,
        name: props.title,
        price: Number(liveBasePrice.value),
        image: props.image,
        productId: props.productId,
        withInstallation: isInstalled.value,
        installationPrice: finalInstallPrice.value, // Use discounted price
        installationRateId: matchedRate.value?.id || null,
    });
    if (!added) {
        addToast('В одном заказе может быть не больше 20 разных позиций', 'error');
        return;
    }
    
    // Feedback: Toast + Button State
    addToast(`Добавлено в корзину: ${props.title}`);
    
    buttonState.value = 'success';
    setTimeout(() => {
        buttonState.value = 'default';
    }, 2000);
}

const buttonLabel = computed(() => {
    if (!hasKnownPrice.value && availabilityState.value.isUnknown) return 'Уточнить цену и наличие';
    if (!hasKnownPrice.value) return 'Уточнить цену';
    if (isExplicitOutOfStock.value) return 'Сообщить о поступлении';
    if (!availabilityState.value.canOrder) return 'Уточнить наличие';
    return buttonState.value === 'success' ? 'Добавлено' : 'В корзину';
});

const buttonIcon = computed(() => {
    if (isExplicitOutOfStock.value) return 'notifications_active';
    if (shouldOpenInquiry.value) return 'support_agent';
    return buttonState.value === 'success' ? 'check' : 'shopping_cart';
});

const buttonVariant = computed(() => {
    return shouldOpenInquiry.value ? 'notify' : 'primary';
});

const inquiryModalTitle = computed(() => {
    if (!hasKnownPrice.value && availabilityState.value.isUnknown) return 'Уточнить цену и наличие';
    if (!hasKnownPrice.value) return 'Уточнить цену';
    if (isExplicitOutOfStock.value) return 'Сообщить о поступлении';
    return 'Уточнить наличие';
});

const inquiryModalDescription = computed(() => {
    if (!hasKnownPrice.value && availabilityState.value.isUnknown) {
        return 'Оставьте телефон, и мы уточним цену и наличие этой модели.';
    }
    if (!hasKnownPrice.value) {
        return 'Оставьте телефон, и мы уточним актуальную цену этой модели.';
    }
    if (isExplicitOutOfStock.value) {
        return 'Оставьте телефон, и мы сообщим, когда модель появится в наличии.';
    }
    return 'Оставьте телефон, и мы уточним наличие и срок поставки этой модели.';
});

const inquirySuccessText = computed(() => {
    if (isExplicitOutOfStock.value) return 'Сообщим, когда товар появится в наличии.';
    return 'Менеджер свяжется с вами и уточнит детали.';
});

const validateNotifyPhone = () => {
    notifyForm.value.phone = formatPhoneForDisplay(notifyForm.value.phone);
    notifyPhoneError.value = validateRequiredBelarusPhone(
        notifyForm.value.phone,
        true,
    );
    return !notifyPhoneError.value;
};

const openNotifyModal = () => {
    showNotifyModal.value = true;
};

const closeNotifyModal = () => {
    showNotifyModal.value = false;
    notifySubmitting.value = false;
    notifySuccess.value = false;
    notifyPhoneError.value = '';
    notifyForm.value = { name: '', phone: '' };
};

const handlePrimaryAction = () => {
    if (shouldOpenInquiry.value) {
        openNotifyModal();
        return;
    }
    addToCart();
};

const submitNotifyLead = async () => {
    if (!validateNotifyPhone()) return;
    if (!props.productId) return;

    notifySubmitting.value = true;
    const result = await submitProductAvailabilityLead({
        product_id: Number(props.productId),
        phone: notifyForm.value.phone,
        name: (notifyForm.value.name || '').trim() || null,
    });
    notifySubmitting.value = false;

    if (!result) {
        notifyPhoneError.value = 'Не удалось отправить запрос. Попробуйте позже.';
        return;
    }

    notifySuccess.value = true;
    addToast(`Запрос отправлен: ${props.title}`);
    setTimeout(() => {
        closeNotifyModal();
    }, 2500);
};
</script>

<template>
  <div class="price-container" :class="{ 'size-large': large }">
    <!-- Price Display -->
    <div class="price-wrapper">
        <!-- Sale Badge -->
        <div v-if="discountPct > 0" class="discount-badge sale-badge">
          -{{ discountPct }}%
        </div>
        
        <span v-if="priceDisplay.old" class="old-price">
            {{ priceDisplay.old }} <span class="price-byn"></span>
        </span>
        <span class="final-price" :class="{ 'pulse-primary': isInstalled }">
          {{ priceDisplay.current }} <span v-if="priceDisplay.showCurrency" class="price-byn"></span>
        </span>
    </div>

    <div
      v-if="availabilityMessage"
      class="availability-note"
      :class="availabilityTone"
    >
      {{ availabilityMessage }}
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
                  +{{ finalInstallPrice }} <span class="price-byn"></span>
                </span>
             </div>
             <span v-else class="inst-price">
                +{{ effectiveInstallPrice }} <span class="price-byn"></span>
             </span>
          </div>
      </div>
    </div>

    <!-- Non-fixed rate message -->
    <div v-if="matchedRate && !matchedRate.is_fixed" class="non-fixed-message">
        Монтаж: <span class="inst-price">от {{ matchedRate.base_price }} <span class="price-byn"></span></span>
    </div>

    <!-- Actions (Centered) -->
    <div class="actions-container">
        <button 
            class="btn-action js-track-cart"
            :class="[buttonVariant, { success: buttonState === 'success' && canAddToCart }]"
            @click.stop="handlePrimaryAction"
        >
            <span class="material-icons-round">{{ buttonIcon }}</span>
            {{ buttonLabel }}
        </button>
        <!-- "Buy in 1 click" removed for micro cards, kept for large if requested? 
             User specifically said remove quick order from thumbnails. 
             In large view (product page) it might be useful, but user said "it doesn't work".
             Removing from everywhere to be safe and clean.
        -->
    </div>

    <div v-if="showNotifyModal" class="modal-overlay" @click.self="closeNotifyModal">
      <div class="modal-card glass">
        <button class="modal-close-btn" @click="closeNotifyModal" type="button">
          <span class="material-icons-round">close</span>
        </button>

        <div v-if="!notifySuccess">
          <h3 class="modal-title">{{ inquiryModalTitle }}</h3>
          <p class="modal-desc">
            {{ inquiryModalDescription }}
          </p>

          <form class="notify-form" @submit.prevent="submitNotifyLead">
            <div class="form-group">
              <label>Ваше имя</label>
              <input
                v-model="notifyForm.name"
                type="text"
                class="form-input"
                placeholder="Необязательно"
              />
            </div>

            <div class="form-group">
              <label>Телефон</label>
              <input
                ref="notifyPhoneInputRef"
                v-model="notifyForm.phone"
                type="tel"
                class="form-input"
                :class="{ invalid: notifyPhoneError }"
                placeholder="+375 (XX) XXX-XX-XX или +7 XXX XXX-XX-XX"
                @blur="validateNotifyPhone"
              />
              <span v-if="notifyPhoneError" class="err-msg">{{ notifyPhoneError }}</span>
            </div>

            <button type="submit" class="submit-btn" :disabled="notifySubmitting">
              <span v-if="notifySubmitting">Отправка…</span>
              <span v-else>Отправить</span>
            </button>
          </form>
        </div>

        <div v-else class="success-state">
          <div class="success-icon">
            <span class="material-icons-round">check_circle</span>
          </div>
          <h3>Запрос отправлен</h3>
          <p>{{ inquirySuccessText }}</p>
        </div>
      </div>
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
    transition:
      color 0.3s cubic-bezier(0.4, 0, 0.2, 1),
      transform 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  }

  .pulse-primary {
    color: var(--primary);
    transform: scale(1.05);
  }

  .availability-note {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    text-align: center;
    font-size: 0.9rem;
    font-weight: 600;
    color: #475569;
    background: rgba(148, 163, 184, 0.12);
    border: 1px solid rgba(100, 116, 139, 0.22);
    border-radius: 999px;
    padding: 0.45rem 0.9rem;
    width: auto;
    max-width: 100%;
  }

  .availability-note.vitebsk {
    color: #0f766e;
    background: rgba(15, 118, 110, 0.12);
    border-color: rgba(15, 118, 110, 0.32);
  }

  .availability-note.minsk {
    color: #0369a1;
    background: rgba(3, 105, 161, 0.10);
    border-color: rgba(3, 105, 161, 0.22);
  }

  :global(.dark .availability-note) {
    color: rgba(241, 245, 249, 0.82);
    background: rgba(148, 163, 184, 0.14);
    border-color: rgba(148, 163, 184, 0.24);
  }

  :global(.dark .availability-note.vitebsk) {
    color: #f0fdfa;
    background: #115e59;
    border-color: rgba(94, 234, 212, 0.55);
  }

  :global(.dark .availability-note.minsk) {
    color: #7dd3fc;
    background: rgba(3, 105, 161, 0.16);
    border-color: rgba(125, 211, 252, 0.22);
  }

  /* Discount Badge (Orange) */
  .discount-badge {
    position: absolute;
    top: -12px;
    right: -24px;
    background: #c2410c;
    color: #fff7ed;
    font-size: 0.75rem;
    font-weight: 800;
    padding: 2px 8px;
    border-radius: 6px;
    box-shadow: 0 4px 12px rgba(194, 65, 12, 0.32);
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
    transition:
      border-color 0.2s ease,
      background-color 0.2s ease,
      transform 0.2s ease;
  }
  
  .installation-toggle:hover {
    border-color: var(--primary);
    background: rgba(0, 127, 128, 0.06);
  }

  .installation-toggle.active {
    background: rgba(0, 127, 128, 0.1);
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
    transition:
      left 0.3s ease,
      background-color 0.3s ease;
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
      color: #0f766e;
      font-weight: 800;
      font-size: 0.95rem;
  }

  :global(.dark .discount-price) {
      color: #99f6e4;
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
      transition:
        background-color 0.2s ease,
        color 0.2s ease,
        transform 0.2s ease,
        box-shadow 0.2s ease,
        border-color 0.2s ease;
      border: none;
      font-family: inherit;
      width: 100%;
      max-width: 240px;
  }

  .btn-action.primary {
      background: var(--primary);
      color: white;
      box-shadow: 0 4px 15px rgba(0, 127, 128, 0.3);
  }

  .btn-action.primary:hover {
      background: var(--primary-dark);
      transform: translateY(-2px);
      box-shadow: 0 6px 20px rgba(0, 127, 128, 0.4);
  }

  .btn-action.notify {
      background: #fff7ed;
      color: #b45309;
      border: 1px solid #fdba74;
      box-shadow: 0 4px 15px rgba(251, 146, 60, 0.18);
  }

  .btn-action.notify:hover {
      background: #ffedd5;
      transform: translateY(-2px);
      box-shadow: 0 6px 20px rgba(251, 146, 60, 0.22);
  }

  .btn-action.primary.success {
      background: #10b981; /* Emerald 500 */
      box-shadow: 0 4px 15px rgba(16, 185, 129, 0.4);
      pointer-events: none;
  }

  .btn-action.primary:active {
      transform: translateY(0);
  }

  .btn-action.notify:active {
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

  .size-large .availability-note {
    font-size: 1rem;
  }

  .modal-overlay {
    position: fixed;
    inset: 0;
    background: rgba(15, 23, 42, 0.45);
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 1rem;
    z-index: 120;
  }

  .modal-card {
    position: relative;
    width: min(100%, 420px);
    border-radius: 1.5rem;
    padding: 1.5rem;
    background: var(--panel-glass-bg);
    border: 1px solid var(--panel-glass-border);
    box-shadow: 0 24px 60px rgba(15, 23, 42, 0.22);
  }

  .modal-close-btn {
    position: absolute;
    top: 0.75rem;
    right: 0.75rem;
    border: none;
    background: transparent;
    color: var(--text-muted);
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    justify-content: center;
  }

  .modal-title {
    margin: 0 0 0.5rem;
    font-size: 1.35rem;
    font-weight: 800;
  }

  .modal-desc {
    margin: 0 0 1.25rem;
    color: var(--text-muted);
    line-height: 1.5;
  }

  .notify-form {
    display: flex;
    flex-direction: column;
    gap: 1rem;
  }

  .form-group {
    display: flex;
    flex-direction: column;
    gap: 0.45rem;
  }

  .form-group label {
    font-size: 0.9rem;
    font-weight: 600;
    color: var(--text-muted);
  }

  .form-input {
    border: 1px solid var(--border);
    border-radius: 0.85rem;
    padding: 0.85rem 1rem;
    font: inherit;
    color: var(--text);
    background: white;
  }

  .form-input.invalid {
    border-color: #dc2626;
  }

  .form-input:focus {
    outline: none;
    border-color: var(--primary);
    box-shadow: 0 0 0 3px rgba(0, 127, 128, 0.12);
  }

  .err-msg {
    font-size: 0.85rem;
    color: #dc2626;
  }

  .submit-btn {
    border: none;
    border-radius: 1rem;
    padding: 0.95rem 1.1rem;
    font: inherit;
    font-weight: 700;
    color: white;
    background: var(--primary);
    cursor: pointer;
  }

  .submit-btn:disabled {
    opacity: 0.7;
    cursor: wait;
  }

  .success-state {
    text-align: center;
    padding: 1rem 0.5rem;
  }

  .success-icon {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 4rem;
    height: 4rem;
    border-radius: 999px;
    color: #10b981;
    background: #ecfdf5;
    margin-bottom: 0.75rem;
  }

  .success-icon .material-icons-round {
    font-size: 2rem;
  }

  @media (max-width: 640px) {
    .modal-card {
      padding: 1.25rem;
    }
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
