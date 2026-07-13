/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ManagerOrderEquipmentLinkCreatePayload } from '../models/ManagerOrderEquipmentLinkCreatePayload';
import type { ManagerOrderEquipmentLinkItemResponse } from '../models/ManagerOrderEquipmentLinkItemResponse';
import type { ManagerOrderEquipmentLinkListResponse } from '../models/ManagerOrderEquipmentLinkListResponse';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class ManagerEquipmentLinksService {
    /**
     * List Manager Order Equipment Links
     * @param orderId
     * @returns ManagerOrderEquipmentLinkListResponse Successful Response
     * @throws ApiError
     */
    public static listManagerOrderEquipmentLinks(
        orderId: number,
    ): CancelablePromise<ManagerOrderEquipmentLinkListResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/orders/{order_id}/equipment-links',
            path: {
                'order_id': orderId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Create Manager Order Equipment Link
     * @param orderId
     * @param requestBody
     * @returns ManagerOrderEquipmentLinkItemResponse Successful Response
     * @throws ApiError
     */
    public static createManagerOrderEquipmentLink(
        orderId: number,
        requestBody: ManagerOrderEquipmentLinkCreatePayload,
    ): CancelablePromise<ManagerOrderEquipmentLinkItemResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/orders/{order_id}/equipment-links',
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
     * Delete Manager Order Equipment Link
     * @param orderId
     * @param linkId
     * @returns void
     * @throws ApiError
     */
    public static deleteManagerOrderEquipmentLink(
        orderId: number,
        linkId: number,
    ): CancelablePromise<void> {
        return __request(OpenAPI, {
            method: 'DELETE',
            url: '/api/manager/orders/{order_id}/equipment-links/{link_id}',
            path: {
                'order_id': orderId,
                'link_id': linkId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
