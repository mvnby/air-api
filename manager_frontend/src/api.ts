import {
    OpenAPI,
    ManagerService,
    ManagerOrdersService,
    ManagerDashboardService,
    ManagerInstallersService,
    ManagerStaffService,
    ManagerSettingsService,
    ManagerGoogleAuthService,
    ManagerBackupsService,
    ManagerTariffsService,
    ManagerServiceEstimatesService,
    ManagerBrandsService,
    ManagerMediaService,
    ManagerCatalogQualityService,
    SystemService,
    ApiService,
    type Body_upload_media_assets,
    type ProductCreate,
    type ProductDuplicatePayload,
    type ProductUpdate,
    type ManagerCustomerBranchCreatePayload,
    type ManagerCustomerBranchUpdatePayload,
    type ManagerCustomerUpdatePayload,
    type ManagerCatalogProductItemResponse as Product,
    type ManagerOrderUpdatePayload,
    type DashboardStatsResponse,
    type DashboardTouchpoint,
    type ManagerInstallerCreatePayload,
    type ManagerInstallerUpdatePayload,
    type ManagerStaffCreatePayload,
    type ManagerStaffResponse,
    type ManagerStaffUpdatePayload,
    type ManagerSettingUpdatePayload,
    type ManagerTariffCreatePayload,
    type ManagerQuickTariffListResponse,
    type ManagerQuickTariffResponse,
    type ManagerTariffRuleCreatePayload,
    type ManagerTariffRuleUpdatePayload,
    type ManagerTariffServiceKind,
    type ManagerTariffUpdatePayload,
    type ManagerInstallEstimateCalculatePayload,
    type ManagerInstallEstimateSavePayload,
    type ManagerServiceEstimateListResponse,
    type ManagerServiceEstimateOrderLinesMode,
    type ManagerServiceDescriptionMode,
    type ManagerServiceEstimateOrderLinesResponse,
    type ManagerServiceEstimateResponse,
    type ManagerInstallEstimateResponse,
    type SupplierCreatePayload,
    type SupplierUpdatePayload,
    type SupplierContactCreatePayload,
    type SupplierContactUpdatePayload,
    type SupplierWarehouseCreatePayload,
    type SupplierWarehouseUpdatePayload,
    type SupplierPriceSourceCreatePayload,
    type SupplierPriceSourceUpdatePayload,
    type SupplierMappingCreatePayload,
    type SupplierMappingBulkCreatePayload,
    type SupplierOfferSuggestionsPayload,
    type SupplierSourceUrlImportPayload,
    type SupplyLogisticsMessagePayload,
    type SupplyRequestCreatePayload,
    type SupplyRequestFromOrderLinesPayload,
    type SupplyRequestLineUpdatePayload,
    type SupplyRequestStockCreatePayload,
    type SupplyRequestUpdatePayload,
    type ProductLocalStockPayload,
    type ManagerGoogleAuthStatusResponse,
    type ManagerGoogleAuthUrlResponse,
    type ManagerBackupListResponse,
    type ManagerBackupRunStartResponse,
    type ManagerBackupRunStatusResponse,
    type ManagerRestoreJobStartResponse,
    type ManagerRestoreJobStatusResponse,
    type CatalogImportJobStartResponse,
    type CatalogImportJobStatusResponse,
    type MdvCatalogImportPayload,
    type MdvCatalogPreviewPayload,
    type MdvCatalogPreviewResponse,
    type ManagerBrandResponse,
    type ManagerBrandCreatePayload,
    type ManagerBrandFeatureCreatePayload,
    type ManagerBrandFeatureResponse,
    type ManagerBrandFeatureUpdatePayload,
    type ManagerBrandSeriesCreatePayload,
    type ManagerBrandSeriesResponse,
    type ManagerBrandSeriesUpdatePayload,
    type ManagerBrandUpdatePayload,
    type ManagerCatalogQualityReportResponse,
    type ManagerBackgroundRemovalConfigResponse,
    type ManagerMediaAssetCropPayload,
    type ManagerMediaAssetListResponse,
    type ManagerMediaAssetResponse,
    type ManagerMediaAssetUpdatePayload,
    type ManagerMediaAssetUrlUploadPayload,
    type ManagerMediaAssetUploadResponse,
    type ManagerMediaApplySeriesResponse,
    type ManagerMediaBackfillReferencedAssetsResponse,
    type ManagerMediaProcessingJobCreatePayload,
    type ManagerMediaProcessingJobListResponse,
    type ManagerMediaProcessingJobResponse,
    type ProductImageCropPayload,
    type ProductImageVariantBatchProcessResponse,
    type ProductImageVariantCandidateResponse,
    type ProductImageVariantCandidatesResponse,
    type ProductImageVariantResponse,
    type ProductMainImageCleanupBatchCreatePayload,
    type ProductMainImageCleanupBatchCreateResponse,
    type ProductMainImageCleanupBatchListResponse,
    type ProductMainImageCleanupBatchResponse,
    type ProductMainImageCleanupDecisionResponse,
    type ProductMainImageCleanupItemListResponse,
    type ProductMainImageCleanupItemResponse,
    type SpecRegistryResponse,
} from './client';
import { ManagerTagsService } from './client/services/ManagerTagsService';
import { ManagerLeadsInboxService } from './client/services/ManagerLeadsInboxService';
import type { LeadsInboxItemResponse } from './client/models/LeadsInboxItemResponse';
import {
    getManagerStorefrontRequestHeaders,
    installManagerStorefrontHeaderResolver,
} from './services/manager-storefront-selection';

