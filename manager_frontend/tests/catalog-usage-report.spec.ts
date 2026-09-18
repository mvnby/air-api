import { flushPromises, mount } from '@vue/test-utils';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({ daily: vi.fn() }));
vi.mock('../src/services/catalog-usage-api', async () => {
  const actual = await vi.importActual<typeof import('../src/services/catalog-usage-api')>('../src/services/catalog-usage-api');
  return { ...actual, catalogUsageApi: { record: vi.fn(), daily: mocks.daily } };
});

import CatalogUsageReport from '../src/components/catalog/CatalogUsageReport.vue';
import { managerSession } from '../src/services/manager-session';

const cancelable = <T,>(value: T) => Object.assign(Promise.resolve(value), { cancel: vi.fn(), isCancelled: false });

beforeEach(() => {
  mocks.daily.mockReset();
  managerSession.isAuthenticated.value = true;
  managerSession.auth.value = { capabilities: ['analytics.manage'] } as any;
});
afterEach(() => {
  managerSession.isAuthenticated.value = false;
  managerSession.auth.value = null;
});

describe('CatalogUsageReport', () => {
  it('renders action totals from the anonymous aggregate report', async () => {
    mocks.daily.mockReturnValue(cancelable({
      days: 30, since: '2026-08-12', through: '2026-09-10', timezone: 'Europe/Minsk',
      items: [{ day: '2026-09-10', layout_version: 'catalog_workspace_v1', device: 'desktop', action: 'edit_gallery', outcome: 'success', duration_bucket: '1_3s', count: 3 }],
    }));
    const wrapper = mount(CatalogUsageReport, { props: { open: true } });
    await flushPromises();
    expect(mocks.daily).toHaveBeenCalledWith({ days: 30 });
    expect(wrapper.text()).toContain('Галерея');
    expect(wrapper.text()).toContain('Всего действий: 3');
    wrapper.unmount();
  });
});
