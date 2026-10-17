/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { WorkerPayWorkspace } from '../models/WorkerPayWorkspace';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class InstallerPayService {
    /**
     * Own Pay
     * Read only personal pay history without order costs, other staff pay or private notes.
     *
     * Live identity and actual company membership are required; work closure/revocation
     * does not erase liabilities. Pagination is bounded, reads create no account.
     * @param page
     * @param limit
     * @returns WorkerPayWorkspace Successful Response
     * @throws ApiError
     */
    public static getInstallerPay(
        page: number = 1,
        limit: number = 50,
    ): CancelablePromise<WorkerPayWorkspace> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/installer/pay',
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
