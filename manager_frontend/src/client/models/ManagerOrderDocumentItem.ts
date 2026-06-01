/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type ManagerOrderDocumentItem = {
    id: number;
    proposal_id?: (number | null);
    base_document_id?: (number | null);
    base_customer_contract_id?: (number | null);
    base_document_type?: (string | null);
    base_document_type_label?: (string | null);
    base_document_number?: (string | null);
    base_document_date?: (string | null);
    doc_type: string;
    number: string;
    date: string;
    edit_url?: (string | null);
    is_downloadable?: boolean;
};

