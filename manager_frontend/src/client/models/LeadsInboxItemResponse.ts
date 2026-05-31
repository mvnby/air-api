/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type LeadsInboxItemResponse = {
    id: number;
    status: string;
    is_new: boolean;
    customer_name?: (string | null);
    phone?: (string | null);
    email?: (string | null);
    source?: (string | null);
    comment?: (string | null);
    no_answer_at?: (string | null);
    source_created_at?: (string | null);
    created_at: string;
    customer_type?: string;
    customer_inn?: (string | null);
    customer_full_legal_name?: (string | null);
};

