/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ManagerTariffRuleType } from './ManagerTariffRuleType';
export type ManagerEstimateLineResponse = {
    source_type: string;
    source_id?: (number | null);
    rule_id?: (number | null);
    rule_type?: (ManagerTariffRuleType | null);
    service_id?: (number | null);
    name: string;
    short_name?: (string | null);
    full_description?: (string | null);
    qty: number;
    unit: string;
    unit_price: number;
    line_total: number;
    sort_order?: number;
};

