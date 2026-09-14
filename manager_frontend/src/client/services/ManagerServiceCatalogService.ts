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
