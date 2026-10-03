/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ManagerCustomerReconciliationDocumentItem } from './ManagerCustomerReconciliationDocumentItem';
import type { ManagerCustomerReconciliationPaymentItem } from './ManagerCustomerReconciliationPaymentItem';
import type { ManagerCustomerReconciliationWarning } from './ManagerCustomerReconciliationWarning';
export type ManagerCustomerReconciliationResponse = {
    customer_id: number;
    contract_id?: (number | null);
    ready_for_generation?: boolean;
    warnings?: Array<ManagerCustomerReconciliationWarning>;
    date_from: string;
    date_to: string;
    opening_balance?: number;
    documents_total?: number;
    payments_total?: number;
    closing_balance?: number;
    documents?: Array<ManagerCustomerReconciliationDocumentItem>;
    payments?: Array<ManagerCustomerReconciliationPaymentItem>;
};

