/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ManagerEstimateRuleInputPayload } from './ManagerEstimateRuleInputPayload';
export type PublicServiceEstimateCalculatePayload = {
    tariff_id: number;
    route_length_m?: number;
    quantity?: number;
    extra_holes_count?: number;
    rule_inputs?: Array<ManagerEstimateRuleInputPayload>;
};

