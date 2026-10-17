/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type WorkerMoneyCommandResult = {
    id: number;
    kind: 'client_receipt' | 'handover' | 'receipt_reversal' | 'handover_reversal' | 'offset' | 'offset_reversal' | 'agreement' | 'payout' | 'payout_reversal';
    status: string;
    version: number;
    account_version: number;
};

