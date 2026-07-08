/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { SupplyRequestStockLinePayload } from './SupplyRequestStockLinePayload';
export type SupplyRequestStockCreatePayload = {
    intent?: string;
    comment?: (string | null);
    lines: Array<SupplyRequestStockLinePayload>;
};

