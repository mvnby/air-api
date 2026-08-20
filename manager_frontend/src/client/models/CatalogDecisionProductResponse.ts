/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type CatalogDecisionProductResponse = {
    id: number;
    title: string;
    slug: string;
    main_image?: (string | null);
    brand_title?: (string | null);
    series_title?: (string | null);
    retail_price_byn: number;
    purchase_cost_byn?: (number | null);
    recommended_price_byn?: (number | null);
    margin_abs_byn?: (number | null);
    margin_pct?: (number | null);
    supplier_name?: (string | null);
    supplier_qty?: number;
    availability: 'in_stock' | 'out_of_stock';
    cooling_power_kw?: (number | null);
    cooling_min_kw?: (number | null);
    cooling_max_kw?: (number | null);
    area_m2?: (number | null);
    category?: (string | null);
    indoor_form_factor?: (string | null);
    is_inverter: boolean;
    wifi?: 'builtin' | 'ready' | 'none';
    is_published: boolean;
};

