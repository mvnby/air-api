/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type CallProposalResponse = {
    id: number;
    kind: 'incoming' | 'task' | 'callback';
    payload: Record<string, any>;
    evidence: string;
    needs_clarification: Array<string>;
    accepted_resource_type?: (string | null);
    accepted_resource_id?: (number | null);
    accepted_url?: (string | null);
};

