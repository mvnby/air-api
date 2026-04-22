/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ManagerEstimateRuleInputPayload } from './ManagerEstimateRuleInputPayload';
export type ManagerInstallEstimateSavePayload = {
    tariff_id: number;
    route_length_m?: number;
    quantity?: number;
    extra_holes_count?: number;
    rule_inputs?: Array<ManagerEstimateRuleInputPayload>;
    discount_amount?: number;
    title?: (string | null);
    comment?: (string | null);
    customer_id?: (number | null);
    status?: string;
};

