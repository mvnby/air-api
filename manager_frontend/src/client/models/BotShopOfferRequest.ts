/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { BotShopLine } from './BotShopLine';
export type BotShopOfferRequest = {
    items: Array<BotShopLine>;
    telegram_id: number;
    expected_context_version: number;
    request_id: string;
    title: string;
};

