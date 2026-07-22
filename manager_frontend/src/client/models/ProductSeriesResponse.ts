/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ProductSeriesBrandFeatureResponse } from './ProductSeriesBrandFeatureResponse';
import type { ProductSeriesContentBlockResponse } from './ProductSeriesContentBlockResponse';
import type { ProductSeriesFeatureBlockResponse } from './ProductSeriesFeatureBlockResponse';
import type { PublicFeatureResponse } from './PublicFeatureResponse';
export type ProductSeriesResponse = {
    id: number;
    title: string;
    slug: string;
    tagline?: (string | null);
    short_description?: (string | null);
    description?: (string | null);
    hero_image?: (string | null);
    gallery_images?: Array<string>;
    features?: Array<string>;
    brand_features?: Array<ProductSeriesBrandFeatureResponse>;
    catalog_features?: Array<PublicFeatureResponse>;
    feature_blocks?: Array<ProductSeriesFeatureBlockResponse>;
    content_blocks?: Array<ProductSeriesContentBlockResponse>;
    footnotes?: Array<string>;
    seo_title?: (string | null);
    seo_description?: (string | null);
    source_url?: (string | null);
};

