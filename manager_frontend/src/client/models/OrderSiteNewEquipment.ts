/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { OrderSiteEquipmentComponent } from './OrderSiteEquipmentComponent';
export type OrderSiteNewEquipment = {
    equipment_type?: string;
    display_name?: (string | null);
    brand?: (string | null);
    model?: (string | null);
    serial?: (string | null);
    inventory_number?: (string | null);
    location_hint?: (string | null);
    refrigerant_type?: (string | null);
    installed_at?: (string | null);
    notes?: (string | null);
    components?: Array<OrderSiteEquipmentComponent>;
};

