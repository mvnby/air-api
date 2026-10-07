/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type IncomingPreview = {
    state: 'suggested' | 'unknown' | 'unavailable';
    region_text?: (string | null);
    workflow_type?: (string | null);
    service_type?: (string | null);
    evidence?: Record<string, string>;
    field_sources?: Record<string, string>;
};

