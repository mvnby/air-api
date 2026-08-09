/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ManagerFeatureSeriesAssignmentPayload } from './ManagerFeatureSeriesAssignmentPayload';
import type { ProductSeriesContentBlockResponse } from './ProductSeriesContentBlockResponse';
import type { ProductSeriesFeatureBlockResponse } from './ProductSeriesFeatureBlockResponse';
export type ManagerBrandSeriesUpdatePayload = {
    title?: (string | null);
    slug?: (string | null);
    tagline?: (string | null);
    short_description?: (string | null);
    description?: (string | null);
    hero_image?: (string | null);
    gallery_images?: (Array<string> | null);
    features?: (Array<string> | null);
    brand_feature_ids?: (Array<number> | null);
    feature_assignments?: (Array<ManagerFeatureSeriesAssignmentPayload> | null);
    feature_blocks?: (Array<ProductSeriesFeatureBlockResponse> | null);
    content_blocks?: (Array<ProductSeriesContentBlockResponse> | null);
    footnotes?: (Array<string> | null);
    seo_title?: (string | null);
    seo_description?: (string | null);
    source_url?: (string | null);
    is_featured?: (boolean | null);
    is_published?: (boolean | null);
    sort_order?: (number | null);
};

