/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { BotWorkspaceFact } from './BotWorkspaceFact';
import type { BotWorkspaceProposal } from './BotWorkspaceProposal';
import type { BotWorkspaceRow } from './BotWorkspaceRow';
export type BotWorkspaceDetail = {
    item: BotWorkspaceRow;
    facts: Array<BotWorkspaceFact>;
    description?: (string | null);
    manager_url: string;
    proposals?: Array<BotWorkspaceProposal>;
    actions: Array<'mark_read' | 'mark_unread' | 'complete' | 'reopen' | 'customer_draft' | 'service_order'>;
    version?: (number | null);
    customer_id?: (number | null);
};

