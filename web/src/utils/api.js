const API_BASE = import.meta.env.INTERNAL_API_URL || 'http://app:8000/api/v1';
const PUBLIC_API_BASE = import.meta.env.PUBLIC_API_URL || 'http://localhost:8000/api/v1';

export async function getCatalog(params = {}) {
    // Manually build URLSearchParams to handle arrays correctly (FastAPI expects repeated keys)
    const searchParams = new URLSearchParams();

    Object.entries(params).forEach(([key, value]) => {
        if (Array.isArray(value)) {
            value.forEach(v => searchParams.append(key, v));
        } else if (value !== null && value !== undefined) {
            searchParams.append(key, value);
        }
    });

    const query = searchParams.toString();
    const url = `${API_BASE}/catalog?${query}`;
    console.log('Fetching from:', url);

    try {
        const response = await fetch(url);
        if (!response.ok) throw new Error('API request failed');
        return await response.json();
    } catch (error) {
        console.error('Fetch error:', error);
        return { items: [], meta: { total: 0, page: 1, limit: 20, pages: 0 } };
    }
}

export async function getProductBySlug(slug) {
    const url = `${API_BASE}/products/${slug}`;
    try {
        const response = await fetch(url);
        if (!response.ok) return null;
        return await response.json();
    } catch (error) {
        console.error('Fetch error:', error);
        return null;
    }
}

export async function getProductById(id) {
    // FIX: The backend ID endpoint is /api/products/{id}, NOT /api/v1/products/{id}
    // We strip '/v1' from the base URL to match the router structure.
    const apiRoot = API_BASE.replace(/\/v1\/?$/, '');
    const url = `${apiRoot}/products/${id}`;

    console.log(`[SSR] Fetching product ${id} from: ${url}`);
    try {
        const response = await fetch(url);
        if (!response.ok) {
            console.error(`[SSR] Failed to fetch product ${id}: ${response.status} ${response.statusText}`);
            return null;
        }
        const data = await response.json();
        console.log(`[SSR] Successfully fetched product ${id}: ${data.title}`);
        return data;
    } catch (error) {
        console.error(`[SSR] Error fetching product ${id} from ${url}:`, error.message);
        return null;
    }
}

export async function getGlobalConfig() {
    const url = `${API_BASE}/config`;
    try {
        const response = await fetch(url);
        if (!response.ok) return {};
        return await response.json();
    } catch (error) {
        console.error('Fetch error:', error);
        return {};
    }
}
