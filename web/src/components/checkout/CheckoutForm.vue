<script setup>
import { ref, computed, onMounted } from 'vue';
import { useStore } from '@nanostores/vue';
import { cartItems, cartTotal, clearCart, refreshPrices } from '../../store/cart';
import { createOrder, getProductBySlug, getCompanyByUnp, getBankBySearch } from '../../utils/api';
import IMask from 'imask';

// State
const form = ref({
    name: '',
    phone: '',
    address: '',
    comment: '',
    type: 'individual',
    inn: '',
    full_legal_name: '',
    legal_address: '',
    iban: '',
    bic: '',
    bank_name: ''
});
const isLegalEntity = ref(false);
const phoneInput = ref(null);
let mask = null;
const errors = ref({});
const isSubmitting = ref(false);
const isLoadingData = ref(false);
const submitError = ref(null);

const items = useStore(cartItems);
const total = useStore(cartTotal);
const formatPrice = (p) => p.toLocaleString('ru-RU') + ' р.';

// Validation
const validate = () => {
    errors.value = {};
    if (!form.value.name) errors.value.name = 'Введите имя';
    
    // Phone validation with IMask
    if (!mask || !mask.masked.isComplete) {
        errors.value.phone = 'Введите полный номер телефона';
    }

    if (isLegalEntity.value) {
        if (!form.value.inn) errors.value.inn = 'Введите УНП';
        if (!form.value.full_legal_name) errors.value.full_legal_name = 'Введите название организации';
        if (!form.value.legal_address) errors.value.legal_address = 'Введите юридический адрес';
    }

    return Object.keys(errors.value).length === 0;
};

// Refresh prices on mount to ensure freshness
onMounted(() => {
    refreshPrices();
    
    if (phoneInput.value) {
        mask = IMask(phoneInput.value, {
            mask: '+{375} (00) 000-00-00',
            lazy: false,
            placeholderChar: '_'
        });
        
        // Initial sync
        mask.on('accept', () => {
            form.value.phone = mask.value;
        });
    }
});

// Auto-fill UNP
const onUnpBlur = async () => {
    if (!form.value.inn || form.value.inn.length !== 9) return;
    
    isLoadingData.value = true;
    try {
        const data = await getCompanyByUnp(form.value.inn);
        // EGR API structure: { row: { vnaimp: "...", vpadres: "..." } }
        if (data && data.row) {
             // Remove quotes " from name if needed, or keep them
             form.value.full_legal_name = data.row.vnaimp || form.value.full_legal_name;
             form.value.legal_address = data.row.vpadres || form.value.legal_address;
        }
    } catch (e) {
        console.error("Failed to fetch EGR data", e);
    } finally {
        isLoadingData.value = false;
    }
};

