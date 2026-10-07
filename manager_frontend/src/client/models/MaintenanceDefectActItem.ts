/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { MaintenanceActSelectedObservation } from './MaintenanceActSelectedObservation';
export type MaintenanceDefectActItem = {
    preparation_id: number;
    source_order_id: number;
    continuation_order_id: number;
    document_id: number;
    status: string;
    observations: Array<MaintenanceActSelectedObservation>;
};

