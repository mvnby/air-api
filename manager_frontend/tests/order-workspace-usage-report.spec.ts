import { flushPromises, mount } from '@vue/test-utils';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({ daily: vi.fn() }));
vi.mock('../src/services/order-workspace-usage-api', async () => {
  const actual = await vi.importActual<typeof import('../src/services/order-workspace-usage-api')>('../src/services/order-workspace-usage-api');
  return { ...actual, orderWorkspaceUsageApi: { record: vi.fn(), daily: mocks.daily } };
});

import OrderWorkspaceUsageReport from '../src/components/orders/OrderWorkspaceUsageReport.vue';
import { managerSession } from '../src/services/manager-session';
import { managerStorefrontSelection } from '../src/services/manager-storefront-selection';

const cancelable = <T,>(value: T) => Object.assign(Promise.resolve(value), { cancel: vi.fn(), isCancelled: false });

beforeEach(() => {
  mocks.daily.mockReset();
  managerSession.isAuthenticated.value = true;
  managerSession.auth.value = { tenant_id: 7, staff_user_id: 13, username: 'owner', capabilities: ['analytics.manage'] } as any;
  managerStorefrontSelection.selectedSlug.value = 'minsk';
});
afterEach(() => {
  managerSession.isAuthenticated.value = false;
  managerSession.auth.value = null;
  managerStorefrontSelection.selectedSlug.value = null;
});

describe('OrderWorkspaceUsageReport', () => {
  it('renders semantic opens/actions heatmap from the aggregate report', async () => {
    mocks.daily.mockReturnValue(cancelable({
      days: 30, since: '2026-08-12', through: '2026-09-10', timezone: 'Europe/Minsk', layout_version: 'workspace_v1',
      items: [
        { day: '2026-09-10', count: 4, metric: 'proposal_open', workflow: 'repair', party_kind: 'company', viewport: 'desktop' },
        { day: '2026-09-10', count: 2, metric: 'product_add', workflow: 'repair', party_kind: 'company', viewport: 'desktop' },
      ],
    }));
    const wrapper = mount(OrderWorkspaceUsageReport, { props: { open: true } });
    await flushPromises();

    expect(mocks.daily).toHaveBeenCalledWith({ days: 30, workflow: undefined, party_kind: undefined, viewport: undefined });
    expect(wrapper.text()).toContain('Открытия 4');
    expect(wrapper.text()).toContain('Действия 2');
    expect(wrapper.text()).toContain('Добавление товара');
    wrapper.unmount();
  });

  it('cancels and reloads when the storefront scope changes', async () => {
    const pending = Object.assign(new Promise<any>(() => undefined), { cancel: vi.fn(), isCancelled: false });
    mocks.daily.mockReturnValueOnce(pending).mockReturnValueOnce(cancelable({
      days: 30, since: '2026-08-12', through: '2026-09-10', timezone: 'Europe/Minsk', layout_version: 'workspace_v1', items: [],
    }));
    const wrapper = mount(OrderWorkspaceUsageReport, { props: { open: true } });

    managerStorefrontSelection.selectedSlug.value = 'vitebsk';
    await flushPromises();

    expect(pending.cancel).toHaveBeenCalledOnce();
    expect(mocks.daily).toHaveBeenCalledTimes(2);
    wrapper.unmount();
  });
});
