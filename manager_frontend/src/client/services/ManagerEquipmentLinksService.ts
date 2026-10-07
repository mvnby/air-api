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
     * Read equipment associated with a scoped order, including legacy source-order
     * associations without duplicate equipment entries. Missing or inaccessible order returns
     * 404. This does not create missing explicit links.
     *
     * Access and scope: Manager access is required; the order and its children are restricted
     * to the authenticated tenant and selected storefront. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
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
     * Associate existing customer equipment with an order after checking customer/branch
     * compatibility and link role. Missing order/equipment returns 404 and incompatible
     * relationships or role returns 400. An existing order/equipment pair is reused and its
     * role may be updated; this does not create an equipment unit.
     *
     * Access and scope: Manager access is required; the order and its children are restricted
     * to the authenticated tenant and selected storefront. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
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
     * Delete one equipment/order association and return 204, clearing matching legacy
     * source_order_id when necessary. Equipment, warranty snapshots and service history are
     * retained. Missing/inaccessible order/link/equipment returns 404, including after prior
     * deletion.
     *
     * Access and scope: Manager access is required; the order and its children are restricted
     * to the authenticated tenant and selected storefront. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
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
