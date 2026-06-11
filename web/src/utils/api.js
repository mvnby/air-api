const ENV_API_URL = import.meta.env.INTERNAL_API_URL || 'http://app:8000/api/v1';
const PUBLIC_API_URL = (import.meta.env.PUBLIC_API_URL || 'http://localhost:8000').replace(/\/api\/v1\/?$/, "");

// Re-export spec formatting utilities
export { formatSpec, formatAllSpecs, SPEC_DICT } from './spec-dictionary';
const normalizeApiV1Base = (raw) => {
    const base = String(raw || "").trim().replace(/\/$/, "");
    if (!base) return "";
    if (base.endsWith("/api/v1")) return base;
    return `${base.replace(/\/api\/v1$/, "")}/api/v1`;
};

const uniqueNonEmpty = (values) => [...new Set(values.map((v) => String(v || "").trim()).filter(Boolean))];

// Ensure standard formatting (no trailing slash)
// INTERNAL_URL is used for SSR (Server Side Rendering) inside Docker network
const INTERNAL_URL = normalizeApiV1Base(import.meta.env.INTERNAL_API_URL || 'http://app:8000/api/v1');
// PUBLIC_URL is used for Client-side requests (Browser)
const CLIENT_URL = normalizeApiV1Base(import.meta.env.PUBLIC_API_URL || 'http://localhost:8000/api/v1');

// Define API versions relative to the base
// Use Client-side URL if not in SSR
const API_V1 = import.meta.env.SSR ? INTERNAL_URL : CLIENT_URL;
const API_ROOT = API_V1.replace(/\/v1$/, ""); // Fallback for non-versioned endpoints if any

const readProcessEnv = (key) => {
    if (typeof process === "undefined" || !process?.env) return undefined;
    return process.env[key];
};

const isEnabledFlag = (value) =>
    ["1", "true", "yes", "on"].includes(String(value || "").trim().toLowerCase());

const parsePositiveInt = (value, fallback) => {
    const parsed = Number.parseInt(String(value || ""), 10);
    return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
};

const runtimeCache = new Map();
const runtimeCacheMaxEntries = () =>
    parsePositiveInt(readProcessEnv("SSR_RUNTIME_DATA_CACHE_MAX_ENTRIES"), 200);

export function isRuntimeFreshnessEnabled() {
    return (
        import.meta.env.SSR &&
        isEnabledFlag(import.meta.env.SSR_RUNTIME_FRESHNESS || readProcessEnv("SSR_RUNTIME_FRESHNESS"))
    );
}

async function fetchCatalogRevision() {
    const fallbackTtlMs = parsePositiveInt(readProcessEnv("SSR_RUNTIME_FRESHNESS_FALLBACK_TTL_MS"), 15000);
    const timeoutMs = parsePositiveInt(readProcessEnv("SSR_RUNTIME_REVISION_TIMEOUT_MS"), 4000);
    const fallbackBucket = Math.floor(Date.now() / fallbackTtlMs);
    const fallback = {
        revision: `fallback-${fallbackBucket}`,
        updated_at: null,
        unavailable: true,
        ttlMs: fallbackTtlMs,
    };

    if (!isRuntimeFreshnessEnabled()) return null;

    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), timeoutMs);

    try {
        const data = await fetchJson(`${API_V1}/catalog/revision`, { signal: controller.signal }, false);
        const revision = String(data?.revision ?? "").trim();
        if (!revision) {
            throw new Error("catalog revision response did not include revision");
        }
        return {
            revision,
            updated_at: data?.updated_at || null,
            unavailable: false,
            ttlMs: parsePositiveInt(readProcessEnv("SSR_RUNTIME_DATA_CACHE_TTL_MS"), 30000),
        };
    } catch (error) {
        console.error("[API] Catalog revision unavailable, using short fallback cache key:", error.message);
        return fallback;
    } finally {
        clearTimeout(timeout);
    }
}

