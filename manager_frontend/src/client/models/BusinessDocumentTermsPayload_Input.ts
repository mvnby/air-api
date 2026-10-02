/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { PaymentScheduleItemPayload_Input } from './PaymentScheduleItemPayload_Input';
export type BusinessDocumentTermsPayload_Input = {
    contract_scenario?: (string | null);
    subject?: (string | null);
    delivery_deadline?: (string | null);
    performance_deadline?: (string | null);
    valid_until?: (string | null);
    additional_conditions?: (string | null);
    additional_conditions_overridden?: boolean;
    payment_schedule?: Array<PaymentScheduleItemPayload_Input>;
    goods_warranty_months?: (number | null);
    goods_warranty_terms?: (string | null);
    work_warranty_months?: (number | null);
    work_warranty_terms?: (string | null);
};

