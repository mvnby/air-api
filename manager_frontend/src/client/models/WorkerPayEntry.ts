/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type WorkerPayEntry = {
    id: number;
    kind: 'payout' | 'offset' | 'payout_reversal' | 'offset_reversal';
    status: 'recorded' | 'reversed';
    amount: string;
    currency: string;
    method: 'cash' | 'bank' | 'offset';
    created_at: string;
    version: number;
    can_reverse?: boolean;
};

