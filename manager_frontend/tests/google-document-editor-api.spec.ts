import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { OpenAPI } from '../src/client';
import {
  googleDocumentEditorApi,
  GoogleDocumentEditorApiError,
  type GoogleDocumentEditSession,
} from '../src/features/documents/integrations/google-document-editor-api';

const target = {
  kind: 'managed-document' as const,
  documentId: 77,
};
const templateTarget = {
  kind: 'template-version' as const,
  templateId: 10,
  versionId: 20,
  legalEntityId: 5,
};
const session: GoogleDocumentEditSession = {
  id: 'session-77',
  status: 'changed',
  edit_url: 'https://docs.google.com/document/d/77/edit',
  can_edit: true,
  base_checksum_sha256: 'a'.repeat(64),
  remote_revision: 'revision-2',
  modified_at: '2026-09-02T10:00:00Z',
  last_synced_at: '2026-09-02T09:00:00Z',
  detail: null,
};
const previousBase = OpenAPI.BASE;
const previousToken = OpenAPI.TOKEN;

beforeEach(() => {
  OpenAPI.BASE = '/backend';
});

afterEach(() => {
  OpenAPI.BASE = previousBase;
  OpenAPI.TOKEN = previousToken;
  vi.restoreAllMocks();
});

describe('googleDocumentEditorApi', () => {
  it('recognizes a missing session by typed HTTP status, independent of message text', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(
      JSON.stringify({ detail: { message: 'Сеанс пока не создан', error_code: 'external_edit_not_found' } }),
      { status: 404, headers: { 'Content-Type': 'application/json' } },
    ));

    await expect(googleDocumentEditorApi.getSession(target)).resolves.toBeNull();
  });

  it('preserves a typed backend error code for non-404 failures', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(
      JSON.stringify({ detail: { message: 'Google временно недоступен', error_code: 'google_drive_unavailable' } }),
      { status: 503, headers: { 'Content-Type': 'application/json' } },
    ));

    await expect(googleDocumentEditorApi.getSession(target)).rejects.toEqual(expect.objectContaining<Partial<GoogleDocumentEditorApiError>>({
      status: 503,
      code: 'google_drive_unavailable',
    }));
  });

  it('reports a no-op template sync without claiming that a version was created', async () => {
    vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(new Response(JSON.stringify(session), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }))
      .mockResolvedValueOnce(new Response(JSON.stringify({
        session: { ...session, status: 'ready' },
        new_template_version: null,
      }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }));

    const result = await googleDocumentEditorApi.syncSession(templateTarget);

    expect(result.newTemplateVersionCreated).toBe(false);
    expect(result.session.status).toBe('ready');
  });

  it('does not post sync when the issue context is cancelled during its nested session read', async () => {
    let resolveRead!: (response: Response) => void;
    const fetch = vi.spyOn(globalThis, 'fetch').mockReturnValue(new Promise<Response>((resolve) => { resolveRead = resolve; }));
    let active = true;
    const pending = googleDocumentEditorApi.syncSession(target, () => active);
    await vi.waitFor(() => expect(fetch).toHaveBeenCalledTimes(1));
    active = false;
    resolveRead(new Response(JSON.stringify(session), { status: 200 }));
    await expect(pending).rejects.toMatchObject({ name: 'AbortError' });
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(fetch.mock.calls[0]?.[1]?.method).toBe('GET');
  });

  it('checks the continuation again after asynchronous POST token resolution before fetch', async () => {
    let resolveToken!: (token: string) => void;
    const tokenBarrier = new Promise<string>((resolve) => { resolveToken = resolve; });
    const token = vi.fn(async (options) => options.method === 'POST' ? tokenBarrier : 'get-token');
    OpenAPI.TOKEN = token;
    const fetch = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify(session), { status: 200 }));
    let active = true;
    const pending = googleDocumentEditorApi.syncSession(target, () => active);
    await vi.waitFor(() => expect(token).toHaveBeenCalledTimes(2));
    active = false;
    resolveToken('post-token');
    await expect(pending).rejects.toMatchObject({ name: 'AbortError' });
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it('still posts guarded sync with the observed revision while the action is current', async () => {
    const fetch = vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(new Response(JSON.stringify(session), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ ...session, status: 'ready' }), { status: 200 }));
    const result = await googleDocumentEditorApi.syncSession(target, () => true);
    expect(result.session.status).toBe('ready');
    expect(fetch).toHaveBeenCalledTimes(2);
    expect(fetch.mock.calls[1]?.[1]).toEqual(expect.objectContaining({
      method: 'POST',
      body: expect.stringContaining('"expected_remote_revision":"revision-2"'),
    }));
  });
});
