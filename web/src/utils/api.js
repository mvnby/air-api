const ENV_API_URL = import.meta.env.INTERNAL_API_URL || 'http://app:8000/api/v1';
const PUBLIC_API_ROOT = (import.meta.env.PUBLIC_API_URL || 'http://localhost:8000').replace(/\/api\/v1\/?$/, "");

// Ensure standard formatting (no trailing slash)
const INTERNAL_URL = (import.meta.env.INTERNAL_API_URL || 'http://app:8000/api/v1').replace(/\/$/, "");
const PUBLIC_URL = (import.meta.env.PUBLIC_API_URL || 'http://localhost:8000/api/v1').replace(/\/$/, "");

// Define API versions relative to the base
// Use Client-side URL if not in SSR
const API_V1 = import.meta.env.SSR ? INTERNAL_URL : PUBLIC_URL;
const API_ROOT = API_V1.replace(/\/v1$/, ""); // Fallback for non-versioned endpoints

export function resolveImageUrl(path) {
    if (!path) return "/placeholder.jpg";
    if (path.startsWith("http")) return path;
    return `${PUBLIC_API_ROOT}/${path.replace(/^\//, "")}`;
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

async function fetchJson(url, errorMsg = 'API request failed') {
    try {
        const response = await fetch(url);
        if (!response.ok) {
            console.error(`[API] Error ${response.status} from ${url}`);
            return null; // Return null on error primarily
        }
        return await response.json();
    } catch (error) {
        console.error(`[API] Fetch error for ${url}:`, error.message);
        return null;
    }
}

export async function getCatalog(params = {}) {
    const query = buildQuery(params);
    const url = `${API_V1}/catalog?${query}`;
    console.log('[API] Fetching Catalog:', url);

    const data = await fetchJson(url);
    if (!data) {
        return { items: [], meta: { total: 0, page: 1, limit: 20, pages: 0 } };
    }
    return data;
}

export async function getProducts() {
    // Fetch all products for SSG (limit 1000 for now)
    const data = await getCatalog({ limit: 1000 });
    return data && data.items ? data.items : [];
}

export async function getProductBySlug(slug) {
    return await fetchJson(`${API_V1}/products/${slug}`);
}

export async function getProductById(id) {
    // Uses API_ROOT because ID endpoint is at /api/products/{id}
    const url = `${API_ROOT}/products/${id}`;
    console.log(`[SSR] Fetching product ${id} from: ${url}`);
    return await fetchJson(url);
}

export async function getGlobalConfig() {
    const data = await fetchJson(`${API_V1}/config`);
    return data || {};
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

    const discount = parseInt(config.install_discount || "100", 10);
    const minBundlePrice = Math.max(0, minStandardPrice - discount);

    return {
        minStandardPrice,
        minBundlePrice,
        discount
    };
}
