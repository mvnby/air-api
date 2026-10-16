/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type Body_attach_internal_bot_order_file_v1 = {
    expected_context_version?: (number | null);
    telegram_id: number;
    file_id: string;
    telegram_chat_id?: (number | null);
    telegram_message_id?: (number | null);
    file: Blob;
};

