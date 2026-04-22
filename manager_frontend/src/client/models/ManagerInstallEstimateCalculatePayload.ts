/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ManagerEstimateRuleInputPayload } from './ManagerEstimateRuleInputPayload';
export type ManagerInstallEstimateCalculatePayload = {
    tariff_id: number;
    route_length_m?: number;
    quantity?: number;
    extra_holes_count?: number;
    rule_inputs?: Array<ManagerEstimateRuleInputPayload>;
    discount_amount?: number;
};

