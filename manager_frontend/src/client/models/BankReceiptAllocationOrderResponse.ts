/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type BankReceiptAllocationOrderResponse = {
    order_id: number;
    title?: (string | null);
    customer_name?: (string | null);
    status: string;
    created_at: string;
    total_amount: number;
    total_payments: number;
    balance_due_before_receipt: number;
    current_allocation: number;
    resulting_balance_due: number;
};

