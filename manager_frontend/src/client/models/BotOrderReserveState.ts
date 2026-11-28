/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { BotReserveLine } from './BotReserveLine';
export type BotOrderReserveState = {
    enabled: boolean;
    unavailable_reason?: (string | null);
    manager_status?: (string | null);
    can_set_order_status?: boolean;
    supplier_access?: boolean;
    supplier_access_reason?: (string | null);
    lines?: Array<BotReserveLine>;
};

