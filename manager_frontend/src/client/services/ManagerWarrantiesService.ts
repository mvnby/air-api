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
     * Read shared warranty policy definitions filtered by supplier, brand, series or product;
     * inactive policies are excluded by default. This list is unpaginated. Policies are
     * definitions for coverage selection, not the live warranty status of a customer equipment
     * record.
     *
     * Access and scope: Manager access is required; these definitions are shared across
     * tenants. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * See [warranty policy
     * contract](https://github.com/mvnby/air-api/blob/main/docs/warranty-policies.md).
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
     * Create a shared warranty policy with at least one supplier/brand/series/product target.
     * Invalid references, incompatible series/brand selection or invalid duration/maintenance
     * terms return 400. This defines future coverage selection without rewriting existing
     * equipment coverage snapshots. Repeated POSTs have no idempotency receipt.
     *
     * Access and scope: system-tenant Manager access is required; these are shared platform
     * definitions. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * See [warranty policy
     * contract](https://github.com/mvnby/air-api/blob/main/docs/warranty-policies.md).
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
     * Update only submitted shared warranty-policy fields. Missing policy returns 404; invalid
     * targets, relationships or durations return 400. Omitted series selection is preserved
     * and an explicitly empty selection clears it. Existing equipment warranty snapshots are
     * not recalculated from the edited definition.
     *
     * Access and scope: system-tenant Manager access is required; these are shared platform
     * definitions. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * See [warranty policy
     * contract](https://github.com/mvnby/air-api/blob/main/docs/warranty-policies.md).
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
     * Read warranty coverage snapshots and their current temporal, maintenance and
     * operator-decision status for customer equipment. Missing/inaccessible equipment returns
     * 404. Reading computes status without changing the stored policy snapshot or recording a
     * warranty decision.
     *
     * Access and scope: Manager access is required; equipment ownership is inherited from its
     * customer in the authenticated tenant. Linked orders must also belong to the selected
     * storefront. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * See [warranty policy
     * contract](https://github.com/mvnby/air-api/blob/main/docs/warranty-policies.md).
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
     * Record a voided/restored decision with a required reason for an equipment coverage under
     * a coverage lock, appending decision history. Missing/inaccessible equipment/coverage
     * returns 404 and invalid action/reason returns 400. Restoring equipment/supplier coverage
     * cannot override warranty_mode=none; valid restoration recalculates maintenance status.
     * Repeats append decisions because no idempotency receipt is used; shared policy
     * definitions remain unchanged.
     *
     * Access and scope: Manager access is required; equipment ownership is inherited from its
     * customer in the authenticated tenant. Linked orders must also belong to the selected
     * storefront. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * See [warranty policy
     * contract](https://github.com/mvnby/air-api/blob/main/docs/warranty-policies.md).
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
