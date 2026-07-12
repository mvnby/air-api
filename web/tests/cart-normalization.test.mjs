import assert from 'node:assert/strict';
import test from 'node:test';

import {
    MAX_CART_LINES,
    normalizeCartItems,
} from '../src/utils/cart-normalization.js';


const item = (index, overrides = {}) => ({
    id: `product-${index}`,
    productId: index + 1,
    name: `Product ${index}`,
    image: '',
    price: 100,
    quantity: 1,
    withInstallation: false,
    installationPrice: 0,
    installationRateId: null,
    installationMeters: 3,
    installationOptions: [],
    ...overrides,
});


test('normalizes old persisted carts to the public checkout limits', () => {
    const raw = Array.from({ length: 25 }, (_, index) => item(index, {
        quantity: 999,
        installationMeters: 999,
        installationOptions: ['valid-option', 'valid-option', '<script>'],
    }));

    const normalized = normalizeCartItems(raw);

    assert.equal(normalized.length, MAX_CART_LINES);
    assert.equal(normalized[0].quantity, 20);
    assert.equal(normalized[0].installationMeters, 50);
    assert.deepEqual(normalized[0].installationOptions, []);
});


test('merges duplicate persisted lines without exceeding quantity 20', () => {
    const normalized = normalizeCartItems([
        item(1, { quantity: 15 }),
        item(1, { quantity: 10 }),
    ]);

    assert.equal(normalized.length, 1);
    assert.equal(normalized[0].quantity, 20);
});


test('keeps a cached quote for toggling installation after reload', () => {
    const normalized = normalizeCartItems([
        null,
        { id: '', productId: 0 },
        item(2, {
            withInstallation: false,
            installationPrice: 500,
            installationRateId: 7,
            installationOptions: ['canopy'],
        }),
    ]);

    assert.equal(normalized.length, 1);
    assert.equal(normalized[0].installationPrice, 500);
    assert.equal(normalized[0].installationRateId, 7);
    assert.deepEqual(normalized[0].installationOptions, []);
});
