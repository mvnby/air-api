/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ManagerCatalogQualityIssueResponse } from './ManagerCatalogQualityIssueResponse';
import type { ManagerCatalogQualitySupplierResponse } from './ManagerCatalogQualitySupplierResponse';
export type ManagerCatalogQualityProductResponse = {
    product_id: number;
    title: string;
    slug?: (string | null);
    brand_id?: (number | null);
    brand_title?: (string | null);
    series_id?: (number | null);
    series_title?: (string | null);
    equipment_type?: (string | null);
    equipment_type_label?: (string | null);
    equipment_subtype?: (string | null);
    equipment_subtype_label?: (string | null);
    main_image?: (string | null);
    price?: number;
    is_published?: boolean;
    score: number;
    issue_count: number;
    image_count?: number;
    main_image_width?: (number | null);
    main_image_height?: (number | null);
    media_status?: string;
    supplier_mapping_count?: number;
    suppliers?: Array<ManagerCatalogQualitySupplierResponse>;
    available_qty?: number;
    created_at?: (string | null);
    critical_issue_count?: number;
    fixable_issue_count?: number;
    work_priority?: 'high' | 'medium' | 'low';
    priority_reason?: string;
    group_key?: (string | null);
    group_label?: (string | null);
    issues?: Array<ManagerCatalogQualityIssueResponse>;
};

