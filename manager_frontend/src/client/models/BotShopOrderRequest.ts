/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { BotShopLine } from './BotShopLine';
export type BotShopOrderRequest = {
    items: Array<BotShopLine>;
    idempotency_key: string;
    prospect_type: 'individual' | 'company';
    proposal_mode: 'bundle' | 'alternatives';
    telegram_id: number;
    expected_context_version: number;
};

