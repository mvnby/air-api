/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class AdminDocsService {
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
}
