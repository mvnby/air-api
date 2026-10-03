/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { CustomerRequisitesExtractedData } from './CustomerRequisitesExtractedData';
export type CustomerRequisitesConfirmPayload = {
    action: string;
    customer_id?: (number | null);
    extracted?: (CustomerRequisitesExtractedData | null);
    selected_fields?: (Array<'name' | 'full_legal_name' | 'customer_type' | 'inn' | 'legal_address' | 'bank_name' | 'bic' | 'iban' | 'email' | 'phone' | 'signer_position' | 'signer_name' | 'acting_basis'> | null);
    baseline?: (Record<string, (string | null)> | null);
};

