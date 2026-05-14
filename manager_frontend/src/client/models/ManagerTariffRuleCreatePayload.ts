/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ManagerTariffRuleType } from './ManagerTariffRuleType';
export type ManagerTariffRuleCreatePayload = {
    rule_type: ManagerTariffRuleType;
    name: string;
    line_template?: string;
    unit?: string;
    unit_price?: number;
    is_optional?: boolean;
    is_favorite?: boolean;
    is_active?: boolean;
    sort_order?: number;
    service_id?: (number | null);
};

