/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type ManagerCustomerContractItemResponse = {
    source_kind?: 'google' | 'crm';
    can_delete?: boolean;
    legal_entity_id?: (number | null);
    source_document_id?: (number | null);
    source_order_id?: (number | null);
    id: number;
    customer_id: number;
    number: string;
    valid_from: string;
    valid_until: string;
    status: string;
    template_id?: (string | null);
    document_role_type?: (string | null);
    edit_url?: (string | null);
    created_at: string;
    updated_at?: (string | null);
};

