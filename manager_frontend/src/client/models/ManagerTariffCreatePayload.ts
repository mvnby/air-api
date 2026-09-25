/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { InstallationMatcher_Input } from './InstallationMatcher_Input';
import type { ManagerTariffServiceKind } from './ManagerTariffServiceKind';
export type ManagerTariffCreatePayload = {
    service_kind?: ManagerTariffServiceKind;
    short_name: string;
    full_description?: (string | null);
    category?: string;
    power_range?: string;
    base_price?: number;
    installation_code?: (string | null);
    installation_match?: (InstallationMatcher_Input | null);
    installation_price_mode?: 'fixed' | 'from' | 'quote';
    included_holes_by_type?: Record<string, number>;
    included_route_meters?: number;
    is_active?: boolean;
    sort_order?: number;
    comment?: (string | null);
};

