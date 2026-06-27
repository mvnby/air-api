/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ProductSeriesContentBlockResponse } from './ProductSeriesContentBlockResponse';
import type { ProductSeriesFeatureBlockResponse } from './ProductSeriesFeatureBlockResponse';
export type ManagerBrandSeriesResponse = {
    id: number;
    brand_id?: (number | null);
    title: string;
    slug: string;
    tagline?: (string | null);
    short_description?: (string | null);
    description?: (string | null);
    hero_image?: (string | null);
    gallery_images?: Array<string>;
    features?: Array<string>;
    feature_blocks?: Array<ProductSeriesFeatureBlockResponse>;
    content_blocks?: Array<ProductSeriesContentBlockResponse>;
    footnotes?: Array<string>;
    seo_title?: (string | null);
    seo_description?: (string | null);
    source_url?: (string | null);
    is_published: boolean;
    sort_order: number;
    created_at: string;
    products_count?: number;
};

