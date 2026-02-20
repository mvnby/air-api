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
     * Paginated list of installers.
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
     * Create a new installer.
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
     * Search active installers by name (for autocomplete).
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
     * Update an existing installer.
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
