<script setup>
import { useStore } from '@nanostores/vue';
import { cartItems, cartTotal, updateQuantity, removeItem, toggleInstallation, updateInstallationDetails } from '../../store/cart';
import { installationOptions, fetchInstallationOptions } from '../../store/installation';
// ... imports
import { getInstallationRates, getGlobalConfig } from '../../utils/api';

// ...

import { onMounted, ref } from 'vue';

const items = useStore(cartItems);
const total = useStore(cartTotal);
const options = useStore(installationOptions);

const formatPrice = (p) => p.toLocaleString('ru-RU') + ' р.';

// Subtotals
const equipmentTotal = () => items.value.reduce((sum, i) => sum + i.price * i.quantity, 0);
const servicesTotal = () => items.value.reduce((sum, i) => sum + (i.withInstallation ? i.installationPrice * i.quantity : 0), 0);

const rates = ref([]);
const discount = ref(0);

onMounted(async () => {
    const [ratesData, configData] = await Promise.all([
        getInstallationRates(),
        getGlobalConfig(),
        fetchInstallationOptions()
    ]);
    rates.value = ratesData;
    discount.value = parseInt(configData.install_discount || "0", 10);
});

const calculateInstallationPrice = (meters, optionSlugs) => {
    // Find generic rate (assume Wall for now as fallback)
    const rate = rates.value.find(r => r.category === 'Wall') || rates.value[0];
    let price = 0;
    
    if (rate) {
        const extraMeters = Math.max(0, meters - rate.included_pipe_meters);
        price = rate.base_price + (extraMeters * rate.extra_pipe_price);
    }
    
    // Add options
    if (optionSlugs && optionSlugs.length > 0) {
        const optionsCost = optionSlugs.reduce((sum, slug) => {
             const opt = options.value.find(o => o.slug === slug);
             return sum + (opt ? opt.price : 0);
        }, 0);
        price += optionsCost;
    }
    
    // Apply discount (Bundle Logic)
    // We assume items in cart with installation act as bundles
    // Only apply if base price > discount to avoid negative? Or just do it.
    // User logic: 600 - 100 = 500.
    if (discount.value > 0) {
        price = Math.max(0, price - discount.value);
    }
    
    return price;
};

const updateMeters = (item, delta) => {
    const newMeters = Math.max(1, (item.installationMeters || 3) + delta);
    if (newMeters === item.installationMeters) return;
    
    const newPrice = calculateInstallationPrice(newMeters, item.installationOptions);
    
    updateInstallationDetails(item.id, item.withInstallation, {
        meters: newMeters,
        price: newPrice
    });
};

const toggleOption = (item, opt) => {
    const currentOptions = item.installationOptions || [];
    let newOptions;
    if (currentOptions.includes(opt.slug)) {
        newOptions = currentOptions.filter(o => o !== opt.slug);
    } else {
        newOptions = [...currentOptions, opt.slug];
    }
    
    const newPrice = calculateInstallationPrice(item.installationMeters || 3, newOptions);
    
    updateInstallationDetails(item.id, item.withInstallation, {
        options: newOptions,
        price: newPrice
    });
};
</script>

