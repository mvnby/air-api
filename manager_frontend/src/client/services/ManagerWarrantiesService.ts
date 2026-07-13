/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ManagerEquipmentWarrantyCoverageResponse } from '../models/ManagerEquipmentWarrantyCoverageResponse';
import type { ManagerWarrantyDecisionPayload } from '../models/ManagerWarrantyDecisionPayload';
import type { ManagerWarrantyPolicyListResponse } from '../models/ManagerWarrantyPolicyListResponse';
import type { ManagerWarrantyPolicyPayload } from '../models/ManagerWarrantyPolicyPayload';
import type { ManagerWarrantyPolicyResponse } from '../models/ManagerWarrantyPolicyResponse';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class ManagerWarrantiesService {
    /**
     * List Manager Warranty Policies
     * @param supplierId
     * @param brandId
     * @param seriesId
     * @param productId
     * @param includeInactive
     * @returns ManagerWarrantyPolicyListResponse Successful Response
     * @throws ApiError
     */
    public static listManagerWarrantyPolicies(
        supplierId?: (number | null),
        brandId?: (number | null),
        seriesId?: (number | null),
        productId?: (number | null),
        includeInactive: boolean = false,
    ): CancelablePromise<ManagerWarrantyPolicyListResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/warranty-policies',
            query: {
                'supplier_id': supplierId,
                'brand_id': brandId,
                'series_id': seriesId,
                'product_id': productId,
                'include_inactive': includeInactive,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Create Manager Warranty Policy
     * @param requestBody
     * @returns ManagerWarrantyPolicyResponse Successful Response
     * @throws ApiError
     */
    public static createManagerWarrantyPolicy(
        requestBody: ManagerWarrantyPolicyPayload,
    ): CancelablePromise<ManagerWarrantyPolicyResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/warranty-policies',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Patch Manager Warranty Policy
     * @param policyId
     * @param requestBody
     * @returns ManagerWarrantyPolicyResponse Successful Response
     * @throws ApiError
     */
    public static patchManagerWarrantyPolicy(
        policyId: number,
        requestBody: ManagerWarrantyPolicyPayload,
    ): CancelablePromise<ManagerWarrantyPolicyResponse> {
        return __request(OpenAPI, {
            method: 'PATCH',
            url: '/api/manager/warranty-policies/{policy_id}',
            path: {
                'policy_id': policyId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * List Manager Equipment Warranty Coverages
     * @param equipmentId
     * @returns ManagerEquipmentWarrantyCoverageResponse Successful Response
     * @throws ApiError
     */
    public static listManagerEquipmentWarrantyCoverages(
        equipmentId: number,
    ): CancelablePromise<Array<ManagerEquipmentWarrantyCoverageResponse>> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/equipment/{equipment_id}/warranty-coverages',
            path: {
                'equipment_id': equipmentId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Decide Manager Warranty Coverage
     * @param coverageId
     * @param requestBody
     * @returns ManagerEquipmentWarrantyCoverageResponse Successful Response
     * @throws ApiError
     */
    public static decideManagerWarrantyCoverage(
        coverageId: number,
        requestBody: ManagerWarrantyDecisionPayload,
    ): CancelablePromise<ManagerEquipmentWarrantyCoverageResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/warranty-coverages/{coverage_id}/decision',
            path: {
                'coverage_id': coverageId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
