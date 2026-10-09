/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { LeadsInboxHistoryResponse } from './LeadsInboxHistoryResponse';
import type { TenderWorkflowIdentity } from './TenderWorkflowIdentity';
export type TenderWorkflowResponse = {
    order_id: number;
    stage?: ('price_request' | 'price_sent' | 'announced' | 'submitted' | 'completed' | null);
    deadline_at?: (string | null);
    deadline_manual?: boolean;
    price_enquiry?: (TenderWorkflowIdentity | null);
    publications?: Array<TenderWorkflowIdentity>;
    history?: Array<LeadsInboxHistoryResponse>;
};

