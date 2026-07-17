/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type BotRepairApplyRequest = {
    telegram_id: number;
    order_id: number;
    repair_meta_draft: Record<string, any>;
    raw_comment: string;
    telegram_chat_id?: (number | null);
    telegram_message_id?: (number | null);
};

