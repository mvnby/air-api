<script setup>
import { useStore } from '@nanostores/vue';
import { cartItems, cartTotal, updateQuantity, removeItem, toggleInstallation } from '../../store/cart';

const items = useStore(cartItems);
const total = useStore(cartTotal);

const formatPrice = (p) => p.toLocaleString('ru-RU') + ' р.';

// Subtotals
const equipmentTotal = () => items.value.reduce((sum, i) => sum + i.price * i.quantity, 0);
const servicesTotal = () => items.value.reduce((sum, i) => sum + (i.withInstallation ? i.installationPrice * i.quantity : 0), 0);
</script>

<template>
<div class="cart-container">
    <div v-if="items.length === 0" class="empty-state">
        <span class="material-icons-round empty-icon">shopping_cart</span>
        <h2>Корзина пуста</h2>
        <p>Перейдите в каталог, чтобы выбрать товары</p>
        <a href="/catalog" class="btn btn-primary">В каталог</a>
    </div>

    <div v-else class="cart-layout-grid-v2">
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
    gap: 1.5rem;
}

.cart-item {
    display: grid;
    grid-template-columns: 100px 1fr auto auto;
    gap: 2rem;
    align-items: center;
    background: white;
    padding: 1.5rem;
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
    color: #0f172a;
}

/* Install Toggle */
.install-toggle {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    cursor: pointer;
    font-size: 0.9rem;
    color: #64748b;
    user-select: none;
    margin-top: 0.25rem;
}
.checkbox {
    width: 20px;
    height: 20px;
    border: 2px solid #cbd5e1;
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
    background: #f1f5f9;
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
    background: white;
    border-radius: 6px;
    cursor: pointer;
    font-weight: 600;
    color: #334155;
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
    color: #0f172a;
    min-width: 100px;
    text-align: right;
}

/* Summary */
.cart-summary {
    background: white;
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
    color: #0f172a;
}
.summary-row {
    display: flex;
    justify-content: space-between;
    margin-bottom: 1rem;
    font-size: 0.95rem;
    color: #64748b;
}
.summary-divider {
    height: 1px;
    background: #e2e8f0;
    margin: 1.5rem 0;
}
.summary-total {
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-size: 1.25rem;
    font-weight: 800;
    color: #0f172a;
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
</style>
