/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ManagerEstimateLineResponse } from './ManagerEstimateLineResponse';
import type { ManagerTariffBriefResponse } from './ManagerTariffBriefResponse';
export type ManagerServiceEstimateResponse = {
    id: number;
    customer_id?: (number | null);
    tariff?: (ManagerTariffBriefResponse | null);
    title: string;
    comment?: (string | null);
    service_kind: string;
    currency: string;
    subtotal: number;
    discount_amount: number;
    total: number;
    status: string;
    created_by?: (string | null);
    created_at: string;
    lines?: Array<ManagerEstimateLineResponse>;
    calculation_payload?: (Record<string, any> | null);
};

