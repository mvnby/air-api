/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ProductCollectionRuleConfig } from './ProductCollectionRuleConfig';
export type ManagerProductCollectionUpdate = {
    slug?: (string | null);
    internal_name?: (string | null);
    public_title?: (string | null);
    public_description?: (string | null);
    public_badge?: (string | null);
    cta_label?: (string | null);
    cta_url?: (string | null);
    editorial_note?: (string | null);
    status?: ('draft' | 'published' | 'archived' | null);
    mode?: ('manual' | 'automatic' | 'hybrid' | null);
    sort_mode?: ('recommended' | 'price_asc' | 'price_desc' | 'area_asc' | 'area_desc' | 'newest' | null);
    rule_config?: (ProductCollectionRuleConfig | null);
    min_items?: (number | null);
    max_items?: (number | null);
    fallback_collection_id?: (number | null);
    starts_at?: (string | null);
    ends_at?: (string | null);
};

