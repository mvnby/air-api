const API_BASE = import.meta.env.INTERNAL_API_URL || 'http://app:8000/api/v1';
const PUBLIC_API_BASE = import.meta.env.PUBLIC_API_URL || 'http://localhost:8000/api/v1';

export async function getCatalog(params = {}) {
    const query = new URLSearchParams(params).toString();
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
