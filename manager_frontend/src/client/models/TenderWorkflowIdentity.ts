/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type TenderWorkflowIdentity = {
    order_id: number;
    title?: (string | null);
    external_id?: (string | null);
    source?: (string | null);
    source_url?: (string | null);
    status: string;
    archived?: boolean;
    stage?: ('price_request' | 'price_sent' | 'announced' | 'submitted' | 'completed' | null);
    deadline_at?: (string | null);
};

