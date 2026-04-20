/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ProductManualPayload } from './ProductManualPayload';
export type ProductUpdate = {
    title?: (string | null);
    price?: (number | null);
    old_price?: (number | null);
    slug?: (string | null);
    specs?: (Record<string, any> | null);
    is_published?: (boolean | null);
    brand_id?: (number | null);
    series_id?: (number | null);
    tag_ids?: (Array<number> | null);
    manuals?: Array<ProductManualPayload>;
};

