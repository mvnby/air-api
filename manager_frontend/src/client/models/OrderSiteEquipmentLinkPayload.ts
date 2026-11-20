/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { OrderSiteNewEquipment } from './OrderSiteNewEquipment';
export type OrderSiteEquipmentLinkPayload = {
    equipment_id?: (number | null);
    equipment?: (OrderSiteNewEquipment | null);
    role?: 'sale' | 'installation' | 'maintenance' | 'repair' | 'diagnostic' | 'warranty_case' | 'other';
    expected_version: number;
};

