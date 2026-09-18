/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type NativeDocumentTemplateItem = {
    document_role_type?: ('seller_buyer' | 'executor_customer' | 'contractor_customer' | 'seller_payer' | 'executor_payer' | null);
    id: number;
    tenant_id: number;
    legal_entity_id: number;
    name: string;
    doc_type: string;
    description?: (string | null);
    contract_scenario?: (string | null);
    business_role?: (string | null);
    is_default: boolean;
    is_active: boolean;
    sort_order: number;
    created_at: string;
};

