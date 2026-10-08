/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { Body_upload_manager_document_facsimile } from '../models/Body_upload_manager_document_facsimile';
import type { Body_upload_manager_native_template_version } from '../models/Body_upload_manager_native_template_version';
import type { ConditionPresetItem } from '../models/ConditionPresetItem';
import type { ConditionPresetList } from '../models/ConditionPresetList';
import type { ConditionPresetPayload } from '../models/ConditionPresetPayload';
import type { ConsumerEquipmentDefaultsResponse } from '../models/ConsumerEquipmentDefaultsResponse';
import type { DocumentCustomerReadiness } from '../models/DocumentCustomerReadiness';
import type { DocumentFacsimilePdfPayload } from '../models/DocumentFacsimilePdfPayload';
import type { DocumentFacsimilePlacementItem } from '../models/DocumentFacsimilePlacementItem';
import type { DocumentFacsimilePlacementPayload } from '../models/DocumentFacsimilePlacementPayload';
import type { DocumentFacsimilePreviewResponse } from '../models/DocumentFacsimilePreviewResponse';
import type { DocumentLegalEntityCreatePayload } from '../models/DocumentLegalEntityCreatePayload';
import type { DocumentLegalEntityItem } from '../models/DocumentLegalEntityItem';
import type { DocumentLegalEntityListResponse } from '../models/DocumentLegalEntityListResponse';
import type { DocumentLegalEntityUpdatePayload } from '../models/DocumentLegalEntityUpdatePayload';
import type { DocumentNumberPolicyItem } from '../models/DocumentNumberPolicyItem';
import type { DocumentNumberPolicyListResponse } from '../models/DocumentNumberPolicyListResponse';
import type { DocumentNumberPolicyPayload } from '../models/DocumentNumberPolicyPayload';
import type { DocumentPdfRuntimeStatus } from '../models/DocumentPdfRuntimeStatus';
import type { ExternalEditSessionItem } from '../models/ExternalEditSessionItem';
import type { ManagedDocumentArtifactAccessResponse } from '../models/ManagedDocumentArtifactAccessResponse';
import type { ManagedDocumentArtifactListResponse } from '../models/ManagedDocumentArtifactListResponse';
import type { ManagedDocumentDraftPayload } from '../models/ManagedDocumentDraftPayload';
import type { ManagedDocumentItem } from '../models/ManagedDocumentItem';
import type { ManagedDocumentListResponse } from '../models/ManagedDocumentListResponse';
import type { ManagedDocumentReadinessResponse } from '../models/ManagedDocumentReadinessResponse';
import type { ManagedDocumentVoidPayload } from '../models/ManagedDocumentVoidPayload';
import type { NativeDocumentTemplateCreatePayload } from '../models/NativeDocumentTemplateCreatePayload';
import type { NativeDocumentTemplateItem } from '../models/NativeDocumentTemplateItem';
import type { NativeDocumentTemplateListResponse } from '../models/NativeDocumentTemplateListResponse';
import type { NativeDocumentTemplateUpdatePayload } from '../models/NativeDocumentTemplateUpdatePayload';
import type { NativePlaceholderCatalogResponse } from '../models/NativePlaceholderCatalogResponse';
import type { NativeTemplateVersionItem } from '../models/NativeTemplateVersionItem';
import type { NativeTemplateVersionListResponse } from '../models/NativeTemplateVersionListResponse';
import type { OrderEmailComposePayload } from '../models/OrderEmailComposePayload';
import type { OrderEmailComposeResponse } from '../models/OrderEmailComposeResponse';
import type { OrderEmailSendPayload } from '../models/OrderEmailSendPayload';
import type { OutgoingEmailResponse } from '../models/OutgoingEmailResponse';
import type { TemplateExternalEditSyncPayload } from '../models/TemplateExternalEditSyncPayload';
import type { TemplateExternalEditSyncResponse } from '../models/TemplateExternalEditSyncResponse';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class ManagerDocumentSystemService {
    /**
     * List Presets
     * List up to 100 reusable document clauses in the current tenant, newest first. Reading
     * does not apply a clause to an order or document.
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * @returns ConditionPresetList Successful Response
     * @throws ApiError
     */
    public static listManagerDocumentConditionPresets(): CancelablePromise<ConditionPresetList> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/document-system/condition-presets',
        });
    }
    /**
     * Create Preset
     * Save a reusable clause in the current tenant after trimming and case/whitespace
     * normalization for duplicate detection. Invalid or duplicate text returns 409. Repeating
     * this POST can conflict; it is not an idempotency-key replay.
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * @param requestBody
     * @returns ConditionPresetItem Successful Response
     * @throws ApiError
     */
    public static createManagerDocumentConditionPreset(
        requestBody: ConditionPresetPayload,
    ): CancelablePromise<ConditionPresetItem> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/document-system/condition-presets',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Delete Preset
     * Delete a clause in the current tenant, returning 204. Missing or foreign-tenant clause
     * returns 404, including a repeat after deletion; existing document snapshots are not
     * rewritten.
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * @param presetId
     * @returns void
     * @throws ApiError
     */
    public static deleteManagerDocumentConditionPreset(
        presetId: number,
    ): CancelablePromise<void> {
        return __request(OpenAPI, {
            method: 'DELETE',
            url: '/api/manager/document-system/condition-presets/{preset_id}',
            path: {
                'preset_id': presetId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Manager Consumer Equipment Defaults
     * Resolve equipment and warranty defaults for an accessible order/proposal in the current
     * tenant/storefront, optionally at an issue date. Read-only: does not save a document.
     * Missing order returns 404; invalid proposal selection returns 400.
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * @param orderId
     * @param proposalId
     * @param issueDate
     * @returns ConsumerEquipmentDefaultsResponse Successful Response
     * @throws ApiError
     */
    public static getManagerConsumerEquipmentDefaults(
        orderId: number,
        proposalId?: (number | null),
        issueDate?: (string | null),
    ): CancelablePromise<ConsumerEquipmentDefaultsResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/document-system/orders/{order_id}/consumer-defaults',
            path: {
                'order_id': orderId,
            },
            query: {
                'proposal_id': proposalId,
                'issue_date': issueDate,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Upload Facsimile
     * Upload a private PNG signature or seal for a legal entity in the current tenant.
     * Requires owner/admin access. Only signature/seal is accepted; file must be nonempty, at
     * most 5 MB and 20 million pixels (400 otherwise); missing entity returns 404. Makes a new
     * asset current without rewriting already prepared PDFs.
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * @param legalEntityId
     * @param kind
     * @param formData
     * @returns any Successful Response
     * @throws ApiError
     */
    public static uploadManagerDocumentFacsimile(
        legalEntityId: number,
        kind: string,
        formData: Body_upload_manager_document_facsimile,
    ): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/document-system/legal-entities/{legal_entity_id}/facsimiles/{kind}',
            path: {
                'legal_entity_id': legalEntityId,
                'kind': kind,
            },
            formData: formData,
            mediaType: 'multipart/form-data',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Prepare Facsimile Pdf
     * Prepare a separate authoritative signed_pdf artifact for a scoped managed document using
     * signature/seal PNGs and placement. The issued source PDF and earlier copies stay
     * immutable. Submitted placement checks source checksum, current assets and
     * expected_signed_artifact_id to prevent replacing a changed copy;
     * stale/missing/ineligible context returns 409. Sent/signed or closed-order copies cannot
     * be changed; without placement an existing prepared copy can be reused. This is
     * preparation, not email delivery or cryptographic signing. See the [document lifecycle
     * contract](https://github.com/mvnby/air-api/blob/main/docs/document-module-architecture.md).
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * @param documentId
     * @param requestBody
     * @returns any Successful Response
     * @throws ApiError
     */
    public static prepareManagerDocumentFacsimilePdf(
        documentId: number,
        requestBody?: (DocumentFacsimilePdfPayload | null),
    ): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/document-system/documents/{document_id}/facsimile-pdf',
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
     * Get Facsimile Preview
     * Read private/no-store PDF page geometry, current signature/seal assets and
     * expected-state metadata for the scoped facsimile editor. Does not prepare a signed PDF.
     * Unavailable source/document/assets return 409; obtain fresh metadata before saving
     * placement.
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * @param documentId
     * @returns DocumentFacsimilePreviewResponse Successful Response
     * @throws ApiError
     */
    public static getManagerDocumentFacsimilePreview(
        documentId: number,
    ): CancelablePromise<DocumentFacsimilePreviewResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/document-system/documents/{document_id}/facsimile-preview',
            path: {
                'document_id': documentId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Facsimile Preview Page
     * Render one authenticated scoped PDF preview page as private/no-store PNG, with
     * page_number limited to 1–100. Unavailable document/page/render context returns 409. Does
     * not issue or change the PDF.
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * @param documentId
     * @param pageNumber
     * @returns any Successful Response
     * @throws ApiError
     */
    public static getManagerDocumentFacsimilePreviewPage(
        documentId: number,
        pageNumber: number,
    ): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/document-system/documents/{document_id}/facsimile-preview/pages/{page_number}',
            path: {
                'document_id': documentId,
                'page_number': pageNumber,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Facsimile Preview Asset
     * Read an authenticated private/no-store PNG signature/seal asset belonging to this scoped
     * document’s legal entity. asset_id is constrained to the asset identifier format.
     * Unavailable or mismatched asset context returns 409; this is not a public media
     * endpoint.
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * @param documentId
     * @param assetId
     * @returns any Successful Response
     * @throws ApiError
     */
    public static getManagerDocumentFacsimilePreviewAsset(
        documentId: number,
        assetId: string,
    ): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/document-system/documents/{document_id}/facsimile-preview/assets/{asset_id}',
            path: {
                'document_id': documentId,
                'asset_id': assetId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Upsert Placement
     * Set legacy facsimile placement defaults for a native template/version owned by the
     * current tenant. Requires owner/admin access. Missing or inaccessible version returns
     * 404. Updates placement defaults only; previously generated PDFs are not rewritten and
     * document-specific placement is saved by facsimile-pdf.
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * @param templateId
     * @param versionId
     * @param requestBody
     * @returns DocumentFacsimilePlacementItem Successful Response
     * @throws ApiError
     */
    public static upsertManagerDocumentFacsimilePlacement(
        templateId: number,
        versionId: number,
        requestBody: DocumentFacsimilePlacementPayload,
    ): CancelablePromise<DocumentFacsimilePlacementItem> {
        return __request(OpenAPI, {
            method: 'PUT',
            url: '/api/manager/document-system/templates/{template_id}/versions/{version_id}/facsimile-placement',
            path: {
                'template_id': templateId,
                'version_id': versionId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Get Placement
     * Read legacy facsimile placement defaults for a current-tenant native template/version.
     * Requires owner/admin access. Missing/inaccessible or unconfigured placement returns 404.
     * This does not return the current document-specific prepared PDF placement.
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * @param templateId
     * @param versionId
     * @returns DocumentFacsimilePlacementItem Successful Response
     * @throws ApiError
     */
    public static getManagerDocumentFacsimilePlacement(
        templateId: number,
        versionId: number,
    ): CancelablePromise<DocumentFacsimilePlacementItem> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/document-system/templates/{template_id}/versions/{version_id}/facsimile-placement',
            path: {
                'template_id': templateId,
                'version_id': versionId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * List Document Legal Entities
     * List document issuer legal entities owned by the current tenant. Does not list the
     * shared supplier directory or other tenants’ requisites.
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
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
     * Create an issuer legal entity in the current tenant. Requires owner/admin access via
     * route policy. Default-issuer selection is maintained by the service; conflicting
     * identity/default configuration returns 409 and invalid requisites 400. This does not
     * provision an external integration account.
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
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
     * Patch supplied issuer fields/requisites in the current tenant. Requires owner/admin
     * access. Missing entity returns 404, conflicting identity/default configuration 409 and
     * invalid values 400. Existing issued document snapshots remain independent of updated
     * requisites.
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
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
     * Read effective numbering policies for a legal entity in the current tenant, including
     * defaults that are not persisted yet. Missing or inaccessible entity returns 404; reading
     * does not reserve an official number.
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
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
     * Set the effective numbering policy for the selected document kind and current tenant
     * legal entity. Requires owner/admin access. Missing entity returns 404; unsupported kind
     * or invalid policy returns 400. Saving a policy does not reserve or recycle numbers
     * already assigned. See the [document lifecycle
     * contract](https://github.com/mvnby/air-api/blob/main/docs/document-module-architecture.md).
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
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
     * Read the shared supported native document placeholder/condition/table catalog for an
     * accepted document type. Manager access is required by router dependencies; this returns
     * template authoring metadata without tenant CRM data.
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
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
     * List native template definitions under a legal entity owned by the current tenant,
     * optionally filtered by document type. Missing issuer scope returns 404. This lists
     * definitions and their activation state rather than generating an order document.
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
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
     * Create a native template definition under the current tenant’s legal entity. Requires
     * owner/admin access; no DOCX version is uploaded or activated by this command. Missing
     * scope returns 404, conflicting definition 409 and invalid definition 400. See [native
     * template
     * versions](https://github.com/mvnby/air-api/blob/main/docs/native-document-template-bundles.md).
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
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
     * Update Native Document Template
     * Update submitted template definition metadata in the current tenant; route access is
     * Manager (no owner-only policy is attached to this operation). Missing template/scope
     * returns 404, conflicting use-case definition 409 and invalid metadata 400. This does not
     * replace an immutable DOCX version.
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * @param templateId
     * @param requestBody
     * @returns NativeDocumentTemplateItem Successful Response
     * @throws ApiError
     */
    public static updateManagerNativeDocumentTemplate(
        templateId: number,
        requestBody: NativeDocumentTemplateUpdatePayload,
    ): CancelablePromise<NativeDocumentTemplateItem> {
        return __request(OpenAPI, {
            method: 'PATCH',
            url: '/api/manager/document-system/templates/{template_id}',
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
     * List Native Template Versions
     * List immutable versions for a template and legal entity owned by the current tenant.
     * Missing template/issuer scope returns 404; listing does not activate a version.
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
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
     * Upload an immutable native DOCX version for the current tenant’s template/legal entity.
     * Requires owner/admin access. Empty/invalid DOCX or placeholder schema returns 400; file
     * above 5 MB returns 413, semantic template validation issues 422, missing scope 404 and
     * version conflicts 409. When schema is omitted supported placeholders are discovered from
     * the file. Upload does not activate the version. See [native template
     * versions](https://github.com/mvnby/air-api/blob/main/docs/native-document-template-bundles.md).
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
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
     * Activate an existing valid immutable version for the current tenant’s template/legal
     * entity. Requires owner/admin access. Missing version/scope returns 404 and incompatible
     * version state 409. Existing issued document snapshots/artifacts are not regenerated by
     * activation. See [native template
     * versions](https://github.com/mvnby/air-api/blob/main/docs/native-document-template-bundles.md).
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
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
     * Download the stored immutable DOCX source for a current-tenant template/version after
     * checksum verification. Requires owner/admin access. Missing version returns 404;
     * missing/corrupt source integrity returns 409. Returns a private/no-store binary
     * attachment rather than JSON.
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
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
     * Check the configured native PDF converter’s runtime health without rendering a document.
     * Manager access is required by router dependencies; response reports shared converter
     * availability/provider/detail, not tenant business data. available=false is a health
     * result rather than proof of successful generation.
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
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
     * Compose Native Order Email
     * Compose suggested recipient, subject/body and selected document attachments for an
     * accessible order in the current tenant/storefront. Preview only: does not submit email
     * or mark documents sent. Invalid document/template/order selection returns 400.
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * @param orderId
     * @param requestBody
     * @returns OrderEmailComposeResponse Successful Response
     * @throws ApiError
     */
    public static composeManagerNativeOrderEmail(
        orderId: number,
        requestBody: OrderEmailComposePayload,
    ): CancelablePromise<OrderEmailComposeResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/document-system/orders/{order_id}/email/compose',
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
     * Send Native Order Email
     * Send an email for an accessible order with selected native/legacy document attachments,
     * recording outgoing-email state and document delivery. Manager access is required;
     * current SMTP sending supports the system tenant only (409
     * tenant_email_sender_not_configured for partner tenants). Invalid selection/content
     * returns 400 and send failure 502. No caller idempotency receipt is provided: inspect
     * outgoing-email history before repeating a lost send response. See the [document
     * lifecycle
     * contract](https://github.com/mvnby/air-api/blob/main/docs/document-module-architecture.md).
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * @param orderId
     * @param requestBody
     * @returns OutgoingEmailResponse Successful Response
     * @throws ApiError
     */
    public static sendManagerNativeOrderEmail(
        orderId: number,
        requestBody: OrderEmailSendPayload,
    ): CancelablePromise<OutgoingEmailResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/document-system/orders/{order_id}/email',
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
     * Get Native Template Google Edit Session
     * Inspect and refresh the Google editing session for a template version/legal entity in
     * the current tenant. Requires owner/admin access. Remote changes are reported rather than
     * silently replacing the immutable local version. Missing session returns 404, conflicting
     * state 409, provider failure 502; tenant Drive availability is checked first.
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * @param templateId
     * @param versionId
     * @param legalEntityId
     * @returns ExternalEditSessionItem Successful Response
     * @throws ApiError
     */
    public static getManagerNativeTemplateGoogleEditSession(
        templateId: number,
        versionId: number,
        legalEntityId: number,
    ): CancelablePromise<ExternalEditSessionItem> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/document-system/templates/{template_id}/versions/{version_id}/google-edit-session',
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
     * Create Native Template Google Edit Session
     * Ensure a Google editable copy of a native template version in the current tenant.
     * Requires owner/admin access. Reuses an existing eligible session; creating a copy does
     * not activate or overwrite the immutable version. Missing version/scope returns 404,
     * session/version conflict 409, invalid input/source 400 and provider failure 502; tenant
     * Drive availability is required.
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * @param templateId
     * @param versionId
     * @param legalEntityId
     * @returns ExternalEditSessionItem Successful Response
     * @throws ApiError
     */
    public static createManagerNativeTemplateGoogleEditSession(
        templateId: number,
        versionId: number,
        legalEntityId: number,
    ): CancelablePromise<ExternalEditSessionItem> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/document-system/templates/{template_id}/versions/{version_id}/google-edit-session',
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
     * Sync Native Template Google Edit Session
     * Import a remote template edit as a new validated native version in the current tenant.
     * Requires owner/admin access, expected base checksum, expected remote revision and
     * idempotency_key. Retain the same command on retry; reread session state on conflict.
     * Returns the version and session; activation is a separate command. Missing
     * version/session returns 404, stale state 409, semantic DOCX validation 422, invalid
     * input 400 and provider failure 502. See [native template
     * versions](https://github.com/mvnby/air-api/blob/main/docs/native-document-template-bundles.md).
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * @param templateId
     * @param versionId
     * @param legalEntityId
     * @param requestBody
     * @returns TemplateExternalEditSyncResponse Successful Response
     * @throws ApiError
     */
    public static syncManagerNativeTemplateGoogleEditSession(
        templateId: number,
        versionId: number,
        legalEntityId: number,
        requestBody: TemplateExternalEditSyncPayload,
    ): CancelablePromise<TemplateExternalEditSyncResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/document-system/templates/{template_id}/versions/{version_id}/google-edit-session/sync',
            path: {
                'template_id': templateId,
                'version_id': versionId,
            },
            query: {
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
     * Get Managed Document Google Edit Session
     * Inspect the optional Google editing session for a scoped managed draft and refresh its
     * remote revision/status. Does not synchronize edits into the authoritative local source.
     * Missing document/session returns 404, incompatible state 409 and provider failure 502; a
     * missing/unavailable tenant Drive connection fails separately. See the [document
     * lifecycle
     * contract](https://github.com/mvnby/air-api/blob/main/docs/document-module-architecture.md).
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * @param documentId
     * @returns ExternalEditSessionItem Successful Response
     * @throws ApiError
     */
    public static getManagerManagedDocumentGoogleEditSession(
        documentId: number,
    ): CancelablePromise<ExternalEditSessionItem> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/document-system/documents/{document_id}/google-edit-session',
            path: {
                'document_id': documentId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Create Managed Document Google Edit Session
     * Ensure a provider-owned editable Google copy for a scoped native draft, recording the
     * actor. The native source/context remain authoritative; issued documents cannot be edited
     * through this draft path. Reuses the existing session when appropriate. Missing document
     * returns 404, draft/session conflicts 409, invalid source 400 and provider failure 502;
     * tenant Drive availability is checked first. See the [document lifecycle
     * contract](https://github.com/mvnby/air-api/blob/main/docs/document-module-architecture.md).
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * @param documentId
     * @returns ExternalEditSessionItem Successful Response
     * @throws ApiError
     */
    public static createManagerManagedDocumentGoogleEditSession(
        documentId: number,
    ): CancelablePromise<ExternalEditSessionItem> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/document-system/documents/{document_id}/google-edit-session',
            path: {
                'document_id': documentId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Sync Managed Document Google Edit Session
     * Import the edited Google DOCX into the scoped draft after checking
     * expected_base_checksum_sha256 and expected_remote_revision. Requires a caller
     * idempotency_key; retain the same command on retry. Validates document structure before
     * making the new local source authoritative. Missing document/session returns 404,
     * stale/immutable state 409, invalid input 400 and provider failure 502. Does not issue
     * the document. See the [document lifecycle
     * contract](https://github.com/mvnby/air-api/blob/main/docs/document-module-architecture.md).
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * @param documentId
     * @param requestBody
     * @returns ExternalEditSessionItem Successful Response
     * @throws ApiError
     */
    public static syncManagerManagedDocumentGoogleEditSession(
        documentId: number,
        requestBody: TemplateExternalEditSyncPayload,
    ): CancelablePromise<ExternalEditSessionItem> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/document-system/documents/{document_id}/google-edit-session/sync',
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
     * Preview Managed Document Draft
     * Render a private/no-store PDF preview for a scoped managed draft using its saved
     * context/template or edited source. Does not issue the document or reserve a number.
     * Missing/inaccessible document returns 404, incompatible draft state 409 and
     * rendering/source failure 503. See the [document lifecycle
     * contract](https://github.com/mvnby/air-api/blob/main/docs/document-module-architecture.md).
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * @param documentId
     * @returns any Successful Response
     * @throws ApiError
     */
    public static previewManagerManagedDocumentDraft(
        documentId: number,
    ): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/document-system/documents/{document_id}/preview',
            path: {
                'document_id': documentId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * List Managed Order Documents
     * List documents for an order accessible in the current tenant/storefront, with
     * lifecycle/provider metadata and accessible native artifacts. Missing order returns 404.
     * Reading legacy metadata does not migrate or regenerate legacy files. See the [document
     * lifecycle
     * contract](https://github.com/mvnby/air-api/blob/main/docs/document-module-architecture.md).
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
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
     * Create a native draft and immutable context snapshot for the current tenant/storefront
     * order, selected proposal, issuer and document basis. Closed orders or incompatible
     * template/replacement context return 409; missing dependencies 404, invalid selection 400
     * and unavailable template storage 503. No official number is reserved yet. Repeating POST
     * creates another draft; no caller idempotency receipt is provided. See the [document
     * lifecycle
     * contract](https://github.com/mvnby/air-api/blob/main/docs/document-module-architecture.md).
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
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
     * Delete a scoped unissued native draft, returning 204. A draft with reserved official
     * number, issuance/artifacts or immutable state cannot be deleted (409); missing document
     * returns 404. Use lifecycle commands for issued records, not this endpoint. A repeat
     * after deletion returns 404.
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
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
     * Issue a current-tenant managed draft by reserving its official number and rendering
     * immutable DOCX/PDF artifacts. Saved external edits must be synchronized and their remote
     * revision verified first. Missing document returns 404, state/edit conflicts 409 and
     * generation failure 503. A failed render retains its reservation; retry the same document
     * rather than creating a new draft. Already issued/sent/signed records reuse their
     * issuance result. See the [document lifecycle
     * contract](https://github.com/mvnby/air-api/blob/main/docs/document-module-architecture.md).
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
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
     * Void a scoped managed document with an explicit reason and mark its numbering
     * reservation void. Artifacts and official number are retained; voiding does not delete or
     * recycle them. Missing document returns 404, forbidden lifecycle transition or invalid
     * reason 409. See the [document lifecycle
     * contract](https://github.com/mvnby/air-api/blob/main/docs/document-module-architecture.md).
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
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
     * List private artifact metadata for a document accessible in the current
     * tenant/storefront. Missing document returns 404. This does not return artifact bytes or
     * provide a public media URL.
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
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
     * Resolve private access to a scoped artifact. Returns a provider signed URL for a bounded
     * TTL of 30–3600 seconds, or the authenticated API download path when signing is
     * unavailable. Missing artifact/file returns 404 and integrity failure 409. The fallback
     * path still requires Manager authentication; expires_in is not an anonymous access grant.
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
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
     * Download bytes of a scoped private artifact after storage integrity validation. Missing
     * artifact/file returns 404 and corrupt/incompatible storage metadata 409. Response is an
     * attachment with its artifact content type and private/no-store headers. Read-only access
     * remains separate from issuance.
     *
     * Access requires an authenticated Manager session/JWT and live membership; see [Manager
     * access](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
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
    /**
     * Check Managed Document Readiness
     * Read the selected native version and scoped order facts without creating a draft
     * or reserving a number. Reports only applicable placeholders surviving the frozen
     * party conditions. Creating a draft and issuing it repeat server-side checks;
     * this response is advisory and does not authorize issuance. Returns 404 for
     * scoped dependencies, 409 for incompatible context, 400 for invalid facts and
     * 503 for unavailable private template bytes. Manager membership is required.
     * @param orderId
     * @param requestBody
     * @returns ManagedDocumentReadinessResponse Successful Response
     * @throws ApiError
     */
    public static checkManagerManagedDocumentReadiness(
        orderId: number,
        requestBody: ManagedDocumentDraftPayload,
    ): CancelablePromise<ManagedDocumentReadinessResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/document-system/orders/{order_id}/documents/readiness',
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
     * Get Managed Document Readiness
     * Check a scoped draft's persisted facts against its frozen native template.
     *
     * Reads source bytes without refreshing the snapshot or calling an edit provider.
     * Issued documents are not rechecked. Missing/inaccessible documents return 404,
     * incompatible context 409, unavailable source 503 and invalid snapshot 400.
     * Manager membership is required. The issuance service repeats this check.
     * @param documentId
     * @returns DocumentCustomerReadiness Successful Response
     * @throws ApiError
     */
    public static getManagerManagedDocumentReadiness(
        documentId: number,
    ): CancelablePromise<DocumentCustomerReadiness> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/document-system/documents/{document_id}/readiness',
            path: {
                'document_id': documentId,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
