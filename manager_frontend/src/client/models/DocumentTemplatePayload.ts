/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type DocumentTemplatePayload = {
    name: string;
    doc_type: string;
    google_template_id: string;
    document_role_type?: (string | null);
    description?: (string | null);
    base_document_type_label?: (string | null);
    is_default?: boolean;
    is_active?: boolean;
    is_open_contract?: boolean;
    client_restricted?: boolean;
    sort_order?: number;
    customer_ids?: Array<number>;
    linked_contract_template_ids?: Array<number>;
    linked_act_template_ids?: Array<number>;
};

