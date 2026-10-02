import type { LeadsInboxItemResponse } from '../client/models/LeadsInboxItemResponse';
import type { LeadsInboxDetailResponse } from '../client/models/LeadsInboxDetailResponse';
import type { LeadsInboxHistoryResponse } from '../client/models/LeadsInboxHistoryResponse';
import type { LeadsInboxListResponse } from '../client/models/LeadsInboxListResponse';
import { OpenAPI } from '../client/core/OpenAPI';
import { request } from '../client/core/request';

export type InboxHistory = LeadsInboxHistoryResponse;
export type InboxItem = LeadsInboxItemResponse & Pick<LeadsInboxDetailResponse, 'original_text' | 'original_text_truncated'> & { auto_archive_at?: string | null };
export type InboxContactRequest = { item: InboxItem; note?: string; nextFollowupAt?: string };
export type InboxPage = LeadsInboxListResponse;
export type InboxRefusalReason = 'profile' | 'region' | 'terms' | 'capacity' | 'unclear' | 'other';
export const inboxChangedEvent = 'manager:inbox-changed';
export const notifyInboxChanged = () => window.dispatchEvent(new Event(inboxChangedEvent));
const path = (kind: 'order' | 'lead' = 'order') => `/api/manager/leads/inbox/${kind === 'lead' ? 'raw/' : ''}{order_id}`;
export const leadInboxApi = {
  list: (scope: 'active' | 'archive', page: number, limit: number, search?: string, source?: string, unreadOnly = false, sort = 'newest') =>
    request<InboxPage>(OpenAPI, { method: 'GET', url: '/api/manager/leads/inbox', query: { scope, page, limit, search, source, unread_only: unreadOnly, sort } }),
  detail: (id: number, kind?: 'order' | 'lead') => request<LeadsInboxDetailResponse>(OpenAPI, { method: 'GET', url: path(kind), path: { order_id: id } }),
  tender: (id: number, body: { is_tender: boolean; deadline_at?: string | null; source_url?: string | null }) => request<LeadsInboxDetailResponse>(OpenAPI, { method: 'PATCH', url: `${path()}/tender`, path: { order_id: id }, body, mediaType: 'application/json' }),
  read: (id: number, isRead: boolean, kind?: 'order' | 'lead') => request<InboxItem>(OpenAPI, { method: 'PUT', url: `${path(kind)}/read`, path: { order_id: id }, body: { is_read: isRead }, mediaType: 'application/json' }),
  archive: (id: number, reason: InboxRefusalReason, note?: string, kind?: 'order' | 'lead') => request<InboxItem>(OpenAPI, { method: 'POST', url: `${path(kind)}/archive`, path: { order_id: id }, body: { outcome: 'refusal', reason, note }, mediaType: 'application/json' }),
  archiveNonRequest: (id: number, outcome: 'spam' | 'duplicate', note?: string, kind?: 'order' | 'lead') => request<InboxItem>(OpenAPI, { method: 'POST', url: `${path(kind)}/archive`, path: { order_id: id }, body: { outcome, note }, mediaType: 'application/json' }),
  restore: (id: number, kind?: 'order' | 'lead') => request<InboxItem>(OpenAPI, { method: 'POST', url: `${path(kind)}/restore`, path: { order_id: id } }),
  noAnswer: (id: number, nextFollowupAt?: string, kind?: 'order' | 'lead', note?: string) => request<InboxItem>(OpenAPI, { method: 'POST', url: `${path(kind)}/no-answer`, path: { order_id: id }, body: { next_followup_at: nextFollowupAt, note }, mediaType: 'application/json' }),
};
