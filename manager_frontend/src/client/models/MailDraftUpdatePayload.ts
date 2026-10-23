/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type MailDraftUpdatePayload = {
    in_reply_to?: (string | null);
    references?: Array<string>;
    expected_version: number;
    account_id?: (string | null);
    to?: (Array<string> | null);
    cc?: (Array<string> | null);
    bcc?: (Array<string> | null);
    subject?: (string | null);
    body_text?: (string | null);
    order_id?: (number | null);
    customer_id?: (number | null);
};