<template>
<div class="cart-container">
    <div v-if="items.length === 0" key="empty" class="empty-state">
        <span class="material-icons-round empty-icon">shopping_cart</span>
        <h2>Корзина пуста</h2>
        <p>Перейдите в каталог, чтобы выбрать товары</p>
        <a href="/catalog" class="btn btn-primary">В каталог</a>
    </div>

    <div v-if="items.length > 0" key="list" class="cart-layout-grid-v2">
        <!-- List -->
        <div class="cart-items">
            <div v-for="item in items" :key="item.id + item.withInstallation" class="cart-item">
                <div class="item-img">
                    <img :src="item.image || '/placeholder.png'" :alt="item.name" />
                </div>
                <div class="item-info">
                    <h3 class="item-name">{{ item.name }}</h3>
                    <div class="item-price">{{ formatPrice(item.price) }}</div>
                    
                    <div class="item-controls">
                         <!-- Installation Toggle -->
                        <div 
                            class="install-toggle" 
                            :class="{ active: item.withInstallation }"
                            @click="toggleInstallation(item.id, item.withInstallation)"
                        >
                            <div class="checkbox">
                                <span v-if="item.withInstallation" class="material-icons-round check">check</span>
                            </div>
                            <span class="label">Монтаж (+{{ item.installationPrice }} р.)</span>
                        </div>
                        
                          <!-- Installation Settings -->
                        <div v-if="item.withInstallation" class="install-settings">
                             <div class="setting-row">
                                <span class="setting-label">Трасса:</span>
                                <div class="qty-micro">
                                     <button @click="updateMeters(item, -1)">−</button>
                                     <span>{{ item.installationMeters || 3 }}м</span>
                                     <button @click="updateMeters(item, 1)">+</button>
                                </div>
                             </div>
                             
                             <!-- Add-ons -->
                             <div v-if="options.length > 0" class="addons-list">
                                 <div v-for="opt in options" :key="opt.slug" class="addon-row">
                                     <label class="checkbox-label">
                                        <input type="checkbox" 
                                            :checked="item.installationOptions?.includes(opt.slug)" 
                                            @change="toggleOption(item, opt)"
                                        />
                                        <span class="addon-name">{{ opt.name }}</span>
                                        <span class="addon-price">+{{ opt.price }} р.</span>
                                        <span v-if="opt.description" class="info-icon" :title="opt.description">i</span>
                                        <!-- Optional Image Thumbnail -->
                                        <div v-if="opt.image" class="addon-thumb-hover">
                                            <img :src="opt.image" class="thumb" />
                                        </div>
                                     </label>
                                 </div>
                             </div>
                        </div>
                    </div>
                </div>

                <div class="item-actions">
                    <div class="quantity-control">
                        <button class="qty-btn" @click="updateQuantity(item.id, item.withInstallation, item.quantity - 1)">−</button>
                        <span class="qty-val">{{ item.quantity }}</span>
                        <button class="qty-btn" @click="updateQuantity(item.id, item.withInstallation, item.quantity + 1)">+</button>
                    </div>
                    <button class="remove-btn" @click="removeItem(item.id, item.withInstallation)">
                        <span class="material-icons-round">delete</span>
                    </button>
                </div>
                 <div class="item-total">
                    {{ formatPrice((item.price + (item.withInstallation ? item.installationPrice : 0)) * item.quantity) }}
                </div>
            </div>
        </div>

        <!-- Summary -->
        <div class="cart-summary">
            <h3>Ваш заказ</h3>
            <div class="summary-row">
                <span>Оборудование:</span>
                <span>{{ formatPrice(equipmentTotal()) }}</span>
            </div>
            <div class="summary-row">
                <span>Услуги (Монтаж):</span>
                <span>{{ formatPrice(servicesTotal()) }}</span>
            </div>
            <div class="summary-divider"></div>
            <div class="summary-total">
                <span>Итого:</span>
                <span>{{ formatPrice(total) }}</span>
            </div>
            
            <a href="/checkout" class="btn btn-primary btn-block checkout-btn">
                Оформить заказ
            </a>
        </div>
    </div>
</div>
</template>

<style>
/* Layout logic moved to Astro pages for global scope */

/* Items */
.cart-items {
    display: flex;
    flex-direction: column;
    gap: 1rem;
}

.cart-item {
    display: grid;
    grid-template-columns: 100px 1fr auto auto;
    gap: 2rem;
    align-items: center;
    background: var(--surface);
    padding: 1rem;
    border-radius: 1.5rem;
    box-shadow: 0 4px 12px rgba(0,0,0,0.03);
    border: 1px solid var(--border);
    transition: transform 0.2s, box-shadow 0.2s;
}
.cart-item:hover {
    transform: translateY(-2px);
    box-shadow: 0 8px 24px rgba(0,0,0,0.06);
}

.item-img img {
    width: 100px;
    height: 100px;
    object-fit: contain;
    border-radius: 1rem;
    background: var(--bg);
    padding: 0.5rem;
}

.item-info {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
}
.item-name {
    font-size: 1rem;
    font-weight: 600;
    line-height: 1.3;
}
.item-price {
    font-weight: 700;
    color: var(--text);
}

/* Install Toggle */
.install-toggle {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    cursor: pointer;
    font-size: 0.9rem;
    color: var(--primary);
    user-select: none;
    margin-top: 0.25rem;
}
.checkbox {
    width: 20px;
    height: 20px;
    border: 2px solid var(--border);
    border-radius: 4px;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: background 0.2s, border-color 0.2s;
}
.check {
    font-size: 16px;
    color: white;
}
.install-toggle.active .checkbox {
    background: #007f80;
    border-color: #007f80;
}
.install-toggle.active .label {
    color: #007f80;
    font-weight: 500;
}

