import { afterEach, describe, expect, it, vi } from 'vitest';
import { OpenAPI } from '../src/client/core/OpenAPI';
import { downloadSourceOriginal } from '../src/services/order-source-review';

describe('Authenticated source original download', () => {
  const initial = { TOKEN: OpenAPI.TOKEN, HEADERS: OpenAPI.HEADERS, BASE: OpenAPI.BASE };
  afterEach(() => {
    Object.assign(OpenAPI, initial);
    vi.restoreAllMocks(); vi.unstubAllGlobals(); vi.useRealTimers();
  });

  it('uses current bearer and storefront headers and downloads only after the authenticated response', async () => {
    vi.useFakeTimers();
    OpenAPI.BASE = 'https://api.test';
    OpenAPI.TOKEN = async () => 'manager-token';
    OpenAPI.HEADERS = async () => ({ 'X-Storefront-Id': '1' });
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, blob: async () => new Blob(['original']) });
    vi.stubGlobal('fetch', fetchMock);
    const create = vi.fn().mockReturnValue('blob:original'); const revoke = vi.fn();
    vi.stubGlobal('URL', class extends URL { static createObjectURL = create; static revokeObjectURL = revoke; });
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined);
    await downloadSourceOriginal(461, 'doc/id', 'ТЗ.pdf', () => true);
    const [url, options] = fetchMock.mock.calls[0]!;
    expect(url).toBe('https://api.test/api/manager/orders/461/source-documents/doc%2Fid');
    expect(options.headers.get('Authorization')).toBe('Bearer manager-token');
    expect(options.headers.get('X-Storefront-Id')).toBe('1');
    expect(click).toHaveBeenCalledTimes(1); expect(create).toHaveBeenCalledTimes(1);
    await vi.runAllTimersAsync(); expect(revoke).toHaveBeenCalledWith('blob:original');
  });

  it('never downloads a response belonging to an old order scope', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, blob: async () => new Blob(['old']) }));
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined);
    await downloadSourceOriginal(461, 'doc', 'old.pdf', () => false);
    expect(click).not.toHaveBeenCalled();
  });
});
