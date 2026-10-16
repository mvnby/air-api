/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { CompanySitesResponse } from '../models/CompanySitesResponse';
import type { PlatformCompanyListResponse } from '../models/PlatformCompanyListResponse';
import type { PlatformCompanyResponse } from '../models/PlatformCompanyResponse';
import type { PlatformCompanyUpdate } from '../models/PlatformCompanyUpdate';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class ManagerPlatformCompaniesService {
    /**
     * List Platform Companies
     * List every company, owners, live staff counts and all sites/domains for the platform owner.
     *
     * Includes disabled/demo companies and unpublished sites; never exposes credentials.
     * Independent of selected company headers. Company owners/admins receive 403.
     * Page-based pagination is bounded to 100 companies; search matches name or slug.
     * @param page
     * @param limit
     * @param search
     * @returns PlatformCompanyListResponse Successful Response
     * @throws ApiError
     */
    public static managerListPlatformCompanies(
        page: number = 1,
        limit: number = 50,
        search?: (string | null),
    ): CancelablePromise<PlatformCompanyListResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/platform/companies',
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
     * Update Platform Company
     * Change a company name or active/disabled status as the live platform owner; audit atomically.
     *
     * Requires X-Kitlane-Team: 1, approved origin and exact expected_updated_at. Stale state
     * returns 409, missing company 404; the canonical system company cannot be disabled.
     * Disabling blocks company access on fresh requests; it does not delete business data,
     * change catalog grants, provision sites or edit DNS. Re-read before retrying a conflict.
     * @param tenantId
     * @param requestBody
     * @returns PlatformCompanyResponse Successful Response
     * @throws ApiError
     */
    public static managerUpdatePlatformCompany(
        tenantId: number,
        requestBody: PlatformCompanyUpdate,
    ): CancelablePromise<PlatformCompanyResponse> {
        return __request(OpenAPI, {
            method: 'PATCH',
            url: '/api/manager/platform/companies/{tenant_id}',
            path: {
                'tenant_id': tenantId,
            },
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * List Company Sites
     * Show all sites and domain states in the selected company to its owner/admin.
     *
     * Includes draft and disabled sites for visibility. This read-only endpoint cannot
     * provision a site, publish it or alter a domain. No other company's sites are returned.
     * Page-based pagination returns at most 100 sites.
     * @param page
     * @param limit
     * @returns CompanySitesResponse Successful Response
     * @throws ApiError
     */
    public static managerListCompanySites(
        page: number = 1,
        limit: number = 100,
    ): CancelablePromise<CompanySitesResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/company/sites',
            query: {
                'page': page,
                'limit': limit,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
