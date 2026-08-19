import { flushPromises, mount } from '@vue/test-utils';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  listCollections: vi.fn(),
  getRuleOptions: vi.fn(),
}));

vi.mock('../src/client', () => ({
  ManagerProductCollectionsService: {
    listManagerProductCollections: mocks.listCollections,
    getManagerProductCollectionRuleOptions: mocks.getRuleOptions,
  },
}));

import ProductCollectionsView from '../src/views/ProductCollectionsView.vue';
import { MANAGER_CAPABILITY } from '../src/manager-capabilities';
import { sanitizeProductCollectionRuleConfig } from '../src/components/product-collections/product-collection-rule-permissions';
import { managerSession } from '../src/services/manager-session';

describe('product collection internal stock rule permissions', () => {
  beforeEach(() => {
    mocks.listCollections.mockResolvedValue({ items: [] });
    mocks.getRuleOptions.mockResolvedValue({ brands: [], series: [], features: [] });
  });

  afterEach(() => {
    managerSession.auth.value = null;
    vi.clearAllMocks();
  });

  it('hides sourcing rules and strips stale values for tenant managers', async () => {
    managerSession.auth.value = {
      capabilities: [MANAGER_CAPABILITY.storefrontCollectionsManage],
    } as any;
    const wrapper = mount(ProductCollectionsView);
    await flushPromises();

    expect(wrapper.find('[data-testid="internal-stock-rules"]').exists()).toBe(false);
    expect(sanitizeProductCollectionRuleConfig({
      product_kinds: ['complete_split_system'],
      public_stock_states: ['supplier_stock'],
    }, false)).toEqual({
      product_kinds: ['complete_split_system'],
    });
    wrapper.unmount();
  });

  it('keeps the canonical platform control and outgoing values', async () => {
    managerSession.auth.value = {
      capabilities: [
        MANAGER_CAPABILITY.storefrontCollectionsManage,
        MANAGER_CAPABILITY.platformManage,
      ],
    } as any;
    const wrapper = mount(ProductCollectionsView);
    await flushPromises();
    const modeSelect = wrapper.findAll('select').find(
      select => select.find('option[value="automatic"]').exists(),
    );
    expect(modeSelect).toBeDefined();
    await modeSelect!.setValue('automatic');

    expect(wrapper.find('[data-testid="internal-stock-rules"]').exists()).toBe(true);
    expect(sanitizeProductCollectionRuleConfig({
      public_stock_states: ['local_stock'],
    }, true).public_stock_states).toEqual(['local_stock']);
    wrapper.unmount();
  });
});
