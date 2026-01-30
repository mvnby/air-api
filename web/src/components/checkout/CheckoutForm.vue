<script setup>
import { ref, computed, onMounted } from 'vue';
import { useStore } from '@nanostores/vue';
import { cartItems, cartTotal, clearCart, refreshPrices } from '../../store/cart';
import { createOrder, getProductBySlug } from '../../utils/api';

// State
const form = ref({
    name: '',
    phone: '',
    address: '',
    comment: ''
});
const errors = ref({});
const isSubmitting = ref(false);
const submitError = ref(null);

const items = useStore(cartItems);
const total = useStore(cartTotal);
const formatPrice = (p) => p.toLocaleString('ru-RU') + ' р.';

// Validation
const validate = () => {
    errors.value = {};
    if (!form.value.name) errors.value.name = 'Введите имя';
    if (!form.value.phone) errors.value.phone = 'Введите телефон';
    // Simple phone check, basic length
    if (form.value.phone && form.value.phone.replace(/\D/g, '').length < 9) {
        errors.value.phone = 'Некорректный номер';
    }
    return Object.keys(errors.value).length === 0;
};

// Refresh prices on mount to ensure freshness
onMounted(() => {
    refreshPrices();
});

const submitOrderHandler = async () => {
    if (!validate()) return;
    if (items.value.length === 0) return;

    isSubmitting.value = true;
    submitError.value = null;

    try {
        // Prepare items with ID resolution
        // Note: now refreshPrices ensures we have productId, but in case it's missing (e.g. offline/fail),
        // we might still try to fetch or fail gracefully.
        
        const orderItems = await Promise.all(items.value.map(async (i) => {
            let pid = i.productId;
            if (!pid) {
                // Fallback: Fetch ID by slug from API if not in store
                try {
                   const p = await getProductBySlug(i.id);
                   if (p && p.id) pid = p.id;
                } catch (e) {
                   console.error("Failed to fetch ID for", i.id);
                }
            }
            
            if (!pid) throw new Error(`Не удалось получить ID для товара: ${i.name}`);
            
            return {
                product_id: pid,
                quantity: i.quantity,
                // Installation snapshot fields (Phase: Snapshot Pricing Refactor)
                with_installation: i.withInstallation || false,
                installation_price: i.withInstallation ? (i.installationPrice || 0) : 0,
                installation_meta: i.withInstallation ? {
                    source: "web_calculator",
                    discount_applied: true,
                    base_rate: i.installationPrice ? i.installationPrice + 100 : 0,  // Assuming 100 BYN discount rough calc if not strict
                    meters: i.installationMeters || 3,
                    options: i.installationOptions || []
                } : null,
                installation_options: i.installationOptions || []
            };
        }));

        const payload = {
            customer: {
                name: form.value.name,
                phone: form.value.phone,
                address: form.value.address
            },
            comment: form.value.comment,
            items: orderItems
        };

        const res = await createOrder(payload);

        if (!res) {
             throw new Error('Ошибка при создании заказа. Пожалуйста, попробуйте позже.');
        }

        // Success
        clearCart();
        window.location.href = '/success';

    } catch (e) {
        console.error(e);
        // If API unified error handling threw with structure
        if (e.details && Array.isArray(e.details.detail)) {
             submitError.value = e.details.detail.map(err => `${err.loc.join('.')}: ${err.msg}`).join('; ');
        } else if (e.details && typeof e.details.detail === 'string') {
             submitError.value = e.details.detail;
        } else {
             submitError.value = e.message;
        }
    } finally {
        isSubmitting.value = false;
    }
};

// Phone mask helper (simplistic)
const onPhoneInput = (e) => {
    // Only basic cleaning
    form.value.phone = e.target.value; 
}
</script>

