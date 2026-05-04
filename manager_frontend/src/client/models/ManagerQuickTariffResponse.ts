/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ManagerTariffServiceKind } from './ManagerTariffServiceKind';
export type ManagerQuickTariffResponse = {
    tariff_id: number;
    service_kind: ManagerTariffServiceKind;
    title: string;
    price: number;
    category?: string;
    power_range?: string;
    included_route_meters?: number;
};

