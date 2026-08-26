/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type DocumentLegalEntityItem = {
    id: number;
    tenant_id: number;
    slug: string;
    display_name: string;
    legal_name?: (string | null);
    unp?: (string | null);
    is_vat_payer: boolean;
    is_default: boolean;
    requisites: Record<string, string>;
    status: string;
    created_at: string;
    updated_at: string;
};

