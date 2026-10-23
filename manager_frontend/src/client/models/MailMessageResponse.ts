/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { MailAttachmentResponse } from './MailAttachmentResponse';
export type MailMessageResponse = {
    id: number;
    version: number;
    status: string;
    folder: 'inbox' | 'outbox' | 'drafts';
    account_id?: string;
    sender_email?: (string | null);
    sender_name?: (string | null);
    to?: Array<string>;
    cc?: Array<string>;
    bcc?: Array<string>;
    subject?: string;
    body_text?: string;
    attachments?: Array<MailAttachmentResponse>;
    order_id?: (number | null);
    customer_id?: (number | null);
    manager_url: string;
    error?: (string | null);
    created_at: string;
    updated_at?: (string | null);
    sent_at?: (string | null);
    confirmed_version?: (number | null);
    content_hash?: (string | null);
    csrf_token?: (string | null);
    message_id?: (string | null);
    reply_to?: Array<string>;
    in_reply_to?: (string | null);
    references?: Array<string>;
    delivery_projection_pending?: boolean;
};

