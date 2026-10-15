/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { CatalogDecisionProductResponse } from './CatalogDecisionProductResponse';
import type { ManagerTenantCatalogImageResponse } from './ManagerTenantCatalogImageResponse';
import type { ManagerTenantCatalogManualResponse } from './ManagerTenantCatalogManualResponse';
import type { ManagerTenantCatalogSpecificationGroupResponse } from './ManagerTenantCatalogSpecificationGroupResponse';
import type { ManagerTenantCatalogSpecificationResponse } from './ManagerTenantCatalogSpecificationResponse';
/**
 * Shared product content with only the current storefront's commercial view.
 */
export type ManagerTenantCatalogProductDetailResponse = {
    id: number;
    title: string;
    slug: string;
    brand_title?: (string | null);
    series_title?: (string | null);
    main_image?: (string | null);
    /**
     * Plain text; render as text, never HTML.
     */
    description?: string;
    images?: Array<ManagerTenantCatalogImageResponse>;
    summary_fields?: Array<ManagerTenantCatalogSpecificationResponse>;
    specification_groups?: Array<ManagerTenantCatalogSpecificationGroupResponse>;
    manuals?: Array<ManagerTenantCatalogManualResponse>;
    effective_price?: (number | null);
    allowed: boolean;
    /**
     * Current eligible decision projection; absent when selection is unavailable.
     */
    selection_item?: (CatalogDecisionProductResponse | null);
};

