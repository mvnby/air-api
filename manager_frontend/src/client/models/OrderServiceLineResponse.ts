/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { InstallationDisplayLineResponse } from './InstallationDisplayLineResponse';
export type OrderServiceLineResponse = {
    id: number;
    proposal_id?: (number | null);
    service_id?: (number | null);
    service_title: string;
    description?: (string | null);
    installation_display_lines?: Array<InstallationDisplayLineResponse>;
    service_category?: (string | null);
    quantity: number;
    price: number;
    cost?: (number | null);
    line_total: number;
    installation_estimate_revision_id?: (number | null);
    installation_projection_mode?: (string | null);
};

