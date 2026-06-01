/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type DocumentTemplateItem = {
    id: string;
    document_template_id?: (number | null);
    name: string;
    document_role_type?: string;
    is_open_contract?: boolean;
    doc_type?: string;
    description?: (string | null);
    base_document_type_label?: (string | null);
    is_default?: boolean;
    is_active?: boolean;
    client_restricted?: boolean;
    sort_order?: number;
    customer_ids?: Array<number>;
    linked_contract_template_ids?: Array<number>;
    linked_act_template_ids?: Array<number>;
};

