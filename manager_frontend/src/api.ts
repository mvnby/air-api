const API_BASE = '/api/manager';

export interface Product {
    id: number;
    title: string;
    price: number;
    main_image?: string;
    is_published: boolean;
}

export const api = {
    async searchImages(query: string) {
        const res = await fetch(`${API_BASE}/search-images?q=${encodeURIComponent(query)}`, {
            method: 'POST',
        });
        if (!res.ok) throw new Error('Search failed');
        return res.json() as Promise<string[]>;
    },

    async uploadImage(productId: number, imageUrl: string, isInstallation: boolean = false) {
        const res = await fetch(`${API_BASE}/upload-image?product_id=${productId}&url=${encodeURIComponent(imageUrl)}&is_installation=${isInstallation}`, {
            method: 'POST',
        });
        if (!res.ok) throw new Error('Upload failed');
        return res.json();
    },

    // Legacy API reuse
    async getProducts(limit = 50, page = 1) {
        const res = await fetch(`/api/v1/products?limit=${limit}&page=${page}`);
        if (!res.ok) throw new Error('Failed to load products');
        return res.json();
    }
};
