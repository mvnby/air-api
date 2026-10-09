/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type MaintenanceOfferItem = {
    id: number;
    source_order_id: number;
    continuation_order_id: number;
    proposal_id: number;
    version: number;
    state: string;
    snapshot: Record<string, any>;
    events: Array<Record<string, any>>;
    resolutions: Array<Record<string, any>>;
};

