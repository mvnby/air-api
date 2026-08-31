/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { Body_upload_manager_native_template_version } from '../models/Body_upload_manager_native_template_version';
import type { DocumentLegalEntityCreatePayload } from '../models/DocumentLegalEntityCreatePayload';
import type { DocumentLegalEntityItem } from '../models/DocumentLegalEntityItem';
import type { DocumentLegalEntityListResponse } from '../models/DocumentLegalEntityListResponse';
import type { DocumentLegalEntityUpdatePayload } from '../models/DocumentLegalEntityUpdatePayload';
import type { DocumentNumberPolicyItem } from '../models/DocumentNumberPolicyItem';
import type { DocumentNumberPolicyListResponse } from '../models/DocumentNumberPolicyListResponse';
import type { DocumentNumberPolicyPayload } from '../models/DocumentNumberPolicyPayload';
import type { DocumentPdfRuntimeStatus } from '../models/DocumentPdfRuntimeStatus';
import type { ManagedDocumentArtifactAccessResponse } from '../models/ManagedDocumentArtifactAccessResponse';
import type { ManagedDocumentArtifactListResponse } from '../models/ManagedDocumentArtifactListResponse';
import type { ManagedDocumentDraftPayload } from '../models/ManagedDocumentDraftPayload';
import type { ManagedDocumentItem } from '../models/ManagedDocumentItem';
import type { ManagedDocumentListResponse } from '../models/ManagedDocumentListResponse';
import type { ManagedDocumentVoidPayload } from '../models/ManagedDocumentVoidPayload';
import type { NativeDocumentTemplateCreatePayload } from '../models/NativeDocumentTemplateCreatePayload';
import type { NativeDocumentTemplateItem } from '../models/NativeDocumentTemplateItem';
import type { NativeDocumentTemplateListResponse } from '../models/NativeDocumentTemplateListResponse';
import type { NativePlaceholderCatalogResponse } from '../models/NativePlaceholderCatalogResponse';
import type { NativeTemplateVersionItem } from '../models/NativeTemplateVersionItem';
import type { NativeTemplateVersionListResponse } from '../models/NativeTemplateVersionListResponse';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class ManagerDocumentSystemService {
    /**
     * List Document Legal Entities
     * @returns DocumentLegalEntityListResponse Successful Response
     * @throws ApiError
     */
    public static listManagerDocumentLegalEntities(): CancelablePromise<DocumentLegalEntityListResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/document-system/legal-entities',
        });
    }
    /**
     * Create Document Legal Entity
     * @param requestBody
     * @returns DocumentLegalEntityItem Successful Response
     * @throws ApiError
     */
    public static createManagerDocumentLegalEntity(
        requestBody: DocumentLegalEntityCreatePayload,
    ): CancelablePromise<DocumentLegalEntityItem> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/document-system/legal-entities',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Patch Document Legal Entity
     * @param legalEntityId
     * @param requestBody
     * @returns DocumentLegalEntityItem Successful Response
     * @throws ApiError
     */
    public static patchManagerDocumentLegalEntity(
        legalEntityId: number,
        requestBody: DocumentLegalEntityUpdatePayload,
    ): CancelablePromise<DocumentLegalEntityItem> {
        return __request(OpenAPI, {
            method: 'PATCH',
            url: '/api/manager/document-system/legal-entities/{legal_entity_id}',
            path: {
                'legal_entity_id': legalEntityId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * List Document Number Policies
     * @param legalEntityId
     * @returns DocumentNumberPolicyListResponse Successful Response
     * @throws ApiError
     */
    public static listManagerDocumentNumberPolicies(
        legalEntityId: number,
    ): CancelablePromise<DocumentNumberPolicyListResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/document-system/legal-entities/{legal_entity_id}/number-policies',
            path: {
                'legal_entity_id': legalEntityId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Upsert Document Number Policy
     * @param legalEntityId
     * @param documentType
     * @param requestBody
     * @returns DocumentNumberPolicyItem Successful Response
     * @throws ApiError
     */
    public static upsertManagerDocumentNumberPolicy(
        legalEntityId: number,
        documentType: string,
        requestBody: DocumentNumberPolicyPayload,
    ): CancelablePromise<DocumentNumberPolicyItem> {
        return __request(OpenAPI, {
            method: 'PUT',
            url: '/api/manager/document-system/legal-entities/{legal_entity_id}/number-policies/{document_type}',
            path: {
                'legal_entity_id': legalEntityId,
                'document_type': documentType,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Native Placeholder Catalog
     * @param docType
     * @returns NativePlaceholderCatalogResponse Successful Response
     * @throws ApiError
     */
    public static getManagerNativePlaceholderCatalog(
        docType: string,
    ): CancelablePromise<NativePlaceholderCatalogResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/document-system/placeholder-catalog',
            query: {
                'doc_type': docType,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * List Native Document Templates
     * @param legalEntityId
     * @param docType
     * @returns NativeDocumentTemplateListResponse Successful Response
     * @throws ApiError
     */
    public static listManagerNativeDocumentTemplates(
        legalEntityId: number,
        docType?: (string | null),
    ): CancelablePromise<NativeDocumentTemplateListResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/document-system/templates',
            query: {
                'legal_entity_id': legalEntityId,
                'doc_type': docType,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Create Native Document Template
     * @param requestBody
     * @returns NativeDocumentTemplateItem Successful Response
     * @throws ApiError
     */
    public static createManagerNativeDocumentTemplate(
        requestBody: NativeDocumentTemplateCreatePayload,
    ): CancelablePromise<NativeDocumentTemplateItem> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/document-system/templates',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * List Native Template Versions
     * @param templateId
     * @param legalEntityId
     * @returns NativeTemplateVersionListResponse Successful Response
     * @throws ApiError
     */
    public static listManagerNativeTemplateVersions(
        templateId: number,
        legalEntityId: number,
    ): CancelablePromise<NativeTemplateVersionListResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/document-system/templates/{template_id}/versions',
            path: {
                'template_id': templateId,
            },
            query: {
                'legal_entity_id': legalEntityId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Upload Native Template Version
     * @param templateId
     * @param formData
     * @returns NativeTemplateVersionItem Successful Response
     * @throws ApiError
     */
    public static uploadManagerNativeTemplateVersion(
        templateId: number,
        formData: Body_upload_manager_native_template_version,
    ): CancelablePromise<NativeTemplateVersionItem> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/document-system/templates/{template_id}/versions',
            path: {
                'template_id': templateId,
            },
            formData: formData,
            mediaType: 'multipart/form-data',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Activate Native Template Version
     * @param templateId
     * @param versionId
     * @param legalEntityId
     * @returns NativeTemplateVersionItem Successful Response
     * @throws ApiError
     */
    public static activateManagerNativeTemplateVersion(
        templateId: number,
        versionId: number,
        legalEntityId: number,
    ): CancelablePromise<NativeTemplateVersionItem> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/document-system/templates/{template_id}/versions/{version_id}/activate',
            path: {
                'template_id': templateId,
                'version_id': versionId,
            },
            query: {
                'legal_entity_id': legalEntityId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Download Native Template Version Source
     * @param templateId
     * @param versionId
     * @param legalEntityId
     * @returns any Immutable DOCX template source
     * @throws ApiError
     */
    public static downloadManagerNativeTemplateVersionSource(
        templateId: number,
        versionId: number,
        legalEntityId: number,
    ): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/document-system/templates/{template_id}/versions/{version_id}/source',
            path: {
                'template_id': templateId,
                'version_id': versionId,
            },
            query: {
                'legal_entity_id': legalEntityId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Document Pdf Runtime
     * @returns DocumentPdfRuntimeStatus Successful Response
     * @throws ApiError
     */
    public static getManagerDocumentPdfRuntime(): CancelablePromise<DocumentPdfRuntimeStatus> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/document-system/runtime/pdf',
        });
    }
    /**
     * List Managed Order Documents
     * @param orderId
     * @returns ManagedDocumentListResponse Successful Response
     * @throws ApiError
     */
    public static listManagerManagedOrderDocuments(
        orderId: number,
    ): CancelablePromise<ManagedDocumentListResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/document-system/orders/{order_id}/documents',
            path: {
                'order_id': orderId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Create Managed Document Draft
     * @param orderId
     * @param requestBody
     * @returns ManagedDocumentItem Successful Response
     * @throws ApiError
     */
    public static createManagerManagedDocumentDraft(
        orderId: number,
        requestBody: ManagedDocumentDraftPayload,
    ): CancelablePromise<ManagedDocumentItem> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/document-system/orders/{order_id}/documents/drafts',
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
     * Delete Managed Document Draft
     * @param documentId
     * @returns void
     * @throws ApiError
     */
    public static deleteManagerManagedDocumentDraft(
        documentId: number,
    ): CancelablePromise<void> {
        return __request(OpenAPI, {
            method: 'DELETE',
            url: '/api/manager/document-system/documents/{document_id}/draft',
            path: {
                'document_id': documentId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Issue Managed Document
     * @param documentId
     * @returns ManagedDocumentItem Successful Response
     * @throws ApiError
     */
    public static issueManagerManagedDocument(
        documentId: number,
    ): CancelablePromise<ManagedDocumentItem> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/document-system/documents/{document_id}/issue',
            path: {
                'document_id': documentId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Void Managed Document
     * @param documentId
     * @param requestBody
     * @returns ManagedDocumentItem Successful Response
     * @throws ApiError
     */
    public static voidManagerManagedDocument(
        documentId: number,
        requestBody: ManagedDocumentVoidPayload,
    ): CancelablePromise<ManagedDocumentItem> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/document-system/documents/{document_id}/void',
            path: {
                'document_id': documentId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * List Document Artifacts
     * @param documentId
     * @returns ManagedDocumentArtifactListResponse Successful Response
     * @throws ApiError
     */
    public static listManagerDocumentArtifacts(
        documentId: number,
    ): CancelablePromise<ManagedDocumentArtifactListResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/document-system/documents/{document_id}/artifacts',
            path: {
                'document_id': documentId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Document Artifact Access
     * @param artifactId
     * @returns ManagedDocumentArtifactAccessResponse Successful Response
     * @throws ApiError
     */
    public static getManagerDocumentArtifactAccess(
        artifactId: string,
    ): CancelablePromise<ManagedDocumentArtifactAccessResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/document-system/artifacts/{artifact_id}/access',
            path: {
                'artifact_id': artifactId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Download Document Artifact
     * @param artifactId
     * @returns any Successful Response
     * @throws ApiError
     */
    public static downloadManagerDocumentArtifact(
        artifactId: string,
    ): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/document-system/artifacts/{artifact_id}/download',
            path: {
                'artifact_id': artifactId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
