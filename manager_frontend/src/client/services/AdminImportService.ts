/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class AdminImportService {
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
}
