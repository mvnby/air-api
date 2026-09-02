import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { OpenAPI } from '../src/client';
import { openNativeDocumentPreview } from '../src/features/documents/integrations/native-document-preview';

const previousOpenApi = {
  BASE: OpenAPI.BASE,
  TOKEN: OpenAPI.TOKEN,
  WITH_CREDENTIALS: OpenAPI.WITH_CREDENTIALS,
  CREDENTIALS: OpenAPI.CREDENTIALS,
};
const previousCreateObjectUrl = URL.createObjectURL;
const previousRevokeObjectUrl = URL.revokeObjectURL;

beforeEach(() => {
  OpenAPI.BASE = '/backend';
  OpenAPI.TOKEN = undefined;
  OpenAPI.WITH_CREDENTIALS = true;
  OpenAPI.CREDENTIALS = 'include';
});

afterEach(() => {
  OpenAPI.BASE = previousOpenApi.BASE;
  OpenAPI.TOKEN = previousOpenApi.TOKEN;
  OpenAPI.WITH_CREDENTIALS = previousOpenApi.WITH_CREDENTIALS;
  OpenAPI.CREDENTIALS = previousOpenApi.CREDENTIALS;
  vi.restoreAllMocks();
  vi.useRealTimers();
  if (previousCreateObjectUrl) URL.createObjectURL = previousCreateObjectUrl;
  else delete (URL as Partial<typeof URL>).createObjectURL;
  if (previousRevokeObjectUrl) URL.revokeObjectURL = previousRevokeObjectUrl;
  else delete (URL as Partial<typeof URL>).revokeObjectURL;
});

describe('openNativeDocumentPreview', () => {
  it('opens the draft PDF inline and releases its object URL', async () => {
    vi.useFakeTimers();
    const replace = vi.fn();
    vi.spyOn(window, 'open').mockReturnValue({ opener: null, location: { replace }, close: vi.fn() } as never);
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(
      new Blob(['draft pdf'], { type: 'application/pdf' }),
      { status: 200, headers: { 'Content-Type': 'application/pdf' } },
    ));
    URL.createObjectURL = vi.fn().mockReturnValue('blob:crm-draft-preview');
    URL.revokeObjectURL = vi.fn();

    await openNativeDocumentPreview(77);

    expect(fetch).toHaveBeenCalledWith(
      '/backend/api/manager/document-system/documents/77/preview',
      expect.objectContaining({ credentials: 'include' }),
    );
    expect(replace).toHaveBeenCalledWith('blob:crm-draft-preview');
    vi.advanceTimersByTime(60_000);
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:crm-draft-preview');
  });

  it('closes the placeholder tab and exposes the backend error', async () => {
    const close = vi.fn();
    vi.spyOn(window, 'open').mockReturnValue({ opener: null, location: { replace: vi.fn() }, close } as never);
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(
      JSON.stringify({ detail: { message: 'У черновика нет активного шаблона' } }),
      { status: 409, headers: { 'Content-Type': 'application/json' } },
    ));

    await expect(openNativeDocumentPreview(77)).rejects.toThrow('У черновика нет активного шаблона');
    expect(close).toHaveBeenCalledOnce();
  });
});
