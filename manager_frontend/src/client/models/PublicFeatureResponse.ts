/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { FeatureCategoryResponse } from './FeatureCategoryResponse';
export type PublicFeatureResponse = {
    id: number;
    slug: string;
    name: string;
    short_description?: (string | null);
    full_description?: (string | null);
    category: FeatureCategoryResponse;
    scope_type: 'universal' | 'brand' | 'series' | 'product' | 'derived';
    source: 'product_override' | 'product_manual' | 'series' | 'brand' | 'derived';
    is_overridden?: boolean;
    sort_order?: number;
    feature_sort_order?: number;
    icon?: (string | null);
    icon_url?: (string | null);
    image_url?: (string | null);
    video_url?: (string | null);
    footnote?: (string | null);
    applied_rule?: (string | null);
};

