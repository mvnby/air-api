/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ManagerEstimateLineResponse } from './ManagerEstimateLineResponse';
export type ManagerInstallEstimateResponse = {
    tariff_id: number;
    category: string;
    power_range: string;
    currency?: string;
    route_length_m: number;
    included_pipe_meters: number;
    extra_pipe_meters: number;
    quantity: number;
    lines: Array<ManagerEstimateLineResponse>;
    subtotal: number;
    discount_amount: number;
    total: number;
};

