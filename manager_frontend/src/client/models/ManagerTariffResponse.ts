/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ManagerTariffRuleResponse } from './ManagerTariffRuleResponse';
import type { ManagerTariffServiceKind } from './ManagerTariffServiceKind';
export type ManagerTariffResponse = {
    id: number;
    service_kind: ManagerTariffServiceKind;
    short_name?: (string | null);
    full_description?: (string | null);
    selector_label: string;
    estimate_template: string;
    category: string;
    power_range: string;
    base_price: number;
    included_route_meters: number;
    is_active: boolean;
    sort_order: number;
    comment?: (string | null);
    rules?: Array<ManagerTariffRuleResponse>;
};

