/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type BotAccountLinkClaimRequest = {
    token: string;
    purpose: 'link' | 'login';
    telegram_id: number;
    chat_id: number;
    message_id: number;
    telegram_username?: (string | null);
    telegram_display_name: string;
};