export async function createRuntimeFreshnessContext() {
    const revisionState = await fetchCatalogRevision();
    if (!revisionState) return null;

    const statuses = new Set();
    return {
        revision: revisionState.revision,
        updated_at: revisionState.updated_at,
        unavailable: revisionState.unavailable,
        ttlMs: revisionState.ttlMs,
        mark(status) {
            if (status) statuses.add(status);
        },
        cacheStatus() {
            if (statuses.has("stale") || revisionState.unavailable) return "stale";
            if (statuses.has("miss")) return "miss";
            if (statuses.has("hit")) return "hit";
            return "miss";
        },
    };
}

function trimRuntimeCache() {
    const maxEntries = runtimeCacheMaxEntries();
    while (runtimeCache.size > maxEntries) {
        const oldestKey = runtimeCache.keys().next().value;
        if (!oldestKey) break;
        runtimeCache.delete(oldestKey);
    }
}

async function fetchJsonWithRuntimeCache(url, options = {}, returnNullOnError = true, runtimeFreshness = null) {
    const method = String(options?.method || "GET").toUpperCase();
    if (!runtimeFreshness || method !== "GET") {
        return await fetchJson(url, options, returnNullOnError);
    }

    const now = Date.now();
    const cacheKey = `${runtimeFreshness.revision} ${method} ${url}`;
    const cached = runtimeCache.get(cacheKey);
    if (cached && cached.expiresAt > now) {
        runtimeFreshness.mark(runtimeFreshness.unavailable ? "stale" : "hit");
        return cached.data;
    }

    const data = await fetchJson(url, options, returnNullOnError);
    if (data !== null && data !== undefined) {
        runtimeCache.set(cacheKey, {
            data,
            expiresAt: now + runtimeFreshness.ttlMs,
        });
        trimRuntimeCache();
    }

    runtimeFreshness.mark(runtimeFreshness.unavailable ? "stale" : "miss");
    return data;
}

function getRuntimeFreshnessOption(options = {}) {
    return options.runtimeFreshness || options.freshness || null;
}

export function applyRuntimeFreshnessHeaders(response, runtimeFreshness) {
    if (!runtimeFreshness || !response?.headers) return;
    response.headers.set("X-Catalog-Revision", runtimeFreshness.revision);
    response.headers.set("X-Web-Data-Cache", runtimeFreshness.cacheStatus());
    response.headers.set("Cache-Control", "no-store");
}

export function createRuntimeNotFoundResponse(response, runtimeFreshness) {
    applyRuntimeFreshnessHeaders(response, runtimeFreshness);
    const headers = new Headers(response?.headers || {});
    headers.set("Content-Type", "text/html; charset=utf-8");
    headers.set("Cache-Control", "no-store");
    return new Response(
        "<!doctype html><html><head><title>Not found</title></head><body><h1>404</h1></body></html>",
        {
            status: 404,
            headers,
        },
    );
}

export function resolveImageUrl(path) {
    if (!path) return "/no-photo.png";
    if (path.startsWith("http")) return path;
    // Images are always served from public root, not API v1
    const root = import.meta.env.PUBLIC_API_URL || 'http://localhost:8000';
    const cleanRoot = root.replace(/\/api\/v1\/?$/, "").replace(/\/$/, "");
    return `${cleanRoot}/${path.replace(/^\//, "")}`;
}

// Formatting helpers
function buildQuery(params) {
    const searchParams = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
        if (Array.isArray(value)) {
            value.forEach(v => searchParams.append(key, v));
        } else if (value !== null && value !== undefined) {
            searchParams.append(key, value);
        }
    });
    return searchParams.toString();
}

/**
 * Generic fetch wrapper with unified error handling
 * @param {string} url 
 * @param {object} options 
 * @param {boolean} returnNullOnError - if true, returns null instead of throwing (legacy mode)
 */
