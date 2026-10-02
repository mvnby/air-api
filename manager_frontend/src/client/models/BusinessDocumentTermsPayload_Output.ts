/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { PaymentScheduleItemPayload_Output } from './PaymentScheduleItemPayload_Output';
export type BusinessDocumentTermsPayload_Output = {
    contract_scenario?: (string | null);
    subject?: (string | null);
    delivery_deadline?: (string | null);
    performance_deadline?: (string | null);
    valid_until?: (string | null);
    additional_conditions?: (string | null);
    additional_conditions_overridden?: boolean;
    payment_schedule?: Array<PaymentScheduleItemPayload_Output>;
    goods_warranty_months?: (number | null);
    goods_warranty_terms?: (string | null);
    work_warranty_months?: (number | null);
    work_warranty_terms?: (string | null);
};

