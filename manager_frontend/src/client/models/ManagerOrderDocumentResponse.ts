/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type ManagerOrderDocumentResponse = {
    doc_id: number;
    proposal_id?: (number | null);
    base_document_id?: (number | null);
    base_customer_contract_id?: (number | null);
    scope_customer_branch_id?: (number | null);
    scope_title?: (string | null);
    scope_address?: (string | null);
    scope_meta?: Record<string, any>;
    doc_type: string;
    edit_url: string;
};

