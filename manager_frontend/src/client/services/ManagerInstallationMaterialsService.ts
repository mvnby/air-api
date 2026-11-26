/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { InstallationMaterialCostInput } from '../models/InstallationMaterialCostInput';
import type { InstallationMaterialCostResult } from '../models/InstallationMaterialCostResult';
import type { InstallationMaterialPriceInput } from '../models/InstallationMaterialPriceInput';
import type { InstallationMaterialPriceItem } from '../models/InstallationMaterialPriceItem';
import type { InstallationMaterialPriceList } from '../models/InstallationMaterialPriceList';
import type { InstallationMaterialPriceUpdate } from '../models/InstallationMaterialPriceUpdate';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class ManagerInstallationMaterialsService {
    /**
     * List Manager Installation Material Prices
     * Read the authenticated company's private purchase prices for installation materials.
     * @param q
     * @param offset
     * @param limit
     * @returns InstallationMaterialPriceList Successful Response
     * @throws ApiError
     */
    public static listManagerInstallationMaterialPrices(
        q: string = '',
        offset?: number,
        limit: number = 50,
    ): CancelablePromise<InstallationMaterialPriceList> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/installation-materials',
            query: {
                'q': q,
                'offset': offset,
                'limit': limit,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Create Manager Installation Material Price
     * Record the listed purchase price and quantity of a supplier pack.
     * @param requestBody
     * @returns InstallationMaterialPriceItem Successful Response
     * @throws ApiError
     */
    public static createManagerInstallationMaterialPrice(
        requestBody: InstallationMaterialPriceInput,
    ): CancelablePromise<InstallationMaterialPriceItem> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/installation-materials',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Update Manager Installation Material Price
     * Replace a price using its current version in the authenticated company.
     * @param priceId
     * @param requestBody
     * @returns InstallationMaterialPriceItem Successful Response
     * @throws ApiError
     */
    public static updateManagerInstallationMaterialPrice(
        priceId: number,
        requestBody: InstallationMaterialPriceUpdate,
    ): CancelablePromise<InstallationMaterialPriceItem> {
        return __request(OpenAPI, {
            method: 'PUT',
            url: '/api/manager/installation-materials/{price_id}',
            path: {
                'price_id': priceId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Calculate Manager Installation Material Cost
     * Calculate consumption costs in BYN from current prices. This read saves no order or estimate.
     * @param requestBody
     * @returns InstallationMaterialCostResult Successful Response
     * @throws ApiError
     */
    public static calculateManagerInstallationMaterialCost(
        requestBody: InstallationMaterialCostInput,
    ): CancelablePromise<InstallationMaterialCostResult> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/installation-materials/calculate',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
