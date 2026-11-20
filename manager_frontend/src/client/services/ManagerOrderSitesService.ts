/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ConnectorWriteResult_OrderSiteEquipmentLinkResult_ } from '../models/ConnectorWriteResult_OrderSiteEquipmentLinkResult_';
import type { ConnectorWriteResult_OrderSiteItem_ } from '../models/ConnectorWriteResult_OrderSiteItem_';
import type { OrderSiteAddRequest } from '../models/OrderSiteAddRequest';
import type { OrderSiteEquipmentLinkRequest } from '../models/OrderSiteEquipmentLinkRequest';
import type { OrderSiteEquipmentList } from '../models/OrderSiteEquipmentList';
import type { OrderSiteList } from '../models/OrderSiteList';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class ManagerOrderSitesService {
    /**
     * Manager List Order Sites
     * List saved sites and the legacy primary address of an accessible order.
     * @param orderId
     * @param limit
     * @param offset
     * @returns OrderSiteList Successful Response
     * @throws ApiError
     */
    public static managerListOrderSites(
        orderId: number,
        limit: number = 100,
        offset?: number,
    ): CancelablePromise<OrderSiteList> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/orders/{order_id}/sites',
            path: {
                'order_id': orderId,
            },
            query: {
                'limit': limit,
                'offset': offset,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Manager Add Order Site
     * Add a site from the order customer's branch or from an order-specific address.
     * @param orderId
     * @param requestBody
     * @returns ConnectorWriteResult_OrderSiteItem_ Successful Response
     * @throws ApiError
     */
    public static managerAddOrderSite(
        orderId: number,
        requestBody: OrderSiteAddRequest,
    ): CancelablePromise<ConnectorWriteResult_OrderSiteItem_> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/orders/{order_id}/sites',
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
     * Manager List Order Site Equipment
     * List equipment explicitly assigned to the site's order and its active components.
     * @param orderId
     * @param siteId
     * @param limit
     * @param offset
     * @returns OrderSiteEquipmentList Successful Response
     * @throws ApiError
     */
    public static managerListOrderSiteEquipment(
        orderId: number,
        siteId: number,
        limit: number = 100,
        offset?: number,
    ): CancelablePromise<OrderSiteEquipmentList> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/orders/{order_id}/sites/{site_id}/equipment',
            path: {
                'order_id': orderId,
                'site_id': siteId,
            },
            query: {
                'limit': limit,
                'offset': offset,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Manager Link Order Site Equipment
     * Link an existing unit or create it atomically with its site assignment and components.
     * @param orderId
     * @param siteId
     * @param requestBody
     * @returns ConnectorWriteResult_OrderSiteEquipmentLinkResult_ Successful Response
     * @throws ApiError
     */
    public static managerLinkOrderSiteEquipment(
        orderId: number,
        siteId: number,
        requestBody: OrderSiteEquipmentLinkRequest,
    ): CancelablePromise<ConnectorWriteResult_OrderSiteEquipmentLinkResult_> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/orders/{order_id}/sites/{site_id}/equipment',
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
