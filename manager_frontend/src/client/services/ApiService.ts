/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { AddressSuggestResponse } from '../models/AddressSuggestResponse';
import type { ArticleResponse } from '../models/ArticleResponse';
import type { Body_create_installation_estimate_lead } from '../models/Body_create_installation_estimate_lead';
import type { Body_create_repair_diagnostic_lead } from '../models/Body_create_repair_diagnostic_lead';
import type { CatalogResponse } from '../models/CatalogResponse';
import type { CatalogRevisionResponse } from '../models/CatalogRevisionResponse';
import type { FiltersConfigResponse } from '../models/FiltersConfigResponse';
import type { InstallationEstimateLeadResponse } from '../models/InstallationEstimateLeadResponse';
import type { InstallationPreviewPayload } from '../models/InstallationPreviewPayload';
import type { InstallationPreviewResponse } from '../models/InstallationPreviewResponse';
import type { InstallationPricingConfigResponse } from '../models/InstallationPricingConfigResponse';
import type { InstallationResolvePayload } from '../models/InstallationResolvePayload';
import type { InstallationResolveResponse } from '../models/InstallationResolveResponse';
import type { ManagerInstallEstimateResponse } from '../models/ManagerInstallEstimateResponse';
import type { ManagerTariffServiceKind } from '../models/ManagerTariffServiceKind';
import type { MultiSplitLeadPayload } from '../models/MultiSplitLeadPayload';
import type { MultiSplitLeadResponse } from '../models/MultiSplitLeadResponse';
import type { MultiSplitOptionsResponse } from '../models/MultiSplitOptionsResponse';
import type { MultiSplitPreviewRequest } from '../models/MultiSplitPreviewRequest';
import type { MultiSplitPreviewResponse } from '../models/MultiSplitPreviewResponse';
import type { NativeOpportunity } from '../models/NativeOpportunity';
import type { OrderPayload } from '../models/OrderPayload';
import type { OrderResponse } from '../models/OrderResponse';
import type { ProductAvailabilityLeadPayload } from '../models/ProductAvailabilityLeadPayload';
import type { ProductAvailabilityLeadResponse } from '../models/ProductAvailabilityLeadResponse';
import type { ProductResponse } from '../models/ProductResponse';
import type { ProductSeriesNavigationResponse } from '../models/ProductSeriesNavigationResponse';
import type { PublicBrandDetailResponse } from '../models/PublicBrandDetailResponse';
import type { PublicBrandResponse } from '../models/PublicBrandResponse';
import type { PublicContactLeadPayload } from '../models/PublicContactLeadPayload';
import type { PublicContactLeadResponse } from '../models/PublicContactLeadResponse';
import type { PublicProductCollectionPlacementResponse } from '../models/PublicProductCollectionPlacementResponse';
import type { PublicProductSearchResponse } from '../models/PublicProductSearchResponse';
import type { PublicSeriesPageResponse } from '../models/PublicSeriesPageResponse';
import type { PublicServiceEstimateCalculatePayload } from '../models/PublicServiceEstimateCalculatePayload';
import type { PublicServiceTariffListResponse } from '../models/PublicServiceTariffListResponse';
import type { PublicStorefrontContextResponse } from '../models/PublicStorefrontContextResponse';
import type { RepairDiagnosticLeadResponse } from '../models/RepairDiagnosticLeadResponse';
import type { ServiceResponse } from '../models/ServiceResponse';
import type { SpecRegistryResponse } from '../models/SpecRegistryResponse';
import type { SpecsKeysResponse } from '../models/SpecsKeysResponse';
import type { StorefrontSettingsResponse } from '../models/StorefrontSettingsResponse';
import type { TenderLeadPushResult } from '../models/TenderLeadPushResult';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class ApiService {
    /**
     * Search Products
     * Search storefront-visible products using fuzzy matching and optional inverter filtering.
     * Uses public tenant resolution; does not expose the unrestricted Manager catalog.
     *
     * Access and scope: storefront context is resolved by the public gateway; tenant-aware
     * operations use that storefront. Signed headers are verified outside OpenAPI. See
     * [storefront
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/storefront-context-contract.md#resolution-and-compatibility).
     * @param q
     * @param isInverter
     * @returns PublicProductSearchResponse Successful Response
     * @throws ApiError
     */
    public static searchProductsApiProductsSearchGet(
        q?: string,
        isInverter?: boolean,
    ): CancelablePromise<PublicProductSearchResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/products/search',
            query: {
                'q': q,
                'is_inverter': isInverter,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Filterable Tags
     * Read the shared filterable tag dictionary for authenticated Manager workflows. Requires
     * get_current_username; this legacy /api/admin path is not a supplier integration surface.
     * @returns any Successful Response
     * @throws ApiError
     */
    public static getFilterableTagsApiAdminTagsFilterableGet(): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/admin/tags/filterable',
        });
    }
    /**
     * Admin Search Products
     * Search shared products by query and optional tag IDs for authenticated Manager
     * workflows. Requires get_current_username; this legacy helper does not use the storefront
     * catalog projection.
     * @param q
     * @param tagIds
     * @returns any Successful Response
     * @throws ApiError
     */
    public static adminSearchProductsApiAdminProductsSearchGet(
        q: string = '',
        tagIds?: Array<number>,
    ): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/admin/products/search',
            query: {
                'q': q,
                'tag_ids': tagIds,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Admin Search Services
     * Search shared services by query for authenticated Manager workflows. Requires
     * get_current_username; this helper is not a public service tariff calculation.
     * @param q
     * @returns any Successful Response
     * @throws ApiError
     */
    public static adminSearchServicesApiAdminServicesSearchGet(
        q: string = '',
    ): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/admin/services/search',
            query: {
                'q': q,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Health Check
     * Check API and database availability without business-data access. No Manager or bot
     * token is required. Use /api/ready as the separate traffic-readiness check.
     * @returns any Successful Response
     * @throws ApiError
     */
    public static healthCheckApiHealthGet(): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/health',
        });
    }
    /**
     * Readiness Check
     * Check whether this API node can receive public traffic, including database and scheduler
     * runtime readiness. Returns the readiness service status and body (including non-success
     * status when unready); no Manager or bot token is required.
     * @returns any Successful Response
     * @throws ApiError
     */
    public static readinessCheckApiReadyGet(): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/ready',
        });
    }
    /**
     * Get Catalog Revision
     * Read the contextual catalog and storefront revisions used in cache keys. Returns
     * X-Catalog-Revision, X-Storefront-Catalog-Revision and a weak ETag, with private
     * revalidation headers and Vary: X-MVN-Storefront-Host. This handler returns the revision
     * body; it does not implement conditional 304 responses.
     *
     * Access and scope: storefront context is resolved by the public gateway; tenant-aware
     * operations use that storefront. Signed headers are verified outside OpenAPI. See
     * [storefront
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/storefront-context-contract.md#resolution-and-compatibility).
     * @returns CatalogRevisionResponse Successful Response
     * @throws ApiError
     */
    public static getCatalogRevision(): CancelablePromise<CatalogRevisionResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/catalog/revision',
        });
    }
    /**
     * Get Articles
     * List published articles, newest first. Articles are shared content: this handler does
     * not apply tenant filtering to the article service.
     *
     * Access and scope: storefront context is resolved by the public gateway; tenant-aware
     * operations use that storefront. Signed headers are verified outside OpenAPI. See
     * [storefront
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/storefront-context-contract.md#resolution-and-compatibility).
     * @returns ArticleResponse Successful Response
     * @throws ApiError
     */
    public static getArticlesApiV1ContentArticlesGet(): CancelablePromise<Array<ArticleResponse>> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/content/articles',
        });
    }
    /**
     * Get Article
     * Read one published shared article by slug. Missing or unpublished content returns 404;
     * the article query is not tenant-scoped.
     *
     * Access and scope: storefront context is resolved by the public gateway; tenant-aware
     * operations use that storefront. Signed headers are verified outside OpenAPI. See
     * [storefront
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/storefront-context-contract.md#resolution-and-compatibility).
     * @param slug
     * @returns ArticleResponse Successful Response
     * @throws ApiError
     */
    public static getArticleApiV1ContentArticlesSlugGet(
        slug: string,
    ): CancelablePromise<ArticleResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/content/articles/{slug}',
            path: {
                'slug': slug,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Services
     * Return storefront-visible service content through the installation pricing bridge, with
     * private/no-store response headers.
     *
     * Access and scope: storefront context is resolved by the public gateway; tenant-aware
     * operations use that storefront. Signed headers are verified outside OpenAPI. See
     * [storefront
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/storefront-context-contract.md#resolution-and-compatibility).
     * @returns ServiceResponse Successful Response
     * @throws ApiError
     */
    public static getServicesApiV1ContentServicesGet(): CancelablePromise<Array<ServiceResponse>> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/content/services',
        });
    }
    /**
     * Get Public Brands
     * List published brands with products visible in the resolved storefront catalog.
     *
     * Access and scope: storefront context is resolved by the public gateway; tenant-aware
     * operations use that storefront. Signed headers are verified outside OpenAPI. See
     * [storefront
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/storefront-context-contract.md#resolution-and-compatibility).
     * @returns PublicBrandResponse Successful Response
     * @throws ApiError
     */
    public static getPublicBrands(): CancelablePromise<Array<PublicBrandResponse>> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/content/brands',
        });
    }
    /**
     * Get Public Brand
     * Read a published brand by slug when it has products visible in this storefront. Missing
     * or unavailable brands return 404.
     *
     * Access and scope: storefront context is resolved by the public gateway; tenant-aware
     * operations use that storefront. Signed headers are verified outside OpenAPI. See
     * [storefront
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/storefront-context-contract.md#resolution-and-compatibility).
     * @param slug
     * @returns PublicBrandDetailResponse Successful Response
     * @throws ApiError
     */
    public static getPublicBrand(
        slug: string,
    ): CancelablePromise<PublicBrandDetailResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/content/brands/{slug}',
            path: {
                'slug': slug,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Public Brand Series
     * Read a published brand series and its storefront-visible product cards. Missing or
     * unavailable series return 404.
     *
     * Access and scope: storefront context is resolved by the public gateway; tenant-aware
     * operations use that storefront. Signed headers are verified outside OpenAPI. See
     * [storefront
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/storefront-context-contract.md#resolution-and-compatibility).
     * @param brandSlug
     * @param seriesSlug
     * @returns PublicSeriesPageResponse Successful Response
     * @throws ApiError
     */
    public static getPublicBrandSeries(
        brandSlug: string,
        seriesSlug: string,
    ): CancelablePromise<PublicSeriesPageResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/content/brands/{brand_slug}/series/{series_slug}',
            path: {
                'brand_slug': brandSlug,
                'series_slug': seriesSlug,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Service Options
     * Read legacy service options for the requested category in this storefront. Returns 409
     * book_preview_required when the published price-book contract replaces that category; use
     * the installation preview contract instead.
     *
     * Access and scope: storefront context is resolved by the public gateway; tenant-aware
     * operations use that storefront. Signed headers are verified outside OpenAPI. See
     * [storefront
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/storefront-context-contract.md#resolution-and-compatibility).
     * @param category
     * @returns ServiceResponse Successful Response
     * @throws ApiError
     */
    public static getServiceOptionsApiV1ServicesOptionsGet(
        category: string = 'installation_option',
    ): CancelablePromise<Array<ServiceResponse>> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/services/options',
            query: {
                'category': category,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Installation Rates
     * Read legacy installation rates for this storefront. Disabled installation returns an
     * empty list; an authoritative published price book returns 409 book_preview_required.
     *
     * Access and scope: storefront context is resolved by the public gateway; tenant-aware
     * operations use that storefront. Signed headers are verified outside OpenAPI. See
     * [storefront
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/storefront-context-contract.md#resolution-and-compatibility).
     * @returns any Successful Response
     * @throws ApiError
     */
    public static getInstallationRatesApiV1InstallationRatesGet(): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/installation-rates',
        });
    }
    /**
     * Get Global Config
     * Return the public key/value configuration for the resolved storefront, not private
     * platform settings.
     *
     * Access and scope: storefront context is resolved by the public gateway; tenant-aware
     * operations use that storefront. Signed headers are verified outside OpenAPI. See
     * [storefront
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/storefront-context-contract.md#resolution-and-compatibility).
     * @returns any Successful Response
     * @throws ApiError
     */
    public static getConfig(): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/config',
        });
    }
    /**
     * Create Public Contact Lead
     * Create a website contact lead in the resolved storefront. For required keys, unsigned
     * compatibility, conflicting payloads (409) and retries after 503 with Retry-After, see
     * [public write
     * idempotency](https://github.com/mvnby/air-api/blob/main/docs/storefront-context-contract.md#public-write-idempotency).
     * Retain the same key and content when retrying.
     *
     * Access and scope: storefront context is resolved by the public gateway; tenant-aware
     * operations use that storefront. Signed headers are verified outside OpenAPI. See
     * [storefront
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/storefront-context-contract.md#resolution-and-compatibility).
     * @param requestBody
     * @param idempotencyKey
     * @returns PublicContactLeadResponse Successful Response
     * @throws ApiError
     */
    public static createPublicContactLead(
        requestBody: PublicContactLeadPayload,
        idempotencyKey?: (string | null),
    ): CancelablePromise<PublicContactLeadResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/leads/contact',
            headers: {
                'Idempotency-Key': idempotencyKey,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                400: `Invalid Content-Length or idempotency key`,
                401: `Invalid or unsupported storefront signature envelope`,
                409: `Idempotency key reused with different content`,
                413: `Storefront request body exceeds the configured limit`,
                422: `Validation Error`,
                503: `Request can be retried after a short delay`,
            },
        });
    }
    /**
     * Create Installation Estimate Lead
     * Create an installation estimate lead with categorized image uploads. Idempotency-Key is
     * required; upload/content validation can return 400 and model validation 422. For
     * required keys, unsigned compatibility, conflicting payloads (409) and retries after 503
     * with Retry-After, see [public write
     * idempotency](https://github.com/mvnby/air-api/blob/main/docs/storefront-context-contract.md#public-write-idempotency).
     * Retain the same key and content when retrying.
     *
     * Access and scope: storefront context is resolved by the public gateway; tenant-aware
     * operations use that storefront. Signed headers are verified outside OpenAPI. See
     * [storefront
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/storefront-context-contract.md#resolution-and-compatibility).
     * @param idempotencyKey
     * @param formData
     * @returns InstallationEstimateLeadResponse Successful Response
     * @throws ApiError
     */
    public static createInstallationEstimateLead(
        idempotencyKey: string,
        formData: Body_create_installation_estimate_lead,
    ): CancelablePromise<InstallationEstimateLeadResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/leads/installation-estimate',
            headers: {
                'Idempotency-Key': idempotencyKey,
            },
            formData: formData,
            mediaType: 'multipart/form-data',
            errors: {
                400: `Invalid Content-Length, image, idempotency key, or upload limits`,
                401: `Invalid or unsupported storefront signature envelope`,
                409: `Idempotency key reused with different content`,
                413: `Storefront request body exceeds the configured limit`,
                422: `Validation Error`,
                503: `Request can be retried after a short delay`,
            },
        });
    }
    /**
     * Create Product Availability Lead
     * Create a storefront product availability inquiry. A product unavailable to that
     * storefront returns 404. For required keys, unsigned compatibility, conflicting payloads
     * (409) and retries after 503 with Retry-After, see [public write
     * idempotency](https://github.com/mvnby/air-api/blob/main/docs/storefront-context-contract.md#public-write-idempotency).
     * Retain the same key and content when retrying.
     *
     * Access and scope: storefront context is resolved by the public gateway; tenant-aware
     * operations use that storefront. Signed headers are verified outside OpenAPI. See
     * [storefront
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/storefront-context-contract.md#resolution-and-compatibility).
     * @param requestBody
     * @param idempotencyKey
     * @returns ProductAvailabilityLeadResponse Successful Response
     * @throws ApiError
     */
    public static createProductAvailabilityLead(
        requestBody: ProductAvailabilityLeadPayload,
        idempotencyKey?: (string | null),
    ): CancelablePromise<ProductAvailabilityLeadResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/leads/product-availability',
            headers: {
                'Idempotency-Key': idempotencyKey,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                400: `Invalid Content-Length or idempotency key`,
                401: `Invalid or unsupported storefront signature envelope`,
                409: `Idempotency key reused with different content`,
                413: `Storefront request body exceeds the configured limit`,
                422: `Validation Error`,
                503: `Request can be retried after a short delay`,
            },
        });
    }
    /**
     * Create Repair Diagnostic Lead
     * Create a repair diagnostic lead from multipart JSON payload and categorized uploads.
     * Malformed payload/images/limits return 400 or 422 according to validation stage. For
     * required keys, unsigned compatibility, conflicting payloads (409) and retries after 503
     * with Retry-After, see [public write
     * idempotency](https://github.com/mvnby/air-api/blob/main/docs/storefront-context-contract.md#public-write-idempotency).
     * Retain the same key and content when retrying.
     *
     * Access and scope: storefront context is resolved by the public gateway; tenant-aware
     * operations use that storefront. Signed headers are verified outside OpenAPI. See
     * [storefront
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/storefront-context-contract.md#resolution-and-compatibility).
     * @param formData
     * @param idempotencyKey
     * @returns RepairDiagnosticLeadResponse Successful Response
     * @throws ApiError
     */
    public static createRepairDiagnosticLead(
        formData: Body_create_repair_diagnostic_lead,
        idempotencyKey?: (string | null),
    ): CancelablePromise<RepairDiagnosticLeadResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/leads/repair-diagnostic',
            headers: {
                'Idempotency-Key': idempotencyKey,
            },
            formData: formData,
            mediaType: 'multipart/form-data',
            errors: {
                400: `Invalid Content-Length, form data, idempotency key, or upload limits`,
                401: `Invalid or unsupported storefront signature envelope`,
                409: `Idempotency key reused with different content`,
                413: `Storefront request body exceeds the configured limit`,
                422: `Validation Error`,
                503: `Request can be retried after a short delay`,
            },
        });
    }
    /**
     * Create Order
     * Create an order from the resolved storefront cart and customer details. The server
     * verifies pricing and installation acceptance; pricing conflicts return 409. Installation
     * acceptance requires exactly one submitted Idempotency-Key even for unsigned
     * compatibility clients. For required keys, unsigned compatibility, conflicting payloads
     * (409) and retries after 503 with Retry-After, see [public write
     * idempotency](https://github.com/mvnby/air-api/blob/main/docs/storefront-context-contract.md#public-write-idempotency).
     * Retain the same key and content when retrying.
     *
     * Access and scope: storefront context is resolved by the public gateway; tenant-aware
     * operations use that storefront. Signed headers are verified outside OpenAPI. See
     * [storefront
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/storefront-context-contract.md#resolution-and-compatibility).
     * @param requestBody
     * @param idempotencyKey
     * @returns OrderResponse Successful Response
     * @throws ApiError
     */
    public static createOrder(
        requestBody: OrderPayload,
        idempotencyKey?: (string | null),
    ): CancelablePromise<OrderResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/orders',
            headers: {
                'Idempotency-Key': idempotencyKey,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                400: `Invalid Content-Length or idempotency key`,
                401: `Invalid or unsupported storefront signature envelope`,
                409: `Installation pricing conflict or Idempotency-Key reused with different content.`,
                413: `Storefront request body exceeds the configured limit`,
                422: `Validation Error`,
                503: `Request can be retried after a short delay`,
            },
        });
    }
    /**
     * Get Public Spec Keys
     * List specification keys available in the resolved storefront catalog, for building
     * supported filters.
     *
     * Access and scope: storefront context is resolved by the public gateway; tenant-aware
     * operations use that storefront. Signed headers are verified outside OpenAPI. See
     * [storefront
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/storefront-context-contract.md#resolution-and-compatibility).
     * @returns SpecsKeysResponse Successful Response
     * @throws ApiError
     */
    public static getPublicSpecKeys(): CancelablePromise<SpecsKeysResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/specs/keys',
        });
    }
    /**
     * Get Public Spec Registry
     * Return the shared canonical specification registry and aliases; this dictionary is
     * global rather than a tenant product listing.
     *
     * Access and scope: storefront context is resolved by the public gateway; tenant-aware
     * operations use that storefront. Signed headers are verified outside OpenAPI. See
     * [storefront
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/storefront-context-contract.md#resolution-and-compatibility).
     * @returns SpecRegistryResponse Successful Response
     * @throws ApiError
     */
    public static getPublicSpecRegistry(): CancelablePromise<SpecRegistryResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/specs/registry',
        });
    }
    /**
     * Get Filters Config
     * Return filter choices derived from the resolved storefront catalog; use these choices
     * when constructing product queries.
     *
     * Access and scope: storefront context is resolved by the public gateway; tenant-aware
     * operations use that storefront. Signed headers are verified outside OpenAPI. See
     * [storefront
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/storefront-context-contract.md#resolution-and-compatibility).
     * @returns FiltersConfigResponse Successful Response
     * @throws ApiError
     */
    public static getFiltersConfig(): CancelablePromise<FiltersConfigResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/filters/config',
        });
    }
    /**
     * Generate Product Description
     * Generate product description text from shared product tags/specifications without saving
     * it. A missing product is returned as description error text with HTTP success, not 404.
     * Requires Manager authentication via get_current_username; operates on the shared product
     * catalog, outside the public storefront read contract.
     * @param productId
     * @returns any Successful Response
     * @throws ApiError
     */
    public static generateProductDescriptionApiProductsProductIdGenerateDescriptionPost(
        productId: number,
    ): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/products/{product_id}/generate-description',
            path: {
                'product_id': productId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Catalog
     * Return a filtered, sorted storefront product page, with public prices, supply metrics,
     * features and warranty projection. /v1/catalog is an alias of /v1/products with a
     * distinct operation ID. page starts at 1 and limit is 1–100; the service rejects
     * out-of-range values with 400. Response meta describes the filtered result set.
     *
     * Access and scope: storefront context is resolved by the public gateway; tenant-aware
     * operations use that storefront. Signed headers are verified outside OpenAPI. See
     * [storefront
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/storefront-context-contract.md#resolution-and-compatibility).
     * @param page
     * @param limit
     * @param sort
     * @param minPrice
     * @param maxPrice
     * @param areaMin
     * @param areaMax
     * @param heatingMin
     * @param hasWifi
     * @param hasFreshAir
     * @param color Canonical indoor unit color family
     * @param indoorTypes Canonical indoor unit types (duct/cassette/floor_ceiling/column/console)
     * @param tagSlugs
     * @param brandSlugs Canonical brand slugs to include
     * @param isInverter
     * @param q Smart search query
     * @returns CatalogResponse Successful Response
     * @throws ApiError
     */
    public static getProductsV1(
        page: number = 1,
        limit: number = 20,
        sort: string = 'recommended',
        minPrice?: (number | null),
        maxPrice?: (number | null),
        areaMin?: (number | null),
        areaMax?: (number | null),
        heatingMin?: (number | null),
        hasWifi?: (boolean | null),
        hasFreshAir?: (boolean | null),
        color?: (string | null),
        indoorTypes?: (Array<string> | null),
        tagSlugs?: (Array<string> | null),
        brandSlugs?: (Array<string> | null),
        isInverter?: (boolean | null),
        q?: (string | null),
    ): CancelablePromise<CatalogResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/products',
            query: {
                'page': page,
                'limit': limit,
                'sort': sort,
                'min_price': minPrice,
                'max_price': maxPrice,
                'area_min': areaMin,
                'area_max': areaMax,
                'heating_min': heatingMin,
                'has_wifi': hasWifi,
                'has_fresh_air': hasFreshAir,
                'color': color,
                'indoor_types': indoorTypes,
                'tag_slugs': tagSlugs,
                'brand_slugs': brandSlugs,
                'is_inverter': isInverter,
                'q': q,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Catalog
     * Return a filtered, sorted storefront product page, with public prices, supply metrics,
     * features and warranty projection. /v1/catalog is an alias of /v1/products with a
     * distinct operation ID. page starts at 1 and limit is 1–100; the service rejects
     * out-of-range values with 400. Response meta describes the filtered result set.
     *
     * Access and scope: storefront context is resolved by the public gateway; tenant-aware
     * operations use that storefront. Signed headers are verified outside OpenAPI. See
     * [storefront
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/storefront-context-contract.md#resolution-and-compatibility).
     * @param page
     * @param limit
     * @param sort
     * @param minPrice
     * @param maxPrice
     * @param areaMin
     * @param areaMax
     * @param heatingMin
     * @param hasWifi
     * @param hasFreshAir
     * @param color Canonical indoor unit color family
     * @param indoorTypes Canonical indoor unit types (duct/cassette/floor_ceiling/column/console)
     * @param tagSlugs
     * @param brandSlugs Canonical brand slugs to include
     * @param isInverter
     * @param q Smart search query
     * @returns CatalogResponse Successful Response
     * @throws ApiError
     */
    public static getProducts(
        page: number = 1,
        limit: number = 20,
        sort: string = 'recommended',
        minPrice?: (number | null),
        maxPrice?: (number | null),
        areaMin?: (number | null),
        areaMax?: (number | null),
        heatingMin?: (number | null),
        hasWifi?: (boolean | null),
        hasFreshAir?: (boolean | null),
        color?: (string | null),
        indoorTypes?: (Array<string> | null),
        tagSlugs?: (Array<string> | null),
        brandSlugs?: (Array<string> | null),
        isInverter?: (boolean | null),
        q?: (string | null),
    ): CancelablePromise<CatalogResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/catalog',
            query: {
                'page': page,
                'limit': limit,
                'sort': sort,
                'min_price': minPrice,
                'max_price': maxPrice,
                'area_min': areaMin,
                'area_max': areaMax,
                'heating_min': heatingMin,
                'has_wifi': hasWifi,
                'has_fresh_air': hasFreshAir,
                'color': color,
                'indoor_types': indoorTypes,
                'tag_slugs': tagSlugs,
                'brand_slugs': brandSlugs,
                'is_inverter': isInverter,
                'q': q,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Vitebsk Featured Products
     * Return up to six featured storefront product projections with public supply, feature and
     * warranty information.
     *
     * Access and scope: storefront context is resolved by the public gateway; tenant-aware
     * operations use that storefront. Signed headers are verified outside OpenAPI. See
     * [storefront
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/storefront-context-contract.md#resolution-and-compatibility).
     * @returns ProductResponse Successful Response
     * @throws ApiError
     */
    public static getVitebskFeaturedProducts(): CancelablePromise<Array<ProductResponse>> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/products/vitebsk-featured',
        });
    }
    /**
     * Get Product Series Navigation
     * Return the series navigation visible in the resolved storefront catalog.
     *
     * Access and scope: storefront context is resolved by the public gateway; tenant-aware
     * operations use that storefront. Signed headers are verified outside OpenAPI. See
     * [storefront
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/storefront-context-contract.md#resolution-and-compatibility).
     * @returns ProductSeriesNavigationResponse Successful Response
     * @throws ApiError
     */
    public static getProductSeriesNavigation(): CancelablePromise<ProductSeriesNavigationResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/product-series/navigation',
        });
    }
    /**
     * Get Product By Identifier
     * Resolve one storefront-visible product by identifier and include its visible series
     * siblings. A missing or unavailable product returns 404; this does not expose a product
     * from another storefront.
     *
     * Access and scope: storefront context is resolved by the public gateway; tenant-aware
     * operations use that storefront. Signed headers are verified outside OpenAPI. See
     * [storefront
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/storefront-context-contract.md#resolution-and-compatibility).
     * @param identifier
     * @returns ProductResponse Successful Response
     * @throws ApiError
     */
    public static getProduct(
        identifier: string,
    ): CancelablePromise<ProductResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/products/{identifier}',
            path: {
                'identifier': identifier,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Proxy Egr
     * Look up Belarus registry requisites by a nine-digit UNP. Requires Manager
     * authentication; invalid UNP returns 422. Data comes from the shared external registry,
     * not tenant CRM records.
     * @param unp
     * @returns any Successful Response
     * @throws ApiError
     */
    public static proxyEgrApiAdminProxyEgrGet(
        unp: string,
    ): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/admin/proxy/egr',
            query: {
                'unp': unp,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Find Bank
     * Read the shared NBRB bank reference, optionally matching BIC or Belarus IBAN. Requires
     * Manager authentication. Without search returns the bank list; a miss is an error object
     * with HTTP 200. Reference data uses a 72-hour in-process cache and can fall back to
     * cached data on fetch exceptions.
     * @param search BIC код или IBAN
     * @returns any Successful Response
     * @throws ApiError
     */
    public static findBankApiAdminProxyBankGet(
        search?: string,
    ): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/admin/proxy/bank',
            query: {
                'search': search,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Public Proxy Egr
     * Public Belarus registry lookup by a nine-digit UNP (422 for invalid format). No Manager
     * token or storefront signature is required: this is an explicit gateway exception. Reads
     * shared external registry data, not tenant records.
     * @param unp
     * @returns any Successful Response
     * @throws ApiError
     */
    public static publicProxyEgrApiV1ProxyEgrGet(
        unp: string,
    ): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/proxy/egr',
            query: {
                'unp': unp,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Public Find Bank
     * Public bank lookup by BIC or Belarus IBAN. No Manager token or storefront signature is
     * required: this is an explicit gateway exception. Empty search returns []; a miss returns
     * an error object with HTTP 200. Uses the shared cached NBRB reference.
     * @param search BIC код или IBAN
     * @returns any Successful Response
     * @throws ApiError
     */
    public static publicFindBankApiV1ProxyBankGet(
        search?: string,
    ): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/proxy/bank',
            query: {
                'search': search,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Public Address Suggest
     * Public address suggestions for a query of at least two characters. No Manager token or
     * storefront signature is required: this is an explicit gateway exception. Returns an
     * empty items list when suggestions are disabled or the upstream HTTP request fails.
     * @param q
     * @returns AddressSuggestResponse Successful Response
     * @throws ApiError
     */
    public static publicAddressSuggest(
        q: string,
    ): CancelablePromise<AddressSuggestResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/address-suggest',
            query: {
                'q': q,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Public Product Collection Placement
     * Resolve published product collections for a storefront surface and slot. Keys are
     * lowercased before resolution; the result contains the placement projection rather than
     * editable collection definitions.
     *
     * Access and scope: storefront context is resolved by the public gateway; tenant-aware
     * operations use that storefront. Signed headers are verified outside OpenAPI. See
     * [storefront
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/storefront-context-contract.md#resolution-and-compatibility).
     * @param surfaceKey
     * @param slotKey
     * @returns PublicProductCollectionPlacementResponse Successful Response
     * @throws ApiError
     */
    public static getPublicProductCollectionPlacement(
        surfaceKey: string,
        slotKey: string,
    ): CancelablePromise<PublicProductCollectionPlacementResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/content/placements/{surface_key}/{slot_key}/collections',
            path: {
                'surface_key': surfaceKey,
                'slot_key': slotKey,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Public Storefront Context
     * Resolve public tenant/storefront identity, locale, currency and hostname from the
     * current storefront scope. Returns 404 when that storefront is unavailable; the caller
     * cannot select an arbitrary tenant in the body.
     *
     * Access and scope: storefront context is resolved by the public gateway; tenant-aware
     * operations use that storefront. Signed headers are verified outside OpenAPI. See
     * [storefront
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/storefront-context-contract.md#resolution-and-compatibility).
     * @returns PublicStorefrontContextResponse Successful Response
     * @throws ApiError
     */
    public static getPublicStorefrontContext(): CancelablePromise<PublicStorefrontContextResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/storefront/context',
        });
    }
    /**
     * Get Public Storefront Settings
     * Read settings for the storefront selected by public tenant resolution, including its
     * configured service availability.
     *
     * Access and scope: storefront context is resolved by the public gateway; tenant-aware
     * operations use that storefront. Signed headers are verified outside OpenAPI. See
     * [storefront
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/storefront-context-contract.md#resolution-and-compatibility).
     * @returns StorefrontSettingsResponse Successful Response
     * @throws ApiError
     */
    public static getPublicStorefrontSettings(): CancelablePromise<StorefrontSettingsResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/storefront-settings',
        });
    }
    /**
     * Get Public Installation Pricing Config
     * Tell the storefront which installation pricing contract is authoritative. Response uses
     * private/no-store headers; read this before choosing legacy calculation or price-book
     * preview.
     *
     * Access and scope: storefront context is resolved by the public gateway; tenant-aware
     * operations use that storefront. Signed headers are verified outside OpenAPI. See
     * [storefront
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/storefront-context-contract.md#resolution-and-compatibility).
     * @returns InstallationPricingConfigResponse Successful Response
     * @throws ApiError
     */
    public static getPublicInstallationPricingConfig(): CancelablePromise<InstallationPricingConfigResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/service-pricing/installation/config',
        });
    }
    /**
     * Resolve Public Installation Tariff
     * Resolve a tariff using the storefront installation price book. Disabled installation is
     * reported as status=unavailable with service_direction_not_enabled, rather than 404. Does
     * not create an order.
     *
     * Access and scope: storefront context is resolved by the public gateway; tenant-aware
     * operations use that storefront. Signed headers are verified outside OpenAPI. See
     * [storefront
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/storefront-context-contract.md#resolution-and-compatibility).
     * @param requestBody
     * @returns InstallationResolveResponse Successful Response
     * @throws ApiError
     */
    public static resolvePublicInstallationTariff(
        requestBody: InstallationResolvePayload,
    ): CancelablePromise<InstallationResolveResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/service-pricing/installation/resolve',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Preview Public Installation Estimate
     * Calculate a price-book installation preview and, outside read-only demo scope, persist
     * its receipt using the required Idempotency-Key. Public callers cannot approve site
     * access: approved_site_access returns 422. Disabled installation returns
     * status=unavailable. A persistent preview replays the same input/key for its 30-minute
     * receipt lifetime; another input with that key returns 409 idempotency_key_reused. A
     * price-book revision mismatch returns 409 price_changed. Receipt
     * contention/unavailability can return 503 with Retry-After: 1; retain the same input/key
     * for a retry. Preview is not acceptance or order creation.
     *
     * Access and scope: storefront context is resolved by the public gateway; tenant-aware
     * operations use that storefront. Signed headers are verified outside OpenAPI. See
     * [storefront
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/storefront-context-contract.md#resolution-and-compatibility).
     * @param idempotencyKey
     * @param requestBody
     * @returns InstallationPreviewResponse Successful Response
     * @throws ApiError
     */
    public static previewPublicInstallationEstimate(
        idempotencyKey: string,
        requestBody: InstallationPreviewPayload,
    ): CancelablePromise<InstallationPreviewResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/service-pricing/installation/preview',
            headers: {
                'Idempotency-Key': idempotencyKey,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * List Public Service Tariffs
     * List active service tariffs and active rules for this storefront and service direction.
     * Disabled direction returns 404; installation backed by a published price book returns
     * 409 book_preview_required.
     *
     * Access and scope: storefront context is resolved by the public gateway; tenant-aware
     * operations use that storefront. Signed headers are verified outside OpenAPI. See
     * [storefront
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/storefront-context-contract.md#resolution-and-compatibility).
     * @param serviceKind
     * @returns PublicServiceTariffListResponse Successful Response
     * @throws ApiError
     */
    public static listPublicServiceTariffs(
        serviceKind: ManagerTariffServiceKind,
    ): CancelablePromise<PublicServiceTariffListResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/service-pricing/tariffs',
            query: {
                'service_kind': serviceKind,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Calculate Public Service Tariff
     * Calculate a legacy active tariff within this storefront without creating an order.
     * Disabled service direction returns 404; installation with a published price book returns
     * 409 book_preview_required. Tariff access and active status are checked by the tariff
     * service.
     *
     * Access and scope: storefront context is resolved by the public gateway; tenant-aware
     * operations use that storefront. Signed headers are verified outside OpenAPI. See
     * [storefront
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/storefront-context-contract.md#resolution-and-compatibility).
     * @param requestBody
     * @returns ManagerInstallEstimateResponse Successful Response
     * @throws ApiError
     */
    public static calculatePublicServiceTariff(
        requestBody: PublicServiceEstimateCalculatePayload,
    ): CancelablePromise<ManagerInstallEstimateResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/service-pricing/calculate',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Yandex Business Feed
     * Return the shared Yandex Business price-list XML generated by the feed service. No
     * Manager token or storefront signature is required: this is an explicit public gateway
     * exception. Response is application/xml, not JSON or a tenant-selected catalog page.
     * @returns string Successful Response
     * @throws ApiError
     */
    public static getYandexBusinessFeed(): CancelablePromise<string> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/feeds/yandex-business.yml',
        });
    }
    /**
     * List Public Multi Split Options
     * List storefront-visible indoor or outdoor units for multi-split selection, with public
     * prices and pagination; limit is at most 100.
     *
     * Access and scope: storefront context is resolved by the public gateway; tenant-aware
     * operations use that storefront. Signed headers are verified outside OpenAPI. See
     * [storefront
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/storefront-context-contract.md#resolution-and-compatibility).
     * @param kind
     * @param page
     * @param limit
     * @returns MultiSplitOptionsResponse Successful Response
     * @throws ApiError
     */
    public static listPublicMultiSplitOptions(
        kind: 'outdoor_unit' | 'indoor_unit',
        page: number = 1,
        limit: number = 40,
    ): CancelablePromise<MultiSplitOptionsResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/multi-split/options',
            query: {
                'kind': kind,
                'page': page,
                'limit': limit,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Preview Public Multi Split
     * Validate a multi-split selection server-side in the resolved storefront and return its
     * public price projection without creating a lead. Invalid or incompatible selection
     * returns 422.
     *
     * Access and scope: storefront context is resolved by the public gateway; tenant-aware
     * operations use that storefront. Signed headers are verified outside OpenAPI. See
     * [storefront
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/storefront-context-contract.md#resolution-and-compatibility).
     * @param requestBody
     * @returns MultiSplitPreviewResponse Successful Response
     * @throws ApiError
     */
    public static previewPublicMultiSplit(
        requestBody: MultiSplitPreviewRequest,
    ): CancelablePromise<MultiSplitPreviewResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/multi-split/preview',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Create Public Multi Split Lead
     * Validate a multi-split selection and create a lead in this storefront. Idempotency-Key
     * is required; invalid selection or intake values return 422. For required keys, unsigned
     * compatibility, conflicting payloads (409) and retries after 503 with Retry-After, see
     * [public write
     * idempotency](https://github.com/mvnby/air-api/blob/main/docs/storefront-context-contract.md#public-write-idempotency).
     * Retain the same key and content when retrying.
     *
     * Access and scope: storefront context is resolved by the public gateway; tenant-aware
     * operations use that storefront. Signed headers are verified outside OpenAPI. See
     * [storefront
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/storefront-context-contract.md#resolution-and-compatibility).
     * @param idempotencyKey
     * @param requestBody
     * @returns MultiSplitLeadResponse Successful Response
     * @throws ApiError
     */
    public static createPublicMultiSplitLead(
        idempotencyKey: string,
        requestBody: MultiSplitLeadPayload,
    ): CancelablePromise<MultiSplitLeadResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/multi-split/leads',
            headers: {
                'Idempotency-Key': idempotencyKey,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Push Tender Lead
     * Accept one native opportunity using the dedicated Bearer key and server-owned destination.
     *
     * Activation and writable-primary controls fail closed. Replays deduplicate by source and
     * external tender ID; source updates preserve staff workflow and reviewed enrichment.
     * Creation follows the existing confirmed/eligible/deadline rules. Older updates cannot
     * replace newer source state. Push does not advance the shared pull cursor or timestamp.
     * The validated native model is limited to 64 KiB; IDs are producer-owned and timestamps
     * are timezone-aware. Returns a nullable order ID and created/updated/unchanged/skipped.
     * Configured intake rejects missing/wrong keys with 401, invalid destination with 403,
     * disabled/unwritable intake with 503 and malformed payload with 422. The outer HA fence
     * may return its own 503 before routing.
     * No source HTTP request, customer qualification or downstream business action is performed.
     *
     * See [intake contract](https://github.com/mvnby/air-api/blob/main/docs/belzakupki-intake.md#direct-push-intake-849-first-release-slice).
     * @param requestBody
     * @returns TenderLeadPushResult Successful Response
     * @throws ApiError
     */
    public static pushTenderLead(
        requestBody: NativeOpportunity,
    ): CancelablePromise<TenderLeadPushResult> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/integrations/tenders/leads',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
