/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { InboxRelatedRequest } from './InboxRelatedRequest';
import type { LeadsInboxArchiveResponse } from './LeadsInboxArchiveResponse';
import type { LeadsInboxTenderResponse } from './LeadsInboxTenderResponse';
export type LeadsInboxItemResponse = {
    id: number;
    entity_kind?: 'order' | 'lead';
    related_requests?: Array<InboxRelatedRequest>;
    status: string;
    is_new: boolean;
    is_read?: boolean;
    read_at?: (string | null);
    source_kind?: 'customer_request' | 'tender';
    title?: (string | null);
    summary?: (string | null);
    budget_amount?: (number | null);
    budget_currency?: (string | null);
    quantity?: (number | null);
    location?: (string | null);
    deadline_at?: (string | null);
    archive?: (LeadsInboxArchiveResponse | null);
    auto_archive_at?: (string | null);
    linked_order_id?: (number | null);
    customer_id?: (number | null);
    customer_name?: (string | null);
    phone?: (string | null);
    email?: (string | null);
    source?: (string | null);
    comment?: (string | null);
    no_answer_at?: (string | null);
    no_answer_count?: number;
    next_followup_at?: (string | null);
    source_created_at?: (string | null);
    created_at: string;
    customer_type?: (string | null);
    customer_inn?: (string | null);
    customer_full_legal_name?: (string | null);
    customer_delivery_address?: (string | null);
    object_type?: (string | null);
    service_type?: (string | null);
    equipment_class?: (string | null);
    marketing_source?: (string | null);
    attachment_count?: number;
    tender?: (LeadsInboxTenderResponse | null);
    commercial_terms_summary?: Array<string>;
};

