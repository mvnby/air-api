const ENV_API_URL = import.meta.env.INTERNAL_API_URL || 'http://app:8000/api/v1';
const PUBLIC_API_ROOT = (import.meta.env.PUBLIC_API_URL || 'http://localhost:8000').replace(/\/api\/v1\/?$/, "");

// Ensure standard formatting (no trailing slash)
const BASE_URL = ENV_API_URL.replace(/\/$/, "");

// Define API versions relative to the base
// Assumption: BASE_URL points to .../api/v1
const API_V1 = BASE_URL;
const API_ROOT = BASE_URL.replace(/\/v1$/, ""); // Fallback for non-versioned endpoints

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

export async function submitContactForm(data) {
    // Assuming POST /leads based on context
    const url = `${API_V1}/leads`;
    try {
        const response = await fetch(url, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(data),
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
