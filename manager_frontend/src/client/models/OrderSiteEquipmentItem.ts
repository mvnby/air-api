/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ManagerEquipmentDetailResponse } from './ManagerEquipmentDetailResponse';
export type OrderSiteEquipmentItem = {
    equipment_id: number;
    site_id: number;
    role: 'sale' | 'installation' | 'maintenance' | 'repair' | 'diagnostic' | 'warranty_case' | 'other';
    equipment: ManagerEquipmentDetailResponse;
};

