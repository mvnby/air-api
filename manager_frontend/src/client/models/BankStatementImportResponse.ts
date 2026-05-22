/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type BankStatementImportResponse = {
    rows?: number;
    credit_rows?: number;
    created?: number;
    matched_existing?: number;
    skipped?: number;
    suspicious?: number;
    receipt_ids?: Array<number>;
    created_receipt_ids?: Array<number>;
    matched_receipt_ids?: Array<number>;
    suspicious_receipt_ids?: Array<number>;
};

