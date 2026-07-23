/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ProductManualPayload } from './ProductManualPayload';
export type ProductDuplicatePayload = {
    title?: (string | null);
    price?: (number | null);
    old_price?: (number | null);
    product_kind?: ('unknown' | 'complete_split_system' | 'indoor_unit' | 'outdoor_unit' | 'panel' | 'accessory' | 'consumable' | 'other' | null);
    slug?: (string | null);
    description?: (string | null);
    is_inverter?: (boolean | null);
    power_cooling?: (number | null);
    main_image?: (string | null);
    source_url?: (string | null);
    specs?: (Record<string, any> | null);
    is_published?: (boolean | null);
    brand_id?: (number | null);
    series_id?: (number | null);
    tag_ids?: (Array<number> | null);
    manuals?: Array<ProductManualPayload>;
    copy_gallery?: boolean;
    copy_manuals?: boolean;
    copy_tags?: boolean;
    make_unpublished?: boolean;
};

