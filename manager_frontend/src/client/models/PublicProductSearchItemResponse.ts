/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { PublicProductWarrantyResponse } from './PublicProductWarrantyResponse';
/**
 * Small public projection; internal sourcing and margin data is excluded.
 */
export type PublicProductSearchItemResponse = {
    /**
     * Exact manufacturer designation from canonical model specs; null when unconfirmed.
     */
    model_code?: (string | null);
    /**
     * Confirmed nominal capacity class (e.g. 07, 09, 12); never inferred from title or kW. Null when unknown or inapplicable.
     */
    capacity_class?: (string | null);
    id: number;
    title: string;
    slug?: (string | null);
    price: number;
    old_price?: (number | null);
    installation_discount?: number;
    product_kind?: 'unknown' | 'complete_split_system' | 'indoor_unit' | 'outdoor_unit' | 'panel' | 'accessory' | 'consumable' | 'other';
    is_inverter: boolean;
    power_cooling?: (number | null);
    main_image?: (string | null);
    card_image?: (string | null);
    full_image?: (string | null);
    specs?: Record<string, any>;
    vitebsk_qty?: number;
    minsk_qty?: number;
    availability_status?: (string | null);
    public_stock_state?: ('local_stock' | 'supplier_stock' | 'available_to_order' | 'out_of_stock' | null);
    delivery_min_days?: (number | null);
    delivery_max_days?: (number | null);
    warranty?: (PublicProductWarrantyResponse | null);
};

