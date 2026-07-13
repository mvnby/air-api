/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type ManagerEquipmentCreatePayload = {
    customer_id: number;
    customer_branch_id?: (number | null);
    catalog_product_id?: (number | null);
    source_order_id?: (number | null);
    supplier_id?: (number | null);
    order_role?: string;
    work_warranty_months?: (number | null);
    work_warranty_terms?: (string | null);
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
    warranty_started_at?: (string | null);
    warranty_expires_at?: (string | null);
    warranty_terms?: (string | null);
    notes?: (string | null);
    is_archived?: boolean;
};

