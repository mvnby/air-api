/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { BotOrderDocument } from './BotOrderDocument';
import type { BotOrderFollowup } from './BotOrderFollowup';
import type { BotOrderIssuance } from './BotOrderIssuance';
import type { BotOrderIssuer } from './BotOrderIssuer';
import type { BotOrderPayments } from './BotOrderPayments';
import type { BotOrderProposal } from './BotOrderProposal';
import type { BotOrderReserveState } from './BotOrderReserveState';
export type BotOrderDesk = {
    proposals: Array<BotOrderProposal>;
    selected_proposal_id: (number | null);
    id: number;
    title: string;
    status: string;
    status_label: string;
    currency: string;
    revision: string;
    manager_url: string;
    followup: BotOrderFollowup;
    documents: Array<BotOrderDocument>;
    document_issuers: Array<BotOrderIssuer>;
    reserve: BotOrderReserveState;
    payments: BotOrderPayments;
    issuance: Array<BotOrderIssuance>;
};

