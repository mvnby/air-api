/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { Body_upload_manager_maintenance_observation_photo } from '../models/Body_upload_manager_maintenance_observation_photo';
import type { CreateMaintenanceObservation } from '../models/CreateMaintenanceObservation';
import type { MaintenanceDefectActItem } from '../models/MaintenanceDefectActItem';
import type { MaintenanceDefectActList } from '../models/MaintenanceDefectActList';
import type { MaintenanceObservationDetail } from '../models/MaintenanceObservationDetail';
import type { MaintenanceObservationList } from '../models/MaintenanceObservationList';
import type { MaintenanceOfferCommand } from '../models/MaintenanceOfferCommand';
import type { MaintenanceOfferItem } from '../models/MaintenanceOfferItem';
import type { MaintenanceOfferList } from '../models/MaintenanceOfferList';
import type { MaintenanceWorkspaceItem } from '../models/MaintenanceWorkspaceItem';
import type { ManagerServiceAttachmentItemResponse } from '../models/ManagerServiceAttachmentItemResponse';
import type { PrepareMaintenanceDefectAct } from '../models/PrepareMaintenanceDefectAct';
import type { PrepareMaintenanceOffer } from '../models/PrepareMaintenanceOffer';
import type { ResolveMaintenanceObservation } from '../models/ResolveMaintenanceObservation';
import type { UpdateMaintenanceObservation } from '../models/UpdateMaintenanceObservation';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class ManagerMaintenanceObservationsService {
    /**
     * List Order Observations
     * List separate findings from this source order, newest first. Manager role and source
     * tenant/storefront plus saved customer ownership are required; inaccessible order returns
     * 404. limit is 1–100 with offset pagination. Reading changes no service or document state.
     * See [maintenance findings](https://github.com/mvnby/air-api/blob/main/docs/equipment-maintenance.md).
     * @param orderId
     * @param limit
     * @param offset
     * @returns MaintenanceObservationList Successful Response
     * @throws ApiError
     */
    public static listManagerOrderMaintenanceObservations(
        orderId: number,
        limit: number = 50,
        offset?: number,
    ): CancelablePromise<MaintenanceObservationList> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/orders/{order_id}/maintenance-observations',
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
     * Create Observation
     * Save one factual observation from an open or CLOSED maintenance order. The server
     * records author, origin, immutable comment and customer/object context. Equipment is
     * optional and must match that context. Manager role and tenant/storefront ownership are
     * required. Same command_key and content return the existing ID; key reuse with different
     * content returns 409, invalid context 400, inaccessible order 404. No order, document,
     * executed service event or commercial decision is created or changed.
     * See [maintenance findings](https://github.com/mvnby/air-api/blob/main/docs/equipment-maintenance.md).
     * @param orderId
     * @param requestBody
     * @returns MaintenanceObservationDetail Successful Response
     * @throws ApiError
     */
    public static createManagerMaintenanceObservation(
        orderId: number,
        requestBody: CreateMaintenanceObservation,
    ): CancelablePromise<MaintenanceObservationDetail> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/orders/{order_id}/maintenance-observations',
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
     * List Equipment Observations
     * List findings currently associated with equipment. Manager role, customer tenant and
     * each source order's storefront are checked; inaccessible equipment returns 404.
     * limit is 1–100 with offset pagination. Unknown equipment findings remain on the source ТО.
     * See [maintenance findings](https://github.com/mvnby/air-api/blob/main/docs/equipment-maintenance.md).
     * @param equipmentId
     * @param limit
     * @param offset
     * @returns MaintenanceObservationList Successful Response
     * @throws ApiError
     */
    public static listManagerEquipmentMaintenanceObservations(
        equipmentId: number,
        limit: number = 50,
        offset?: number,
    ): CancelablePromise<MaintenanceObservationList> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/equipment/{equipment_id}/maintenance-observations',
            path: {
                'equipment_id': equipmentId,
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
     * Get Observation
     * Read original provenance, current facts, revision history and photo metadata. Manager
     * role, source order tenant/storefront and saved customer ownership are required;
     * inaccessible finding returns 404. Photo bytes use existing short-lived attachment access.
     * See [private attachments](https://github.com/mvnby/air-api/blob/main/docs/service-attachments.md).
     * @param observationId
     * @returns MaintenanceObservationDetail Successful Response
     * @throws ApiError
     */
    public static getManagerMaintenanceObservation(
        observationId: number,
    ): CancelablePromise<MaintenanceObservationDetail> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/maintenance-observations/{observation_id}',
            path: {
                'observation_id': observationId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Update Observation
     * Correct facts, recommendation or equipment with expected_version. Manager role,
     * source order tenant/storefront and saved customer context are required. Stale versions
     * return 409; invalid equipment 400; inaccessible finding 404. A new audited revision is
     * saved; original comment, origin, order and issued documents remain unchanged, also on CLOSED ТО.
     * See [maintenance findings](https://github.com/mvnby/air-api/blob/main/docs/equipment-maintenance.md).
     * @param observationId
     * @param requestBody
     * @returns MaintenanceObservationDetail Successful Response
     * @throws ApiError
     */
    public static updateManagerMaintenanceObservation(
        observationId: number,
        requestBody: UpdateMaintenanceObservation,
    ): CancelablePromise<MaintenanceObservationDetail> {
        return __request(OpenAPI, {
            method: 'PATCH',
            url: '/api/manager/maintenance-observations/{observation_id}',
            path: {
                'observation_id': observationId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Upload Photo
     * Upload a private photo attached to exactly this observation. Manager role and source
     * tenant/storefront plus customer access are required, including CLOSED ТО. Same key and
     * file return the same attachment; different file with that key returns 409. Invalid file
     * type/size returns 400, inaccessible observation 404. Existing private storage, previews
     * and attachment access are reused; no public URL or service event is created.
     * See [private attachments](https://github.com/mvnby/air-api/blob/main/docs/service-attachments.md).
     * @param observationId
     * @param formData
     * @returns ManagerServiceAttachmentItemResponse Successful Response
     * @throws ApiError
     */
    public static uploadManagerMaintenanceObservationPhoto(
        observationId: number,
        formData: Body_upload_manager_maintenance_observation_photo,
    ): CancelablePromise<ManagerServiceAttachmentItemResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/maintenance-observations/{observation_id}/photos',
            path: {
                'observation_id': observationId,
            },
            formData: formData,
            mediaType: 'multipart/form-data',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Prepare Defect Act
     * Explicitly prepare a native defect-act draft from current versions of selected
     * findings on one open or CLOSED ТО. Manager and tenant/storefront/customer/object
     * ownership are required. Same command key/content returns the same document;
     * different content or stale versions return 409, mixed context/missing requisites 400,
     * inaccessible source/issuer 404. Creates/reuses a linked NEGOTIATION continuation,
     * never executable work, scheduling, a contract or customer delivery. Snapshot sources
     * are immutable; preview, issue and delivery use the existing document lifecycle.
     * See [maintenance acts](https://github.com/mvnby/air-api/blob/main/docs/equipment-maintenance.md).
     * @param orderId
     * @param requestBody
     * @returns MaintenanceDefectActItem Successful Response
     * @throws ApiError
     */
    public static prepareManagerMaintenanceDefectAct(
        orderId: number,
        requestBody: PrepareMaintenanceDefectAct,
    ): CancelablePromise<MaintenanceDefectActItem> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/orders/{order_id}/maintenance-defect-acts',
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
     * List Defect Acts
     * List defect-act preparations linked to a scoped source ТО, including CLOSED history.
     * Requires Manager tenant/storefront access to the source and continuation. Missing or
     * inaccessible context returns 404. limit is 1–100 with offset pagination. Reading does
     * not prepare, issue, send or update documents or observations.
     * See [maintenance acts](https://github.com/mvnby/air-api/blob/main/docs/equipment-maintenance.md).
     * @param orderId
     * @param limit
     * @param offset
     * @returns MaintenanceDefectActList Successful Response
     * @throws ApiError
     */
    public static listManagerMaintenanceDefectActs(
        orderId: number,
        limit: number = 50,
        offset?: number,
    ): CancelablePromise<MaintenanceDefectActList> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/orders/{order_id}/maintenance-defect-acts',
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
     * Maintenance Workspace
     * Explicitly create/reuse the same scoped repair card. No execution, crew, slot or document is assigned.
     * Idempotent by source order; inaccessible source is 404, incompatible context 400/409.
     * See [maintenance workflow](https://github.com/mvnby/air-api/blob/main/docs/equipment-maintenance.md).
     * @param orderId
     * @returns MaintenanceWorkspaceItem Successful Response
     * @throws ApiError
     */
    public static prepareManagerMaintenanceWorkspace(
        orderId: number,
    ): CancelablePromise<MaintenanceWorkspaceItem> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/orders/{order_id}/maintenance-workspace',
            path: {
                'order_id': orderId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Maintenance Offers
     * Read scoped immutable commercial versions, decisions and resolutions. Pagination limit 1–100.
     * No lifecycle mutation; inaccessible source/continuation returns 404.
     * See [maintenance workflow](https://github.com/mvnby/air-api/blob/main/docs/equipment-maintenance.md).
     * @param orderId
     * @param limit
     * @param offset
     * @returns MaintenanceOfferList Successful Response
     * @throws ApiError
     */
    public static listManagerMaintenanceOffers(
        orderId: number,
        limit: number = 50,
        offset?: number,
    ): CancelablePromise<MaintenanceOfferList> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/orders/{order_id}/maintenance-offers',
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
     * Prepare Offer
     * Freeze real ordinary proposal lines and selected finding revisions in a draft. Manager scope required.
     * Same command key/content replays, different content or stale revision returns 409. Mixed context returns 400.
     * No issue, send, consent, execution or resolution is implicit.
     * See [maintenance workflow](https://github.com/mvnby/air-api/blob/main/docs/equipment-maintenance.md).
     * @param orderId
     * @param requestBody
     * @returns MaintenanceOfferItem Successful Response
     * @throws ApiError
     */
    public static prepareManagerMaintenanceOffer(
        orderId: number,
        requestBody: PrepareMaintenanceOffer,
    ): CancelablePromise<MaintenanceOfferItem> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/orders/{order_id}/maintenance-offers',
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
     * Offer Command
     * Explicit audited issue/send/answer/continue, with command key and expected version. Send records actual
     * delivery evidence; it does not contact a customer. Continue uses only the approved subset on the same repair card.
     * Manager tenant/storefront required; inaccessible context 404, stale/conflicting version 409, invalid subset 400.
     * See [maintenance workflow](https://github.com/mvnby/air-api/blob/main/docs/equipment-maintenance.md).
     * @param orderId
     * @param offerId
     * @param requestBody
     * @returns MaintenanceOfferItem Successful Response
     * @throws ApiError
     */
    public static commandManagerMaintenanceOffer(
        orderId: number,
        offerId: number,
        requestBody: MaintenanceOfferCommand,
    ): CancelablePromise<MaintenanceOfferItem> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/orders/{order_id}/maintenance-offers/{offer_id}/commands',
            path: {
                'order_id': orderId,
                'offer_id': offerId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Resolve Observation
     * Explicit confirmation of actual repair with actor/time/evidence, separate from commercial consent.
     * Writes equipment REPAIR history when equipment is known. Scoped manager access required, 404 inaccessible,
     * 409 stale/conflicting/unauthorized work; identical command is replay-safe.
     * See [maintenance workflow](https://github.com/mvnby/air-api/blob/main/docs/equipment-maintenance.md).
     * @param observationId
     * @param requestBody
     * @returns any Successful Response
     * @throws ApiError
     */
    public static resolveManagerMaintenanceObservation(
        observationId: number,
        requestBody: ResolveMaintenanceObservation,
    ): CancelablePromise<Record<string, any>> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/maintenance-observations/{observation_id}/resolution',
            path: {
                'observation_id': observationId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Customer Observations
     * List scoped findings including unknown equipment at a customer/object. Manager ownership required;
     * inaccessible customer returns 404. Optional branch filter and limit 1–100, offset pagination.
     * See [maintenance workflow](https://github.com/mvnby/air-api/blob/main/docs/equipment-maintenance.md).
     * @param customerId
     * @param branchId
     * @param limit
     * @param offset
     * @returns MaintenanceObservationList Successful Response
     * @throws ApiError
     */
    public static listManagerCustomerMaintenanceObservations(
        customerId: number,
        branchId?: (number | null),
        limit: number = 50,
        offset?: number,
    ): CancelablePromise<MaintenanceObservationList> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/customers/{customer_id}/maintenance-observations',
            path: {
                'customer_id': customerId,
            },
            query: {
                'branch_id': branchId,
                'limit': limit,
                'offset': offset,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
