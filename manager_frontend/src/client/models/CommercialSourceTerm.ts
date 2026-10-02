/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type CommercialSourceTerm = {
    kind: 'payment' | 'delivery';
    source: string;
    evidence: string;
    share_percent?: (string | null);
    due_days?: (number | null);
    day_kind?: ('calendar' | 'banking' | 'working' | null);
    due_event?: ('before_supply' | 'before_work' | 'after_supply' | 'after_work' | 'after_acceptance' | null);
    trigger_text?: (string | null);
    deadline?: (string | null);
    issues?: Array<string>;
};

