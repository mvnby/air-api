/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ManagerCatalogQualityReportResponse } from '../models/ManagerCatalogQualityReportResponse';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class ManagerCatalogQualityService {
    /**
     * Get Manager Catalog Quality Report
     * @param page
     * @param limit
     * @param q
     * @param category
     * @param severity
     * @param issueCode
     * @param onlyProblems
     * @returns ManagerCatalogQualityReportResponse Successful Response
     * @throws ApiError
     */
    public static getManagerCatalogQualityReport(
        page: number = 1,
        limit: number = 40,
        q?: (string | null),
        category?: ('media' | 'identity' | 'specs' | 'commerce' | 'supplier' | null),
        severity?: ('critical' | 'warning' | 'info' | null),
        issueCode?: (string | null),
        onlyProblems: boolean = true,
    ): CancelablePromise<ManagerCatalogQualityReportResponse> {
        return __request(OpenAPI, {
            method: 'GET',
            url: '/api/manager/catalog-quality/report',
            query: {
                'page': page,
                'limit': limit,
                'q': q,
                'category': category,
                'severity': severity,
                'issue_code': issueCode,
                'only_problems': onlyProblems,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
