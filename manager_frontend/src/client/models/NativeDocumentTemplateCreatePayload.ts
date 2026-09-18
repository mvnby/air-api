/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type NativeDocumentTemplateCreatePayload = {
    document_role_type?: ('seller_buyer' | 'executor_customer' | 'contractor_customer' | null);
    legal_entity_id: number;
    name: string;
    doc_type: string;
    description?: (string | null);
    contract_scenario?: (string | null);
    business_role?: (string | null);
};