OpenAPI.WITH_CREDENTIALS = true;
installManagerStorefrontHeaderResolver();

export type Segment = 'all' | 'b2c' | 'b2b';
export type DashboardView = 'kanban' | 'list';
export { type Product, type DashboardStatsResponse, type DashboardTouchpoint };
export type { ProductCreate, ProductDuplicatePayload, ProductUpdate };
export type { SpecRegistryResponse };
export type { LeadsInboxItemResponse };
export type { ManagerGoogleAuthStatusResponse, ManagerGoogleAuthUrlResponse };
export type { ManagerStaffCreatePayload, ManagerStaffResponse, ManagerStaffUpdatePayload };
export type {
    ManagerBackupListResponse,
    ManagerBackupRunStartResponse,
    ManagerBackupRunStatusResponse,
    ManagerRestoreJobStartResponse,
    ManagerRestoreJobStatusResponse,
    CatalogImportJobStartResponse,
    CatalogImportJobStatusResponse,
    MdvCatalogImportPayload,
    MdvCatalogPreviewPayload,
    MdvCatalogPreviewResponse,
};
export type {
    ManagerInstallEstimateCalculatePayload,
    ManagerInstallEstimateSavePayload,
    ManagerServiceEstimateListResponse,
    ManagerServiceEstimateOrderLinesMode,
    ManagerServiceDescriptionMode,
    ManagerServiceEstimateOrderLinesResponse,
    ManagerServiceEstimateResponse,
    ManagerInstallEstimateResponse,
};
export type {
    ManagerQuickTariffListResponse,
    ManagerQuickTariffResponse,
};

type ManagerBrand = ManagerBrandResponse;
type ManagerBrandFeature = ManagerBrandFeatureResponse;
type ManagerBrandSeries = ManagerBrandSeriesResponse;

export type {
    ManagerBrand,
    ManagerBrandCreatePayload,
    ManagerBrandFeature,
    ManagerBrandFeatureCreatePayload,
    ManagerBrandFeatureUpdatePayload,
    ManagerBrandSeries,
    ManagerBrandSeriesCreatePayload,
    ManagerBrandSeriesUpdatePayload,
    ManagerBrandUpdatePayload,
};
export type { ManagerCatalogQualityReportResponse };
export type {
    Body_upload_media_assets,
    ManagerBackgroundRemovalConfigResponse,
    ManagerMediaAssetCropPayload,
    ManagerMediaAssetListResponse,
    ManagerMediaAssetResponse,
    ManagerMediaAssetUpdatePayload,
    ManagerMediaAssetUrlUploadPayload,
    ManagerMediaAssetUploadResponse,
    ManagerMediaApplySeriesResponse,
    ManagerMediaBackfillReferencedAssetsResponse,
    ManagerMediaProcessingJobCreatePayload,
    ManagerMediaProcessingJobListResponse,
    ManagerMediaProcessingJobResponse,
};
export type {
    ProductImageVariantBatchProcessResponse,
    ProductImageVariantCandidateResponse,
    ProductImageVariantCandidatesResponse,
    ProductImageVariantResponse,
    ProductImageCropPayload,
};
export type {
    ProductMainImageCleanupBatchCreatePayload,
    ProductMainImageCleanupBatchCreateResponse,
    ProductMainImageCleanupBatchListResponse,
    ProductMainImageCleanupBatchResponse,
    ProductMainImageCleanupDecisionResponse,
    ProductMainImageCleanupItemListResponse,
    ProductMainImageCleanupItemResponse,
};
export type {
    SupplierContactCreatePayload,
    SupplierContactUpdatePayload,
    SupplierWarehouseCreatePayload,
    SupplierWarehouseUpdatePayload,
    SupplyLogisticsMessagePayload,
    SupplyRequestCreatePayload,
    SupplyRequestFromOrderLinesPayload,
    SupplyRequestLineUpdatePayload,
    SupplyRequestStockCreatePayload,
    SupplyRequestUpdatePayload,
};

const parseContentDispositionFilename = (header: string | null): string | undefined => {
    if (!header) return undefined;

    const utf8Match = header.match(/filename\*=UTF-8''([^;]+)/i);
    if (utf8Match?.[1]) {
        try {
            return decodeURIComponent(utf8Match[1].trim());
        } catch {
            return utf8Match[1].trim();
        }
    }

    const asciiMatch = header.match(/filename="?([^";]+)"?/i);
    return asciiMatch?.[1]?.trim();
};

export const downloadManagerDocBlob = async (docId: number): Promise<{ blob: Blob; filename?: string }> => {
    const url = `${OpenAPI.BASE}/api/manager/docs/${encodeURIComponent(String(docId))}/download`;
    const response = await fetch(url, {
        method: 'GET',
        credentials: OpenAPI.WITH_CREDENTIALS ? OpenAPI.CREDENTIALS : 'same-origin',
        headers: {
            Accept: 'application/pdf',
            ...getManagerStorefrontRequestHeaders(url),
        },
    });

    if (!response.ok) {
        let message = `Ошибка скачивания документа (${response.status})`;
        try {
            const payload = await response.json();
            message = payload?.detail?.message || payload?.detail || payload?.message || message;
        } catch {
            const text = await response.text();
            if (text) message = text;
        }
        throw new Error(message);
    }

    return {
        blob: await response.blob(),
        filename: parseContentDispositionFilename(response.headers.get('Content-Disposition')),
    };
};

