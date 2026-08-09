/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { FeatureRulePayload } from './FeatureRulePayload';
export type FeatureUpdatePayload = {
    slug?: (string | null);
    name?: (string | null);
    short_description?: (string | null);
    full_description?: (string | null);
    category_id?: (number | null);
    scope_type?: ('universal' | 'brand' | null);
    brand_id?: (number | null);
    replaces_feature_id?: (number | null);
    icon_media_id?: (number | null);
    image_media_id?: (number | null);
    icon?: (string | null);
    image_url?: (string | null);
    video_url?: (string | null);
    footnote?: (string | null);
    source_url?: (string | null);
    aliases?: (Array<string> | null);
    seo_title?: (string | null);
    seo_description?: (string | null);
    source_notes?: (string | null);
    legal_notes?: (string | null);
    is_active?: (boolean | null);
    sort_order?: (number | null);
    rules?: (Array<FeatureRulePayload> | null);
};

