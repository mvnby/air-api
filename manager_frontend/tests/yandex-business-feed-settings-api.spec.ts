import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  previewYandexBusinessFeedSettings,
  updateYandexBusinessFeedSettings,
} from '../src/services/yandex-business-feed-settings';

const settings = {
  selection_mode: 'curated_collections' as const,
  include_services: false,
  require_ready_image: true,
  require_in_stock: false,
};

describe('Yandex Business feed settings API', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('sends an unsaved configuration to the preview endpoint', async () => {
    const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ ...settings, product_offer_count: 12 }), { status: 200 }));
    vi.stubGlobal('fetch', fetch);

    await previewYandexBusinessFeedSettings(settings);

    expect(fetch).toHaveBeenCalledWith(expect.stringContaining('/settings/preview'), expect.objectContaining({ method: 'POST', body: JSON.stringify(settings) }));
  });

  it('persists only on the explicit update request', async () => {
    const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify(settings), { status: 200 }));
    vi.stubGlobal('fetch', fetch);

    await updateYandexBusinessFeedSettings(settings);

    expect(fetch).toHaveBeenCalledWith(expect.stringContaining('/settings'), expect.objectContaining({ method: 'PUT', body: JSON.stringify(settings) }));
  });
});
