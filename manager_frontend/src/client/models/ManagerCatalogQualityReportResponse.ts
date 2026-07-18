/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ManagerCatalogQualityCategoryResponse } from './ManagerCatalogQualityCategoryResponse';
import type { ManagerCatalogQualityFilterOptionsResponse } from './ManagerCatalogQualityFilterOptionsResponse';
import type { ManagerCatalogQualityGroupResponse } from './ManagerCatalogQualityGroupResponse';
import type { ManagerCatalogQualityProductResponse } from './ManagerCatalogQualityProductResponse';
import type { ManagerCatalogQualitySummaryItemResponse } from './ManagerCatalogQualitySummaryItemResponse';
import type { Meta } from './Meta';
export type ManagerCatalogQualityReportResponse = {
    generated_at: string;
    total_products: number;
    problem_products: number;
    critical_products: number;
    fixable_products: number;
    average_score: number;
    items: Array<ManagerCatalogQualityProductResponse>;
    summary: Array<ManagerCatalogQualitySummaryItemResponse>;
    categories: Array<ManagerCatalogQualityCategoryResponse>;
    groups?: Array<ManagerCatalogQualityGroupResponse>;
    filter_options: ManagerCatalogQualityFilterOptionsResponse;
    severity_issue_counts?: Record<string, number>;
    severity_product_counts?: Record<string, number>;
    meta: Meta;
};

