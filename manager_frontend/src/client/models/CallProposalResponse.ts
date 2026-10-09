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
    /**
     * Desired Minsk day derived from the original call clock; does not imply an hour or confirmed visit.
     */
    requested_date?: (string | null);
    /**
     * Same desired-date precision as IncomingResponse. Date-only proposals leave payload.requested_at empty; an explicit manual timestamp has datetime precision.
     */
    date_precision?: ('date' | 'datetime' | null);
    accepted_resource_type?: (string | null);
    accepted_resource_id?: (number | null);
    accepted_url?: (string | null);
};

