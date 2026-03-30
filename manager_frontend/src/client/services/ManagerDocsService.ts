/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { Body_upload_manager_order_document } from '../models/Body_upload_manager_order_document';
import type { DocumentTemplateListResponse } from '../models/DocumentTemplateListResponse';
import type { ManagerActionMessageResponse } from '../models/ManagerActionMessageResponse';
import type { ManagerOrderDocumentItem } from '../models/ManagerOrderDocumentItem';
import type { ManagerOrderDocumentListResponse } from '../models/ManagerOrderDocumentListResponse';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class ManagerDocsService {
    /**
     * Get Manager Order Documents
     * @param orderId
     * @returns ManagerOrderDocumentListResponse Successful Response
     * @throws ApiError
     */
    public static getManagerOrderDocuments(
        orderId: number,
    ): CancelablePromise<ManagerOrderDocumentListResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/orders/{order_id}/documents',
            path: {
                'order_id': orderId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Upload Manager Order Document
     * @param orderId
     * @param formData
     * @returns ManagerOrderDocumentItem Successful Response
     * @throws ApiError
     */
    public static uploadManagerOrderDocument(
        orderId: number,
        formData: Body_upload_manager_order_document,
    ): CancelablePromise<ManagerOrderDocumentItem> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/orders/{order_id}/documents/upload',
            path: {
                'order_id': orderId,
            },
            formData: formData,
            mediaType: 'multipart/form-data',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Manager Doc Download
     * @param docId
     * @returns any Successful Response
     * @throws ApiError
     */
    public static getManagerDocDownload(
        docId: number,
    ): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/docs/{doc_id}/download',
            path: {
                'doc_id': docId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Delete Manager Doc
     * @param docId
     * @returns ManagerActionMessageResponse Successful Response
     * @throws ApiError
     */
    public static deleteManagerDoc(
        docId: number,
    ): CancelablePromise<ManagerActionMessageResponse> {
        return __request(OpenAPI, {
            method: 'DELETE',
            url: '/api/manager/docs/{doc_id}',
            path: {
                'doc_id': docId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Doc Templates
     * @param docType
     * @returns DocumentTemplateListResponse Successful Response
     * @throws ApiError
     */
    public static getDocTemplates(
        docType: string,
    ): CancelablePromise<DocumentTemplateListResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/docs/templates/{doc_type}',
            path: {
                'doc_type': docType,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
