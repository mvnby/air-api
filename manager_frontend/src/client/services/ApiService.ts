/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ArticleResponse } from '../models/ArticleResponse';
import type { CatalogResponse } from '../models/CatalogResponse';
import type { OrderPayload } from '../models/OrderPayload';
import type { OrderResponse } from '../models/OrderResponse';
import type { ProductResponse } from '../models/ProductResponse';
import type { ServiceResponse } from '../models/ServiceResponse';
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
     * Get Public Spec Keys
     * Публичный список всех доступных характеристик.
     * Используется для построения динамических фильтров на сайте.
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
     * Ищет банк локально в справочнике НБРБ.
     * Принимает:
     * - BIC (код банка, например '153001755')
     * - IBAN (вырезает код из строки вида BYxx [CODE] xxxx...)
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
     * Generate Product Description
     * Генерирует описание на основе тегов и возвращает текст.
     * Админ может потом его отредактировать и сохранить.
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
     * Get paginated product catalog with filtering and sorting.
     *
     * **Filters:**
     * - `min_price`, `max_price`: Price range filter
     * - `area_min`, `area_max`: Area coverage filter
     * - `tag_slugs`: Filter by tag slugs (e.g., 'inverter', 'chigo', 'area-25')
     * - `is_inverter`: Filter by inverter technology
     *
     * **Sorting:**
     * - `newest`: Recently added products (default)
     * - `price_asc`: Price low to high
     * - `price_desc`: Price high to low
     * - `area_asc`: Area low to high
     * - `area_desc`: Area high to low
     * @param page
     * @param limit
     * @param sort
     * @param minPrice
     * @param maxPrice
     * @param areaMin
     * @param areaMax
     * @param tagSlugs
     * @param isInverter
     * @returns CatalogResponse Successful Response
     * @throws ApiError
     */
    public static getProductsV1(
        page: number = 1,
        limit: number = 20,
        sort: string = 'newest',
        minPrice?: (number | null),
        maxPrice?: (number | null),
        areaMin?: (number | null),
        areaMax?: (number | null),
        tagSlugs?: (Array<string> | null),
        isInverter?: (boolean | null),
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
                'tag_slugs': tagSlugs,
                'is_inverter': isInverter,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Catalog
     * Get paginated product catalog with filtering and sorting.
     *
     * **Filters:**
     * - `min_price`, `max_price`: Price range filter
     * - `area_min`, `area_max`: Area coverage filter
     * - `tag_slugs`: Filter by tag slugs (e.g., 'inverter', 'chigo', 'area-25')
     * - `is_inverter`: Filter by inverter technology
     *
     * **Sorting:**
     * - `newest`: Recently added products (default)
     * - `price_asc`: Price low to high
     * - `price_desc`: Price high to low
     * - `area_asc`: Area low to high
     * - `area_desc`: Area high to low
     * @param page
     * @param limit
     * @param sort
     * @param minPrice
     * @param maxPrice
     * @param areaMin
     * @param areaMax
     * @param tagSlugs
     * @param isInverter
     * @returns CatalogResponse Successful Response
     * @throws ApiError
     */
    public static getProducts(
        page: number = 1,
        limit: number = 20,
        sort: string = 'newest',
        minPrice?: (number | null),
        maxPrice?: (number | null),
        areaMin?: (number | null),
        areaMax?: (number | null),
        tagSlugs?: (Array<string> | null),
        isInverter?: (boolean | null),
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
                'tag_slugs': tagSlugs,
                'is_inverter': isInverter,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Product By Identifier
     * Get product details by ID or slug (Hybrid Access).
     *
     * Returns full product information including tags, specifications, and images.
     * Raises 404 if product not found.
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
     * Get list of all available services (Legacy, redirects to valid logic).
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
     * Create Order
     * Create a new order from website.
     *
     * Accepts customer information and cart items. Creates or updates customer record,
     * creates order with NEW_LEAD status and lead_source=SITE.
     *
     * Returns created order details.
     * @param requestBody
     * @returns OrderResponse Successful Response
     * @throws ApiError
     */
    public static createOrder(
        requestBody: OrderPayload,
    ): CancelablePromise<OrderResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/v1/orders',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Global Config
     * Get all global configuration parameters as a key-value dictionary.
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
}
