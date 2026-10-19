/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ManagerAccessoriesWorkspace } from '../models/ManagerAccessoriesWorkspace';
import type { ProductAccessoriesUpdate } from '../models/ProductAccessoriesUpdate';
import type { SeriesAccessoriesUpdate } from '../models/SeriesAccessoriesUpdate';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class ManagerCatalogAccessoriesService {
    /**
     * Get Series Accessories
     * Read ordered accessory product links for a shared series. Catalog master edit
     * permission is required; missing series returns 404. Published and unpublished
     * accessories are shown for editing. Compatibility does not imply availability,
     * automatic order lines or a Wi-Fi capability. Prices are resolved on public read.
     * @param targetId
     * @returns ManagerAccessoriesWorkspace Successful Response
     * @throws ApiError
     */
    public static getManagerSeriesAccessories(
        targetId: number,
    ): CancelablePromise<ManagerAccessoriesWorkspace> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/catalog-accessories/series/{target_id}',
            path: {
                'target_id': targetId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Set Series Accessories
     * Replace the complete ordered accessory set for a shared series (up to 100).
     * Catalog master edit permission is required. Missing series returns 404; missing
     * products, non-accessory products or a self-compatible series returns 400;
     * duplicate/nonpositive IDs return 422. Empty list clears links. Model exceptions
     * remain intact. Identical saves preserve catalog revision and ordering; repeating
     * the exact PUT is safe. This updates compatibility only, never orders or offers.
     * @param targetId
     * @param requestBody
     * @returns ManagerAccessoriesWorkspace Successful Response
     * @throws ApiError
     */
    public static setManagerSeriesAccessories(
        targetId: number,
        requestBody: SeriesAccessoriesUpdate,
    ): CancelablePromise<ManagerAccessoriesWorkspace> {
        return __request(OpenAPI, {
            method: 'PUT',
            url: '/api/manager/catalog-accessories/series/{target_id}',
            path: {
                'target_id': targetId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Product Accessories
     * Read series accessories and explicit model includes/excludes for a shared
     * product. Catalog master edit permission is required; missing product returns
     * 404. inherited records their series origin, override is true/false for model
     * decisions or null for inheritance, and is_enabled is the effective decision.
     * Compatibility never follows from matching brands or Wi-Fi flags.
     * @param targetId
     * @returns ManagerAccessoriesWorkspace Successful Response
     * @throws ApiError
     */
    public static getManagerProductAccessories(
        targetId: number,
    ): CancelablePromise<ManagerAccessoriesWorkspace> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/catalog-accessories/products/{target_id}',
            path: {
                'target_id': targetId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Set Product Accessories
     * Replace all explicit model overrides (up to 100). Catalog master edit
     * permission is required. is_enabled=true includes an accessory, false excludes
     * it, and omitting a previous override restores series inheritance. Series order
     * stays intact; additional model items follow it in submitted order. Missing
     * product returns 404; invalid accessory kind, missing accessory or self-link
     * returns 400; duplicate IDs return 422. Repeating an unchanged PUT is safe and
     * creates no new catalog revision. No order, price or tenant offer is changed.
     * @param targetId
     * @param requestBody
     * @returns ManagerAccessoriesWorkspace Successful Response
     * @throws ApiError
     */
    public static setManagerProductAccessories(
        targetId: number,
        requestBody: ProductAccessoriesUpdate,
    ): CancelablePromise<ManagerAccessoriesWorkspace> {
        return __request(OpenAPI, {
            method: 'PUT',
            url: '/api/manager/catalog-accessories/products/{target_id}',
            path: {
                'target_id': targetId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
