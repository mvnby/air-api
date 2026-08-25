/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ProductBrandResponse } from './ProductBrandResponse';
import type { ProductImageResponse } from './ProductImageResponse';
import type { ProductManualResponse } from './ProductManualResponse';
import type { ProductSeriesResponse } from './ProductSeriesResponse';
import type { ProductSiblingResponse } from './ProductSiblingResponse';
import type { PublicFeatureResponse } from './PublicFeatureResponse';
import type { TagResponse } from './TagResponse';
export type ProductResponse = {
    id: number;
    title: string;
    slug: (string | null);
    price: number;
    old_price: (number | null);
    product_kind?: 'unknown' | 'complete_split_system' | 'indoor_unit' | 'outdoor_unit' | 'panel' | 'accessory' | 'consumable' | 'other';
    is_inverter: boolean;
    power_cooling: (number | null);
    main_image: (string | null);
    card_image?: (string | null);
    full_image?: (string | null);
    is_published: boolean;
    created_at: string;
    installation_discount?: number;
    vitebsk_qty?: number;
    minsk_qty?: number;
    availability_status?: (string | null);
    public_stock_state?: ('local_stock' | 'supplier_stock' | 'available_to_order' | 'out_of_stock' | null);
    delivery_min_days?: (number | null);
    delivery_max_days?: (number | null);
    brand?: (ProductBrandResponse | null);
    series?: (ProductSeriesResponse | null);
    tags?: Array<TagResponse>;
    specs?: Record<string, any>;
    images?: Array<string>;
    gallery_images?: Array<ProductImageResponse>;
    manuals?: Array<ProductManualResponse>;
    series_siblings?: Array<ProductSiblingResponse>;
    features?: Array<PublicFeatureResponse>;
};

