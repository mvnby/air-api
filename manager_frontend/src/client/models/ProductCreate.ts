/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ProductManualPayload } from './ProductManualPayload';
export type ProductCreate = {
    title: string;
    price?: number;
    old_price?: (number | null);
    slug?: (string | null);
    description?: string;
    area?: number;
    is_inverter?: boolean;
    power_cooling?: (number | null);
    main_image?: (string | null);
    source_url?: (string | null);
    specs?: Record<string, any>;
    is_published?: boolean;
    brand_id?: (number | null);
    series_id?: (number | null);
    tag_ids?: Array<number>;
    manuals?: Array<ProductManualPayload>;
};