async function fetchJson(url, options = {}, returnNullOnError = true) {
    try {
        const response = await fetch(url, options);
        if (!response.ok) {
            // Try to parse error message
            let errorDetails = null;
            try { errorDetails = await response.json(); } catch (e) {/* ignore */ }

            const error = new Error(`API Error ${response.status}: ${url}`);
            error.status = response.status;
            error.details = errorDetails;

            console.error(`[API] Error ${response.status} from ${url}`, errorDetails);

            if (returnNullOnError) return null;
            throw error;
        }
        return await response.json();
    } catch (error) {
        console.error(`[API] Fetch error for ${url}:`, error.message);
        if (returnNullOnError) return null;
        throw error;
    }
}

function getSsgApiCandidates() {
    return uniqueNonEmpty([
        INTERNAL_URL,
        CLIENT_URL,
        normalizeApiV1Base(import.meta.env.PUBLIC_API_URL),
        normalizeApiV1Base(import.meta.env.INTERNAL_API_URL),
        "http://localhost:8000/api/v1",
    ]);
}

async function getCatalogStrictForSsg(params = {}) {
    const query = buildQuery(params);
    const candidates = getSsgApiCandidates();
    const errors = [];

    for (const baseUrl of candidates) {
        const url = `${baseUrl}/catalog?${query}`;
        try {
            const data = await fetchJson(url, {}, false);
            if (data && Array.isArray(data.items)) {
                return data;
            }
            errors.push(`${url} -> invalid payload`);
        } catch (error) {
            errors.push(`${url} -> ${error.message}`);
        }
    }

    throw new Error(`[SSG] Failed to fetch catalog. Tried: ${candidates.join(", ")}. Errors: ${errors.join(" | ")}`);
}

export async function getCatalog(params = {}, options = {}) {
    const query = buildQuery(params);
    const url = `${API_V1}/catalog?${query}`;
    const runtimeFreshness = getRuntimeFreshnessOption(options);

    const data = await fetchJsonWithRuntimeCache(url, {}, true, runtimeFreshness);
    if (!data) {
        return { items: [], meta: { total: 0, page: 1, limit: 20, pages: 0 } };
    }
    return data;
}

export async function getCatalogForSsg(params = {}) {
    if (import.meta.env.SSR) {
        return await getCatalogStrictForSsg(params);
    }
    return await getCatalog(params);
}

async function getProductSeriesNavigationStrictForSsg() {
    const candidates = getSsgApiCandidates();

    for (const baseUrl of candidates) {
        const data = await fetchJson(`${baseUrl}/product-series/navigation`);
        if (data && data.products && typeof data.products === "object") {
            return data;
        }
    }

    return null;
}

export async function getProductSeriesNavigation(options = {}) {
    const runtimeFreshness = getRuntimeFreshnessOption(options);
    const data = await fetchJsonWithRuntimeCache(
        `${API_V1}/product-series/navigation`,
        {},
        true,
        runtimeFreshness,
    );
    return data && data.products ? data : { products: {} };
}

export async function getProductSeriesNavigationForSsg() {
    if (import.meta.env.SSR) {
        return await getProductSeriesNavigationStrictForSsg();
    }
    return await getProductSeriesNavigation();
}

export async function getVitebskFeaturedProducts() {
    const url = `${API_V1}/products/vitebsk-featured`;
    const data = await fetchJson(url);
    return data || [];
}

export async function getFiltersConfig(options = {}) {
    const runtimeFreshness = getRuntimeFreshnessOption(options);
    const data = await fetchJsonWithRuntimeCache(`${API_V1}/filters/config`, {}, true, runtimeFreshness);
    return data || { price: { min: null, max: null }, area: { min: null, max: null }, brands: [], expert_tags: [] };
}

export async function getPublicBrands(options = {}) {
    const runtimeFreshness = getRuntimeFreshnessOption(options);
    if (runtimeFreshness) {
        const data = await fetchJsonWithRuntimeCache(`${API_V1}/content/brands`, {}, true, runtimeFreshness);
        return Array.isArray(data) ? data : [];
    }

    if (import.meta.env.SSR) {
        for (const baseUrl of getSsgApiCandidates()) {
            const data = await fetchJson(`${baseUrl}/content/brands`);
            if (Array.isArray(data)) return data;
        }
        return [];
    }

    const data = await fetchJson(`${API_V1}/content/brands`);
    return Array.isArray(data) ? data : [];
}

