/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { CatalogDecisionAttachToOrderPayload } from '../models/CatalogDecisionAttachToOrderPayload';
import type { CatalogDecisionCreateCollectionPayload } from '../models/CatalogDecisionCreateCollectionPayload';
import type { CatalogDecisionCreateOrderPayload } from '../models/CatalogDecisionCreateOrderPayload';
import type { CatalogDecisionFilterOptionsResponse } from '../models/CatalogDecisionFilterOptionsResponse';
import type { CatalogDecisionListResponse } from '../models/CatalogDecisionListResponse';
import type { ManagerOrderDetailResponse } from '../models/ManagerOrderDetailResponse';
import type { ManagerProductCollectionResponse } from '../models/ManagerProductCollectionResponse';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class ManagerCatalogDecisionService {
    /**
     * List Catalog Decision Filter Options
     * Read available brands, series and supported technical filters for the selected
     * storefront’s split-system decision catalog. Options use storefront
     * visibility/eligibility; this does not expose a supplier-management surface or mutate
     * product data.
     *
     * Access and scope: Manager access is required; data is restricted to the authenticated
     * tenant and selected storefront. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * @returns CatalogDecisionFilterOptionsResponse Successful Response
     * @throws ApiError
     */
    public static listManagerCatalogDecisionFilterOptions(): CancelablePromise<CatalogDecisionFilterOptionsResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/catalog-decision/filter-options',
        });
    }
    /**
     * List Catalog Decision Products
     * Read eligible complete split systems with technical and commercial projections; limit is
     * 1–100. Availability defaults to in_stock; include_orderable removes that restriction.
     * category=multi, unsupported BTU classes or inverted retail bounds return 422. Explicit
     * product_ids is limited to 24. Demo purchase-cost projection uses a synthetic discount
     * from RRC rather than actual supplier cost. This endpoint only reads.
     *
     * Access and scope: Manager access is required; data is restricted to the authenticated
     * tenant and selected storefront. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * @param page
     * @param limit
     * @param search
     * @param coolingBtuClasses
     * @param coolingMinKw
     * @param coolingMaxKw
     * @param retailMinByn
     * @param retailMaxByn
     * @param areaMin
     * @param areaMax
     * @param category
     * @param indoorFormFactor
     * @param brandIds
     * @param seriesIds
     * @param isInverter
     * @param hasWifi
     * @param wifi
     * @param availability
     * @param includeOrderable
     * @param productIds
     * @param isPublished
     * @param sort
     * @param direction
     * @param heatingMin Required outdoor heating temperature in Celsius; includes colder-rated models.
     * @returns CatalogDecisionListResponse Successful Response
     * @throws ApiError
     */
    public static listManagerCatalogDecisionProducts(
        page: number = 1,
        limit: number = 40,
        search?: (string | null),
        coolingBtuClasses?: (Array<number> | null),
        coolingMinKw?: (number | null),
        coolingMaxKw?: (number | null),
        retailMinByn?: (number | null),
        retailMaxByn?: (number | null),
        areaMin?: (number | null),
        areaMax?: (number | null),
        category?: ('household' | 'multi' | 'semi_industrial' | null),
        indoorFormFactor?: ('wall' | 'cassette' | 'duct' | 'floor_ceiling' | 'column' | 'console' | null),
        brandIds?: (Array<number> | null),
        seriesIds?: (Array<number> | null),
        isInverter?: (boolean | null),
        hasWifi?: (boolean | null),
        wifi?: ('builtin' | 'ready' | 'none' | null),
        availability?: ('in_stock' | 'out_of_stock' | null),
        includeOrderable: boolean = false,
        productIds?: (Array<number> | null),
        isPublished?: (boolean | null),
        sort: 'retail_price' | 'purchase_cost' | 'rrc' | 'margin_abs' | 'margin_pct' | 'availability' | 'cooling_power' | 'title' = 'title',
        direction: 'asc' | 'desc' = 'asc',
        heatingMin?: (number | null),
    ): CancelablePromise<CatalogDecisionListResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/catalog-decision/products',
            query: {
                'page': page,
                'limit': limit,
                'search': search,
                'cooling_btu_classes': coolingBtuClasses,
                'cooling_min_kw': coolingMinKw,
                'cooling_max_kw': coolingMaxKw,
                'retail_min_byn': retailMinByn,
                'retail_max_byn': retailMaxByn,
                'area_min': areaMin,
                'area_max': areaMax,
                'category': category,
                'indoor_form_factor': indoorFormFactor,
                'brand_ids': brandIds,
                'series_ids': seriesIds,
                'is_inverter': isInverter,
                'has_wifi': hasWifi,
                'wifi': wifi,
                'availability': availability,
                'include_orderable': includeOrderable,
                'product_ids': productIds,
                'is_published': isPublished,
                'sort': sort,
                'direction': direction,
                'heating_min': heatingMin,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Create Catalog Decision Collection
     * Create a manual draft collection from the chosen split-system IDs, preserving their
     * order as pinned items. Requires Manager access; unlike the general collection routes
     * this bridge does not require storefront.collections.manage. Empty title/duplicates or
     * non-split-system selections return 400; products unavailable to the storefront return
     * 404. Each POST creates a new collection.
     *
     * Access and scope: Manager access is required; data is restricted to the authenticated
     * tenant and selected storefront. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * See [collection
     * contract](https://github.com/mvnby/air-api/blob/main/docs/product-collections.md).
     * @param requestBody
     * @returns ManagerProductCollectionResponse Successful Response
     * @throws ApiError
     */
    public static createManagerCatalogDecisionCollection(
        requestBody: CatalogDecisionCreateCollectionPayload,
    ): CancelablePromise<ManagerProductCollectionResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/catalog-decision/collections',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Attach Catalog Decision To Order
     * Add selected equipment to a scoped negotiation-stage order. auto returns 409 when active
     * proposals already contain products; replace_selected replaces the selected proposal,
     * new_alternative creates variant(s), and append_to_proposal skips products already in the
     * chosen draft. Invalid selection/proposal/lifecycle mode returns 400. Commands lock the
     * order and recalculate financials. No idempotency receipt exists; repeating
     * new_alternative can create another proposal.
     *
     * Access and scope: Manager access is required; data is restricted to the authenticated
     * tenant and selected storefront. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * @param orderId
     * @param requestBody
     * @returns ManagerOrderDetailResponse Successful Response
     * @throws ApiError
     */
    public static attachManagerCatalogDecisionToOrder(
        orderId: number,
        requestBody: CatalogDecisionAttachToOrderPayload,
    ): CancelablePromise<ManagerOrderDetailResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/catalog-decision/orders/{order_id}/attach',
            path: {
                'order_id': orderId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Create Catalog Decision Order
     * Create a scoped negotiation-stage quick order with a new proposal and selected equipment
     * snapshots. Duplicate products, empty key or invalid mode returns 400. idempotency_key is
     * scoped to tenant/storefront; a repeat returns the existing order even if the new payload
     * differs, rather than checking a payload receipt. Reuse a key only for the same creation
     * intent.
     *
     * Access and scope: Manager access is required; data is restricted to the authenticated
     * tenant and selected storefront. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * @param requestBody
     * @returns ManagerOrderDetailResponse Successful Response
     * @throws ApiError
     */
    public static createManagerCatalogDecisionOrder(
        requestBody: CatalogDecisionCreateOrderPayload,
    ): CancelablePromise<ManagerOrderDetailResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/catalog-decision/orders',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
