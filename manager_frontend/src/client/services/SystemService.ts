/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class SystemService {
    /**
     * Trigger Rebuild Web
     * Trigger a turbo-rebuild of the frontend Astro site.
     * Accessible only by authenticated managers/admins.
     * @returns any Successful Response
     * @throws ApiError
     */
    public static triggerRebuildWebApiSystemRebuildWebPost(): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/system/rebuild-web',
        });
    }
}
