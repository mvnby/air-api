/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ActTermsPayload } from './ActTermsPayload';
import type { BusinessDocumentTermsPayload_Input } from './BusinessDocumentTermsPayload_Input';
import type { ConsumerDocumentTermsPayload } from './ConsumerDocumentTermsPayload';
import type { ParticipantStatementPayload } from './ParticipantStatementPayload';
import type { TransportTermsPayload } from './TransportTermsPayload';
export type ManagedDocumentDraftParameterUpdate = {
    expected_revision: string;
    reset_editable_copy?: boolean;
    issue_date?: (string | null);
    issue_city?: (string | null);
    business_terms?: (BusinessDocumentTermsPayload_Input | null);
    consumer_terms?: (ConsumerDocumentTermsPayload | null);
    act_terms?: (ActTermsPayload | null);
    transport_terms?: (TransportTermsPayload | null);
    participant_statement?: (ParticipantStatementPayload | null);
};

