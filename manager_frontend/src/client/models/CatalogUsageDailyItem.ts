/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type CatalogUsageDailyItem = {
    device: 'mobile' | 'tablet' | 'desktop';
    action: 'product_open' | 'filter_apply' | 'filter_zero_results' | 'edit_basics' | 'edit_pricing' | 'edit_specifications' | 'edit_gallery' | 'edit_features' | 'bulk_edit' | 'gallery_quick_exit' | 'media_load';
    outcome: 'success' | 'cancelled' | 'failed' | 'zero_results' | 'quick_exit';
    duration_bucket?: 'none' | 'under_1s' | '1_3s' | '3_10s' | '10_30s' | 'over_30s';
    day: string;
    layout_version: string;
    count: number;
};