.install-settings {
    margin-top: 0.75rem;
    padding-left: 2rem; /* Indent to align with text */
}
.setting-row {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    font-size: 0.85rem;
    color: var(--text-muted);
}
.qty-micro {
    display: flex;
    align-items: center;
    gap: 0.25rem;
    background: var(--bg);
    border-radius: 4px;
    padding: 2px;
}
.qty-micro button {
    width: 20px;
    height: 20px;
    border: none;
    background: white;
    border-radius: 3px;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    color: var(--text);
    font-size: 1rem;
    line-height: 1;
}
.qty-micro span {
    font-weight: 600;
    font-size: 0.85rem;
    padding: 0 4px;
    min-width: 24px;
    text-align: center;
}

/* Actions */
.item-actions {
    display: flex;
    align-items: center;
    gap: 1rem;
}
.quantity-control {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    background: var(--bg);
    padding: 4px;
    border-radius: 8px;
}
.qty-btn {
    width: 28px;
    height: 28px;
    display: flex;
    align-items: center;
    justify-content: center;
    border: none;
    background: var(--surface);
    border-radius: 6px;
    cursor: pointer;
    font-weight: 600;
    color: var(--text);
    box-shadow: 0 1px 2px rgba(0,0,0,0.05);
}
.qty-btn:hover {
    background: #e2e8f0;
}
.qty-val {
    width: 24px;
    text-align: center;
    font-weight: 600;
    font-size: 0.9rem;
}

.remove-btn {
    color: #94a3b8;
    background: transparent;
    border: none;
    cursor: pointer;
    padding: 4px;
    transition: color 0.2s;
}
.remove-btn:hover {
    color: #ef4444;
}

.item-total {
    font-weight: 700;
    font-size: 1.1rem;
    color: var(--text);
    min-width: 100px;
    text-align: right;
}

/* Summary */
.cart-summary {
    background: var(--surface);
    padding: 2rem;
    border-radius: 2rem;
    box-shadow: 0 10px 30px rgba(0, 0, 0, 0.05);
    border: 1px solid var(--border);
    height: fit-content;
    position: sticky;
    top: 2rem;
}
.cart-summary h3 {
    font-size: 1.25rem;
    font-weight: 700;
    margin-bottom: 1.5rem;
    color: var(--text);
}
.summary-row {
    display: flex;
    justify-content: space-between;
    margin-bottom: 1rem;
    font-size: 0.95rem;
    color: var(--text-muted);
}
.summary-divider {
    height: 1px;
    background: var(--border);
    margin: 1.5rem 0;
}
.summary-total {
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-size: 1.25rem;
    font-weight: 800;
    color: var(--text);
    margin-bottom: 1.5rem;
}
.checkout-btn {
    width: 100%;
    padding: 1rem;
    font-size: 1rem;
    font-weight: 600;
    text-align: center;
    border-radius: 0.75rem;
    background: #007f80;
    color: white;
    text-decoration: none;
    display: block;
    box-shadow: 0 4px 12px rgba(0, 127, 128, 0.3);
    transition: background 0.2s;
}
.checkout-btn:hover {
    background: #006b6c;
}

/* Mobile */
@media (max-width: 900px) {
    .cart-layout-grid {
        grid-template-columns: 1fr;
    }
}
@media (max-width: 640px) {
    .cart-item {
        grid-template-columns: 80px 1fr;
        grid-template-areas: 
            "img info"
            "actions actions"
            "total total";
        gap: 1rem;
    }
    .item-img { grid-area: img; }
    .item-info { grid-area: info; }
    .item-actions { 
        grid-area: actions; 
        justify-content: space-between;
    }
    .item-total { 
        grid-area: total; 
        text-align: left;
        margin-top: 0.5rem;
        padding-top: 0.5rem;
        border-top: 1px dashed #e2e8f0;
    }
}
/* Add-ons styles */
.addons-list {
    margin-top: 0.75rem;
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
}

.addon-row {
    font-size: 0.85rem;
}

.checkbox-label {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    cursor: pointer;
    color: var(--text);
}

.checkbox-label input {
    accent-color: var(--primary);
    width: 16px;
    height: 16px;
}

.addon-price {
    color: var(--text-muted);
    font-size: 0.8rem;
}

.info-icon {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 16px;
    height: 16px;
    border-radius: 50%;
    background: #e0f2f1;
    color: #007f80;
    font-size: 10px;
    font-weight: bold;
    cursor: help;
}

.addon-thumb-hover {
    display: none; /* Hide for now, can be tooltip */
}
</style>
