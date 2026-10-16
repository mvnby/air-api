/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ManagerAccountCompaniesResponse } from '../models/ManagerAccountCompaniesResponse';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class ManagerAccountService {
    /**
     * List Account Companies
     * Bootstrap active company choices from the authenticated person, ignoring selection headers.
     *
     * Actual memberships use current workspace roles; verified platform owners also see virtual
     * support contexts without creating memberships. Invalid JWTs return401. Multiple companies
     * require explicit selection on business requests, never on this account bootstrap.
     * @param page
     * @param limit
     * @returns ManagerAccountCompaniesResponse Successful Response
     * @throws ApiError
     */
    public static managerListAccountCompanies(
        page: number = 1,
        limit: number = 100,
    ): CancelablePromise<ManagerAccountCompaniesResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/account/companies',
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
