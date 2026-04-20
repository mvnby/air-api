/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ManagerEstimateAddonPayload } from './ManagerEstimateAddonPayload';
export type ManagerInstallEstimateCalculatePayload = {
    tariff_id?: (number | null);
    category?: (string | null);
    power_range?: (string | null);
    route_length_m?: number;
    quantity?: number;
    extra_holes_count?: number;
    extra_hole_price?: number;
    addons?: Array<ManagerEstimateAddonPayload>;
    discount_amount?: number;
};

