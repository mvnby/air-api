import assert from 'node:assert/strict';
import test from 'node:test';

import {
    calculateInstallationPrice,
    matchProductInstallationRate,
} from '../src/utils/installation-pricing.js';


const rates = [
    {
        id: 1,
        category: 'Wall',
        power_range: '07-12',
        base_price: 600,
        extra_pipe_price: 50,
        included_pipe_meters: 3,
        is_fixed: true,
    },
    {
        id: 2,
        category: 'Wall',
        power_range: '18-24',
        base_price: 750,
        extra_pipe_price: 65,
        included_pipe_meters: 3,
        is_fixed: true,
    },
    {
        id: 3,
        category: 'Duct',
        power_range: 'All',
        base_price: 1500,
        extra_pipe_price: 0,
        included_pipe_meters: 3,
        is_fixed: false,
    },
];


test('matches the canonical product rate by category and area fallback', () => {
    const matched = matchProductInstallationRate({
        rates,
        tags: [{ slug: 'wall' }],
        area: 50,
    });

    assert.equal(matched?.id, 2);
});


test('prefers an exact canonical power tag over area fallback', () => {
    const matched = matchProductInstallationRate({
        rates,
        tags: [{ slug: 'wall' }, { slug: '07-12' }],
        area: 70,
    });

    assert.equal(matched?.id, 1);
});


test('calculates the same fixed bundle breakdown as the backend', () => {
    const quote = calculateInstallationPrice({
        rate: rates[1],
        meters: 5,
        options: [{ slug: 'vibration-stand', price: 50 }],
        selectedOptionSlugs: ['vibration-stand'],
        bundleDiscount: 100,
        applyBundleDiscount: true,
    });

    assert.deepEqual(quote, {
        status: 'fixed',
        total: 830,
        meters: 5,
        basePrice: 750,
        extraMeters: 2,
        extraMetersPrice: 130,
        bundleDiscount: 100,
        optionsTotal: 50,
    });
});


test('does not apply a product bundle discount to service-only pricing', () => {
    const quote = calculateInstallationPrice({
        rate: rates[1],
        meters: 5,
        options: [{ slug: 'vibration-stand', price: 50 }],
        selectedOptionSlugs: ['vibration-stand'],
        bundleDiscount: 100,
        applyBundleDiscount: false,
    });

    assert.equal(quote.total, 930);
    assert.equal(quote.bundleDiscount, 0);
});


test('non-fixed rates are represented as manual quotes', () => {
    const quote = calculateInstallationPrice({ rate: rates[2], meters: 5 });

    assert.equal(quote.status, 'manual_quote');
    assert.equal(quote.total, 0);
});
