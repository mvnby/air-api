/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
/**
 * expected_version is the displayed worker cash account version.
 */
export type WorkerCashHandoverCreate = {
    idempotency_key: string;
    expected_version: number;
    amount: (number | string);
    currency: 'BYN' | 'USD' | 'EUR';
    recipient_staff_user_id: number;
};

