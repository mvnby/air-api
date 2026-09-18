/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type CatalogManagementFilters = {
    search?: (string | null);
    brand_ids?: Array<number>;
    series_ids?: Array<number>;
    supplier_id?: (number | null);
    category?: ('household' | 'multi' | 'semi_industrial' | null);
    category_missing?: boolean;
    cooling_btu_classes?: Array<7 | 9 | 12 | 18 | 24 | 30 | 36 | 42 | 60>;
    cooling_min_kw?: (number | null);
    cooling_max_kw?: (number | null);
    retail_min_byn?: (number | null);
    retail_max_byn?: (number | null);
    area_min?: (number | null);
    area_max?: (number | null);
    indoor_form_factor?: ('wall' | 'cassette' | 'duct' | 'floor_ceiling' | 'column' | 'console' | null);
    heating_min?: (-20 | -25 | -30 | null);
    is_inverter?: (boolean | null);
    wifi?: ('builtin' | 'ready' | 'none' | null);
    availability?: ('in_stock' | 'out_of_stock' | null);
    is_published?: (boolean | null);
    missing?: ('brand' | 'series' | 'image' | 'price' | null);
    feature_id?: (number | null);
    has_feature?: (boolean | null);
    in_yandex_feed?: (boolean | null);
};

