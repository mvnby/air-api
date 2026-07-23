/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ProductCollectionExclusionResponse } from './ProductCollectionExclusionResponse';
import type { PublicProductCollectionItemResponse } from './PublicProductCollectionItemResponse';
export type ProductCollectionPreviewResponse = {
    collection_id: number;
    collection_slug: string;
    below_min_items: boolean;
    fallback_used?: boolean;
    items?: Array<PublicProductCollectionItemResponse>;
    excluded_items?: Array<ProductCollectionExclusionResponse>;
};

