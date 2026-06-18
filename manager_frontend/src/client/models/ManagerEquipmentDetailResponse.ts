/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ManagerEquipmentComponentItemResponse } from './ManagerEquipmentComponentItemResponse';
import type { ManagerEquipmentServiceHistoryItemResponse } from './ManagerEquipmentServiceHistoryItemResponse';
export type ManagerEquipmentDetailResponse = {
    id: number;
    customer_id: number;
    customer_branch_id?: (number | null);
    catalog_product_id?: (number | null);
    source_order_id?: (number | null);
    equipment_type?: string;
    equipment_source?: string;
    display_name?: (string | null);
    brand?: (string | null);
    model?: (string | null);
    serial?: (string | null);
    inventory_number?: (string | null);
    location_hint?: (string | null);
    refrigerant_type?: (string | null);
    installed_at?: (string | null);
    commissioned_at?: (string | null);
    warranty_started_at?: (string | null);
    warranty_expires_at?: (string | null);
    warranty_terms?: (string | null);
    warranty_status?: string;
    notes?: (string | null);
    is_archived?: boolean;
    created_at: string;
    updated_at?: (string | null);
    components?: Array<ManagerEquipmentComponentItemResponse>;
    recent_history?: Array<ManagerEquipmentServiceHistoryItemResponse>;
};

