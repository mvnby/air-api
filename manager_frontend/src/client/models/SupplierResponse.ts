/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type SupplierResponse = {
    id: number;
    name: string;
    code: string;
    is_active: boolean;
    priority: number;
    spreadsheet_id?: (string | null);
    spreadsheet_url?: (string | null);
    google_sheet_synced_at?: (string | null);
    legal_name?: (string | null);
    tax_id?: (string | null);
    legal_address?: (string | null);
    postal_address?: (string | null);
    default_payment_method?: string;
    payment_comment?: (string | null);
    created_at: string;
    updated_at: string;
};

