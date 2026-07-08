/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { SupplyRequestLineResponse } from './SupplyRequestLineResponse';
export type SupplyRequestResponse = {
    id: number;
    supplier_id: number;
    supplier_name?: (string | null);
    warehouse_id?: (number | null);
    warehouse_name?: (string | null);
    warehouse_address?: (string | null);
    supplier_contact_id?: (number | null);
    supplier_contact_name?: (string | null);
    logistics_contact_id?: (number | null);
    logistics_contact_name?: (string | null);
    status: string;
    intent: string;
    payment_method: string;
    comment?: (string | null);
    supplier_message_snapshot?: (string | null);
    logistics_message_snapshot?: (string | null);
    created_by?: (string | null);
    supplier_message_sent_at?: (string | null);
    logistics_message_sent_at?: (string | null);
    created_at: string;
    updated_at: string;
    lines?: Array<SupplyRequestLineResponse>;
};

