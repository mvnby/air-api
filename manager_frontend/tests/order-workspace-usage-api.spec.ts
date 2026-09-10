import { flushPromises } from '@vue/test-utils';
import { describe, expect, it, vi } from 'vitest';
import { OpenAPI, ManagerOrderUsageService } from '../src/client';

describe('generated usage transport cancellation', () => {
  it('does not send an old batch if cancelled while storefront headers are resolving', async () => {
    const previousHeaders = OpenAPI.HEADERS;
    const fetch = vi.spyOn(globalThis, 'fetch');
    let resolveHeaders!: (headers: Record<string, string>) => void;
    OpenAPI.HEADERS = () => new Promise((resolve) => { resolveHeaders = resolve; });
    try {
      const pending = ManagerOrderUsageService.recordManagerOrderUsage({
        layout_version: 'workspace_v1',
        events: [{ metric: 'order_open', workflow: 'repair', party_kind: 'company', viewport: 'desktop' }],
      });
      const cancelled = pending.catch(error => error);
      pending.cancel();
      resolveHeaders({ 'X-Manager-Storefront': 'new-storefront' });
      await flushPromises();
      expect((await cancelled).isCancelled).toBe(true);
      expect(fetch).not.toHaveBeenCalled();
    } finally {
      OpenAPI.HEADERS = previousHeaders;
      fetch.mockRestore();
    }
  });
});
