/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type ProductMainImageCleanupItemResponse = {
    id?: (number | null);
    batch_id?: (number | null);
    product_id: number;
    product_title?: (string | null);
    product_slug?: (string | null);
    product_brand_id?: (number | null);
    product_brand_title?: (string | null);
    product_series_id?: (number | null);
    product_series_title?: (string | null);
    product_model?: (string | null);
    product_current_main_image?: (string | null);
    source_product_image_id?: (number | null);
    original_image_url: string;
    candidate_image_url?: (string | null);
    approved_image_url?: (string | null);
    status: string;
    skip_reason?: (string | null);
    reject_reason?: (string | null);
    failure_reason?: (string | null);
    processor_method?: (string | null);
    processor_version?: (string | null);
    confidence_score?: (number | null);
    quality_score?: (number | null);
    candidate_storage_provider?: (string | null);
    candidate_content_hash?: (string | null);
    candidate_width?: (number | null);
    candidate_height?: (number | null);
    approved_by?: (string | null);
    created_at: string;
    updated_at: string;
    approved_at?: (string | null);
};

