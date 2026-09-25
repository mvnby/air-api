/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { InstallationMatcher_Input } from './InstallationMatcher_Input';
import type { ManagerTariffServiceKind } from './ManagerTariffServiceKind';
export type ManagerTariffUpdatePayload = {
    service_kind?: (ManagerTariffServiceKind | null);
    short_name?: (string | null);
    full_description?: (string | null);
    category?: (string | null);
    power_range?: (string | null);
    base_price?: (number | null);
    installation_code?: (string | null);
    installation_match?: (InstallationMatcher_Input | null);
    installation_price_mode?: ('fixed' | 'from' | 'quote' | null);
    included_holes_by_type?: (Record<string, number> | null);
    included_route_meters?: (number | null);
    is_active?: (boolean | null);
    sort_order?: (number | null);
    comment?: (string | null);
};

