/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ManagerCustomerReconciliationDocumentItem } from './ManagerCustomerReconciliationDocumentItem';
import type { ManagerCustomerReconciliationPaymentItem } from './ManagerCustomerReconciliationPaymentItem';
export type ManagerCustomerReconciliationResponse = {
    customer_id: number;
    date_from: string;
    date_to: string;
    opening_balance?: number;
    documents_total?: number;
    payments_total?: number;
    closing_balance?: number;
    documents?: Array<ManagerCustomerReconciliationDocumentItem>;
    payments?: Array<ManagerCustomerReconciliationPaymentItem>;
};

