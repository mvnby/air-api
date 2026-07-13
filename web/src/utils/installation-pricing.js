const PRODUCT_CATEGORY_SLUGS = ['wall', 'cassette', 'duct', 'ceiling', 'multisplit'];

const normalize = (value) => String(value || '').trim().toLowerCase();

export function getInstallationAreaRangeMax(powerRange) {
    const key = normalize(powerRange);
    if (key.includes('07-12')) return 35;
    if (key.includes('18-24')) return 70;
    if (key.includes('30-36')) return 100;
    if (['area-20', 'area-25', 'area-35'].some(value => key.includes(value))) return 35;
    if (['area-50', 'area-70'].some(value => key.includes(value))) return 70;
    if (['area-80', 'area-100'].some(value => key.includes(value))) return 100;
    return null;
}

export function installationCategoryMatchesRate(rateCategory, productCategory) {
    const rate = normalize(rateCategory);
    if (['wall', 'duct', 'multisplit'].includes(productCategory)) {
        return rate === productCategory;
    }
    if (['cassette', 'ceiling'].includes(productCategory)) {
        return ['cassette', 'ceiling', 'cassette/ceiling'].includes(rate);
    }
    return rate === productCategory;
}

export function matchProductInstallationRate({ rates = [], tags = [], area = 0 } = {}) {
    if (!Array.isArray(rates) || rates.length === 0) return null;

    const tagSlugs = new Set(
        (Array.isArray(tags) ? tags : [])
            .map(tag => normalize(typeof tag === 'string' ? tag : tag?.slug))
            .filter(Boolean),
    );
    const productCategory = PRODUCT_CATEGORY_SLUGS.find(slug => tagSlugs.has(slug)) || 'wall';
    const categoryRates = rates.filter(rate => (
        installationCategoryMatchesRate(rate?.category, productCategory)
    ));
    if (categoryRates.length === 0) return null;

    for (const rate of categoryRates) {
        const powerRange = normalize(rate?.power_range);
        if (powerRange === 'all') return rate;
        const rateSlugs = powerRange.split(',').map(value => value.trim()).filter(Boolean);
        if (rateSlugs.some(slug => tagSlugs.has(slug))) return rate;
    }

    const productArea = Number(area) || 0;
    if (productArea > 0) {
        const areaRates = categoryRates
            .map(rate => ({ rate, maxArea: getInstallationAreaRangeMax(rate?.power_range) }))
            .filter(entry => entry.maxArea !== null)
            .sort((left, right) => Number(left.maxArea) - Number(right.maxArea));
        if (areaRates.length > 0) {
            return areaRates.find(entry => productArea <= Number(entry.maxArea))?.rate
                || areaRates[areaRates.length - 1].rate;
        }
    }
    return null;
}

export function calculateInstallationPrice({
    rate,
    meters = 3,
    options = [],
    selectedOptionSlugs = [],
    bundleDiscount = 0,
    applyBundleDiscount = false,
} = {}) {
    const normalizedMeters = Math.min(50, Math.max(1, Number(meters) || 3));
    if (!rate || !rate.is_fixed) {
        return {
            status: 'manual_quote',
            total: 0,
            meters: normalizedMeters,
            basePrice: 0,
            extraMeters: 0,
            extraMetersPrice: 0,
            bundleDiscount: 0,
            optionsTotal: 0,
        };
    }

    const basePrice = Math.max(0, Number(rate.base_price) || 0);
    const includedMeters = Math.max(0, Number(rate.included_pipe_meters) || 0);
    const extraMeterUnitPrice = Math.max(0, Number(rate.extra_pipe_price) || 0);
    const extraMeters = Math.max(0, normalizedMeters - includedMeters);
    const extraMetersPrice = Math.round(extraMeters * extraMeterUnitPrice);
    const selectedSlugs = new Set(Array.isArray(selectedOptionSlugs) ? selectedOptionSlugs : []);
    const optionsTotal = (Array.isArray(options) ? options : []).reduce((sum, option) => (
        selectedSlugs.has(option?.slug) ? sum + Math.max(0, Number(option?.price) || 0) : sum
    ), 0);
    const rawDiscount = Number(bundleDiscount);
    const configuredDiscount = applyBundleDiscount
        && Number.isInteger(rawDiscount)
        && rawDiscount >= 0
        && rawDiscount <= 10_000
        ? rawDiscount
        : 0;
    const appliedDiscount = Math.min(configuredDiscount, basePrice + extraMetersPrice);

    return {
        status: 'fixed',
        total: basePrice + extraMetersPrice - appliedDiscount + optionsTotal,
        meters: normalizedMeters,
        basePrice,
        extraMeters,
        extraMetersPrice,
        bundleDiscount: appliedDiscount,
        optionsTotal,
    };
}
