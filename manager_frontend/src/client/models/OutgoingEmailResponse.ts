/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type OutgoingEmailResponse = {
    id: number;
    status: string;
    order_id?: (number | null);
    customer_id?: (number | null);
    recipient_email: string;
    subject: string;
    body_text?: (string | null);
    body_html?: (string | null);
    from_email?: (string | null);
    from_name?: (string | null);
    reply_to?: (string | null);
    attachments?: null;
    error?: (string | null);
    sent_at?: (string | null);
    created_at: string;
    updated_at?: (string | null);
};

