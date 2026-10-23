/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type MailDraftCreatePayload = {
    in_reply_to?: (string | null);
    references?: Array<string>;
    account_id?: string;
    to?: Array<string>;
    cc?: Array<string>;
    bcc?: Array<string>;
    subject?: string;
    body_text?: string;
    order_id?: (number | null);
    customer_id?: (number | null);
};

