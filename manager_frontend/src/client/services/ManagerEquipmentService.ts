/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ManagerEquipmentComponentCreatePayload } from '../models/ManagerEquipmentComponentCreatePayload';
import type { ManagerEquipmentComponentItemResponse } from '../models/ManagerEquipmentComponentItemResponse';
import type { ManagerEquipmentComponentUpdatePayload } from '../models/ManagerEquipmentComponentUpdatePayload';
import type { ManagerEquipmentCreatePayload } from '../models/ManagerEquipmentCreatePayload';
import type { ManagerEquipmentDetailResponse } from '../models/ManagerEquipmentDetailResponse';
import type { ManagerEquipmentFromOrderPayload } from '../models/ManagerEquipmentFromOrderPayload';
import type { ManagerEquipmentFromOrderResponse } from '../models/ManagerEquipmentFromOrderResponse';
import type { ManagerEquipmentHistoryFromRepairOrderPayload } from '../models/ManagerEquipmentHistoryFromRepairOrderPayload';
import type { ManagerEquipmentItemResponse } from '../models/ManagerEquipmentItemResponse';
import type { ManagerEquipmentListResponse } from '../models/ManagerEquipmentListResponse';
import type { ManagerEquipmentServiceHistoryCreatePayload } from '../models/ManagerEquipmentServiceHistoryCreatePayload';
import type { ManagerEquipmentServiceHistoryItemResponse } from '../models/ManagerEquipmentServiceHistoryItemResponse';
import type { ManagerEquipmentServiceHistoryListResponse } from '../models/ManagerEquipmentServiceHistoryListResponse';
import type { ManagerEquipmentUpdatePayload } from '../models/ManagerEquipmentUpdatePayload';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class ManagerEquipmentService {
    /**
     * List Manager Equipment
     * @param customerId
     * @param customerBranchId
     * @param page
     * @param limit
     * @param includeArchived
     * @returns ManagerEquipmentListResponse Successful Response
     * @throws ApiError
     */
    public static listManagerEquipment(
        customerId?: (number | null),
        customerBranchId?: (number | null),
        page: number = 1,
        limit: number = 20,
        includeArchived: boolean = false,
    ): CancelablePromise<ManagerEquipmentListResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/equipment',
            query: {
                'customer_id': customerId,
                'customer_branch_id': customerBranchId,
                'page': page,
                'limit': limit,
                'include_archived': includeArchived,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Create Manager Equipment
     * @param requestBody
     * @returns ManagerEquipmentItemResponse Successful Response
     * @throws ApiError
     */
    public static createManagerEquipment(
        requestBody: ManagerEquipmentCreatePayload,
    ): CancelablePromise<ManagerEquipmentItemResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/equipment',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Create Manager Equipment From Order
     * @param orderId
     * @param requestBody
     * @returns ManagerEquipmentFromOrderResponse Successful Response
     * @throws ApiError
     */
    public static createManagerEquipmentFromOrder(
        orderId: number,
        requestBody: ManagerEquipmentFromOrderPayload,
    ): CancelablePromise<ManagerEquipmentFromOrderResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/equipment/from-order/{order_id}',
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
     * Get Manager Equipment
     * @param equipmentId
     * @param historyLimit
     * @returns ManagerEquipmentDetailResponse Successful Response
     * @throws ApiError
     */
    public static getManagerEquipment(
        equipmentId: number,
        historyLimit: number = 10,
    ): CancelablePromise<ManagerEquipmentDetailResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/equipment/{equipment_id}',
            path: {
                'equipment_id': equipmentId,
            },
            query: {
                'history_limit': historyLimit,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Patch Manager Equipment
     * @param equipmentId
     * @param requestBody
     * @returns ManagerEquipmentItemResponse Successful Response
     * @throws ApiError
     */
    public static patchManagerEquipment(
        equipmentId: number,
        requestBody: ManagerEquipmentUpdatePayload,
    ): CancelablePromise<ManagerEquipmentItemResponse> {
        return __request(OpenAPI, {
            method: 'PATCH',
            url: '/api/manager/equipment/{equipment_id}',
            path: {
                'equipment_id': equipmentId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Create Manager Equipment Component
     * @param equipmentId
     * @param requestBody
     * @returns ManagerEquipmentComponentItemResponse Successful Response
     * @throws ApiError
     */
    public static createManagerEquipmentComponent(
        equipmentId: number,
        requestBody: ManagerEquipmentComponentCreatePayload,
    ): CancelablePromise<ManagerEquipmentComponentItemResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/equipment/{equipment_id}/components',
            path: {
                'equipment_id': equipmentId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Patch Manager Equipment Component
     * @param equipmentId
     * @param componentId
     * @param requestBody
     * @returns ManagerEquipmentComponentItemResponse Successful Response
     * @throws ApiError
     */
    public static patchManagerEquipmentComponent(
        equipmentId: number,
        componentId: number,
        requestBody: ManagerEquipmentComponentUpdatePayload,
    ): CancelablePromise<ManagerEquipmentComponentItemResponse> {
        return __request(OpenAPI, {
            method: 'PATCH',
            url: '/api/manager/equipment/{equipment_id}/components/{component_id}',
            path: {
                'equipment_id': equipmentId,
                'component_id': componentId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * List Manager Equipment History
     * @param equipmentId
     * @param page
     * @param limit
     * @returns ManagerEquipmentServiceHistoryListResponse Successful Response
     * @throws ApiError
     */
    public static listManagerEquipmentHistory(
        equipmentId: number,
        page: number = 1,
        limit: number = 20,
    ): CancelablePromise<ManagerEquipmentServiceHistoryListResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/equipment/{equipment_id}/history',
            path: {
                'equipment_id': equipmentId,
            },
            query: {
                'page': page,
                'limit': limit,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Create Manager Equipment History
     * @param equipmentId
     * @param requestBody
     * @returns ManagerEquipmentServiceHistoryItemResponse Successful Response
     * @throws ApiError
     */
    public static createManagerEquipmentHistory(
        equipmentId: number,
        requestBody: ManagerEquipmentServiceHistoryCreatePayload,
    ): CancelablePromise<ManagerEquipmentServiceHistoryItemResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/equipment/{equipment_id}/history',
            path: {
                'equipment_id': equipmentId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Create Manager Equipment History From Repair Order
     * @param equipmentId
     * @param requestBody
     * @returns ManagerEquipmentServiceHistoryItemResponse Successful Response
     * @throws ApiError
     */
    public static createManagerEquipmentHistoryFromRepairOrder(
        equipmentId: number,
        requestBody: ManagerEquipmentHistoryFromRepairOrderPayload,
    ): CancelablePromise<ManagerEquipmentServiceHistoryItemResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/equipment/{equipment_id}/history/from-repair-order',
            path: {
                'equipment_id': equipmentId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
