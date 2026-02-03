/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { Body_upload_images_admin_api_upload_images_post } from '../models/Body_upload_images_admin_api_upload_images_post';
import type { OrderStatusUpdate } from '../models/OrderStatusUpdate';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class AdminService {
    /**
     * Get Dashboard Stats
     * Dashboard stats endpoint - uses session-based auth (called from admin panel AJAX).
     * @returns any Successful Response
     * @throws ApiError
     */
    public static getDashboardStatsAdminStatsGet(): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/admin/stats',
        });
    }
    /**
     * Import Process
     * @returns any Successful Response
     * @throws ApiError
     */
    public static importProcessAdminImportOnlinerPost(): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/admin/import_onliner',
        });
    }
    /**
     * Update Sync Mode
     * @returns any Successful Response
     * @throws ApiError
     */
    public static updateSyncModeAdminUpdateSyncModePost(): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/admin/update_sync_mode',
        });
    }
    /**
     * Generate Document
     * Универсальный роут для генерации документов.
     * doc_type: contract | offer | invoice | act | tn2 | ttn1
     * Возвращает ссылку на редактирование в Google Docs.
     * @param docType
     * @param orderId
     * @returns any Successful Response
     * @throws ApiError
     */
    public static generateDocumentAdminDocsGenerateDocTypeOrderIdGet(
        docType: string,
        orderId: number,
    ): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/admin/docs/generate/{doc_type}/{order_id}',
            path: {
                'doc_type': docType,
                'order_id': orderId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Download Document Pdf
     * Скачивает документ в формате PDF из Google Drive.
     * @param docId
     * @returns any Successful Response
     * @throws ApiError
     */
    public static downloadDocumentPdfAdminDocsDownloadDocIdGet(
        docId: number,
    ): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/admin/docs/download/{doc_id}',
            path: {
                'doc_id': docId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Delete Document
     * Удаляет документ из БД и перемещает файл в корзину Google Drive.
     * @param docId
     * @returns any Successful Response
     * @throws ApiError
     */
    public static deleteDocumentAdminDocsDeleteDocIdGet(
        docId: number,
    ): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/admin/docs/delete/{doc_id}',
            path: {
                'doc_id': docId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
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
    /**
     * Search Installers
     * Search installers for Select2.
     * @param q
     * @returns any Successful Response
     * @throws ApiError
     */
    public static searchInstallersAdminApiAdminInstallersSearchGet(
        q: string = '',
    ): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/admin/api/admin/installers/search',
            query: {
                'q': q,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Calendar Events
     * Get events for FullCalendar (Orders with Installation or Assessment dates).
     * @param start
     * @param end
     * @returns any Successful Response
     * @throws ApiError
     */
    public static getCalendarEventsAdminCalendarEventsGet(
        start?: (string | null),
        end?: (string | null),
    ): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/admin/calendar/events',
            query: {
                'start': start,
                'end': end,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Upload Images
     * Bulk upload images for articles/products.
     * Returns list of web-accessible URLs.
     * @param formData
     * @returns any Successful Response
     * @throws ApiError
     */
    public static uploadImagesAdminApiUploadImagesPost(
        formData: Body_upload_images_admin_api_upload_images_post,
    ): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/admin/api/upload_images',
            formData: formData,
            mediaType: 'multipart/form-data',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * List Article Images
     * List all images associated with an article slug.
     * @param slug
     * @returns any Successful Response
     * @throws ApiError
     */
    public static listArticleImagesAdminApiArticleImagesSlugGet(
        slug: string,
    ): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/admin/api/article_images/{slug}',
            path: {
                'slug': slug,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
