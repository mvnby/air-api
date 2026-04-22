/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ManagerEstimateLineResponse } from './ManagerEstimateLineResponse';
import type { ManagerTariffBriefResponse } from './ManagerTariffBriefResponse';
export type ManagerInstallEstimateResponse = {
    tariff: ManagerTariffBriefResponse;
    currency?: string;
    route_length_m: number;
    quantity: number;
    lines: Array<ManagerEstimateLineResponse>;
    rule_lines: Array<ManagerEstimateLineResponse>;
    subtotal: number;
    discount_amount: number;
    total: number;
};

