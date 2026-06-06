/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ProductBrandResponse } from './ProductBrandResponse';
import type { ProductImageResponse } from './ProductImageResponse';
import type { ProductManualResponse } from './ProductManualResponse';
import type { ProductSiblingResponse } from './ProductSiblingResponse';
import type { TagResponse } from './TagResponse';
export type ProductResponse = {
    id: number;
    title: string;
    slug: (string | null);
    price: number;
    old_price: (number | null);
    area: number;
    is_inverter: boolean;
    power_cooling: (number | null);
    main_image: (string | null);
    card_image?: (string | null);
    full_image?: (string | null);
    is_published: boolean;
    created_at: string;
    vitebsk_qty?: number;
    minsk_qty?: number;
    availability_status?: (string | null);
    brand?: (ProductBrandResponse | null);
    tags?: Array<TagResponse>;
    specs?: Record<string, any>;
    images?: Array<string>;
    gallery_images?: Array<ProductImageResponse>;
    manuals?: Array<ProductManualResponse>;
    series_siblings?: Array<ProductSiblingResponse>;
};

