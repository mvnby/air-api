/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type OrderInspectionSavePayload = {
    idempotency_key: string;
    status: 'defect_found' | 'no_defect_found' | 'inconclusive' | 'restored';
    facts: string;
    trial_result?: (string | null);
    event_history?: (string | null);
    recommendations?: (string | null);
    performed_actions?: (string | null);
    inspected_at?: (string | null);
    performer?: (string | null);
    expected_version: number;
};

