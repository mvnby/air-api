/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { BotQuickOrderDraft } from './BotQuickOrderDraft';
import type { BotQuickOrderScenarioOption } from './BotQuickOrderScenarioOption';
export type BotQuickOrderDraftSessionResponse = {
    draft_id: string;
    version: number;
    status: 'active' | 'created' | 'cancelled';
    draft: BotQuickOrderDraft;
    order_id?: (number | null);
    expires_at: string;
    scenarios?: Array<BotQuickOrderScenarioOption>;
};

