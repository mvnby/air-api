/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type ManagerEquipmentItemResponse = {
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
};
