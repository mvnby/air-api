/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { OrderEquipmentIdentity } from './OrderEquipmentIdentity';
export type OrderEquipmentState = {
    order_id: number;
    version: string;
    items: Array<OrderEquipmentIdentity>;
    total: number;
    candidate?: (OrderEquipmentIdentity | null);
    manager_url: string;
};

