/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ManagerInstallationRateSelectionStatus } from './ManagerInstallationRateSelectionStatus';
/**
 * A public checkout rate with read-only resolver presentation metadata.
 */
export type ManagerInstallationRateResponse = {
    id: number;
    category: string;
    power_range: string;
    base_price: number;
    extra_pipe_price: number;
    included_pipe_meters: number;
    is_fixed: boolean;
    comment?: (string | null);
    title: string;
    equipment_label: string;
    power_label: string;
    selection_status: ManagerInstallationRateSelectionStatus;
    selection_note: string;
};

