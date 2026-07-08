/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { OutgoingEmailAttachmentResponse } from './OutgoingEmailAttachmentResponse';
import type { OutgoingEmailResponse } from './OutgoingEmailResponse';
export type OutgoingEmailDetailResponse = {
    id: number;
    status: string;
    retry_of_email_id?: (number | null);
    order_id?: (number | null);
    customer_id?: (number | null);
    customer_name?: (string | null);
    order_title?: (string | null);
    recipient_email: string;
    subject: string;
    body_text?: (string | null);
    body_html?: (string | null);
    from_email?: (string | null);
    from_name?: (string | null);
    reply_to?: (string | null);
    attachments?: (Array<OutgoingEmailAttachmentResponse> | null);
    error?: (string | null);
    sent_at?: (string | null);
    created_at: string;
    updated_at?: (string | null);
    retry_attempts?: Array<OutgoingEmailResponse>;
};

