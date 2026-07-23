/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { BankReceiptAllocationOrderResponse } from './BankReceiptAllocationOrderResponse';
import type { PaymentCurrency } from './PaymentCurrency';
export type BankReceiptAllocationDetailResponse = {
    receipt_id: number;
    status: string;
    currency: PaymentCurrency;
    receipt_amount: number;
    allocated_amount: number;
    unallocated_amount: number;
    orders?: Array<BankReceiptAllocationOrderResponse>;
};

