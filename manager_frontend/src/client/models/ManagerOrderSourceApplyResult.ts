/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { SourceEquipmentPrefillResult } from './SourceEquipmentPrefillResult';
export type ManagerOrderSourceApplyResult = {
    order_id: number;
    customer_id?: (number | null);
    attachment_ids?: Array<number>;
    applied_fields?: Array<string>;
    equipment_prefill?: (SourceEquipmentPrefillResult | null);
};

