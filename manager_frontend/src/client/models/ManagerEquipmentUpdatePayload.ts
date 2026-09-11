/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type ManagerEquipmentUpdatePayload = {
    customer_branch_id?: (number | null);
    catalog_product_id?: (number | null);
    source_order_id?: (number | null);
    equipment_type?: (string | null);
    equipment_source?: (string | null);
    display_name?: (string | null);
    brand?: (string | null);
    model?: (string | null);
    serial?: (string | null);
    inventory_number?: (string | null);
    location_hint?: (string | null);
    refrigerant_type?: (string | null);
    installed_at?: (string | null);
    commissioned_at?: (string | null);
    warranty_mode?: ('auto' | 'manual' | 'none' | null);
    warranty_duration_months?: (number | null);
    warranty_started_at?: (string | null);
    warranty_expires_at?: (string | null);
    warranty_terms?: (string | null);
    maintenance_enabled?: (boolean | null);
    maintenance_interval_months?: (number | null);
    maintenance_anchor_at?: (string | null);
    notes?: (string | null);
    is_archived?: (boolean | null);
};

