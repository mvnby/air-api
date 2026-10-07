/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ManagerInstallerCreatePayload } from '../models/ManagerInstallerCreatePayload';
import type { ManagerInstallerListResponse } from '../models/ManagerInstallerListResponse';
import type { ManagerInstallerResponse } from '../models/ManagerInstallerResponse';
import type { ManagerInstallerUpdatePayload } from '../models/ManagerInstallerUpdatePayload';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class ManagerInstallersService {
    /**
     * List Installers
     * Read a paginated installer/staff projection for the tenant, optionally filtering by
     * search text. page starts at 1; this route currently accepts limit 1–500, default 100.
     * Membership status determines tenant activity independently of the global staff identity.
     *
     * Access and scope: Manager access is required; installer visibility follows staff
     * membership in the authenticated tenant. The system tenant also sees unmapped legacy
     * installers. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * @param page
     * @param limit
     * @param search
     * @returns ManagerInstallerListResponse Successful Response
     * @throws ApiError
     */
    public static getManagerInstallers(
        page: number = 1,
        limit: number = 100,
        search?: (string | null),
    ): CancelablePromise<ManagerInstallerListResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/installers',
            query: {
                'page': page,
                'limit': limit,
                'search': search,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Create Installer
     * Create an installer and ensure its linked staff identity and membership in the
     * authenticated tenant. Creation errors are returned as 400. This has staff-account side
     * effects and no idempotency receipt, so repeated calls are not guaranteed to reuse a
     * prior installer.
     *
     * Access and scope: Manager access is required; installer visibility follows staff
     * membership in the authenticated tenant. The system tenant also sees unmapped legacy
     * installers. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * @param requestBody
     * @returns ManagerInstallerResponse Successful Response
     * @throws ApiError
     */
    public static createManagerInstaller(
        requestBody: ManagerInstallerCreatePayload,
    ): CancelablePromise<ManagerInstallerResponse> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/manager/installers',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Search Installers
     * Search active tenant installers by name for autocomplete. q must be nonempty and limit
     * is 1–100, default 50; this is a bounded suggestion list without page navigation. No
     * installer/staff membership is created.
     *
     * Access and scope: Manager access is required; installer visibility follows staff
     * membership in the authenticated tenant. The system tenant also sees unmapped legacy
     * installers. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * @param q Search term for installer name
     * @param limit
     * @returns ManagerInstallerListResponse Successful Response
     * @throws ApiError
     */
    public static searchManagerInstallers(
        q: string,
        limit: number = 50,
    ): CancelablePromise<ManagerInstallerListResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/installers/search',
            query: {
                'q': q,
                'limit': limit,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * Update Installer
     * Update submitted non-null installer identity fields and/or the current tenant
     * membership’s activity. Missing/inaccessible installer returns 404. Partners cannot edit
     * shared identity fields when the staff user has multiple memberships; this service
     * rejection is not converted to a dedicated client error by this route. Omitted/null
     * fields are ignored, including telegram_id; membership changes also recompute aggregate
     * staff activity. No expected-version guard is used.
     *
     * Access and scope: Manager access is required; installer visibility follows staff
     * membership in the authenticated tenant. The system tenant also sees unmapped legacy
     * installers. See [Manager
     * authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
     * @param installerId
     * @param requestBody
     * @returns ManagerInstallerResponse Successful Response
     * @throws ApiError
     */
    public static updateManagerInstaller(
        installerId: number,
        requestBody: ManagerInstallerUpdatePayload,
    ): CancelablePromise<ManagerInstallerResponse> {
        return __request(OpenAPI, {
            method: 'PUT',
            url: '/api/manager/installers/{installer_id}',
            path: {
                'installer_id': installerId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
