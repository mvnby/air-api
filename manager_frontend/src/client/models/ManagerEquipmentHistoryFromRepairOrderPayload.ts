/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { EquipmentServiceEventType } from './EquipmentServiceEventType';
export type ManagerEquipmentHistoryFromRepairOrderPayload = {
    order_id: number;
    event_type?: (EquipmentServiceEventType | null);
    event_date?: (string | null);
    notes?: (string | null);
};
