<script setup>
import { ref, computed } from 'vue';
import { useStore } from '@nanostores/vue';
import { cartItems, cartTotal, clearCart } from '../../store/cart';

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

// API
const API_URL = import.meta.env.PUBLIC_API_URL || 'https://api.mvn.by'; 
// Note: In development it might be localhost:8000. 
// Ideally should use existing api utils but wrapping POST separately here for clarity or import `createOrder` if exists.
// I will assume we fetch directly or use a helper. 
// Given current Utils: `api.ts` has getProducts, getInstallationRates etc.
// Let's implement fetch here for now.

const submitOrder = async () => {
    if (!validate()) return;
    if (items.value.length === 0) return;

    isSubmitting.value = true;
    submitError.value = null;

    try {
        // Prepare items with ID resolution
        const orderItems = await Promise.all(items.value.map(async (i) => {
            let pid = i.productId;
            if (!pid) {
                // Fallback: Fetch ID by slug from API
                try {
                   // We need to dynamic import or assume api is available
                   const { getProductBySlug } = await import('../../utils/api'); 
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
                    base_rate: i.installationPrice ? i.installationPrice + 100 : 0  // Assuming 100 BYN discount
                } : null
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

        const response = await fetch(`${API_URL}/api/v1/orders`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(payload)
        });

        if (!response.ok) {
            const errData = await response.json();
            let msg = 'Ошибка при создании заказа';
            if (errData.detail) {
                if (Array.isArray(errData.detail)) {
                    msg = errData.detail.map(e => `${e.loc[e.loc.length-1]}: ${e.msg}`).join('; ');
                } else {
                    msg = errData.detail;
                }
            }
            throw new Error(msg);
        }

        // Success
        clearCart();
        window.location.href = '/success';

    } catch (e) {
        console.error(e);
        submitError.value = e.message;
    } finally {
        isSubmitting.value = false;
    }
};

// Phone mask helper (simplistic)
const onPhoneInput = (e) => {
    let val = e.target.value.replace(/\D/g, '');
    // Only basic cleaning, full mask logic is complex without library
    // We'll leave it simple for now or use library if available
    form.value.phone = e.target.value; 
}
</script>

<template>
<div class="checkout-container">
    <div v-if="items.length === 0" class="empty-msg">
        <h2>Корзина пуста</h2>
        <a href="/catalog">В каталог</a>
    </div>

    <div v-else class="checkout-layout">
        <!-- Form -->
        <div class="form-section card">
            <h2>Оформление заказа</h2>
            
            <form @submit.prevent="submitOrder" class="checkout-form">
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
        <div class="summary-section">
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
                    <button @click="submitOrder" class="btn btn-primary btn-block big" :disabled="isSubmitting">
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

<style scoped>
.checkout-container {
    padding: 1rem 0;
}

.checkout-layout {
    display: grid;
    grid-template-columns: 1fr 380px;
    gap: 2rem;
    align-items: start;
}

.card {
    background: white;
    padding: 2rem;
    border-radius: 1.5rem;
    box-shadow: 0 4px 20px rgba(0,0,0,0.03);
    border: 1px solid #f1f5f9;
}

h2 {
    font-size: 1.5rem;
    font-weight: 700;
    margin-bottom: 2rem;
    color: #0f172a;
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
    color: #334155;
}
.req { color: #ef4444; }

input, textarea {
    width: 100%;
    padding: 0.8rem 1rem;
    border-radius: 0.75rem;
    border: 1px solid #cbd5e1;
    font-size: 1rem;
    transition: border-color 0.2s, box-shadow 0.2s;
    font-family: inherit;
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
    color: #334155;
    padding-right: 1rem;
}
.mini-item .qty {
    color: #94a3b8;
    font-weight: 600;
}
.mini-item .price {
    font-weight: 600;
    color: #0f172a;
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
    color: #0f172a;
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
    .checkout-layout {
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
