import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { OpenAPI } from '../src/client';
import { templateAuditApi, type AuditContext } from '../src/features/documents/integrations/template-audit-api';

const original = { base: OpenAPI.BASE, token: OpenAPI.TOKEN, headers: OpenAPI.HEADERS, credentials: OpenAPI.WITH_CREDENTIALS };
const context: AuditContext = {
  synthetic: true, label: 'Учебный пример', values: { 'customer.name': 'Вымышленный клиент' },
  conditions: {}, table_rows: {}, field_labels: { 'customer.name': 'Имя клиента' }, condition_labels: {}, table_labels: {}, row_field_labels: {}, source_hash: 'a'.repeat(64), context_hash: 'b'.repeat(64), legal_sources_hash: 'c'.repeat(64),
};
beforeEach(() => { OpenAPI.BASE = '/backend'; });
afterEach(() => {
  OpenAPI.BASE = original.base;
  OpenAPI.TOKEN = original.token;
  OpenAPI.HEADERS = original.headers;
  OpenAPI.WITH_CREDENTIALS = original.credentials;
  vi.restoreAllMocks();
});

describe('templateAuditApi', () => {
  it('uses the authenticated shared request helper and bounds the issuer report list', async () => {
    OpenAPI.TOKEN = async () => 'test-manager-token';
    const fetch = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({ items: [], total: 0, page: 2, limit: 25 }), {
      status: 200, headers: { 'Content-Type': 'application/json' },
    }));
    await expect(templateAuditApi.list(5, 2)).resolves.toMatchObject({ items: [], page: 2 });
    expect(fetch.mock.calls[0]![0]).toBe('/backend/api/manager/document-system/template-audits?legal_entity_id=5&page=2&limit=25');
    expect(new Headers(fetch.mock.calls[0]![1]?.headers).get('Authorization')).toBe('Bearer test-manager-token');
  });

  it('uses shared token and configured headers for uncached private PDF bytes', async () => {
    OpenAPI.TOKEN = async () => 'test-manager-token';
    OpenAPI.HEADERS = { 'X-Context': 'test-context' };
    OpenAPI.WITH_CREDENTIALS = true;
    const fetch = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('%PDF-fictional', {
      status: 200, headers: { 'Content-Type': 'application/pdf' },
    }));
    const body = { ...context, format: 'pdf' as const };
    const result = await templateAuditApi.preview(7, 1, body);
    expect(result.size).toBe('%PDF-fictional'.length);
    expect(result.type).toBe('application/pdf');
    expect(fetch.mock.calls[0]![0]).toBe('/backend/api/manager/document-system/template-audits/7/proposals/1/preview');
    const options = fetch.mock.calls[0]![1]!;
    const headers = new Headers(options.headers);
    expect(headers.get('Authorization')).toBe('Bearer test-manager-token');
    expect(headers.get('X-Context')).toBe('test-context');
    expect(headers.get('Accept')).toBe('application/pdf');
    expect(options).toMatchObject({ method: 'POST', cache: 'no-store', credentials: OpenAPI.CREDENTIALS });
    expect(JSON.parse(String(options.body))).toEqual({
      synthetic: true, label: context.label, values: context.values, conditions: context.conditions, table_rows: context.table_rows,
      format: 'pdf', source_hash: context.source_hash, context_hash: context.context_hash, legal_sources_hash: context.legal_sources_hash,
    });
  });

  it('requests one explicit bounded occurrence page for a finding', async () => {
    const fetch = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('{}', {
      status: 200, headers: { 'Content-Type': 'application/json' },
    }));
    await templateAuditApi.get(7, { findingId: 'finding-1', page: 2 });
    expect(fetch.mock.calls[0]![0]).toBe('/backend/api/manager/document-system/template-audits/7?occurrences_finding_id=finding-1&occurrences_page=2');
  });

  it('surfaces the server reason when preview context becomes stale', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({ detail: { message: 'Контекст шаблона изменился' } }), {
      status: 409, headers: { 'Content-Type': 'application/json' },
    }));
    await expect(templateAuditApi.preview(7, 1, { ...context, format: 'pdf' })).rejects.toThrow('Контекст шаблона изменился');
  });
});
