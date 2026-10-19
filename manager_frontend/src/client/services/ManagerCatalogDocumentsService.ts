/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { Body_upload_manager_catalog_document } from '../models/Body_upload_manager_catalog_document';
import type { CatalogDocumentsReplacePayload } from '../models/CatalogDocumentsReplacePayload';
import type { CatalogDocumentUploadResponse } from '../models/CatalogDocumentUploadResponse';
import type { CatalogDocumentWorkspace } from '../models/CatalogDocumentWorkspace';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class ManagerCatalogDocumentsService {
    /**
     * Get Manager Catalog Documents
     * Read own, inherited and effective shared catalog reference documents.
     *
     * Requires platform-owner or delegated catalog.master.edit permission. Internal research sources are included;
     * these are not order documents. Inherited documents preserve their original brand
     * or series owner and are edited there. Missing target returns 404. No content is
     * fetched from external URLs. Effective references deduplicate identical canonical
     * URLs, preferring the product, then series, then brand; separate URLs are retained.
     * @param targetType
     * @param targetId
     * @returns CatalogDocumentWorkspace Successful Response
     * @throws ApiError
     */
    public static getManagerCatalogDocuments(
        targetType: 'brand' | 'series' | 'product',
        targetId: number,
    ): CancelablePromise<CatalogDocumentWorkspace> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/catalog-documents/{target_type}/{target_id}',
            path: {
                'target_type': targetType,
                'target_id': targetId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Replace Manager Catalog Documents
     * Replace up to 100 own technical/reference documents in the shared catalog.
     *
     * Requires platform-owner or delegated catalog.master.edit permission. An empty set
     * removes only the target's own references; inherited files remain attached to their
     * owner. References default to public and inherited; set visibility=internal for
     * staff/AI research and inherit_to_products=false for owner-only materials. Missing
     * target returns 404; duplicate URLs return 400. Metadata and catalog invalidation
     * commit together; an unchanged ordered set does not bump the catalog revision.
     * No external URLs are fetched and no stored files are physically deleted.
     * @param targetType
     * @param targetId
     * @param requestBody
     * @returns CatalogDocumentWorkspace Successful Response
     * @throws ApiError
     */
    public static replaceManagerCatalogDocuments(
        targetType: 'brand' | 'series' | 'product',
        targetId: number,
        requestBody: CatalogDocumentsReplacePayload,
    ): CancelablePromise<CatalogDocumentWorkspace> {
        return __request(OpenAPI, {
            method: 'PUT',
            url: '/api/manager/catalog-documents/{target_type}/{target_id}',
            path: {
                'target_type': targetType,
                'target_id': targetId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Upload Manager Catalog Document
     * Upload a public PDF/DOCX (up to 25 MiB) and return its immutable material URL.
     *
     * Requires platform-owner or delegated catalog.master.edit permission. Missing target
     * returns 404; invalid type/content returns 400, oversized input 413. Uses the existing
     * public media store under a dedicated catalog-documents namespace, separate from
     * business documents. The returned URL is attached by the subsequent whole-set PUT;
     * upload alone does not change the catalog. Upload only materials approved for public
     * hosting; private research documents must be attached as links to their source.
     * @param targetType
     * @param targetId
     * @param formData
     * @returns CatalogDocumentUploadResponse Successful Response
     * @throws ApiError
     */
    public static uploadManagerCatalogDocument(
        targetType: 'brand' | 'series' | 'product',
        targetId: number,
        formData: Body_upload_manager_catalog_document,
    ): CancelablePromise<CatalogDocumentUploadResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/catalog-documents/{target_type}/{target_id}/upload',
            path: {
                'target_type': targetType,
                'target_id': targetId,
            },
            formData: formData,
            mediaType: 'multipart/form-data',
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
