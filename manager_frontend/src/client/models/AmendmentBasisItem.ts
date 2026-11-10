/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type AmendmentBasisItem = {
    document_id: number;
    legal_entity_id: number;
    number: string;
    date: (string | null);
    status: string;
    original_amount: string;
    effective_additions: string;
    agreed_total: string;
    currency: string;
    revision: string;
    seller_name: string;
    customer_name: string;
    lines: Array<Record<string, string>>;
};

