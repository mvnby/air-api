/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type MaintenanceOfferLine = {
    observation_id: number;
    expected_version: number;
    kind: 'service' | 'product';
    line_id: number;
    purpose: 'diagnosis' | 'repair';
};

