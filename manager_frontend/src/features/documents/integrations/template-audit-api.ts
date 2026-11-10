import { OpenAPI } from '../../../client';
import { getHeaders, request } from '../../../client/core/request';

export type AuditDecisionStatus = 'proposal' | 'needs_legal_review' | 'accepted' | 'rejected' | 'fixed';
export type AuditLawSource = {
  url: string; title: string; provision: string; excerpt: string; checked_at: string;
  effective_from: string; effective_until?: string | null; edition: string;
  applicability: string; content_hash: string; official: boolean;
  verification: 'verified' | 'unavailable' | 'unverified' | 'future';
};
export type AuditFinding = {
  id: string; block_id: string; location_label?: string; original_text: string; proposed_text?: string | null;
  category: string; risk: string; severity: string; confidence: string;
  verification: string; sources: AuditLawSource[]; applicability: string;
  status: AuditDecisionStatus; decision_history: Array<Record<string, unknown>>; decision_current?: boolean | null;
  occurrences?: Array<{ block_id: string; text: string; part?: string; location?: unknown; location_label?: string }>;
  occurrences_total?: number; occurrences_page?: number; occurrences_next_page?: number | null;
};
export type AuditProposal = {
  id: number; base_version_id: number; version_id: number; version_number?: number | null; status: string; source_hash: string;
  edits: Array<{ finding_id: string; block_id: string; expected_text: string; replacement_text: string; reason: string }>;
  created_by: number; channel: string; created_at: string; manager_url?: string; stale?: boolean;
};
export type TemplateAuditReport = {
  id: number; template_id: number; version_id: number; legal_entity_id: number; customer_id: number | null;
  template_name: string; version_number: number;
  revision: number; source_hash: string; context_hash: string; legal_sources_hash: string;
  checked_at: string; coverage: { complete?: boolean; reasons?: unknown[]; [key: string]: unknown };
  checklist: Record<string, string>; findings: AuditFinding[]; proposals: AuditProposal[];
  stale: boolean; stale_reasons: string[];
  legal_currency: 'matches_supplied_hash' | 'changed' | 'requires_external_recheck'; manager_url: string;
};
export type AuditContext = {
  synthetic: true; label: string; values: Record<string, string>; conditions: Record<string, boolean>;
  table_rows: Record<string, Array<Record<string, string>>>;
  field_labels: Record<string, string>; condition_labels: Record<string, string>;
  table_labels: Record<string, string>; row_field_labels: Record<string, string>;
  source_hash: string; context_hash: string; legal_sources_hash: string;
};
export type AuditDecision = {
  expected_revision: number; source_hash: string; context_hash: string; legal_sources_hash: string;
  status: AuditDecisionStatus; reason: string;
};
const root = '/api/manager/document-system/template-audits';
const proposalPath = (reportId: number, proposalId: number) => `${root}/${reportId}/proposals/${encodeURIComponent(proposalId)}`;

export const templateAuditApi = {
  list(legalEntityId: number, page = 1) {
    return request<{ items: TemplateAuditReport[]; total: number; page: number; limit: number }>(OpenAPI, {
      method: 'GET', url: root, query: { legal_entity_id: legalEntityId, page, limit: 25 },
    });
  },
  get(reportId: number, occurrences?: { findingId: string; page: number }) {
    return request<TemplateAuditReport>(OpenAPI, {
      method: 'GET', url: `${root}/${reportId}`,
      query: occurrences ? { occurrences_finding_id: occurrences.findingId, occurrences_page: occurrences.page } : undefined,
    });
  },
  decide(reportId: number, findingId: string, body: AuditDecision) {
    return request<TemplateAuditReport>(OpenAPI, {
      method: 'PATCH', url: `${root}/${reportId}/findings/${encodeURIComponent(findingId)}`, body, mediaType: 'application/json',
    });
  },
  context(reportId: number, proposalId: number) {
    return request<AuditContext>(OpenAPI, { method: 'GET', url: `${proposalPath(reportId, proposalId)}/preview-context` });
  },
  async preview(reportId: number, proposalId: number, body: AuditContext & { format: 'docx' | 'pdf' }) {
    const url = `${proposalPath(reportId, proposalId)}/preview`;
    const payload = {
      synthetic: body.synthetic, label: body.label, values: body.values, conditions: body.conditions,
      table_rows: body.table_rows, format: body.format, source_hash: body.source_hash,
      context_hash: body.context_hash, legal_sources_hash: body.legal_sources_hash,
    };
    const headers = await getHeaders(OpenAPI, { method: 'POST', url, body: payload, mediaType: 'application/json' });
    headers.set('Accept', body.format === 'pdf' ? 'application/pdf' : 'application/vnd.openxmlformats-officedocument.wordprocessingml.document');
    const response = await fetch(`${OpenAPI.BASE}${url}`, {
      method: 'POST', headers, body: JSON.stringify(payload), cache: 'no-store',
      credentials: OpenAPI.WITH_CREDENTIALS ? OpenAPI.CREDENTIALS : 'same-origin',
    });
    if (!response.ok) {
      const payload = await response.json().catch(() => null);
      const detail = payload?.detail;
      throw new Error(typeof detail === 'string' ? detail : detail?.message || `Не удалось подготовить файл (${response.status})`);
    }
    return response.blob();
  },
};
