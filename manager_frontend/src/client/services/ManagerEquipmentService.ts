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
import type { ManagerOrderDetailResponse } from '../models/ManagerOrderDetailResponse';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class ManagerEquipmentService {
    /**
     * List Manager Equipment
     * Read the customer equipment register with customer/branch, text and attention filters;
     * archived records are excluded by default. page starts at 1 and limit is 1–100. Invalid
     * filter combinations return 400 and an inaccessible requested customer returns 404.
     * Warranty and maintenance attention are projections, not automatic service orders.
     *
     * Access and scope: Manager access is required; equipment ownership is inherited from its
     * customer in the authenticated tenant. Linked orders must also belong to the selected
     * storefront. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * See [equipment and
     * maintenance](https://github.com/mvnby/air-api/blob/main/docs/equipment-maintenance.md).
     * @param customerId
     * @param customerBranchId
     * @param page
     * @param limit
     * @param includeArchived
     * @param q
     * @param attention
     * @returns ManagerEquipmentListResponse Successful Response
     * @throws ApiError
     */
    public static listManagerEquipment(
        customerId?: (number | null),
        customerBranchId?: (number | null),
        page: number = 1,
        limit: number = 20,
        includeArchived: boolean = false,
        q?: (string | null),
        attention?: (string | null),
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
                'q': q,
                'attention': attention,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Create Manager Equipment
     * Create a customer equipment record, optional source-order association and applicable
     * warranty snapshots. Invalid customer/branch/order/product relationships or dates return
     * 400; inaccessible customer returns 404. Supplier/invoice fields are writable only by the
     * system tenant, even when explicitly submitted as null; partners receive 403. This POST
     * has no idempotency receipt and repeated calls create additional equipment.
     *
     * Access and scope: Manager access is required; equipment ownership is inherited from its
     * customer in the authenticated tenant. Linked orders must also belong to the selected
     * storefront. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * See [equipment and
     * maintenance](https://github.com/mvnby/air-api/blob/main/docs/equipment-maintenance.md).
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
     * Create missing equipment units from catalog products in the scoped order’s selected
     * proposal, optionally adding component placeholders. Existing unarchived units with the
     * same source order/product count toward the requested quantity, so ordinary repeats
     * create only missing units; archived units do not count. Missing/ineligible order or
     * incompatible input returns 400. Supplier/invoice fields are system-only (403 for partner
     * submissions). This count-based workflow has no idempotency receipt.
     *
     * Access and scope: Manager access is required; equipment ownership is inherited from its
     * customer in the authenticated tenant. Linked orders must also belong to the selected
     * storefront. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * See [equipment and
     * maintenance](https://github.com/mvnby/air-api/blob/main/docs/equipment-maintenance.md).
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
     * Create Manager Maintenance Order
     * Create a new maintenance order for equipment, copying customer/branch contact and
     * address context and linking the equipment to the order. Missing/inaccessible or archived
     * equipment returns 404; invalid creation data returns 400. This does not record completed
     * maintenance or advance its due date. There is no reuse/idempotency receipt: each
     * successful call creates another order. Order creation and subsequent equipment linking
     * use separate commits.
     *
     * Access and scope: Manager access is required; equipment ownership is inherited from its
     * customer in the authenticated tenant. Linked orders must also belong to the selected
     * storefront. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * See [equipment and
     * maintenance](https://github.com/mvnby/air-api/blob/main/docs/equipment-maintenance.md).
     * @param equipmentId
     * @returns ManagerOrderDetailResponse Successful Response
     * @throws ApiError
     */
    public static createManagerMaintenanceOrder(
        equipmentId: number,
    ): CancelablePromise<ManagerOrderDetailResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/equipment/{equipment_id}/maintenance-order',
            path: {
                'equipment_id': equipmentId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Manager Equipment
     * Read one customer equipment card with components, warranty coverages, maintenance
     * projection, linked orders and recent service history. history_limit is 0–100; component
     * supplier/invoice fields are redacted for partners. Missing or inaccessible equipment
     * returns 404; reading does not refresh stored warranty definitions or create a
     * maintenance event.
     *
     * Access and scope: Manager access is required; equipment ownership is inherited from its
     * customer in the authenticated tenant. Linked orders must also belong to the selected
     * storefront. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * See [equipment and
     * maintenance](https://github.com/mvnby/air-api/blob/main/docs/equipment-maintenance.md).
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
     * Update submitted equipment metadata, location, dates, warranty mode and independent
     * maintenance plan. Invalid references or an enabled maintenance plan without a usable
     * anchor date return 400; missing equipment returns 404. Manual warranty changes preserve
     * original coverage snapshots, and returning to auto restores those snapshots rather than
     * selecting current policy definitions. No expected-version or idempotency receipt is
     * required.
     *
     * Access and scope: Manager access is required; equipment ownership is inherited from its
     * customer in the authenticated tenant. Linked orders must also belong to the selected
     * storefront. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * See [equipment and
     * maintenance](https://github.com/mvnby/air-api/blob/main/docs/equipment-maintenance.md).
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
     * Create a component on customer equipment, optionally referencing a shared catalog
     * product and supplier. Missing equipment returns 404 and invalid references/type returns
     * 400. Partners cannot submit supplier/invoice fields, including explicit null (403). This
     * stores component metadata without creating a new catalog product; repeated POSTs can
     * create additional components.
     *
     * Access and scope: Manager access is required; equipment ownership is inherited from its
     * customer in the authenticated tenant. Linked orders must also belong to the selected
     * storefront. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
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
     * Update only submitted component fields; explicit null can clear nullable
     * product/supplier references and is_archived controls archival. Missing
     * equipment/component returns 404 and invalid references/type returns 400.
     * Supplier/invoice fields are system-only (partner submissions return 403). No
     * expected-version guard or idempotency receipt is used.
     *
     * Access and scope: Manager access is required; equipment ownership is inherited from its
     * customer in the authenticated tenant. Linked orders must also belong to the selected
     * storefront. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
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
     * Read service-history events for customer equipment with page starting at 1 and limit
     * 1–100. Missing or inaccessible equipment returns 404. Events record completed work;
     * reading them does not advance maintenance dates or generate orders.
     *
     * Access and scope: Manager access is required; equipment ownership is inherited from its
     * customer in the authenticated tenant. Linked orders must also belong to the selected
     * storefront. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * See [equipment and
     * maintenance](https://github.com/mvnby/air-api/blob/main/docs/equipment-maintenance.md).
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
     * Record a completed service event on equipment, validating any linked order against the
     * same customer/branch. Missing equipment returns 404 and invalid event/order/provider
     * data returns 400. A maintenance event updates warranty maintenance status; repairs and
     * diagnostics do not advance the independent maintenance schedule. No idempotency receipt
     * exists, so repeats create separate events.
     *
     * Access and scope: Manager access is required; equipment ownership is inherited from its
     * customer in the authenticated tenant. Linked orders must also belong to the selected
     * storefront. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * See [equipment and
     * maintenance](https://github.com/mvnby/air-api/blob/main/docs/equipment-maintenance.md).
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
     * Synchronize the equipment repair-history entry from one scoped repair order under an
     * order lock. A repeat updates the existing order-derived entry rather than adding
     * another, preserving manual overrides omitted from the payload. Missing equipment returns
     * 404; invalid repair order, association or conflicting existing history returns 400. This
     * records repair history rather than an actual maintenance event.
     *
     * Access and scope: Manager access is required; equipment ownership is inherited from its
     * customer in the authenticated tenant. Linked orders must also belong to the selected
     * storefront. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * See [equipment and
     * maintenance](https://github.com/mvnby/air-api/blob/main/docs/equipment-maintenance.md).
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
