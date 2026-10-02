/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ManagerInstallationStandardTariff } from './ManagerInstallationStandardTariff';
import type { ManagerTariffServiceKind } from './ManagerTariffServiceKind';
export type ManagerQuickTariffResponse = {
    tariff_id?: (number | null);
    service_kind: ManagerTariffServiceKind;
    short_name: string;
    full_description?: (string | null);
    title: string;
    price: string;
    installation_standard?: (ManagerInstallationStandardTariff | null);
    category?: string;
    power_range?: string;
    included_route_meters?: number;
};

