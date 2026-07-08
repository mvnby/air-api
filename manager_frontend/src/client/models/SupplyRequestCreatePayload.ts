/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { SupplyRequestLineCreatePayload } from './SupplyRequestLineCreatePayload';
export type SupplyRequestCreatePayload = {
    supplier_id: number;
    warehouse_id?: (number | null);
    supplier_contact_id?: (number | null);
    logistics_contact_id?: (number | null);
    intent?: string;
    payment_method?: (string | null);
    comment?: (string | null);
    lines: Array<SupplyRequestLineCreatePayload>;
};

