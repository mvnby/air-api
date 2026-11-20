/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ConnectorWriteResult_OrderInspectionSaved_ } from '../models/ConnectorWriteResult_OrderInspectionSaved_';
import type { ConnectorWriteResult_OrderTechnicalActPrepared_ } from '../models/ConnectorWriteResult_OrderTechnicalActPrepared_';
import type { OrderInspectionSavePayload } from '../models/OrderInspectionSavePayload';
import type { OrderInspectionState } from '../models/OrderInspectionState';
import type { PrepareOrderTechnicalActPayload } from '../models/PrepareOrderTechnicalActPayload';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class ManagerOrderDiagnosticsService {
    /**
     * Get Order Inspection
     * Read the current inspection or one immutable version for scoped equipment.
     * @param orderId
     * @param siteId
     * @param equipmentId
     * @param version
     * @returns OrderInspectionState Successful Response
     * @throws ApiError
     */
    public static getManagerOrderInspection(
        orderId: number,
        siteId: number,
        equipmentId: number,
        version?: (number | null),
    ): CancelablePromise<OrderInspectionState> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/orders/{order_id}/sites/{site_id}/equipment/{equipment_id}/inspection',
            path: {
                'order_id': orderId,
                'site_id': siteId,
                'equipment_id': equipmentId,
            },
            query: {
                'version': version,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Save Order Inspection
     * Record a new version with checked facts, recommendations and performed actions kept separately.
     * @param orderId
     * @param siteId
     * @param equipmentId
     * @param requestBody
     * @returns ConnectorWriteResult_OrderInspectionSaved_ Successful Response
     * @throws ApiError
     */
    public static saveManagerOrderInspection(
        orderId: number,
        siteId: number,
        equipmentId: number,
        requestBody: OrderInspectionSavePayload,
    ): CancelablePromise<ConnectorWriteResult_OrderInspectionSaved_> {
        return __request(OpenAPI, {
            method: 'PUT',
            url: '/api/manager/orders/{order_id}/sites/{site_id}/equipment/{equipment_id}/inspection',
            path: {
                'order_id': orderId,
                'site_id': siteId,
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
     * Prepare Order Technical Act
     * Prepare a native draft for the chosen scope and basis without reserving an official number.
     * @param orderId
     * @param siteId
     * @param requestBody
     * @returns ConnectorWriteResult_OrderTechnicalActPrepared_ Successful Response
     * @throws ApiError
     */
    public static prepareManagerOrderTechnicalAct(
        orderId: number,
        siteId: number,
        requestBody: PrepareOrderTechnicalActPayload,
    ): CancelablePromise<ConnectorWriteResult_OrderTechnicalActPrepared_> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/orders/{order_id}/sites/{site_id}/technical-acts',
            path: {
                'order_id': orderId,
                'site_id': siteId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