export interface ManagerProductFilterOptions {
    heatingMin?: number;
    hasWifi?: boolean;
    hasFreshAir?: boolean;
    brandSlugs?: string[];
    seriesId?: number;
    areaMin?: number;
    areaMax?: number;
    categoryStatus?: 'assigned' | 'missing';
}

export interface CatalogQualityReportParams {
    page?: number;
    limit?: number;
    q?: string | null;
    category?: 'media' | 'identity' | 'specs' | 'commerce' | 'supplier' | null;
    severity?: 'critical' | 'warning' | 'info' | null;
    issueCode?: string | null;
    onlyProblems?: boolean;
    equipmentType?: string | null;
    equipmentSubtype?: string | null;
    brandId?: number | null;
    seriesId?: number | null;
    seriesState?: 'assigned' | 'missing' | null;
    supplierId?: number | null;
    supplierState?: 'mapped' | 'in_stock' | 'unmapped' | 'multiple' | null;
    publication?: 'published' | 'hidden' | null;
    availability?: 'in_stock' | 'out_of_stock' | null;
    priority?: 'high' | 'medium' | 'low' | null;
    scoreMin?: number | null;
    scoreMax?: number | null;
    onlyFixable?: boolean;
    sortBy?: 'priority' | 'score_asc' | 'critical' | 'stock' | 'newest' | 'title' | 'brand' | 'series';
    groupBy?: 'none' | 'brand' | 'series' | 'supplier' | 'equipment_type';
}

