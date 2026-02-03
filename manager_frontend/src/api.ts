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

    // --- PRODUCTS (Public API) ---
    async getProducts(limit = 50, page = 1) {
        return await ApiService.getProducts(page, limit);
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
    }
};