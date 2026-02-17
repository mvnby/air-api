/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { OrderStatusUpdate } from '../models/OrderStatusUpdate';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class AdminOrdersService {
    /**
     * Move Order Status
     * API for Kanban drag-and-drop.
     * @param requestBody
     * @returns any Successful Response
     * @throws ApiError
     */
    public static moveOrderStatusAdminApiOrderMovePost(
        requestBody: OrderStatusUpdate,
    ): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/admin/api/order/move',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
