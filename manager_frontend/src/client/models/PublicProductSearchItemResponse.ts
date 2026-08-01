/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * Small public projection; internal sourcing and margin data is excluded.
 */
export type PublicProductSearchItemResponse = {
    id: number;
    title: string;
    slug?: (string | null);
    price: number;
    old_price?: (number | null);
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
};

