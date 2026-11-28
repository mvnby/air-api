/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type BotOrderPayment = {
    id: number;
    amount: string;
    currency: 'BYN' | 'USD' | 'EUR';
    type: 'prepayment' | 'postpayment';
    received_on: string;
    comment: (string | null);
    bank_confirmed: boolean;
};

