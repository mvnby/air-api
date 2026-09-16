/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ProductCollectionExclusionResponse } from './ProductCollectionExclusionResponse';
import type { PublicProductCollectionItemResponse } from './PublicProductCollectionItemResponse';
export type ProductCollectionPreviewResponse = {
    display_mode?: 'carousel' | 'grid' | 'tiles' | 'single';
    item_limit?: (number | null);
    grid_columns?: number;
    rotation_mode?: 'none' | 'daily';
    collection_id: number;
    collection_slug: string;
    below_min_items: boolean;
    fallback_used?: boolean;
    items?: Array<PublicProductCollectionItemResponse>;
    excluded_items?: Array<ProductCollectionExclusionResponse>;
};

