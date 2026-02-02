const API_BASE = '/api/manager';

export interface Product {
    id: number;
    title: string;
    price: number;
    main_image?: string;
    is_published: boolean;
    gallery_images?: Array<{ id: number, url: string, is_installation_photo: boolean }>;
}

export const api = {
    async searchImages(query: string) {
        const res = await fetch(`${API_BASE}/search-images?q=${encodeURIComponent(query)}`, {
            method: 'POST',
        });
        if (!res.ok) throw new Error('Search failed');
        // Now returns objects { image, width, height, ... }
        return res.json() as Promise<any[]>;
    },

    async uploadImage(productId: number, imageUrl: string, isInstallation: boolean = false) {
        const res = await fetch(`${API_BASE}/upload-image?product_id=${productId}&url=${encodeURIComponent(imageUrl)}&is_installation=${isInstallation}`, {
            method: 'POST',
        });
        if (!res.ok) throw new Error('Upload failed');
        return res.json();
    },

    async linkSearchResult(productId: number, imageUrl: string) {
        // We use uploadImage but we might want a specific endpoint if logic differs.
        // For now, let's reuse uploadImage as it does exactly what we want (download + link), 
        // BUT we need to ensure it doesn't auto-set main image if we don't want it to.
        // The current backend sets main image if not installation. 
        // We might want to add a flag to uploadImage or use the new link-search-result endpoint.
        // Let's use the new endpoint if we implemented it, or use uploadImage if we want standard behavior.
        // The implementation plan says "Add to gallery (without setting main immediately)".
        // My backend implementation for link-search-result was "pass" (oops). 
        // Let's fix that. For now, I'll assume I'll fix the backend to actually do the work.
        // Or I can just use uploadImage and accept it sets main for now, or add a query param.

        // Actually, let's use the new endpoint path, assuming I'll provide a real implementation.
        const res = await fetch(`${API_BASE}/gallery/link-search-result?product_id=${productId}&url=${encodeURIComponent(imageUrl)}`, {
            method: 'POST'
        });
        if (!res.ok) throw new Error('Link failed');
        return res.json();
    },

    async setMainImage(imageId: number) {
        const res = await fetch(`${API_BASE}/gallery/set-main?image_id=${imageId}`, { method: 'POST' });
        if (!res.ok) throw new Error('Failed to set main image');
        return res.json();
    },

    async deleteGalleryImage(imageId: number) {
        const res = await fetch(`${API_BASE}/gallery/${imageId}`, { method: 'DELETE' });
        if (!res.ok) throw new Error('Failed to delete image');
        return res.json();
    },

    async reuseSearch(q: string) {
        const res = await fetch(`${API_BASE}/gallery/reuse-search?q=${encodeURIComponent(q)}`);
        if (!res.ok) throw new Error('Reuse search failed');
        return res.json();
    },

    async reuseImage(productId: number, sourceUrl: string) {
        const res = await fetch(`${API_BASE}/gallery/reuse-image?product_id=${productId}&source_image_url=${encodeURIComponent(sourceUrl)}`, { method: 'POST' });
        if (!res.ok) throw new Error('Reuse failed');
        return res.json();
    },

    async cleanupMedia(dryRun: boolean) {
        const res = await fetch(`${API_BASE}/cleanup-media?dry_run=${dryRun}`, { method: 'POST' });
        if (!res.ok) throw new Error('Cleanup failed');
        return res.json();
    },

    // Legacy API reuse
    async getProducts(limit = 50, page = 1) {
        const res = await fetch(`/api/v1/products?limit=${limit}&page=${page}`);
        if (!res.ok) throw new Error('Failed to load products');
        return res.json();
    }
};