<template>
<div class="checkout-container">
    <div v-if="items.length === 0" key="empty" class="empty-msg"> 
        <h2>Корзина пуста</h2>
        <a href="/catalog">В каталог</a>
    </div>

    <div v-if="items.length > 0" key="form" class="checkout-layout-grid-v2">
        <!-- Form -->
        <div class="form-section card">
            <h2>Оформление заказа</h2>
            
            <form @submit.prevent="submitOrderHandler" class="checkout-form">
                <div class="form-group">
                    <label for="name">Имя <span class="req">*</span></label>
                    <input 
                        type="text" 
                        id="name" 
                        v-model="form.name" 
                        :class="{ invalid: errors.name }"
                        placeholder="Иван Иванович"
                    />
                    <span v-if="errors.name" class="err-msg">{{ errors.name }}</span>
                </div>

                <div class="form-group">
                    <label for="phone">Телефон <span class="req">*</span></label>
                    <input 
                        type="tel" 
                        id="phone" 
                        v-model="form.phone" 
                        @input="onPhoneInput"
                        :class="{ invalid: errors.phone }"
                        placeholder="+375 (XX) XXX-XX-XX"
                    />
                    <span v-if="errors.phone" class="err-msg">{{ errors.phone }}</span>
                </div>

                <div class="form-group">
                    <label for="address">Адрес доставки</label>
                    <textarea 
                        id="address" 
                        v-model="form.address" 
                        placeholder="г. Витебск, ул. ..."
                        rows="3"
                    ></textarea>
                </div>

                <div class="form-group">
                    <label for="comment">Комментарий к заказу</label>
                    <textarea 
                        id="comment" 
                        v-model="form.comment" 
                        placeholder="Код домофона, желаемое время и т.д."
                        rows="2"
                    ></textarea>
                </div>

                <div v-if="submitError" class="submit-error">
                    <span class="material-icons-round">error</span>
                    {{ submitError }}
                </div>

                <!-- Mobile Action -->
                <div class="mobile-action">
                    <button type="submit" class="btn btn-primary btn-block big" :disabled="isSubmitting">
                        {{ isSubmitting ? 'Отправка...' : 'Подтвердить заказ' }}
                    </button>
                    <p class="privacy-note">Нажимая кнопку, вы соглашаетесь с условиями обработки персональных данных</p>
                </div>
            </form>
        </div>

        <!-- Summary Sidebar -->
        <div class="summary-section sticky-sidebar">
            <div class="card summary-card">
                <h3>Ваш заказ</h3>
                <div class="items-list">
                    <div v-for="item in items" :key="item.id+item.withInstallation" class="mini-item">
                        <span class="name">{{ item.name }} <span class="qty">x{{ item.quantity }}</span></span>
                        <span class="price">{{ formatPrice((item.price + (item.withInstallation ? item.installationPrice : 0)) * item.quantity) }}</span>
                    </div>
                </div>
                <div class="divider"></div>
                <div class="total-row">
                    <span>Итого:</span>
                    <span class="total-val">{{ formatPrice(total) }}</span>
                </div>
                
                <div class="desktop-action">
                    <button @click="submitOrderHandler" class="btn btn-primary btn-block big" :disabled="isSubmitting">
                         {{ isSubmitting ? 'Отправка...' : 'Подтвердить заказ' }}
                    </button>
                     <p class="privacy-note">Нажимая кнопку, вы соглашаетесь с условиями обработки персональных данных</p>
                </div>
            </div>
            
            <a href="/cart" class="back-link">
                <span class="material-icons-round">arrow_back</span>
                Вернуться в корзину
            </a>
        </div>
    </div>
</div>
</template>

<style>
/* Layout Grid (Desktop) */
/* Layout logic moved to Astro pages for global scope */

.card {
    background: var(--surface);
    padding: 2.5rem;
    border-radius: 2rem;
    box-shadow: 0 10px 30px rgba(0, 0, 0, 0.05);
    border: 1px solid var(--border);
}

h2 {
    font-size: 1.5rem;
    font-weight: 700;
    margin-bottom: 2rem;
    color: var(--text);
}

.form-group {
    margin-bottom: 1.5rem;
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
}
label {
    font-weight: 600;
    font-size: 0.95rem;
    color: var(--text-muted);
}
.req { color: #ef4444; }

input, textarea {
    width: 100%;
    padding: 0.8rem 1rem;
    border-radius: 0.75rem;
    border: 1px solid var(--border);
    font-size: 1rem;
    transition: border-color 0.2s, box-shadow 0.2s;
    font-family: inherit;
    background: var(--bg);
    color: var(--text);
}
input:focus, textarea:focus {
    outline: none;
    border-color: #007f80;
    box-shadow: 0 0 0 3px rgba(0, 127, 128, 0.1);
}
input.invalid {
    border-color: #ef4444;
}

.err-msg {
    font-size: 0.85rem;
    color: #ef4444;
}

.items-list {
    margin-bottom: 1.5rem;
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
}
.mini-item {
    display: flex;
    justify-content: space-between;
    font-size: 0.95rem;
    line-height: 1.4;
}
.mini-item .name {
    color: var(--text-muted);
    padding-right: 1rem;
}
.mini-item .qty {
    color: var(--text-muted);
    font-weight: 600;
}
.mini-item .price {
    font-weight: 600;
    color: var(--text);
    white-space: nowrap;
}

.divider {
    height: 1px;
    background: #e2e8f0;
    margin: 1rem 0;
}
.total-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-size: 1.25rem;
    font-weight: 800;
    color: var(--text);
    margin-bottom: 2rem;
}

.btn.big {
    padding: 1.2rem;
    font-size: 1.1rem;
}
.privacy-note {
    font-size: 0.75rem;
    color: #94a3b8;
    margin-top: 1rem;
    text-align: center;
    line-height: 1.4;
}

.back-link {
    display: inline-flex;
    align-items: center;
    gap: 0.5rem;
    margin-top: 1.5rem;
    color: #64748b;
    font-weight: 500;
    text-decoration: none;
    transition: color 0.2s;
}
.back-link:hover {
    color: #007f80;
}

.sticky-sidebar {
    position: sticky;
    top: 2rem;
}

.mobile-action {
    display: none;
}
.submit-error {
    background: #fef2f2;
    color: #ef4444;
    padding: 1rem;
    border-radius: 0.75rem;
    margin-bottom: 1.5rem;
    display: flex;
    align-items: center;
    gap: 0.5rem;
    font-size: 0.9rem;
}

@media (max-width: 900px) {
    .checkout-layout-grid-v2 {
        grid-template-columns: 1fr;
        gap: 3rem;
    }
    .summary-section {
        order: -1;
    }
    .desktop-action {
        display: none; /* Hide primary button in sidebar on mobile, move to form bottom */
    }
    .mobile-action {
        display: block;
        margin-top: 2rem;
    }
}
</style>
