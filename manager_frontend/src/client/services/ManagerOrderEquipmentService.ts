/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ConnectorWriteResult_OrderEquipmentSaveResult_ } from '../models/ConnectorWriteResult_OrderEquipmentSaveResult_';
import type { OrderEquipmentSavePayload } from '../models/OrderEquipmentSavePayload';
import type { OrderEquipmentState } from '../models/OrderEquipmentState';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class ManagerOrderEquipmentService {
    /**
     * Get Manager Order Equipment Identities
     * Read saved physical units and their version in the accessible order.
     *
     * An optional existing candidate must belong to the same customer/object. This
     * never creates a unit or refreshes a document snapshot. Inaccessible records
     * return 404; an incompatible customer/object returns 400. Manager membership
     * and tenant/storefront isolation apply to the order and equipment.
     * @param orderId
     * @param equipmentId
     * @param limit
     * @param offset
     * @returns OrderEquipmentState Successful Response
     * @throws ApiError
     */
    public static getManagerOrderEquipmentIdentities(
        orderId: number,
        equipmentId?: (number | null),
        limit: number = 100,
        offset?: number,
    ): CancelablePromise<OrderEquipmentState> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/orders/{order_id}/equipment-identities',
            path: {
                'order_id': orderId,
            },
            query: {
                'equipment_id': equipmentId,
                'limit': limit,
                'offset': offset,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Save Manager Order Equipment Identity
     * Save a confirmed physical unit or associate an existing unit with this order.
     *
     * Reuse the exact idempotency key and payload after a timeout. The order version
     * prevents stale saves; editing an existing identity also requires its own
     * version. Omitted identity fields survive. A source document supplies saved
     * snapshot facts and is never rewritten; repeated adoption reuses its unit.
     * Missing records return 404, stale versions or changed key payloads 409,
     * invalid fields/relationships 400 and temporary receipt contention 503.
     * Requires an active Manager staff membership in the scoped tenant/storefront.
     * @param orderId
     * @param requestBody
     * @returns ConnectorWriteResult_OrderEquipmentSaveResult_ Successful Response
     * @throws ApiError
     */
    public static saveManagerOrderEquipmentIdentity(
        orderId: number,
        requestBody: OrderEquipmentSavePayload,
    ): CancelablePromise<ConnectorWriteResult_OrderEquipmentSaveResult_> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/orders/{order_id}/equipment-identities',
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
