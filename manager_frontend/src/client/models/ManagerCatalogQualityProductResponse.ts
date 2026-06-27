/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ManagerCatalogQualityIssueResponse } from './ManagerCatalogQualityIssueResponse';
export type ManagerCatalogQualityProductResponse = {
    product_id: number;
    title: string;
    slug?: (string | null);
    brand_id?: (number | null);
    brand_title?: (string | null);
    series_id?: (number | null);
    series_title?: (string | null);
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
    available_qty?: number;
    issues?: Array<ManagerCatalogQualityIssueResponse>;
};

