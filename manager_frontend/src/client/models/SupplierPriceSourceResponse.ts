/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type SupplierPriceSourceResponse = {
    id: number;
    supplier_id: number;
    supplier_name?: (string | null);
    source_type: string;
    sheet_name?: (string | null);
    range_a1?: (string | null);
    city_bucket: string;
    header_row_index: number;
    col_external_id: string;
    col_title: string;
    col_wholesale: string;
    col_wholesale_currency: string;
    col_rrc_byn: string;
    col_qty: string;
    col_source_url?: (string | null);
    is_active: boolean;
    last_sync_at?: (string | null);
    last_sync_status?: (string | null);
    last_sync_error?: (string | null);
    created_at: string;
    updated_at: string;
};

