/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { InstallationMeasuredWork } from './InstallationMeasuredWork';
import type { InstallationSelectedWork } from './InstallationSelectedWork';
export type InstallationWorkSummary = {
    installation_key: string;
    display_label?: (string | null);
    tariff_code: string;
    work_label: string;
    measured: Array<InstallationMeasuredWork>;
    selected_extras: Array<InstallationSelectedWork>;
};

