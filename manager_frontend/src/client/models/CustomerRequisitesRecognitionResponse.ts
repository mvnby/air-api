/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { CustomerRequisitesDuplicateCustomer } from './CustomerRequisitesDuplicateCustomer';
import type { CustomerRequisitesExtractedData } from './CustomerRequisitesExtractedData';
export type CustomerRequisitesRecognitionResponse = {
    id: number;
    status: string;
    source: string;
    raw_text: string;
    extracted: CustomerRequisitesExtractedData;
    validation_flags?: Record<string, any>;
    duplicate_customer?: (CustomerRequisitesDuplicateCustomer | null);
    confirmed_customer_id?: (number | null);
    confirmed_action?: (string | null);
    local_file_url?: (string | null);
    created_at: string;
};

