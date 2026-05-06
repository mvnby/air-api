/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { OrderProductLineResponse } from './OrderProductLineResponse';
import type { OrderServiceLineResponse } from './OrderServiceLineResponse';
export type OrderProposalResponse = {
    id: number;
    order_id: number;
    name: string;
    status?: string;
    is_selected?: boolean;
    is_archived?: boolean;
    sort_order?: number;
    total_amount?: number;
    total_cost?: number;
    margin?: number;
    product_lines?: Array<OrderProductLineResponse>;
    service_lines?: Array<OrderServiceLineResponse>;
};

