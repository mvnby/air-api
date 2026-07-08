/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type SupplyRequestLineResponse = {
    id: number;
    request_id: number;
    order_product_link_id?: (number | null);
    source_type: string;
    product_id?: (number | null);
    product_title?: (string | null);
    supplier_offer_external_id?: (string | null);
    supplier_offer_title?: (string | null);
    title_snapshot: string;
    qty: number;
    unit_cost_snapshot?: (number | null);
    status: string;
    reserved_until?: (string | null);
    received_qty: number;
    comment?: (string | null);
    created_at: string;
    updated_at: string;
};

