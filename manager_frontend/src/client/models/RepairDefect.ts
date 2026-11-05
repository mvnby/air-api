/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type RepairDefect = {
    equipment: string;
    verdict: 'repairable' | 'not_repairable' | 'uneconomical' | 'needs_diagnostics' | 'operational';
    finding: string;
    recommendation: string;
    restriction?: (string | null);
    cost?: (string | null);
    term?: (string | null);
};

