import {
    OpenAPI,
    LoginService,
    ManagerService,
    ApiService,
    type ProductResponse as Product // Используем ProductResponse как Product
} from './client';

// 1. Настройка глобального конфига клиента
// Указываем, что нужно отправлять cookies (для авторизации)
OpenAPI.WITH_CREDENTIALS = true;
// Если API живет на том же домене/порту (через прокси), можно оставить BASE пустым или '/'
// OpenAPI.BASE = 'http://localhost:8000'; // Раскомментируй для локальной разработки без прокси

export { type Product }; // Экспортируем тип наружу

export const api = {
    // --- SEARCH & IMAGES (ManagerTools) ---
    async searchImages(query: string) {
        return await ManagerService.searchImages(query);
    },

    async uploadImage(productId: number, imageUrl: string, isInstallation: boolean = false) {
        return await ManagerService.uploadImage(imageUrl, productId, isInstallation);
    },

    async uploadLocalImages(productId: number, files: FileList | File[]) {
        return await ManagerService.uploadLocalImages(productId, {
            files: Array.from(files)
        });
    },

    async linkSearchResult(productId: number, imageUrl: string) {
        return await ManagerService.linkSearchResult(imageUrl, productId);
    },

    async setMainImage(imageId: number) {
        return await ManagerService.setMainImage(imageId);
    },

    async deleteGalleryImage(imageId: number) {
        return await ManagerService.deleteImage(imageId);
    },

    async reuseSearch(q: string) {
        return await ManagerService.reuseSearch(q);
    },

    async reuseImage(productId: number, sourceUrl: string) {
        return await ManagerService.reuseImage(productId, sourceUrl);
    },

    async cleanupMedia(dryRun: boolean) {
        return await ManagerService.cleanupMedia(dryRun);
    },

    async getCommonGalleryImages(productIds: number[]) {
        const params = new URLSearchParams();
        for (const id of productIds) {
            params.append('product_ids', String(id));
        }
        const res = await fetch(`/api/manager/gallery/common-images?${params.toString()}`, {
            credentials: 'include',
        });
        if (!res.ok) {
            throw new Error(`Failed to load common images: ${res.status}`);
        }
        return await res.json();
    },

    async bulkAddGalleryImages(
        productIds: number[],
        sourceUrls: string[],
        setMain: boolean = false,
        skipExisting: boolean = true,
        isInstallation: boolean = false,
    ) {
        const res = await fetch('/api/manager/gallery/bulk-add', {
            method: 'POST',
            credentials: 'include',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                product_ids: productIds,
                source_urls: sourceUrls,
                set_main: setMain,
                skip_existing: skipExisting,
                is_installation: isInstallation,
            }),
        });
        if (!res.ok) {
            throw new Error(`Failed to bulk add images: ${res.status}`);
        }
        return await res.json();
    },

    async bulkDeleteCommonImages(
        productIds: number[],
        urls: string[],
        excludeInstallation: boolean = true,
    ) {
        const res = await fetch('/api/manager/gallery/bulk-delete-common', {
            method: 'POST',
            credentials: 'include',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                product_ids: productIds,
                urls,
                exclude_installation: excludeInstallation,
            }),
        });
        if (!res.ok) {
            throw new Error(`Failed to bulk delete images: ${res.status}`);
        }
        return await res.json();
    },

    async bulkUploadLocalImages(
        productIds: number[],
        files: FileList | File[],
        isInstallation: boolean = false,
        setMain: boolean = false,
    ) {
        const form = new FormData();
        form.append('product_ids_json', JSON.stringify(productIds));
        form.append('is_installation', String(isInstallation));
        form.append('set_main', String(setMain));
        for (const file of Array.from(files)) {
            form.append('files', file);
        }

        const res = await fetch('/api/manager/gallery/bulk-upload-local', {
            method: 'POST',
            credentials: 'include',
            body: form,
        });
        if (!res.ok) {
            throw new Error(`Failed to bulk upload images: ${res.status}`);
        }
        return await res.json();
    },

    // --- PRODUCTS (Public API) ---
    async getProducts(limit = 50, page = 1) {
        return await ApiService.getProducts(page, limit);
    },

    async getPublicSpecKeys() {
        return await ApiService.getPublicSpecKeys();
    },

    // --- BULK TOOLS ---
    async bulkUpdateSpecs(productIds: number[], specs: Record<string, any>, operation: 'merge' | 'replace' | 'delete_keys' = 'merge') {
        return await ManagerService.bulkUpdateSpecs({
            product_ids: productIds,
            specs: specs,
            operation: operation
        });
    },

    // --- AUTH ---
    async login(username: string, password: string) {
        // Используем LoginService. OAuth2 форма требует отправки formData
        const response = await LoginService.loginAccessToken({
            username,
            password,
        });
        return response;
    },

    async checkAuth() {
        return await ManagerService.readUserMe();
    },

    // --- MANAGER LIST ENDPOINTS (Stitch) ---
    async getManagerProducts(
        page = 1,
        limit = 40,
        search?: string,
        isPublished?: boolean,
        areaMin?: number,
        areaMax?: number,
        isInverter?: boolean,
        sort = 'newest'
    ) {
        const params = new URLSearchParams({ page: String(page), limit: String(limit), sort });
        if (search) params.set('search', search);
        if (isPublished !== undefined) params.set('is_published', String(isPublished));
        if (areaMin !== undefined) params.set('area_min', String(areaMin));
        if (areaMax !== undefined) params.set('area_max', String(areaMax));
        if (isInverter !== undefined) params.set('is_inverter', String(isInverter));

        const res = await fetch(`/api/manager/products/list?${params}`, { credentials: 'include' });
        if (!res.ok) throw new Error(`Failed to load products: ${res.status}`);
        return await res.json();
    },

    async getManagerOrders(page = 1, limit = 20, status?: string, search?: string) {
        const params = new URLSearchParams({ page: String(page), limit: String(limit) });
        if (status) params.set('status', status);
        if (search) params.set('search', search);
        const res = await fetch(`/api/manager/orders?${params}`, { credentials: 'include' });
        if (!res.ok) throw new Error(`Failed to load orders: ${res.status}`);
        return await res.json();
    },

    async getManagerCustomers(page = 1, limit = 20, search?: string, type?: string) {
        const params = new URLSearchParams({ page: String(page), limit: String(limit) });
        if (search) params.set('search', search);
        if (type) params.set('type', type);
        const res = await fetch(`/api/manager/customers?${params}`, { credentials: 'include' });
        if (!res.ok) throw new Error(`Failed to load customers: ${res.status}`);
        return await res.json();
    },

    async updateProduct(id: number, data: Partial<Product>) {
        const res = await fetch(`/api/manager/products/${id}`, {
            method: 'PATCH',
            credentials: 'include',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data),
        });
        if (!res.ok) throw new Error(`Failed to update product: ${res.status}`);
        return await res.json();
    },

    async bulkRoundPrices(productIds: number[]) {
        const res = await fetch('/api/manager/products/bulk-round-price', {
            method: 'POST',
            credentials: 'include',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ product_ids: productIds }),
        });
        if (!res.ok) throw new Error(`Failed to round prices: ${res.status}`);
        return await res.json();
    },

    async getAllTags() {
        const res = await fetch('/api/manager/tags/all', { credentials: 'include' });
        if (!res.ok) throw new Error(`Failed to load tags: ${res.status}`);
        return await res.json();
    },
};
