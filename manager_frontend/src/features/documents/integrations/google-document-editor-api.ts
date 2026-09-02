import { OpenAPI } from '../../../client';
import type { ApiRequestOptions } from '../../../client/core/ApiRequestOptions';

export type GoogleDocumentEditTarget =
  | {
    kind: 'template-version';
    templateId: number;
    versionId: number;
    legalEntityId: number;
  }
  | {
    kind: 'managed-document';
    documentId: number;
  };

export type GoogleDocumentEditSession = {
  id: string;
  status: 'ready' | 'changed' | 'syncing' | 'error';
  edit_url: string | null;
  can_edit: boolean;
  base_checksum_sha256: string;
  remote_revision: string | null;
  modified_at: string | null;
  last_synced_at: string | null;
  detail: string | null;
};

export type DocumentDriveConnectionStatus = {
  connected: boolean;
  provider: string;
  account_label: string | null;
  managed_folder_url: string | null;
  connected_at: string | null;
  last_verified_at: string | null;
  last_error_code: string | null;
};

type SessionPayload = GoogleDocumentEditSession | {
  session: GoogleDocumentEditSession;
  new_template_version?: unknown | null;
};

export type GoogleDocumentSyncResult = {
  session: GoogleDocumentEditSession;
  newTemplateVersionCreated: boolean;
};

export class GoogleDocumentEditorApiError extends Error {
  readonly status: number;
  readonly code: string | null;

  constructor(
    message: string,
    status: number,
    code: string | null,
  ) {
    super(message);
    this.name = 'GoogleDocumentEditorApiError';
    this.status = status;
    this.code = code;
  }
}

const resolveToken = async (method: ApiRequestOptions['method'], url: string) => {
  if (typeof OpenAPI.TOKEN === 'function') return OpenAPI.TOKEN({ method, url });
  return OpenAPI.TOKEN;
};

const errorMessage = (payload: unknown, fallback: string) => {
  if (!payload || typeof payload !== 'object') return fallback;
  const detail = (payload as Record<string, unknown>).detail;
  if (typeof detail === 'string') return detail;
  if (detail && typeof detail === 'object') {
    const message = (detail as Record<string, unknown>).message;
    if (typeof message === 'string') return message;
  }
  return fallback;
};

const errorCode = (payload: unknown) => {
  if (!payload || typeof payload !== 'object') return null;
  const detail = (payload as Record<string, unknown>).detail;
  if (!detail || typeof detail !== 'object') return null;
  const code = (detail as Record<string, unknown>).error_code;
  return typeof code === 'string' ? code : null;
};

const request = async <T>(path: string, method: ApiRequestOptions['method'] = 'GET', body?: unknown): Promise<T> => {
  const token = await resolveToken(method, path);
  const headers: Record<string, string> = { Accept: 'application/json' };
  if (token) headers.Authorization = `Bearer ${token}`;
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  const response = await fetch(`${OpenAPI.BASE}${path}`, {
    method,
    body: body === undefined ? undefined : JSON.stringify(body),
    headers,
    credentials: OpenAPI.WITH_CREDENTIALS ? OpenAPI.CREDENTIALS : 'same-origin',
  });
  const payload = response.status === 204 ? null : await response.json().catch(() => null);
  if (!response.ok) {
    throw new GoogleDocumentEditorApiError(
      errorMessage(payload, `Ошибка запроса (${response.status})`),
      response.status,
      errorCode(payload),
    );
  }
  return payload as T;
};

const sessionPath = (target: GoogleDocumentEditTarget, suffix = '') => {
  if (target.kind === 'managed-document') {
    return `/api/manager/document-system/documents/${encodeURIComponent(String(target.documentId))}/google-edit-session${suffix}`;
  }
  const query = new URLSearchParams({ legal_entity_id: String(target.legalEntityId) });
  return `/api/manager/document-system/templates/${encodeURIComponent(String(target.templateId))}/versions/${encodeURIComponent(String(target.versionId))}/google-edit-session${suffix}?${query}`;
};

const unwrapSession = (payload: SessionPayload) => ('session' in payload ? payload.session : payload);

export const googleDocumentEditorApi = {
  getConnectionStatus: () => request<DocumentDriveConnectionStatus>('/api/manager/document-drive/status'),

  getAuthorizationUrl: () => request<{ url: string }>('/api/manager/document-drive/authorization-url'),

  async getSession(target: GoogleDocumentEditTarget) {
    try {
      return unwrapSession(await request<SessionPayload>(sessionPath(target)));
    } catch (error) {
      if (error instanceof GoogleDocumentEditorApiError && error.status === 404) return null;
      throw error;
    }
  },

  async createSession(target: GoogleDocumentEditTarget) {
    const body = target.kind === 'template-version'
      ? { legal_entity_id: target.legalEntityId }
      : undefined;
    return unwrapSession(await request<SessionPayload>(sessionPath(target), 'POST', body));
  },

  async syncSession(target: GoogleDocumentEditTarget) {
    const current = await this.getSession(target);
    if (!current?.base_checksum_sha256 || !current.remote_revision) {
      throw new Error('Google ещё не сообщил версию файла. Обновите страницу и повторите синхронизацию.');
    }
    const body = {
      expected_base_checksum_sha256: current.base_checksum_sha256,
      expected_remote_revision: current.remote_revision,
      idempotency_key: crypto.randomUUID(),
    };
    const payload = await request<SessionPayload>(sessionPath(target, '/sync'), 'POST', body);
    return {
      session: unwrapSession(payload),
      newTemplateVersionCreated: 'session' in payload && Boolean(payload.new_template_version),
    } satisfies GoogleDocumentSyncResult;
  },
};
