import {
    OpenAPI,
    LoginService,
    ManagerService,
    ManagerOrdersService,
    ManagerLeadsService,
    ManagerDashboardService,
    ManagerInstallersService,
    ManagerSettingsService,
    ManagerTariffsService,
    AdminService,
    ApiService,
    type ProductUpdate,
    type ManagerCustomerUpdatePayload,
    type ManagerCatalogProductItemResponse as Product,
    type ManagerOrderUpdatePayload,
    type DashboardStatsResponse,
    type DashboardTouchpoint,
    type ManagerInstallerCreatePayload,
    type ManagerInstallerUpdatePayload,
    type LeadCreatePayload,
    type LeadUpdatePayload,
    type LeadQualifyPayload,
    type LeadLossPayload,

    type ManagerSettingUpdatePayload,
    type ManagerTariffCreatePayload,
    type ManagerTariffUpdatePayload,
} from './client';

OpenAPI.WITH_CREDENTIALS = true;

export type Segment = 'b2c' | 'b2b';
export type DashboardView = 'kanban' | 'list';
export { type Product, type DashboardStatsResponse, type DashboardTouchpoint };

export const api = {
    async login(username: string, password: string) {
        return await LoginService.loginAccessToken({ username, password });
    },

    async checkAuth() {
        return await ManagerService.readUserMe();
    },

    async getDashboardStats() {
        return await ManagerDashboardService.getDashboardStats();
    },

    async getManagerOrders(params: {
        segment: Segment;
        page?: number;
        limit?: number;
        status?: string;
        search?: string;
        overdueOnly?: boolean;
        sort?: string;
    }) {
        return await ManagerOrdersService.getManagerOrders(
            params.segment,
            params.page ?? 1,
            params.limit ?? 50,
            params.status ?? undefined,
            params.search ?? undefined,
            params.overdueOnly ?? false,
            params.sort ?? 'created_at_desc',
        );
    },

    async getManagerOrderDetail(orderId: number) {
        return await ManagerOrdersService.getManagerOrderDetail(orderId);
    },

    async patchManagerOrder(orderId: number, payload: ManagerOrderUpdatePayload) {
        return await ManagerOrdersService.patchManagerOrder(orderId, payload);
    },

    async generateManagerOrderDoc(orderId: number, docType: string) {
        return await ManagerOrdersService.generateManagerOrderDocument(orderId, docType);
    },

    async moveOrderStatus(orderId: number, newStatus: string) {
        return await AdminService.moveOrderStatusAdminApiOrderMovePost({
            order_id: orderId,
            new_status: newStatus,
        });
    },

    async getManagerLeads(params: {
        page?: number;
        limit?: number;
        status?: string;
        source?: string;
        search?: string;
        overdueOnly?: boolean;
        includeArchived?: boolean;
        sort?: string;
    }) {
        return await ManagerLeadsService.getManagerLeads(
            params.page ?? 1,
            params.limit ?? 20,
            params.status ?? undefined,
            params.source ?? undefined,
            params.search ?? undefined,
            params.overdueOnly ?? false,
            params.includeArchived ?? false,
            params.sort ?? 'created_at_desc',
        );
    },

    async createManagerLead(payload: LeadCreatePayload) {
        return await ManagerLeadsService.createManagerLead(payload);
    },

    async patchManagerLead(leadId: number, payload: LeadUpdatePayload) {
        return await ManagerLeadsService.patchManagerLead(leadId, payload);
    },

    async qualifyManagerLead(leadId: number, payload: LeadQualifyPayload) {
        return await ManagerLeadsService.qualifyManagerLead(leadId, payload);
    },

    async markManagerLeadLost(leadId: number, payload: LeadLossPayload) {
        return await ManagerLeadsService.markManagerLeadLost(leadId, payload);
    },

    // Installers
    async getManagerInstallers(page = 1, limit = 100, search?: string) {
        return await ManagerInstallersService.getManagerInstallers(page, limit, search);
    },

    async createManagerInstaller(payload: ManagerInstallerCreatePayload) {
        return await ManagerInstallersService.createManagerInstaller(payload);
    },

    async updateManagerInstaller(id: number, payload: ManagerInstallerUpdatePayload) {
        return await ManagerInstallersService.updateManagerInstaller(id, payload);
    },

    async searchManagerInstallers(q: string, limit = 50) {
        return await ManagerInstallersService.searchManagerInstallers(q, limit);
    },

    // Settings
    async listManagerSettings() {
        return await ManagerSettingsService.listManagerSettings();
    },

    async updateManagerSetting(key: string, payload: ManagerSettingUpdatePayload) {
        return await ManagerSettingsService.updateManagerSetting(key, payload);
    },

    // Tariffs
    async listManagerTariffs() {
        return await ManagerTariffsService.listManagerTariffs();
    },

    async createManagerTariff(payload: ManagerTariffCreatePayload) {
        return await ManagerTariffsService.createManagerTariff(payload);
    },

    async updateManagerTariff(id: number, payload: ManagerTariffUpdatePayload) {
        return await ManagerTariffsService.updateManagerTariff(id, payload);
    },

    async deleteManagerTariff(id: number) {
        return await ManagerTariffsService.deleteManagerTariff(id);
    },
    // External integrations
    async getCompanyByUnp(unp: string) {
        return await ApiService.publicProxyEgrApiV1ProxyEgrGet(unp);
    },

    async getBankBySearch(search: string) {
        return await ApiService.publicFindBankApiV1ProxyBankGet(search);
    },

    // Legacy Product Manager methods
    async getProducts(limit = 50, page = 1) {
        return await ApiService.getProducts(page, limit);
    },

    async searchImages(query: string) {
        return await ManagerService.searchImages(query);
    },

    async uploadImage(productId: number, imageUrl: string, isInstallation = false) {
        return await ManagerService.uploadImage(imageUrl, productId, isInstallation);
    },

    async uploadLocalImages(productId: number, files: FileList | File[]) {
        return await ManagerService.uploadLocalImages(productId, {
            files: Array.from(files),
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

    async getCommonGalleryImages(productIds: number[]) {
        return await ManagerService.getCommonGalleryImages(productIds);
    },

    async bulkAddGalleryImages(
        productIds: number[],
        sourceUrls: string[],
        setMain = false,
        skipExisting = true,
        isInstallation = false,
    ) {
        return await ManagerService.bulkAddGalleryImages({
            product_ids: productIds,
            source_urls: sourceUrls,
            set_main: setMain,
            skip_existing: skipExisting,
            is_installation: isInstallation,
        });
    },

    async bulkDeleteCommonImages(
        productIds: number[],
        urls: string[],
        excludeInstallation = true,
    ) {
        return await ManagerService.bulkDeleteCommonGalleryImages({
            product_ids: productIds,
            urls,
            exclude_installation: excludeInstallation,
        });
    },

    async bulkUploadLocalImages(
        productIds: number[],
        files: FileList | File[],
        isInstallation = false,
        setMain = false,
    ) {
        return await ManagerService.bulkUploadLocalImages({
            product_ids_json: JSON.stringify(productIds),
            is_installation: isInstallation,
            set_main: setMain,
            files: Array.from(files),
        });
    },

    async cleanupMedia(dryRun: boolean) {
        return await ManagerService.cleanupMedia(dryRun);
    },

    async getManagerProducts(
        page = 1,
        limit = 40,
        search?: string,
        isPublished?: boolean,
        areaMin?: number,
        areaMax?: number,
        isInverter?: boolean,
        sort = 'newest',
    ) {
        return await ManagerService.getManagerProducts(
            page,
            limit,
            search ?? undefined,
            isPublished ?? undefined,
            areaMin ?? undefined,
            areaMax ?? undefined,
            isInverter ?? undefined,
            sort,
        );
    },

    async getManagerCustomers(page = 1, limit = 20, search?: string, type?: string, onlyWithOrders = false) {
        return await ManagerService.getManagerCustomers(page, limit, search ?? undefined, type ?? undefined, onlyWithOrders);
    },

    async getManagerCustomerDetail(customerId: number) {
        return await ManagerService.getManagerCustomerDetail(customerId);
    },

    async patchManagerCustomer(customerId: number, payload: ManagerCustomerUpdatePayload) {
        return await ManagerService.patchManagerCustomer(customerId, payload);
    },

    async updateProduct(id: number, data: ProductUpdate) {
        return await ManagerService.updateProduct(id, data);
    },

    async bulkRoundPrices(productIds: number[]) {
        return await ManagerService.bulkRoundPrice({ product_ids: productIds });
    },

    async getAllTags() {
        return await ManagerService.getAllTags();
    },

    async searchProducts(q: string) {
        return await ApiService.adminSearchProductsApiAdminProductsSearchGet(q);
    },

    async smartSearchProducts(q: string, limit = 40): Promise<Product[]> {
        const res = await ManagerService.smartSearchProducts(q, limit);
        return res.items;
    },

    async searchServices(q: string) {
        return await ApiService.adminSearchServicesApiAdminServicesSearchGet(q);
    },

    async getPublicSpecKeys() {
        return await ApiService.getPublicSpecKeys();
    },

    async bulkUpdateSpecs(productIds: number[], specs: Record<string, unknown>, operation: 'merge' | 'replace' | 'delete_keys' = 'merge') {
        return await ManagerService.bulkUpdateSpecs({
            product_ids: productIds,
            specs,
            operation,
        });
    },

    async rebuildWeb() {
        // Manually implement the request for the new endpoint
        const response = await fetch('/api/system/rebuild-web', {
            method: 'POST',
            headers: {
                'Accept': 'application/json',
                'Content-Type': 'application/json',
            },
        });
        if (!response.ok) {
            const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
            throw new Error(error.detail || 'Failed to trigger rebuild');
        }
        return await response.json();
    },

    async importFromOnliner(urls: string[], withRelated: boolean): Promise<{
        success_count: number;
        error_count: number;
        successes: string[];
        errors: string[];
    }> {
        const response = await fetch('/api/manager/catalog/import-onliner', {
            method: 'POST',
            credentials: 'include',
            headers: {
                'Accept': 'application/json',
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ urls, with_related: withRelated }),
        });
        if (!response.ok) {
            const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
            throw new Error(error.detail || 'Failed to import from Onliner');
        }
        return await response.json();
    },
};