export async function getPublicBrandBySlug(slug, options = {}) {
    if (!slug) return null;
    const runtimeFreshness = getRuntimeFreshnessOption(options);
    if (runtimeFreshness) {
        return await fetchJsonWithRuntimeCache(
            `${API_V1}/content/brands/${encodeURIComponent(slug)}`,
            {},
            true,
            runtimeFreshness,
        );
    }

    if (import.meta.env.SSR) {
        for (const baseUrl of getSsgApiCandidates()) {
            const data = await fetchJson(`${baseUrl}/content/brands/${encodeURIComponent(slug)}`);
            if (data) return data;
        }
        return null;
    }

    return await fetchJson(`${API_V1}/content/brands/${encodeURIComponent(slug)}`);
}

export async function getProducts() {
    // During SSG we require a strict fetch to avoid silently dropping product routes.
    if (import.meta.env.SSR) {
        const data = await getCatalogStrictForSsg({ limit: 1000 });
        return data && data.items ? data.items : [];
    }

    // Client-side/runtime usage can stay resilient with soft fallback.
    const data = await getCatalog({ limit: 1000 });
    return data && data.items ? data.items : [];
}

export async function getProductBySlug(slug, options = {}) {
    const runtimeFreshness = getRuntimeFreshnessOption(options);
    return await fetchJsonWithRuntimeCache(
        `${API_V1}/products/${encodeURIComponent(slug)}`,
        {},
        true,
        runtimeFreshness,
    );
}

export async function getProductById(id) {
    return await fetchJson(`${API_V1}/products/${id}`);
}

/**
 * Fetch fresh prices for a list of product IDs or Slugs
 * @param {Array<string|number>} ids 
 */
export async function refreshProductPrices(ids) {
    if (!ids || ids.length === 0) return [];
    const query = buildQuery({ ids: ids, limit: 100 }); // Assuming catalog supports 'ids' filter or we need another way
    // If catalog doesn't support 'ids', we might need to fetch individually or use a specific endpoint.
    // Let's try fetching catalog with these IDs if supported, otherwise falling back to individual.
    // Ideally backend supports POST /products/batch or GET /catalog?ids=...
    // If not, we will just use getCatalog without filters? No, that's inefficient.
    // For now, let's assume we can filter catalog by slugs if they are passed, or just IDs.
    // Check `buildQuery`: it appends array values.

    // Safer approach for now: Promise.all if count is small (<10), otherwise warning.
    // We'll trust getCatalog supports filtering by something or we rely on the component to check.
    // A common pattern is ?ids=1,2,3.
    // Let's assume we can pass `ids` to catalog.

    // Correction: Frontend 'ids' might be mixed slug/int.
    // Let's rely on `getCatalog` supporting specific filters if implemented.
    // If not implemented in backend, we might need to implement it there or here. 
    // Given the task is "Optimization", let's assume we can just fetch fresh data for specific items.

    // FALLBACK: Use getProductBySlug for each item.
    const promises = ids.map(id =>
        typeof id === 'number' ? getProductById(id) : getProductBySlug(id)
    );

    const results = await Promise.all(promises);
    return results.filter(Boolean);
}

let _globalConfigPromise = null;

export async function getGlobalConfig() {
    if (!_globalConfigPromise) {
        _globalConfigPromise = fetchJson(`${API_V1}/config`)
            .catch(err => {
                console.error('[API] Failed to fetch global config:', err);
                _globalConfigPromise = null;
                return {};
            });
    }
    return _globalConfigPromise.then(res => res || {});
}

/**
 * Validate availability and prices for cart items (Batch)
 * @param {Array<number>} ids - List of product IDs
 * @returns {Promise<Array<{id: number, price: number, in_stock: boolean}>>}
 */
