/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type LeadsInboxItemResponse = {
    id: number;
    status: string;
    is_new: boolean;
    customer_id?: (number | null);
    customer_name?: (string | null);
    phone?: (string | null);
    email?: (string | null);
    source?: (string | null);
    comment?: (string | null);
    no_answer_at?: (string | null);
    source_created_at?: (string | null);
    created_at: string;
    customer_type?: (string | null);
    customer_inn?: (string | null);
    customer_full_legal_name?: (string | null);
    customer_delivery_address?: (string | null);
    object_type?: (string | null);
    service_type?: (string | null);
    equipment_class?: (string | null);
    marketing_source?: (string | null);
};

