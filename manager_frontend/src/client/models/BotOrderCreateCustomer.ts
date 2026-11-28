/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type BotOrderCreateCustomer = {
    kind: string;
    name: string;
    customer_type: 'individual' | 'individual_entrepreneur' | 'company';
    phone?: (string | null);
    email?: (string | null);
    inn?: (string | null);
};

