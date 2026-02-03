import { OpenAPI } from './client/core/OpenAPI';
import { ManagerService } from './client/services/ManagerService';
import { LoginService } from './client/services/LoginService';
import { ApiService } from './client/services/ApiService';
// Re-export common models if needed, or define local interfaces compatible with frontend
// import type { ProductResponse } from './client/models/ProductResponse';

// Configure base URL (relative to origin, proxied by Vite)
OpenAPI.BASE = import.meta.env.VITE_API_URL || '/api/manager'.replace('/api/manager', '');
// Logic: If VITE_API_URL is set (e.g. http://localhost:8000), use it.
// Otherwise default to '' (empty) so requests go to '/api/...' relative to current host.
// But generated client uses full paths from schema: e.g. '/api/manager/search-images'.
// So OpenAPI.BASE should be empty string if serving from same origin/proxy.
OpenAPI.BASE = '';
OpenAPI.WITH_CREDENTIALS = true;

// Keep existing interface for backward compatibility if needed, 
// though we usually rely on generated specific responses.
export interface Product {
    id: number;
    title: string;
    price: number;
    main_image?: string | null;
    is_published: boolean;
    gallery_images?: Array<{ id: number, url: string, is_installation_photo: boolean }>;
}

export const api = {
    async searchImages(query: string) {
        return ManagerService.searchImagesApiManagerSearchImagesPost(query);
    },

    async uploadImage(productId: number, imageUrl: string, isInstallation: boolean = false) {
        return ManagerService.uploadImageApiManagerUploadImagePost(imageUrl, productId, isInstallation);
    },

    async uploadLocalImages(productId: number, files: FileList | File[]) {
        // Convert FileList/Array to Array<Blob> as expected by generated client
        const fileArray = Array.from(files);
        return ManagerService.uploadLocalImagesApiManagerUploadLocalImagesPost(
            productId,
            { files: fileArray },
            false // isInstallation (default false in original)
        );
    },

    async linkSearchResult(productId: number, imageUrl: string) {
        return ManagerService.linkSearchResultApiManagerGalleryLinkSearchResultPost(imageUrl, productId);
    },

    async setMainImage(imageId: number) {
        return ManagerService.setMainImageApiManagerGallerySetMainPost(imageId);
    },

    async deleteGalleryImage(imageId: number) {
        return ManagerService.deleteGalleryImageApiManagerGalleryImageIdDelete(imageId);
    },

    async reuseSearch(q: string) {
        return ManagerService.reuseSearchApiManagerGalleryReuseSearchGet(q);
    },

    async reuseImage(productId: number, sourceUrl: string) {
        return ManagerService.reuseImageApiManagerGalleryReuseImagePost(productId, sourceUrl);
    },

    async cleanupMedia(dryRun: boolean) {
        return ManagerService.cleanupMediaApiManagerCleanupMediaPost(dryRun);
    },

    // Legacy API reuse -> Now using generated ApiService
    async getProducts(limit = 50, page = 1) {
        // ApiService.getCatalogApiV1ProductsGet returns CatalogResponse
        return ApiService.getCatalogApiV1ProductsGet(page, limit);
    },

    async login(username: string, password: string) {
        // LoginService expects FormData object
        return LoginService.loginAccessTokenLoginAccessTokenPost({
            username,
            password,
            grant_type: 'password' // OAuth2 standard usually requires this, let's check generated model if needed
        });
    },

    async checkAuth() {
        return ManagerService.checkAuthStatusApiManagerMeGet();
    }
};
