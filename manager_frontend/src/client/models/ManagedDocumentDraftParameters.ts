/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ActTermsPayload } from './ActTermsPayload';
import type { BusinessDocumentTermsPayload_Output } from './BusinessDocumentTermsPayload_Output';
import type { ConsumerDocumentTermsPayload } from './ConsumerDocumentTermsPayload';
import type { ParticipantStatementPayload } from './ParticipantStatementPayload';
import type { TransportTermsPayload } from './TransportTermsPayload';
export type ManagedDocumentDraftParameters = {
    issue_date: string;
    issue_city?: (string | null);
    business_terms?: (BusinessDocumentTermsPayload_Output | null);
    consumer_terms?: (ConsumerDocumentTermsPayload | null);
    act_terms?: (ActTermsPayload | null);
    transport_terms?: (TransportTermsPayload | null);
    participant_statement?: (ParticipantStatementPayload | null);
    revision: string;
    has_editable_copy: boolean;
    total_amount: string;
    order_conditions?: (string | null);
};

