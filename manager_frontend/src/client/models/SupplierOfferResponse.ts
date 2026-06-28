/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type SupplierOfferResponse = {
    supplier_id: number;
    source_id?: (number | null);
    source_name?: (string | null);
    supplier_name?: (string | null);
    external_id: string;
    title_raw?: (string | null);
    title_normalized?: (string | null);
    model_tokens?: Array<string>;
    indoor_model_tokens?: Array<string>;
    outdoor_model_tokens?: Array<string>;
    match_normalizer_version?: (string | null);
    qty: number;
    qty_raw?: (string | null);
    wholesale_raw?: (string | null);
    wholesale_value?: (number | null);
    wholesale_currency?: (string | null);
    rrc_raw?: (string | null);
    rrc_byn?: (number | null);
    is_active: boolean;
    mapping_id?: (number | null);
    product_id?: (number | null);
    product_title?: (string | null);
    updated_at: string;
};

