/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { Body_upload_manager_maintenance_observation_photo } from '../models/Body_upload_manager_maintenance_observation_photo';
import type { CreateMaintenanceObservation } from '../models/CreateMaintenanceObservation';
import type { MaintenanceObservationDetail } from '../models/MaintenanceObservationDetail';
import type { MaintenanceObservationList } from '../models/MaintenanceObservationList';
import type { ManagerServiceAttachmentItemResponse } from '../models/ManagerServiceAttachmentItemResponse';
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
}
