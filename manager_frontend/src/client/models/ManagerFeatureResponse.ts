/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { FeatureCategoryResponse } from './FeatureCategoryResponse';
import type { FeatureRuleResponse } from './FeatureRuleResponse';
export type ManagerFeatureResponse = {
    id: number;
    slug: string;
    name: string;
    short_description?: (string | null);
    full_description?: (string | null);
    category: FeatureCategoryResponse;
    scope_type: 'universal' | 'brand' | 'series' | 'product' | 'derived';
    brand_id?: (number | null);
    replaces_feature_id?: (number | null);
    icon_media_id?: (number | null);
    image_media_id?: (number | null);
    icon?: (string | null);
    icon_url?: (string | null);
    image_url?: (string | null);
    video_url?: (string | null);
    footnote?: (string | null);
    source_url?: (string | null);
    aliases?: Array<string>;
    seo_title?: (string | null);
    seo_description?: (string | null);
    source_notes?: (string | null);
    legal_notes?: (string | null);
    is_active: boolean;
    sort_order: number;
    rules?: Array<FeatureRuleResponse>;
    brands_count?: number;
    series_count?: number;
    products_count?: number;
    created_at: string;
    updated_at: string;
    archived_at?: (string | null);
};

