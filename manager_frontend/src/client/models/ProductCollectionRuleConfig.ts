/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type ProductCollectionRuleConfig = {
    product_kinds?: Array<'unknown' | 'complete_split_system' | 'indoor_unit' | 'outdoor_unit' | 'panel' | 'accessory' | 'consumable' | 'other'>;
    min_price?: (number | null);
    max_price?: (number | null);
    min_area_m2?: (number | null);
    max_area_m2?: (number | null);
    max_noise_min_db?: (number | null);
    max_heating_min_c?: (number | null);
    is_inverter?: (boolean | null);
    wifi_states?: Array<'builtin' | 'ready' | 'none'>;
    brand_ids?: Array<number>;
    series_ids?: Array<number>;
    colors?: Array<string>;
    feature_ids?: Array<number>;
    public_stock_states?: Array<'local_stock' | 'supplier_stock' | 'available_to_order' | 'out_of_stock'>;
};

