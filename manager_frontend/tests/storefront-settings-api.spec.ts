import { describe, expect, it, vi } from 'vitest';

const request = vi.hoisted(() => vi.fn());
vi.mock('../src/client', () => ({ OpenAPI: { BASE: '', WITH_CREDENTIALS: true } }));
vi.mock('../src/client/core/request', () => ({ request }));
vi.mock('../src/client/core/ApiError', () => ({ ApiError: class ApiError extends Error {} }));
import { storefrontSettingsApi } from '../src/features/settings/storefront-settings-api';

describe('storefront settings API', () => {
  it('sends only the editable versioned PUT contract', async () => {
    request.mockResolvedValue({ version: 4 });
    await storefrontSettingsApi.save({
      site: { display_name: 'Partner', city: '', phone: '', email: '', address: '', work_hours: '', support_telegram_url: '', logo_asset_id: 42, compact_logo_asset_id: null, logo_url: '/media/library/original/logo.svg' },
      services: [], version: 3, updated_at: '2026-09-14T10:00:00Z',
    });
    expect(request).toHaveBeenCalledWith(expect.anything(), expect.objectContaining({
      method: 'PUT', url: '/api/manager/storefront-settings',
      body: { site: expect.any(Object), services: [], version: 3 },
    }));
    expect(request.mock.calls[0][1].body).not.toHaveProperty('updated_at');
    expect(request.mock.calls[0][1].body.site).not.toHaveProperty('logo_url');
  });
});
