/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { BotQuickOrderDraft } from './BotQuickOrderDraft';
export type BotQuickOrderCreateRequest = {
    expected_context_version?: (number | null);
    telegram_id: number;
    idempotency_key: string;
    draft: BotQuickOrderDraft;
};

