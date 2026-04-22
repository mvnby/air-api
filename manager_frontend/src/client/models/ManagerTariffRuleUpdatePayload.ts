/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ManagerTariffRuleType } from './ManagerTariffRuleType';
export type ManagerTariffRuleUpdatePayload = {
    rule_type?: (ManagerTariffRuleType | null);
    name?: (string | null);
    line_template?: (string | null);
    unit?: (string | null);
    unit_price?: (number | null);
    is_optional?: (boolean | null);
    is_active?: (boolean | null);
    sort_order?: (number | null);
    service_id?: (number | null);
};

