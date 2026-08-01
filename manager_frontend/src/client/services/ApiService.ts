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
import type { PublicSeriesPageResponse } from '../models/PublicSeriesPageResponse';
import type { PublicStorefrontContextResponse } from '../models/PublicStorefrontContextResponse';
import type { RepairDiagnosticLeadResponse } from '../models/RepairDiagnosticLeadResponse';
import type { ServiceResponse } from '../models/ServiceResponse';
import type { SpecRegistryResponse } from '../models/SpecRegistryResponse';
import type { SpecsKeysResponse } from '../models/SpecsKeysResponse';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class ApiService {
    /**
     * Search Products
     * Search products with fuzzy matching.
     * @param q
     * @param isInverter
     * @returns any Successful Response
     * @throws ApiError
     */
    public static searchProductsApiProductsSearchGet(
        q?: string,
        isInverter?: boolean,
    ): CancelablePromise<any> {
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
     * Check API and database availability.
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
     * Check whether this API node should receive public traffic.
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
     * Get list of published articles ordered by creation date (newest first).
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
     * Get article details by slug. Returns 404 if not found or not published.
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
     * Get list of all available services.
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
     * Get published brands that have at least one published product.
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
     * Get a published brand by slug if it has published products.
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
     * Get one published series and its public product cards.
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
     * Get rich installation options.
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
     * Get all installation rates.
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
     * Get the public storefront configuration as a key-value dictionary.
     * Example: {"phone": "+37529...", "email": "..."}
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
                400: `Invalid idempotency key`,
                409: `Idempotency key reused with different content`,
                422: `Validation Error`,
                428: `Signed write requires Idempotency-Key`,
            },
        });
    }
    /**
     * Create Installation Estimate Lead
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
                400: `Invalid image or upload limits exceeded`,
                409: `Idempotency key reused with different content`,
                422: `Validation Error`,
                503: `Request can be retried after a short delay`,
            },
        });
    }
    /**
     * Create Product Availability Lead
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
                400: `Invalid idempotency key`,
                409: `Idempotency key reused with different content`,
                422: `Validation Error`,
                428: `Signed write requires Idempotency-Key`,
            },
        });
    }
    /**
     * Create Repair Diagnostic Lead
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
                400: `Invalid form data or idempotency key`,
                409: `Idempotency key reused with different content`,
                422: `Validation Error`,
                428: `Signed write requires Idempotency-Key`,
            },
        });
    }
    /**
     * Create Order
     * Create a new order from website.
     * Accepts customer information and cart items.
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
                400: `Invalid idempotency key`,
                409: `The selected installation quote conflicts with current tariffs.`,
                422: `Validation Error`,
                428: `Signed write requires Idempotency-Key`,
            },
        });
    }
    /**
     * Get Public Spec Keys
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
     * @param indoorTypes Indoor unit types for semi-industrial catalog (duct/cassette/floor_ceiling/column)
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
     * @param indoorTypes Indoor unit types for semi-industrial catalog (duct/cassette/floor_ceiling/column)
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
     * Proxy for Belarus EGR (Ministry of Taxes) API.
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
     * Find bank in NBRB reference by BIC/IBAN.
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
     * Public proxy for Belarus EGR (Ministry of Taxes) API.
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
     * Public proxy to find bank details by IBAN/BIC.
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
     * Get Yandex Business Feed
     * @returns string Successful Response
     * @throws ApiError
     */
    public static getYandexBusinessFeed(): CancelablePromise<string> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/v1/feeds/yandex-business.yml',
        });
    }
}
