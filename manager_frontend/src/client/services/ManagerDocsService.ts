/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { Body_attach_manager_doc_file } from '../models/Body_attach_manager_doc_file';
import type { Body_register_manager_external_contract } from '../models/Body_register_manager_external_contract';
import type { Body_upload_manager_order_document } from '../models/Body_upload_manager_order_document';
import type { DocumentTemplateFileListResponse } from '../models/DocumentTemplateFileListResponse';
import type { DocumentTemplateItem } from '../models/DocumentTemplateItem';
import type { DocumentTemplateListResponse } from '../models/DocumentTemplateListResponse';
import type { DocumentTemplatePayload } from '../models/DocumentTemplatePayload';
import type { DocumentTemplateUpdatePayload } from '../models/DocumentTemplateUpdatePayload';
import type { ManagerActionMessageResponse } from '../models/ManagerActionMessageResponse';
import type { ManagerOrderDocumentItem } from '../models/ManagerOrderDocumentItem';
import type { ManagerOrderDocumentListResponse } from '../models/ManagerOrderDocumentListResponse';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class ManagerDocsService {
    /**
     * Get Manager Order Documents
     * List legacy-compatible document metadata for an order in the current Manager
     * tenant/storefront, including basis, scope snapshots and private external file history.
     * Filter by semantic type, site or equipment and optionally include native documents.
     * Missing order returns 404. Native artifacts/lifecycle use document-system endpoints.
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * @param orderId
     * @param includeNative
     * @param documentType
     * @param siteId
     * @param equipmentId
     * @param limit
     * @returns ManagerOrderDocumentListResponse Successful Response
     * @throws ApiError
     */
    public static getManagerOrderDocuments(
        orderId: number,
        includeNative: boolean = false,
        documentType?: (string | null),
        siteId?: (number | null),
        equipmentId?: (number | null),
        limit?: (number | null),
    ): CancelablePromise<ManagerOrderDocumentListResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/orders/{order_id}/documents',
            path: {
                'order_id': orderId,
            },
            query: {
                'include_native': includeNative,
                'document_type': documentType,
                'site_id': siteId,
                'equipment_id': equipmentId,
                'limit': limit,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Upload Manager Order Document
     * Upload a DOC, DOCX or PDF to an accessible order in the current tenant/storefront.
     * Provide document_type, number, document_date and Idempotency-Key for typed private
     * evidence with immutable versions. An optional site/equipment must belong to the order.
     * Typed and legacy uploads return 409 on closed orders. The existing file-only request
     * retains legacy provider behavior and should be reconciled before retrying.
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * @param orderId
     * @param formData
     * @param idempotencyKey
     * @returns ManagerOrderDocumentItem Successful Response
     * @throws ApiError
     */
    public static uploadManagerOrderDocument(
        orderId: number,
        formData: Body_upload_manager_order_document,
        idempotencyKey?: (string | null),
    ): CancelablePromise<ManagerOrderDocumentItem> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/orders/{order_id}/documents/upload',
            path: {
                'order_id': orderId,
            },
            headers: {
                'Idempotency-Key': idempotencyKey,
            },
            formData: formData,
            mediaType: 'multipart/form-data',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Register Manager External Contract
     * Register an external contract’s number/date and optional original for a scoped order.
     * Supply Idempotency-Key and optionally external_status to record typed private evidence.
     * Typed registration accepts DOC, DOCX and PDF and never fetches a URL or replaces the
     * order’s selected framework agreement. Legacy optional reference URLs/files remain
     * compatible. Closed orders return 409.
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * @param orderId
     * @param formData
     * @param idempotencyKey
     * @returns ManagerOrderDocumentItem Successful Response
     * @throws ApiError
     */
    public static registerManagerExternalContract(
        orderId: number,
        formData: Body_register_manager_external_contract,
        idempotencyKey?: (string | null),
    ): CancelablePromise<ManagerOrderDocumentItem> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/orders/{order_id}/documents/external-contract',
            path: {
                'order_id': orderId,
            },
            headers: {
                'Idempotency-Key': idempotencyKey,
            },
            formData: formData,
            mediaType: 'multipart/form-data',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Attach Manager Doc File
     * Append a private file to an accessible document using file_role, expected_version and
     * Idempotency-Key. Signed PDF copies may be attached to eligible closed/issued documents
     * without changing the issued record. A stale version returns 409. A file-only request
     * retains legacy provider behavior for mutable legacy documents.
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * @param docId
     * @param formData
     * @param idempotencyKey
     * @returns ManagerOrderDocumentItem Successful Response
     * @throws ApiError
     */
    public static attachManagerDocFile(
        docId: number,
        formData: Body_attach_manager_doc_file,
        idempotencyKey?: (string | null),
    ): CancelablePromise<ManagerOrderDocumentItem> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/docs/{doc_id}/file',
            path: {
                'doc_id': docId,
            },
            headers: {
                'Idempotency-Key': idempotencyKey,
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
     * Download a document’s stored original, explicitly selected private file_version, or
     * legacy provider file under current tenant/storefront access. For a private PDF,
     * preview=true returns the requested preview_page as a raster PNG without exposing
     * the original PDF in an inline response. Missing document or file returns 404.
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * @param docId
     * @param fileVersion
     * @param preview
     * @param previewPage
     * @returns any Successful Response
     * @throws ApiError
     */
    public static getManagerDocDownload(
        docId: number,
        fileVersion?: (number | null),
        preview: boolean = false,
        previewPage: number = 1,
    ): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/docs/{doc_id}/download',
            path: {
                'doc_id': docId,
            },
            query: {
                'file_version': fileVersion,
                'preview': preview,
                'preview_page': previewPage,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Delete Manager Doc
     * Delete an accessible legacy document record and attempt provider file cleanup. Current
     * tenant/storefront Manager access is required. Closed order, dependent documents or a
     * native-managed lifecycle record returns 409; missing document returns 404. Provider
     * cleanup failure does not imply the database record survived. A repeated delete is not
     * receipt replay.
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
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
     * List Manager Document Templates
     * List the shared managed legacy Google template directory, excluding implicit legacy
     * templates and optionally filtering by document type. Requires system-tenant Manager
     * access; this is not the tenant-owned native template registry.
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * @param docType
     * @returns DocumentTemplateListResponse Successful Response
     * @throws ApiError
     */
    public static listManagerDocumentTemplates(
        docType?: (string | null),
    ): CancelablePromise<DocumentTemplateListResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/docs/document-templates',
            query: {
                'doc_type': docType,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Create Manager Document Template
     * Create a shared legacy Google template definition from a Drive file reference and
     * supplied restrictions/basis links. Requires system-tenant Manager access. Invalid
     * configuration returns 400; this does not upload a native DOCX version. No caller
     * idempotency receipt is provided.
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * @param requestBody
     * @returns DocumentTemplateItem Successful Response
     * @throws ApiError
     */
    public static createManagerDocumentTemplate(
        requestBody: DocumentTemplatePayload,
    ): CancelablePromise<DocumentTemplateItem> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/docs/document-templates',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * List Manager Document Template Files
     * Read candidate files from the configured/shared Google Drive template folder. Requires
     * system-tenant Manager access. This existing endpoint accepts limit 1–200, default 100;
     * credentials/provider listing failure returns 502. Listing does not create a template
     * definition or copy files.
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * @param folderId
     * @param limit
     * @returns DocumentTemplateFileListResponse Successful Response
     * @throws ApiError
     */
    public static listManagerDocumentTemplateFiles(
        folderId: string = '1SClclCJS2FUVtfF-vbVqN8zI77Sl_E9t',
        limit: number = 100,
    ): CancelablePromise<DocumentTemplateFileListResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/docs/document-template-files',
            query: {
                'folder_id': folderId,
                'limit': limit,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Patch Manager Document Template
     * Patch supplied fields of a shared legacy Google template definition. Requires
     * system-tenant Manager access. Invalid or missing template configuration returns 400;
     * existing generated document files are not regenerated by this metadata update.
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * @param templateId
     * @param requestBody
     * @returns DocumentTemplateItem Successful Response
     * @throws ApiError
     */
    public static patchManagerDocumentTemplate(
        templateId: number,
        requestBody: DocumentTemplateUpdatePayload,
    ): CancelablePromise<DocumentTemplateItem> {
        return __request(OpenAPI, {
            method: 'PATCH',
            url: '/api/manager/docs/document-templates/{template_id}',
            path: {
                'template_id': templateId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Delete Manager Document Template
     * Delete a shared legacy template definition after service dependency validation. Requires
     * system-tenant Manager access. A missing definition or service refusal is returned as
     * 404; repeating deletion is not an idempotent receipt.
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * @param templateId
     * @returns ManagerActionMessageResponse Successful Response
     * @throws ApiError
     */
    public static deleteManagerDocumentTemplate(
        templateId: number,
    ): CancelablePromise<ManagerActionMessageResponse> {
        return __request(OpenAPI, {
            method: 'DELETE',
            url: '/api/manager/docs/document-templates/{template_id}',
            path: {
                'template_id': templateId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Doc Templates
     * Resolve available legacy templates for a document kind and optional order/customer
     * context. Manager access and scoped entity checks are required; partner tenants must
     * supply order or customer context (403 otherwise). Missing/inaccessible context returns
     * 404. Partner responses restrict exposed customer IDs to the selected customer; this does
     * not grant access to shared template administration.
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * @param docType
     * @param orderId
     * @param customerId
     * @returns DocumentTemplateListResponse Successful Response
     * @throws ApiError
     */
    public static getDocTemplates(
        docType: string,
        orderId?: (number | null),
        customerId?: (number | null),
    ): CancelablePromise<DocumentTemplateListResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/docs/templates/{doc_type}',
            path: {
                'doc_type': docType,
            },
            query: {
                'order_id': orderId,
                'customer_id': customerId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
