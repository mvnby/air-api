/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { CatalogDecisionAttachToOrderPayload } from '../models/CatalogDecisionAttachToOrderPayload';
import type { CatalogDecisionCreateCollectionPayload } from '../models/CatalogDecisionCreateCollectionPayload';
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
     * @param page
     * @param limit
     * @param search
     * @param coolingBtuClasses
     * @param coolingMinKw
     * @param coolingMaxKw
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
     * @param isPublished
     * @param sort
     * @param direction
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
        areaMin?: (number | null),
        areaMax?: (number | null),
        category?: ('household' | 'multi' | 'semi_industrial' | null),
        indoorFormFactor?: ('wall' | 'cassette' | 'duct' | 'floor_ceiling' | 'column' | null),
        brandIds?: (Array<number> | null),
        seriesIds?: (Array<number> | null),
        isInverter?: (boolean | null),
        hasWifi?: (boolean | null),
        wifi?: ('builtin' | 'ready' | 'none' | null),
        availability?: ('in_stock' | 'out_of_stock' | null),
        isPublished?: (boolean | null),
        sort: 'retail_price' | 'purchase_cost' | 'rrc' | 'margin_abs' | 'margin_pct' | 'availability' | 'cooling_power' | 'title' = 'title',
        direction: 'asc' | 'desc' = 'asc',
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
                'is_published': isPublished,
                'sort': sort,
                'direction': direction,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Create Catalog Decision Collection
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
}