// Auto-fill IBAN
const onIbanBlur = async () => {
     if (!form.value.iban || form.value.iban.length < 10) return;
     
     // Basic cleanup
     const ibanClean = form.value.iban.replace(/\s/g, '').toUpperCase();
     form.value.iban = ibanClean;
     
     isLoadingData.value = true;
     try {
        const data = await getBankBySearch(ibanClean);
        if (data && data.name) {
             form.value.bank_name = data.name + ', ' + data.address;
             form.value.bic = data.bic;
        }
     } catch (e) {
         console.error("Failed to fetch Bank data", e);
     } finally {
         isLoadingData.value = false;
     }
};

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
                address: form.value.address,
                type: isLegalEntity.value ? 'company' : 'individual',
                inn: isLegalEntity.value ? form.value.inn : null,
                full_legal_name: isLegalEntity.value ? form.value.full_legal_name : null,
                legal_address: isLegalEntity.value ? form.value.legal_address : null,
                iban: isLegalEntity.value ? form.value.iban : null,
                bic: isLegalEntity.value ? form.value.bic : null,
                bank_name: isLegalEntity.value ? form.value.bank_name : null
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
                        ref="phoneInput"
                        :class="{ invalid: errors.phone }"
                        placeholder="+375 (XX) XXX-XX-XX"
                    />
                    <span v-if="errors.phone" class="err-msg">{{ errors.phone }}</span>
                </div>

                <!-- B2B Toggle -->
                <div class="form-group checkbox-group">
                    <label class="checkbox-container">
                        <input type="checkbox" v-model="isLegalEntity" />
                        <span class="checkmark"></span>
                        <span class="label-text">Оформить на юридическое лицо (организацию)</span>
                    </label>
                </div>

                <!-- B2B Fields -->
                <Transition name="slide-fade">
                    <div v-if="isLegalEntity" class="legal-fields-wrapper">
                        <div class="form-group">
                            <label for="inn">УНП <span class="req">*</span></label>
                            <div class="input-with-loader">
                                <input 
                                    type="text" 
                                    id="inn" 
                                    v-model="form.inn" 
                                    @blur="onUnpBlur"
                                    :class="{ invalid: errors.inn }"
                                    placeholder="9-значный номер"
                                />
                                <span v-if="isLoadingData" class="loader-icon material-icons-round">sync</span>
                            </div>
                            <span v-if="errors.inn" class="err-msg">{{ errors.inn }}</span>
                        </div>

                        <div class="form-group">
                            <label for="legal_name">Название организации <span class="req">*</span></label>
                            <input 
                                type="text" 
                                id="legal_name" 
                                v-model="form.full_legal_name" 
                                :class="{ invalid: errors.full_legal_name }"
                                placeholder='ООО "Мастер Воздуха"'
                            />
                            <span v-if="errors.full_legal_name" class="err-msg">{{ errors.full_legal_name }}</span>
                        </div>

                        <div class="form-group">
                            <label for="legal_address">Юридический адрес <span class="req">*</span></label>
                            <input 
                                type="text" 
                                id="legal_address" 
                                v-model="form.legal_address" 
                                :class="{ invalid: errors.legal_address }"
                                placeholder="г. Минск, ул. ..."
                            />
                            <span v-if="errors.legal_address" class="err-msg">{{ errors.legal_address }}</span>
                        </div>

                        <div class="divider-small"></div>
                        <h4 class="sub-header">Банковские реквизиты</h4>

                        <div class="form-group">
                            <label for="iban">IBAN (Расчетный счет)</label>
                            <input 
                                type="text" 
                                id="iban" 
                                v-model="form.iban" 
                                @blur="onIbanBlur"
                                placeholder="BYxx ARBK ..."
                            />
                        </div>

                        <div class="form-row">
                            <div class="form-group half">
                                <label for="bic">BIC (Код банка)</label>
                                <input 
                                    type="text" 
                                    id="bic" 
                                    v-model="form.bic" 
                                    placeholder="ARBKBY2X"
                                />
                            </div>
                            <div class="form-group half">
                                <label for="bank_name">Название банка</label>
                                <input 
                                    type="text" 
                                    id="bank_name" 
                                    v-model="form.bank_name" 
                                    placeholder="ОАО 'Белинвестбанк'"
                                />
                            </div>
                        </div>
                    </div>
                </Transition>

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

/* B2B Elements */
.checkbox-group {
    margin-top: 0.5rem;
    margin-bottom: 2rem;
}

.checkbox-container {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    cursor: pointer;
    user-select: none;
    font-weight: 500;
    color: var(--text);
}

.checkbox-container input {
    display: none;
}

.checkmark {
    width: 20px;
    height: 20px;
    border: 2px solid var(--border);
    border-radius: 6px;
    position: relative;
    transition: all 0.2s;
    background: var(--bg);
}

.checkbox-container input:checked ~ .checkmark {
    background: #007f80;
    border-color: #007f80;
}

.checkmark:after {
    content: "";
    position: absolute;
    display: none;
    left: 6px;
    top: 2px;
    width: 5px;
    height: 10px;
    border: solid white;
    border-width: 0 2px 2px 0;
    transform: rotate(45deg);
}

.checkbox-container input:checked ~ .checkmark:after {
    display: block;
}

.legal-fields-wrapper {
    background: rgba(0, 127, 128, 0.03);
    padding: 1.5rem;
    border-radius: 1rem;
    border: 1px dashed rgba(0, 127, 128, 0.2);
    margin-bottom: 1.5rem;
}

/* Animations */
.slide-fade-enter-active {
  transition: all 0.3s ease-out;
}

.slide-fade-leave-active {
  transition: all 0.2s cubic-bezier(1, 0.5, 0.8, 1);
}

.slide-fade-enter-from,
.slide-fade-leave-to {
  transform: translateY(-20px);
  opacity: 0;
  max-height: 0;
  margin-bottom: 0;
  padding-top: 0;
  padding-bottom: 0;
  overflow: hidden;
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

.input-with-loader {
    position: relative;
}
.loader-icon {
    position: absolute;
    right: 12px;
    top: 50%;
    transform: translateY(-50%);
    color: #007f80;
    animation: spin 1s linear infinite;
    font-size: 1.2rem;
}
@keyframes spin { 100% { transform: translateY(-50%) rotate(360deg); } }

.divider-small {
    height: 1px;
    background: rgba(0, 127, 128, 0.1);
    margin: 1.5rem 0 1rem 0;
}
.sub-header {
    font-size: 1rem;
    font-weight: 600;
    color: var(--text-muted);
    margin-bottom: 1rem;
}
.form-row {
    display: flex;
    gap: 1rem;
}
.form-row .half {
    flex: 1;
}
</style>
