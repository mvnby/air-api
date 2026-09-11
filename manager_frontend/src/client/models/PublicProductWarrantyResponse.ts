/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type PublicProductWarrantyResponse = {
    duration_months: number;
    maintenance_required: boolean;
    maintenance_interval_months?: (number | null);
    start_event: 'sale' | 'installation' | 'commissioning' | 'manual';
    allowed_maintenance_provider?: 'any' | 'mvn' | 'authorized';
    grace_period_days?: number;
    terms?: (string | null);
};

