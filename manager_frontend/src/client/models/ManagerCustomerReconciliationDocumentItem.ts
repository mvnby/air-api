/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ManagerCustomerReconciliationBasisDocument } from './ManagerCustomerReconciliationBasisDocument';
export type ManagerCustomerReconciliationDocumentItem = {
    order_id: number;
    order_title: string;
    date: string;
    amount: number;
    basis: string;
    delivery_address?: (string | null);
    documents?: Array<ManagerCustomerReconciliationBasisDocument>;
};

