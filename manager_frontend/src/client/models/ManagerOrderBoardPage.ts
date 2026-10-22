/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ManagerOrderBoardGroup } from './ManagerOrderBoardGroup';
import type { ManagerOrderListItemResponse } from './ManagerOrderListItemResponse';
export type ManagerOrderBoardPage = {
    items?: Array<ManagerOrderListItemResponse>;
    groups?: Array<ManagerOrderBoardGroup>;
    total: number;
    total_orders: number;
    page: number;
    limit: number;
    has_more: boolean;
    queue_counts: Record<string, number>;
    work_counts: Record<string, number>;
};

