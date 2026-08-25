import { flushPromises, mount } from '@vue/test-utils';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  list: vi.fn(),
  updatePolicy: vi.fn(),
  searchProducts: vi.fn(),
  saveProductOverride: vi.fn(),
  deleteProductOverride: vi.fn(),
}));

vi.mock('../src/services/installation-discounts-api', () => ({
  installationDiscountsApi: mocks,
}));

import InstallationDiscountsView from '../src/views/InstallationDiscountsView.vue';

const policy = { is_enabled: true, default_discount: 100, minimum_margin: 350 };
const override = {
  product_id: 12,
  title: 'Gree Pular 12',
  slug: 'gree-pular-12',
  main_image: null,
  retail_price: 2100,
  purchase_cost: 1300,
  margin: 800,
  configured_discount: 0,
  applied_discount: 0,
  has_override: true,
  status: 'disabled' as const,
  status_note: 'Для товара скидка явно отключена.',
};

const response = { policy, items: [override], total: 1, limit: 100, page: 1 };
const searchCandidate = { ...override, product_id: 13, title: 'Gree Pular 09', slug: 'gree-pular-09', has_override: false, configured_discount: 100, applied_discount: 100, status: 'active' as const };

describe('installation discounts manager view', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.list.mockResolvedValue(response);
    mocks.updatePolicy.mockResolvedValue(policy);
    mocks.searchProducts.mockResolvedValue({ items: [searchCandidate] });
    mocks.saveProductOverride.mockResolvedValue({ ...searchCandidate, configured_discount: 150, applied_discount: 150 });
    mocks.deleteProductOverride.mockResolvedValue(undefined);
  });

  it('shows margin data and makes zero an explicit no-discount override', async () => {
    const wrapper = mount(InstallationDiscountsView);
    await flushPromises();

    expect(wrapper.text()).toContain('Скидки на монтаж');
    expect(wrapper.text()).toContain('Защита маржи включена');
    expect(wrapper.text()).toContain('Себестоимость');
    expect(wrapper.text()).toContain('1 300 BYN');
    expect(wrapper.text()).toContain('Без скидки (0 BYN)');
    expect(wrapper.text()).toContain('Для товара скидка явно отключена.');
  });

  it('toggles policy directly and sends the complete policy payload', async () => {
    const wrapper = mount(InstallationDiscountsView);
    await flushPromises();

    await wrapper.get('[role="switch"]').trigger('click');
    await flushPromises();

    expect(mocks.updatePolicy).toHaveBeenCalledWith({
      is_enabled: false,
      default_discount: 100,
      minimum_margin: 350,
    });
  });

  it('adds and removes a product override without a modal', async () => {
    const wrapper = mount(InstallationDiscountsView);
    await flushPromises();

    const search = wrapper.get('input[type="search"]');
    await search.setValue('pular');
    await wrapper.get('form').trigger('submit');
    await flushPromises();
    await wrapper.get('input[aria-label="Скидка для Gree Pular 09"]').setValue(150);
    await wrapper.findAll('button').find((button) => button.text() === 'Добавить')!.trigger('click');
    await flushPromises();
    expect(mocks.saveProductOverride).toHaveBeenCalledWith(13, 150);

    const overrideCard = wrapper.findAll('article').find((card) => card.text().includes('Gree Pular 12'))!;
    await overrideCard.findAll('button').find((button) => button.text() === 'Наследовать общую')!.trigger('click');
    await flushPromises();
    expect(mocks.deleteProductOverride).toHaveBeenCalledWith(12);
  });

  it('lets an existing exception found by search return to the common rule', async () => {
    mocks.searchProducts.mockResolvedValue({ items: [override] });
    const wrapper = mount(InstallationDiscountsView);
    await flushPromises();

    await wrapper.get('input[type="search"]').setValue('pular 12');
    await wrapper.get('form').trigger('submit');
    await flushPromises();

    const searchCard = wrapper.findAll('article')[0];
    await searchCard.findAll('button').find((button) => button.text() === 'Наследовать общую')!.trigger('click');
    await flushPromises();

    expect(mocks.deleteProductOverride).toHaveBeenCalledWith(12);
  });
});
