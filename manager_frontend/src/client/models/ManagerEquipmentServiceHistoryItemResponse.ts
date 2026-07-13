/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { EquipmentServiceEventType } from './EquipmentServiceEventType';
export type ManagerEquipmentServiceHistoryItemResponse = {
    id: number;
    equipment_id: number;
    order_id?: (number | null);
    event_type?: EquipmentServiceEventType;
    event_date: string;
    maintenance_provider?: ('mvn' | 'authorized' | 'external' | null);
    complaint_snapshot?: (string | null);
    diagnostic_result?: (string | null);
    repair_recommendation?: (string | null);
    refrigerant_type?: (string | null);
    refrigerant_amount?: (string | null);
    not_repairable?: boolean;
    not_repairable_reason?: (string | null);
    notes?: (string | null);
    created_at: string;
    updated_at?: (string | null);
};

