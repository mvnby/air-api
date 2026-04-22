/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ManagerTariffServiceKind } from './ManagerTariffServiceKind';
export type ManagerTariffBriefResponse = {
    id: number;
    service_kind: ManagerTariffServiceKind;
    selector_label: string;
    estimate_template: string;
    category: string;
    power_range: string;
    base_price: number;
    included_route_meters: number;
};

