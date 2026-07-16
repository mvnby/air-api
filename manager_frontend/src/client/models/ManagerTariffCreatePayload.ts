/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ManagerTariffServiceKind } from './ManagerTariffServiceKind';
export type ManagerTariffCreatePayload = {
    service_kind?: ManagerTariffServiceKind;
    short_name: string;
    full_description?: (string | null);
    category?: string;
    power_range?: string;
    base_price?: number;
    included_route_meters?: number;
    is_active?: boolean;
    sort_order?: number;
    comment?: (string | null);
};

