/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { MaintenanceObservationRevisionItem } from './MaintenanceObservationRevisionItem';
import type { ManagerServiceAttachmentItemResponse } from './ManagerServiceAttachmentItemResponse';
export type MaintenanceObservationDetail = {
    equipment_id?: (number | null);
    equipment_description: string;
    facts: string;
    recommendation: string;
    id: number;
    source_order_id: number;
    customer_id: number;
    customer_branch_id: (number | null);
    origin: string;
    original_comment: string;
    observed_at: string;
    created_at: string;
    created_by: string;
    updated_at: string;
    updated_by: string;
    version: number;
    resolution?: (Record<string, any> | null);
    equipment_link_state?: 'unlinked' | 'current' | 'moved' | 'archived';
    revisions?: Array<MaintenanceObservationRevisionItem>;
    photos?: Array<ManagerServiceAttachmentItemResponse>;
};

