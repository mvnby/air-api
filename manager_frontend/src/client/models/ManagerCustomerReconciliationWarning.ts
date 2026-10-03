/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type ManagerCustomerReconciliationWarning = {
    code: string;
    message: string;
    order_id?: (number | null);
    document_id?: (number | null);
    payment_id?: (number | null);
    related_document_ids?: Array<number>;
    can_review_legacy?: boolean;
};

