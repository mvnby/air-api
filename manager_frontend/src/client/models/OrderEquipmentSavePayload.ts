/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type OrderEquipmentSavePayload = {
    idempotency_key: string;
    expected_version: string;
    equipment_id?: (number | null);
    expected_equipment_version?: (string | null);
    source_document_id?: (number | null);
    brand?: (string | null);
    model?: (string | null);
    serial?: (string | null);
    equipment_source?: ('customer_owned' | 'sold_by_us' | null);
    role?: 'sale' | 'installation' | 'maintenance' | 'repair' | 'diagnostic' | 'warranty_case' | 'other';
};

