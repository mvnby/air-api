/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ManagerAuthStatusResponse } from '../models/ManagerAuthStatusResponse';
import type { ManagerStorefrontListResponse } from '../models/ManagerStorefrontListResponse';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class InstallerAuthService {
    /**
     * Read Installer Me
     * Read live identity and the selected real company/site for My Work.
     *
     * Accepts the existing Manager company/storefront headers. An invalid explicit
     * selection is denied, never replaced. Only actual owner/admin/manager/installer
     * membership is eligible; virtual platform support and catalog editors are denied.
     * This bootstrap grants no assignment, CRM or write access.
     * @returns ManagerAuthStatusResponse Successful Response
     * @throws ApiError
     */
    public static readInstallerMe(): CancelablePromise<ManagerAuthStatusResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/installer/me',
        });
    }
    /**
     * List Installer Storefronts
     * List active sites of the selected real company, without switching context.
     *
     * Uses the same fresh membership and explicit selection checks as /installer/me.
     * Listing a site grants no assignment or Manager access.
     * @returns ManagerStorefrontListResponse Successful Response
     * @throws ApiError
     */
    public static listInstallerStorefronts(): CancelablePromise<ManagerStorefrontListResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/installer/storefronts',
        });
    }
}
