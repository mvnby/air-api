/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ManagerServiceCatalogClonePayload } from '../models/ManagerServiceCatalogClonePayload';
import type { ManagerServiceCatalogCloneResponse } from '../models/ManagerServiceCatalogCloneResponse';
import type { ManagerServiceCatalogTemplatePreviewResponse } from '../models/ManagerServiceCatalogTemplatePreviewResponse';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class ManagerServiceCatalogService {
    /**
     * Preview Manager Service Catalog Template
     * Read canonical service-template fingerprint/counts and target-tenant state to determine
     * whether a detached clone is available. This performs no writes. The system tenant cannot
     * clone into itself; a partner target must be empty or already match a completed clone,
     * and canonical drafts must match the current published book when one exists.
     *
     * Access and scope: owner/admin access is required in the authenticated tenant and
     * selected storefront; partner owners may use this workflow. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * See [installation estimate
     * contract](https://github.com/mvnby/air-api/blob/main/docs/installation-estimate-contract.md).
     * @returns ManagerServiceCatalogTemplatePreviewResponse Successful Response
     * @throws ApiError
     */
    public static previewManagerServiceCatalogTemplate(): CancelablePromise<ManagerServiceCatalogTemplatePreviewResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/service-catalog/template-preview',
        });
    }
    /**
     * Clone Manager Service Catalog Template
     * Copy the canonical template into the authenticated partner tenant as detached
     * service-card/tariff/rule/rate data, including its own first published book when
     * applicable. expected_fingerprint guards source changes; changed source, partial/nonempty
     * incompatible target or system-tenant target returns 409, missing tenant/storefront 404.
     * Source/target locks protect the atomic copy and audit. A complete matching prior clone
     * returns already_cloned; later canonical edits do not synchronize into the copy.
     *
     * Access and scope: owner/admin access is required in the authenticated tenant and
     * selected storefront; partner owners may use this workflow. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * See [installation estimate
     * contract](https://github.com/mvnby/air-api/blob/main/docs/installation-estimate-contract.md).
     * @param requestBody
     * @returns ManagerServiceCatalogCloneResponse Successful Response
     * @throws ApiError
     */
    public static cloneManagerServiceCatalogTemplate(
        requestBody: ManagerServiceCatalogClonePayload,
    ): CancelablePromise<ManagerServiceCatalogCloneResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/service-catalog/clone-template',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
