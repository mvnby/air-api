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
     * @param equipmentType
     * @param equipmentSubtype
     * @param brandId
     * @param seriesId
     * @param seriesState
     * @param supplierId
     * @param supplierState
     * @param publication
     * @param availability
     * @param priority
     * @param scoreMin
     * @param scoreMax
     * @param onlyFixable
     * @param sortBy
     * @param groupBy
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
        equipmentType?: (string | null),
        equipmentSubtype?: (string | null),
        brandId?: (number | null),
        seriesId?: (number | null),
        seriesState?: ('assigned' | 'missing' | null),
        supplierId?: (number | null),
        supplierState?: ('mapped' | 'in_stock' | 'unmapped' | 'multiple' | null),
        publication?: ('published' | 'hidden' | null),
        availability?: ('in_stock' | 'out_of_stock' | null),
        priority?: ('high' | 'medium' | 'low' | null),
        scoreMin?: (number | null),
        scoreMax?: (number | null),
        onlyFixable: boolean = false,
        sortBy: 'priority' | 'score_asc' | 'critical' | 'stock' | 'newest' | 'title' | 'brand' | 'series' = 'priority',
        groupBy: 'none' | 'brand' | 'series' | 'supplier' | 'equipment_type' = 'none',
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
                'equipment_type': equipmentType,
                'equipment_subtype': equipmentSubtype,
                'brand_id': brandId,
                'series_id': seriesId,
                'series_state': seriesState,
                'supplier_id': supplierId,
                'supplier_state': supplierState,
                'publication': publication,
                'availability': availability,
                'priority': priority,
                'score_min': scoreMin,
                'score_max': scoreMax,
                'only_fixable': onlyFixable,
                'sort_by': sortBy,
                'group_by': groupBy,
            },
            errors: {
                422: `Validation Error`,
            },
        });
    }
}
