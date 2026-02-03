/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class DefaultService {
    /**
     * Serve Manager App
     * @param fullPath
     * @returns any Successful Response
     * @throws ApiError
     */
    public static serveManagerAppManagerFullPathGet(
        fullPath: string,
    ): CancelablePromise<any> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/manager/{full_path}',
            path: {
                'full_path': fullPath,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
