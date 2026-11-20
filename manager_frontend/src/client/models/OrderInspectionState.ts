/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { OrderInspectionRevisionItem } from './OrderInspectionRevisionItem';
export type OrderInspectionState = {
    order_id: number;
    site_id: number;
    equipment_id: number;
    current_version: number;
    inspection?: (OrderInspectionRevisionItem | null);
};

