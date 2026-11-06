/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ActTermsPayload } from './ActTermsPayload';
import type { BusinessDocumentTermsPayload_Output } from './BusinessDocumentTermsPayload_Output';
import type { ConsumerDocumentTermsPayload } from './ConsumerDocumentTermsPayload';
import type { ParticipantStatementPayload } from './ParticipantStatementPayload';
import type { RepairDefect } from './RepairDefect';
import type { TransportTermsPayload } from './TransportTermsPayload';
import type { WaybillCargoLine } from './WaybillCargoLine';
export type ManagedDocumentDraftParameters = {
    issue_date: string;
    issue_city?: (string | null);
    business_terms?: (BusinessDocumentTermsPayload_Output | null);
    consumer_terms?: (ConsumerDocumentTermsPayload | null);
    act_terms?: (ActTermsPayload | null);
    transport_terms?: (TransportTermsPayload | null);
    repair_defect?: (RepairDefect | null);
    participant_statement?: (ParticipantStatementPayload | null);
    waybill_cargo?: (Array<WaybillCargoLine> | null);
    revision: string;
    template_version_id: number;
    has_editable_copy: boolean;
    total_amount: string;
    order_conditions?: (string | null);
};