export const api = {
    async getDashboardStats() {
        return await ManagerDashboardService.getDashboardStats();
    },

    async getCatalogQualityReport(params: CatalogQualityReportParams = {}): Promise<ManagerCatalogQualityReportResponse> {
        return await ManagerCatalogQualityService.getManagerCatalogQualityReport(
            params.page ?? 1,
            params.limit ?? 50,
            params.q ?? null,
            params.category ?? null,
            params.severity ?? null,
            params.issueCode ?? null,
            params.onlyProblems ?? true,
            params.equipmentType ?? null,
            params.equipmentSubtype ?? null,
            params.brandId ?? null,
            params.seriesId ?? null,
            params.seriesState ?? null,
            params.supplierId ?? null,
            params.supplierState ?? null,
            params.publication ?? null,
            params.availability ?? null,
            params.priority ?? null,
            params.scoreMin ?? null,
            params.scoreMax ?? null,
            params.onlyFixable ?? false,
            params.sortBy ?? 'priority',
            params.groupBy ?? 'none',
        );
    },

    async listMediaAssets(params: {
        page?: number;
        limit?: number;
        q?: string | null;
        kind?: string | null;
        tag?: string | null;
        status?: string | null;
    } = {}): Promise<ManagerMediaAssetListResponse> {
        return await ManagerMediaService.listMediaAssets(
            params.page ?? 1,
            params.limit ?? 40,
            params.q ?? null,
            params.kind ?? null,
            params.tag ?? null,
            params.status ?? null,
        );
    },

    async uploadMediaAssets(formData: Body_upload_media_assets): Promise<ManagerMediaAssetUploadResponse> {
        return await ManagerMediaService.uploadMediaAssets(formData);
    },

    async uploadMediaAssetFromUrl(payload: ManagerMediaAssetUrlUploadPayload): Promise<ManagerMediaAssetUploadResponse> {
        return await ManagerMediaService.uploadMediaAssetFromUrl(payload);
    },

    async backfillReferencedMediaAssets(
        execute = false,
        limit = 500,
        includeRemote = false,
    ): Promise<ManagerMediaBackfillReferencedAssetsResponse> {
        return await ManagerMediaService.backfillReferencedMediaAssets(execute, limit, includeRemote);
    },

    async getMediaBackgroundRemovalConfig(): Promise<ManagerBackgroundRemovalConfigResponse> {
        return await ManagerMediaService.getMediaBackgroundRemovalConfig();
    },

    async updateMediaAsset(assetId: number, payload: ManagerMediaAssetUpdatePayload): Promise<ManagerMediaAssetResponse> {
        return await ManagerMediaService.updateMediaAsset(assetId, payload);
    },

    async cropMediaAsset(assetId: number, payload: ManagerMediaAssetCropPayload): Promise<ManagerMediaAssetResponse> {
        return await ManagerMediaService.cropMediaAsset(assetId, payload);
    },

    async removeMediaAssetBackground(assetId: number, provider = 'auto', rembgModel?: string | null): Promise<ManagerMediaAssetResponse> {
        return await ManagerMediaService.removeMediaAssetBackground(assetId, provider, rembgModel);
    },

    async listMediaProcessingJobs(params: {
        status?: string | null;
        limit?: number;
    } = {}): Promise<ManagerMediaProcessingJobListResponse> {
        return await ManagerMediaService.listMediaProcessingJobs(
            params.status ?? null,
            params.limit ?? 20,
        );
    },

    async createMediaProcessingJob(
        assetId: number,
        payload: ManagerMediaProcessingJobCreatePayload,
    ): Promise<ManagerMediaProcessingJobResponse> {
        return await ManagerMediaService.createMediaProcessingJob(assetId, payload);
    },

    async deleteMediaAsset(assetId: number, force = false) {
        return await ManagerMediaService.deleteMediaAsset(assetId, force);
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

    async createManagerOrder(payload: any) {
        return await ManagerOrdersService.createManagerOrder(payload);
    },

    async patchManagerOrder(orderId: number, payload: ManagerOrderUpdatePayload) {
        return await ManagerOrdersService.patchManagerOrder(orderId, payload);
    },

    async generateManagerOrderDoc(orderId: number, docType: string) {
        return await ManagerOrdersService.generateManagerOrderDocument(orderId, docType);
    },

    async moveOrderStatus(orderId: number, newStatus: string) {
        await ManagerOrdersService.patchManagerOrder(orderId, { status: newStatus });
        return { success: true };
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

    // Staff users
    async listManagerStaff(page = 1, limit = 100, search?: string) {
        return await ManagerStaffService.listManagerStaff(page, limit, search);
    },

    async createManagerStaff(payload: ManagerStaffCreatePayload) {
        return await ManagerStaffService.createManagerStaff(payload);
    },

    async patchManagerStaff(id: number, payload: ManagerStaffUpdatePayload) {
        return await ManagerStaffService.patchManagerStaff(id, payload);
    },

    // Settings
    async listManagerSettings() {
        return await ManagerSettingsService.listManagerSettings();
    },

    async updateManagerSetting(key: string, payload: ManagerSettingUpdatePayload) {
        return await ManagerSettingsService.updateManagerSetting(key, payload);
    },

    async getManagerGoogleAuthStatus() {
        return await ManagerGoogleAuthService.getManagerGoogleAuthStatus();
    },

    async getManagerGoogleAuthUrl() {
        return await ManagerGoogleAuthService.getManagerGoogleAuthUrl();
    },

    async listManagerBackups() {
        return await ManagerBackupsService.listManagerBackups();
    },

    async startManagerBackupRun() {
        return await ManagerBackupsService.startManagerBackupRun();
    },

    async getManagerBackupRunStatus(jobId: string) {
        return await ManagerBackupsService.getManagerBackupRunStatus(jobId);
    },

    async startManagerBackupRestore(fileId: string) {
        return await ManagerBackupsService.startManagerBackupRestore(fileId);
    },

    async getManagerBackupRestoreStatus(jobId: string) {
        return await ManagerBackupsService.getManagerBackupRestoreStatus(jobId);
    },

    // Tariffs
    async listManagerTariffs() {
        return await ManagerTariffsService.listManagerTariffs();
    },

    async listManagerTariffsByKind(serviceKind?: ManagerTariffServiceKind, includeInactive = true) {
        return await ManagerTariffsService.listManagerTariffs(serviceKind ?? null, includeInactive);
    },

    async listManagerQuickTariffs(q = '', serviceKind?: ManagerTariffServiceKind | null, limit = 10): Promise<ManagerQuickTariffListResponse> {
        return await ManagerTariffsService.listManagerQuickTariffs(q, serviceKind ?? null, limit);
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

    async listManagerTariffRules(tariffId: number, includeInactive = true) {
        return await ManagerTariffsService.listManagerTariffRules(tariffId, includeInactive);
    },

    async listManagerFavoriteTariffRules(serviceKind: ManagerTariffServiceKind, includeInactive = false, excludeTariffId?: number | null) {
        return await ManagerTariffsService.listManagerFavoriteTariffRules(serviceKind, includeInactive, excludeTariffId ?? null);
    },

    async createManagerTariffRule(tariffId: number, payload: ManagerTariffRuleCreatePayload) {
        return await ManagerTariffsService.createManagerTariffRule(tariffId, payload);
    },

    async updateManagerTariffRule(tariffId: number, ruleId: number, payload: ManagerTariffRuleUpdatePayload) {
        return await ManagerTariffsService.updateManagerTariffRule(tariffId, ruleId, payload);
    },

    async deleteManagerTariffRule(tariffId: number, ruleId: number) {
        return await ManagerTariffsService.deleteManagerTariffRule(tariffId, ruleId);
    },

    // Install estimates (issue #260)
    async calculateManagerInstallEstimate(payload: ManagerInstallEstimateCalculatePayload) {
        return await ManagerServiceEstimatesService.calculateManagerInstallEstimate(payload);
    },

    async createManagerServiceEstimate(payload: ManagerInstallEstimateSavePayload) {
        return await ManagerServiceEstimatesService.createManagerServiceEstimate(payload);
    },

    async listManagerServiceEstimates(page = 1, limit = 20, customerId?: number): Promise<ManagerServiceEstimateListResponse> {
        return await ManagerServiceEstimatesService.listManagerServiceEstimates(page, limit, customerId ?? null);
    },

    async getManagerServiceEstimate(estimateId: number): Promise<ManagerServiceEstimateResponse> {
        return await ManagerServiceEstimatesService.getManagerServiceEstimate(estimateId);
    },

    async getManagerServiceEstimateOrderLines(
        estimateId: number,
        mode: ManagerServiceEstimateOrderLinesMode = 'detailed',
        descriptionMode: ManagerServiceDescriptionMode = 'short',
    ): Promise<ManagerServiceEstimateOrderLinesResponse> {
        return await ManagerServiceEstimatesService.getManagerServiceEstimateOrderLines(estimateId, mode, descriptionMode);
    },

    async deleteManagerServiceEstimate(estimateId: number) {
        return await ManagerServiceEstimatesService.deleteManagerServiceEstimate(estimateId);
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

    async cropGalleryImage(imageId: number, payload: ProductImageCropPayload) {
        return await ManagerService.cropProductImage(imageId, payload);
    },

    async removeProductImageBackground(
        imageId: number,
        provider = 'auto',
        rembgModel?: string | null,
        mode = 'replace',
        setMain = false,
    ) {
        return await ManagerService.removeProductImageBackground(
            imageId,
            provider,
            rembgModel,
            mode,
            setMain,
        );
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

    async applyGalleryToSeries(
        productId: number,
        dryRun = false,
        deleteUnreferenced = false,
    ): Promise<ManagerMediaApplySeriesResponse> {
        return await ManagerService.applyGalleryToSeries(productId, dryRun, deleteUnreferenced);
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

    async getImageVariantCandidates(variantType = 'card', limit = 100, includeInstallation = false) {
        return await ManagerService.getImageVariantCandidates(variantType, limit, includeInstallation);
    },

    async processMissingImageVariants(
        variantType = 'card',
        limit = 100,
        includeInstallation = false,
        dryRun = true,
        provider = 'noop',
        rembgModel?: string | null,
    ) {
        return await ManagerService.processMissingImageVariants(
            variantType,
            limit,
            includeInstallation,
            dryRun,
            provider,
            rembgModel,
        );
    },

    async reprocessImageVariant(imageId: number, variantType = 'card', provider = 'noop', rembgModel?: string | null) {
        return await ManagerService.reprocessImageVariant(imageId, variantType, provider, rembgModel);
    },

    async createMainImageCleanupBatch(payload: ProductMainImageCleanupBatchCreatePayload) {
        return await ManagerService.createMainImageCleanupBatch(payload);
    },

    async listMainImageCleanupBatches(limit = 20, offset = 0) {
        return await ManagerService.listMainImageCleanupBatches(limit, offset);
    },

    async listMainImageCleanupItems(batchId?: number | null, status?: string | null, limit = 100, offset = 0) {
        return await ManagerService.listMainImageCleanupItems(batchId ?? null, status ?? null, limit, offset);
    },

    async approveMainImageCleanupItems(itemIds: number[]) {
        return await ManagerService.approveMainImageCleanupItems({ item_ids: itemIds });
    },

    async rejectMainImageCleanupItems(itemIds: number[], reason: string) {
        return await ManagerService.rejectMainImageCleanupItems({ item_ids: itemIds, reason });
    },

    async getManagerProducts(
        page = 1,
        limit = 40,
        search?: string,
        isPublished?: boolean,
        areaMin?: number,
        areaMax?: number,
        isInverter?: boolean,
        categorySlug?: string,
        sort = 'recommended',
        filters: ManagerProductFilterOptions = {},
    ) {
        return await ManagerService.getManagerProducts(
            page,
            limit,
            search ?? undefined,
            isPublished ?? undefined,
            areaMin ?? undefined,
            areaMax ?? undefined,
            isInverter ?? undefined,
            filters.heatingMin ?? undefined,
            filters.hasWifi ?? undefined,
            filters.hasFreshAir ?? undefined,
            filters.brandSlugs ?? undefined,
            filters.seriesId ?? undefined,
            categorySlug ?? undefined,
            filters.categoryStatus ?? undefined,
            sort,
        );
    },

    async getManagerProduct(productId: number): Promise<Product> {
        return await ManagerService.getManagerProduct(productId);
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

    async getManagerCustomerBranches(customerId: number) {
        return await ManagerService.getManagerCustomerBranches(customerId);
    },

    async createManagerCustomerBranch(customerId: number, payload: ManagerCustomerBranchCreatePayload) {
        return await ManagerService.createManagerCustomerBranch(customerId, payload);
    },

    async patchManagerCustomerBranch(customerId: number, branchId: number, payload: ManagerCustomerBranchUpdatePayload) {
        return await ManagerService.patchManagerCustomerBranch(customerId, branchId, payload);
    },

    async deleteManagerCustomerBranch(customerId: number, branchId: number) {
        return await ManagerService.deleteManagerCustomerBranch(customerId, branchId);
    },

    async deleteManagerCustomer(customerId: number) {
        return await ManagerService.deleteManagerCustomer(customerId);
    },

    async updateProduct(id: number, data: ProductUpdate) {
        return await ManagerService.updateProduct(id, data);
    },

    async createProduct(data: ProductCreate) {
        return await ManagerService.createManagerProduct(data);
    },

    async duplicateProduct(id: number, data: ProductDuplicatePayload) {
        return await ManagerService.duplicateManagerProduct(id, data);
    },

    async deleteProduct(id: number) {
        return await ManagerService.deleteManagerProduct(id);
    },

    async bulkRoundPrices(productIds: number[]) {
        return await ManagerService.bulkRoundPrice({ product_ids: productIds });
    },

    async bulkSetPricesToRrc(productIds: number[]) {
        return await ManagerService.bulkSetRrcPrice({ product_ids: productIds });
    },

    async bulkDeleteProducts(productIds: number[]) {
        return await ManagerService.bulkDeleteManagerProducts({ product_ids: productIds });
    },

    async getAllTags() {
        return await ManagerService.getAllTags();
    },

    async createTagGroup(payload: {
        title: string;
        slug?: string;
        is_public?: boolean;
        color?: string;
        allow_multiple?: boolean;
    }) {
        return await ManagerTagsService.createManagerTagGroup(payload);
    },

    async createTag(payload: {
        group_id: number;
        title: string;
        slug?: string;
        is_public?: boolean;
        is_filter?: boolean;
    }) {
        return await ManagerTagsService.createManagerTag(payload);
    },

    async searchProducts(q: string) {
        return await ApiService.adminSearchProductsApiAdminProductsSearchGet(q);
    },

    async smartSearchProducts(
        q: string,
        limit = 40,
        isInverter?: boolean,
        hasWifi?: boolean,
        categorySlug?: string,
        filters: ManagerProductFilterOptions = {},
    ): Promise<Product[]> {
        const res = await ManagerService.smartSearchProducts(
            q,
            limit,
            isInverter,
            filters.areaMin ?? undefined,
            filters.areaMax ?? undefined,
            filters.heatingMin ?? undefined,
            hasWifi ?? filters.hasWifi ?? undefined,
            filters.hasFreshAir ?? undefined,
            filters.brandSlugs ?? undefined,
            categorySlug,
        );
        return res.items;
    },

    async listSuppliers() {
        return await ManagerService.listSuppliers();
    },

    async createSupplier(payload: SupplierCreatePayload) {
        return await ManagerService.createSupplier(payload);
    },

    async patchSupplier(supplierId: number, payload: SupplierUpdatePayload) {
        return await ManagerService.patchSupplier(supplierId, payload);
    },

    async deleteSupplier(supplierId: number) {
        return await ManagerService.deleteSupplier(supplierId);
    },

    async listSupplierContacts(supplierId: number) {
        return await ManagerService.listSupplierContacts(supplierId);
    },

    async createSupplierContact(supplierId: number, payload: SupplierContactCreatePayload) {
        return await ManagerService.createSupplierContact(supplierId, payload);
    },

    async patchSupplierContact(supplierId: number, contactId: number, payload: SupplierContactUpdatePayload) {
        return await ManagerService.patchSupplierContact(supplierId, contactId, payload);
    },

    async deleteSupplierContact(supplierId: number, contactId: number) {
        return await ManagerService.deleteSupplierContact(supplierId, contactId);
    },

    async listSupplierWarehouses(supplierId: number) {
        return await ManagerService.listSupplierWarehouses(supplierId);
    },

    async createSupplierWarehouse(supplierId: number, payload: SupplierWarehouseCreatePayload) {
        return await ManagerService.createSupplierWarehouse(supplierId, payload);
    },

    async patchSupplierWarehouse(supplierId: number, warehouseId: number, payload: SupplierWarehouseUpdatePayload) {
        return await ManagerService.patchSupplierWarehouse(supplierId, warehouseId, payload);
    },

    async deleteSupplierWarehouse(supplierId: number, warehouseId: number) {
        return await ManagerService.deleteSupplierWarehouse(supplierId, warehouseId);
    },

    async listSupplierSources() {
        return await ManagerService.listSupplierSources();
    },

    async createSupplierSource(payload: SupplierPriceSourceCreatePayload) {
        return await ManagerService.createSupplierSource(payload);
    },

    async patchSupplierSource(sourceId: number, payload: SupplierPriceSourceUpdatePayload) {
        return await ManagerService.patchSupplierSource(sourceId, payload);
    },

    async deleteSupplierSource(sourceId: number) {
        return await ManagerService.deleteSupplierSource(sourceId);
    },

    async analyzeSupplierSource(sourceId: number, limit = 50) {
        return await ManagerService.analyzeSupplierSource(sourceId, limit);
    },

    async syncSupplierSource(sourceId: number) {
        return await ManagerService.syncSupplierSource(sourceId);
    },

    async syncAllSupplierSources() {
        return await ManagerService.syncAllSupplierSources();
    },

    async listUnmappedSupplierOffers(page = 1, limit = 50, supplierId?: number, sourceId?: number) {
        return await ManagerService.listUnmappedSupplierOffers(page, limit, supplierId ?? null, sourceId ?? null);
    },

    async listSupplierSourceUrlImportCandidates(limit = 100, supplierId?: number, sourceId?: number) {
        return await ManagerService.listSupplierSourceUrlImportCandidates(limit, supplierId ?? null, sourceId ?? null);
    },

    async startSupplierSourceUrlImport(payload: SupplierSourceUrlImportPayload) {
        return await ManagerService.startSupplierSourceUrlImport(payload);
    },

    async createSupplierMapping(payload: SupplierMappingCreatePayload) {
        return await ManagerService.createSupplierMapping(payload);
    },

    async createSupplierMappingsBulk(payload: SupplierMappingBulkCreatePayload) {
        return await ManagerService.bulkCreateSupplierMappings(payload);
    },

    async suggestSupplierOffers(payload: SupplierOfferSuggestionsPayload) {
        return await ManagerService.suggestSupplierOffers(payload);
    },

    async listSupplierSheets(supplierId: number) {
        return await ManagerService.listSupplierSheets(supplierId);
    },

    async deleteSupplierMapping(mappingId: number) {
        return await ManagerService.deleteSupplierMapping(mappingId);
    },

    async getProductSupplierOffers(productId: number) {
        return await ManagerService.getProductSupplierOffers(productId);
    },

    async upsertProductLocalStock(productId: number, payload: ProductLocalStockPayload) {
        return await ManagerService.upsertProductLocalStock(productId, payload);
    },

    async listSupplyRequests(params: {
        page?: number;
        limit?: number;
        status?: string | null;
        supplierId?: number | null;
        warehouseId?: number | null;
        sourceType?: string | null;
        orderId?: number | null;
    } = {}) {
        return await ManagerService.listSupplyRequests(
            params.page ?? 1,
            params.limit ?? 50,
            params.status ?? null,
            params.supplierId ?? null,
            params.warehouseId ?? null,
            params.sourceType ?? null,
            params.orderId ?? null,
        );
    },

    async createSupplyRequest(payload: SupplyRequestCreatePayload) {
        return await ManagerService.createSupplyRequest(payload);
    },

    async createSupplyRequestFromOrderLines(payload: SupplyRequestFromOrderLinesPayload) {
        return await ManagerService.createSupplyRequestFromOrderLines(payload);
    },

    async createStockSupplyRequest(payload: SupplyRequestStockCreatePayload) {
        return await ManagerService.createStockSupplyRequest(payload);
    },

    async patchSupplyRequest(requestId: number, payload: SupplyRequestUpdatePayload) {
        return await ManagerService.patchSupplyRequest(requestId, payload);
    },

    async patchSupplyRequestLine(lineId: number, payload: SupplyRequestLineUpdatePayload) {
        return await ManagerService.patchSupplyRequestLine(lineId, payload);
    },

    async generateSupplyRequestSupplierMessage(requestId: number, markSent = false) {
        return await ManagerService.generateSupplyRequestSupplierMessage(requestId, { mark_sent: markSent });
    },

    async generateSupplyLogisticsMessage(payload: SupplyLogisticsMessagePayload) {
        return await ManagerService.generateSupplyLogisticsMessage(payload);
    },

    async searchServices(q: string) {
        return await ApiService.adminSearchServicesApiAdminServicesSearchGet(q);
    },

    async getPublicSpecKeys() {
        return await ApiService.getPublicSpecKeys();
    },

    async getPublicSpecRegistry() {
        return await ApiService.getPublicSpecRegistry();
    },

    async bulkUpdateSpecs(productIds: number[], specs: Record<string, unknown>, operation: 'merge' | 'replace' | 'delete_keys' = 'merge') {
        return await ManagerService.bulkUpdateSpecs({
            product_ids: productIds,
            specs,
            operation,
        });
    },

    async rebuildWeb() {
        return await SystemService.triggerRebuildWebApiSystemRebuildWebPost();
    },

    async getWebRebuildStatus() {
        return await SystemService.getRebuildWebStatusApiSystemRebuildWebStatusGet();
    },

    async importProducts(urls: string[], withRelated: boolean, updateExisting: boolean): Promise<{
        success_count: number;
        error_count: number;
        successes: string[];
        errors: string[];
    }> {
        return await ManagerService.catalogImport({
            urls,
            with_related: withRelated,
            update_existing: updateExisting,
        });
    },

    async startImportProductsJob(
        urls: string[],
        withRelated: boolean,
        updateExisting: boolean,
    ): Promise<CatalogImportJobStartResponse> {
        return await ManagerService.startCatalogImportJob({
            urls,
            with_related: withRelated,
            update_existing: updateExisting,
        });
    },

    async previewMdvCatalogImport(payload: MdvCatalogPreviewPayload): Promise<MdvCatalogPreviewResponse> {
        return await ManagerService.previewMdvCatalogImport(payload);
    },

    async startMdvCatalogImportJob(payload: MdvCatalogImportPayload): Promise<CatalogImportJobStartResponse> {
        return await ManagerService.startMdvCatalogImportJob(payload);
    },

    async getImportProductsJobStatus(jobId: string): Promise<CatalogImportJobStatusResponse> {
        return await ManagerService.getCatalogImportJobStatus(jobId);
    },

    async getCurrentImportProductsJobStatus(): Promise<CatalogImportJobStatusResponse> {
        return await ManagerService.getCurrentCatalogImportJobStatus();
    },

    /** @deprecated Use importProducts() — kept for backward compatibility */
    async importFromOnliner(urls: string[], withRelated: boolean, updateExisting: boolean) {
        return await this.importProducts(urls, withRelated, updateExisting);
    },

    async getManagerTagGroups() {
        return await ManagerTagsService.getManagerTagGroups();
    },

    async createManagerTagGroup(payload: any) {
        return await ManagerTagsService.createManagerTagGroup(payload);
    },

    async updateManagerTagGroup(groupId: number, payload: any) {
        return await ManagerTagsService.updateManagerTagGroup(groupId, payload);
    },

    async deleteManagerTagGroup(groupId: number) {
        return await ManagerTagsService.deleteManagerTagGroup(groupId);
    },

    async createManagerTag(payload: any) {
        return await ManagerTagsService.createManagerTag(payload);
    },

    async updateManagerTag(tagId: number, payload: any) {
        return await ManagerTagsService.updateManagerTag(tagId, payload);
    },

    async deleteManagerTag(tagId: number) {
        return await ManagerTagsService.deleteManagerTag(tagId);
    },

    async listManagerBrands(): Promise<{ items: ManagerBrand[] }> {
        const response = await ManagerBrandsService.listManagerBrands();
        return {
            ...response,
            items: (response.items || []).map((brand) => ({
                ...brand,
                products_count: brand.products_count ?? 0,
            })),
        };
    },

    async createManagerBrand(payload: ManagerBrandCreatePayload): Promise<ManagerBrand> {
        const brand = await ManagerBrandsService.createManagerBrand(payload);
        return { ...brand, products_count: brand.products_count ?? 0 };
    },

    async updateManagerBrand(brandId: number, payload: ManagerBrandUpdatePayload): Promise<ManagerBrand> {
        const brand = await ManagerBrandsService.updateManagerBrand(brandId, payload);
        return { ...brand, products_count: brand.products_count ?? 0 };
    },

    async deleteManagerBrand(brandId: number): Promise<{ message: string }> {
        return await ManagerBrandsService.deleteManagerBrand(brandId);
    },

    async listManagerBrandFeatures(brandId: number): Promise<{ items: ManagerBrandFeature[] }> {
        const response = await ManagerBrandsService.listManagerBrandFeatures(brandId);
        return {
            ...response,
            items: (response.items || []).map((feature) => ({
                ...feature,
                aliases: feature.aliases || [],
                series_count: feature.series_count ?? 0,
            })),
        };
    },

    async createManagerBrandFeature(
        brandId: number,
        payload: ManagerBrandFeatureCreatePayload,
    ): Promise<ManagerBrandFeature> {
        const feature = await ManagerBrandsService.createManagerBrandFeature(brandId, payload);
        return {
            ...feature,
            aliases: feature.aliases || [],
            series_count: feature.series_count ?? 0,
        };
    },

    async updateManagerBrandFeature(
        brandId: number,
        featureId: number,
        payload: ManagerBrandFeatureUpdatePayload,
    ): Promise<ManagerBrandFeature> {
        const feature = await ManagerBrandsService.updateManagerBrandFeature(brandId, featureId, payload);
        return {
            ...feature,
            aliases: feature.aliases || [],
            series_count: feature.series_count ?? 0,
        };
    },

    async deleteManagerBrandFeature(brandId: number, featureId: number): Promise<{ message: string }> {
        return await ManagerBrandsService.deleteManagerBrandFeature(brandId, featureId);
    },

    async listManagerBrandSeries(brandId: number): Promise<{ items: ManagerBrandSeries[] }> {
        const response = await ManagerBrandsService.listManagerBrandSeries(brandId);
        return {
            ...response,
            items: (response.items || []).map((series) => ({
                ...series,
                brand_features: series.brand_features || [],
                brand_feature_ids: series.brand_feature_ids || [],
                features: series.features || [],
                products_count: series.products_count ?? 0,
            })),
        };
    },

    async createManagerBrandSeries(
        brandId: number,
        payload: ManagerBrandSeriesCreatePayload,
    ): Promise<ManagerBrandSeries> {
        const series = await ManagerBrandsService.createManagerBrandSeries(brandId, payload);
        return {
            ...series,
            brand_features: series.brand_features || [],
            brand_feature_ids: series.brand_feature_ids || [],
            features: series.features || [],
            products_count: series.products_count ?? 0,
        };
    },

    async updateManagerBrandSeries(
        brandId: number,
        seriesId: number,
        payload: ManagerBrandSeriesUpdatePayload,
    ): Promise<ManagerBrandSeries> {
        const series = await ManagerBrandsService.updateManagerBrandSeries(brandId, seriesId, payload);
        return {
            ...series,
            brand_features: series.brand_features || [],
            brand_feature_ids: series.brand_feature_ids || [],
            features: series.features || [],
            products_count: series.products_count ?? 0,
        };
    },

    async applyManagerSeriesGalleryToProducts(
        brandId: number,
        seriesId: number,
        sourceUrls: string[],
    ) {
        return await ManagerBrandsService.applyManagerSeriesGalleryToProducts(brandId, seriesId, {
            source_urls: sourceUrls,
        });
    },

    async deleteManagerBrandSeries(brandId: number, seriesId: number): Promise<{ message: string }> {
        return await ManagerBrandsService.deleteManagerBrandSeries(brandId, seriesId);
    },
    // Leads Inbox (Order-based triage)
    async getLeadsCounter() {
        return await ManagerLeadsInboxService.getManagerLeadsCounter();
    },

    async getLeadsInbox(scope: 'active' | 'archive' = 'active', page = 1, limit = 50) {
        return await ManagerLeadsInboxService.getManagerLeadsInbox(scope, page, limit);
    },
};
