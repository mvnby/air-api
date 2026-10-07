/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { MaintenanceActSelectedObservation } from './MaintenanceActSelectedObservation';
export type PrepareMaintenanceDefectAct = {
    command_key: string;
    observations: Array<MaintenanceActSelectedObservation>;
    legal_entity_id: number;
    issue_date: string;
    replaces_document_id?: (number | null);
};

