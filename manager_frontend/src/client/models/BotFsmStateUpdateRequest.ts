/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type BotFsmStateUpdateRequest = {
    storage_key: string;
    bot_id: number;
    chat_id: number;
    user_id: number;
    thread_id?: (number | null);
    business_connection_id?: (string | null);
    destiny?: string;
    write_state?: boolean;
    state?: (string | null);
    write_data?: boolean;
    data?: Record<string, any>;
};

