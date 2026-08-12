/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type SupplierOfferCandidateResponse = {
    offer_id: number;
    supplier_id: number;
    supplier_name?: (string | null);
    source_id?: (number | null);
    source_name?: (string | null);
    external_id: string;
    title_raw?: (string | null);
    title_normalized?: (string | null);
    source_url?: (string | null);
    model_tokens?: Array<string>;
    qty?: number;
    qty_raw?: (string | null);
    wholesale_raw?: (string | null);
    wholesale_value?: (number | null);
    wholesale_currency?: (string | null);
    rrc_raw?: (string | null);
    rrc_byn?: (number | null);
    is_active: boolean;
    status: 'current' | 'free' | 'conflict' | 'inactive';
    mapping_id?: (number | null);
    mapping_is_active?: (boolean | null);
    mapped_product_id?: (number | null);
    mapped_product_title?: (string | null);
    mapped_product_slug?: (string | null);
    mapped_by?: (string | null);
    mapped_at?: (string | null);
    updated_at: string;
};