export async function validateCartItems(ids) {
    if (!ids || ids.length === 0) return [];
    try {
        // Filter for numbers only to be safe
        const validIds = ids.filter(id => typeof id === 'number');
        if (validIds.length === 0) return [];

        return await fetchJson(`${API_V1}/products/prices`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(validIds),
        });
    } catch (e) {
        console.error('[API] validateCartItems failed:', e);
        return [];
    }
}

let _installationRatesPromise = null;

export async function getInstallationRates() {
    if (!_installationRatesPromise) {
        // Cache the promise to prevent race conditions/multiple requests
        _installationRatesPromise = fetchJson(`${API_V1}/installation-rates`)
            .catch(err => {
                console.error('[API] Failed to fetch installation rates:', err);
                _installationRatesPromise = null; // Reset on failure so we can try again
                return [];
            });
    }
    // Handle case where fetchJson returns null (swallowed error)
    return _installationRatesPromise.then(res => res || []);
}

export async function submitContactForm(formData) {
    // We treat contact form submissions as Orders with no items (Leads)
    const url = `${API_V1}/orders`;

    // Transform flat form data to OrderPayload
    const payload = {
        customer: {
            name: formData.name,
            phone: formData.phone,
            email: formData.email || null
        },
        items: [],
        comment: formData.message || formData.comment || null
    };

    try {
        const response = await fetch(url, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(payload),
        });

        if (!response.ok) {
            console.error(`[API] Submit error ${response.status}`);
            return false;
        }
        return true;
    } catch (e) {
        console.error('[API] Submit exception:', e);
        return false;
    }
}

export async function submitProductAvailabilityLead(payload) {
    const url = `${API_V1}/leads/product-availability`;
    try {
        return await fetchJson(url, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(payload),
        }, false);
    } catch (e) {
        console.error('[API] submitProductAvailabilityLead failed:', e);
        return null;
    }
}

export async function getServiceOptions(category = 'installation_option') {
    const url = `${API_V1}/services/options?category=${category}`;
    const data = await fetchJson(url);
    return data || [];
}

export async function getInstallationPricingInfo() {
    const [rates, config] = await Promise.all([
        getInstallationRates(),
        getGlobalConfig()
    ]);

    // Find the minimum base price for standard (Wall) installation
    const wallRates = rates.filter(r => r.category.toLowerCase() === 'wall');
    const minStandardPrice = wallRates.length > 0
        ? Math.min(...wallRates.map(r => r.base_price))
        : 600; // Fallback

    const parsedDiscount = parseInt(config.install_discount || "100", 10);
    const discount = Number.isFinite(parsedDiscount) ? parsedDiscount : 0;
    const minBundlePrice = Math.max(0, minStandardPrice - discount);

    return {
        minStandardPrice,
        minBundlePrice,
        discount
    };
}

/**
 * Create a new order
 * @param {object} payload - Full order payload matching backend schema
 * @returns {Promise<object|null>} Order object or null on error
 */
export async function createOrder(payload) {
    const url = `${API_V1}/orders`;
    // We want to return specific errors for the UI to show form validation issues
    try {
        // Using returnNullOnError = false to catch and throw legacy-style
        const res = await fetchJson(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        }, false);
        return res;
    } catch (e) {
        // Rethrow with details if available, so caller can show specific validation errors
        if (e.details) throw e;
    }
}

// Smart Checkout Helpers
export async function getCompanyByUnp(unp) {
    if (!unp) return null;
    return await fetchJson(`${API_V1}/proxy/egr?unp=${unp}`);
}

export async function getAddressSuggestions(query) {
    const normalized = String(query || '').trim();
    if (normalized.length < 2) return { items: [] };
    return await fetchJson(`${API_V1}/address-suggest?q=${encodeURIComponent(normalized)}`) || { items: [] };
}

export async function getBankBySearch(search) {
    if (!search) return null;
    return await fetchJson(`${API_V1}/proxy/bank?search=${encodeURIComponent(search)}`);
}
