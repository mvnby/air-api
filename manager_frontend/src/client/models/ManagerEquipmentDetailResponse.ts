/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ManagerEquipmentServiceHistoryItemResponse } from './ManagerEquipmentServiceHistoryItemResponse';
export type ManagerEquipmentDetailResponse = {
    id: number;
    customer_id: number;
    customer_branch_id?: (number | null);
    equipment_type?: string;
    display_name?: (string | null);
    brand?: (string | null);
    model?: (string | null);
    serial?: (string | null);
    inventory_number?: (string | null);
    location_hint?: (string | null);
    refrigerant_type?: (string | null);
    notes?: (string | null);
    is_archived?: boolean;
    created_at: string;
    updated_at?: (string | null);
    recent_history?: Array<ManagerEquipmentServiceHistoryItemResponse>;
};

