/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type Body_apply_internal_bot_warranty_nameplate_v1 = {
    telegram_id: number;
    order_id: number;
    unit_type: string;
    file_id: string;
    raw_text: string;
    extracted_json: string;
    validation_json: string;
    telegram_chat_id?: (number | null);
    telegram_message_id?: (number | null);
    file: Blob;
};

