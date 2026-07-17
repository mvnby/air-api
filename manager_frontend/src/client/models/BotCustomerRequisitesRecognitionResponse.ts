/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { BotCustomerBriefResponse } from './BotCustomerBriefResponse';
export type BotCustomerRequisitesRecognitionResponse = {
    id: number;
    status: 'recognized' | 'confirmed' | 'cancelled';
    source: string;
    extracted?: Record<string, any>;
    validation_flags?: Record<string, any>;
    duplicate_customer?: (BotCustomerBriefResponse | null);
    confirmed_customer_id?: (number | null);
    confirmed_action?: ('create' | 'update' | null);
    created_at: string;
};

