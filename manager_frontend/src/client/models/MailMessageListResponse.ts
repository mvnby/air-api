/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { MailMessageResponse } from './MailMessageResponse';
export type MailMessageListResponse = {
    /**
     * Saved mail summaries; body_text contains at most 300 characters. Read message detail/preview for full content and approval hash.
     */
    items: Array<MailMessageResponse>;
    total: number;
    page: number;
    limit: number;
};

