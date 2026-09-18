import { flushPromises, mount } from '@vue/test-utils';
import { afterEach, describe, expect, it, vi } from 'vitest';

import CatalogManagementFilters from '../src/components/products/CatalogManagementFilters.vue';
import CatalogDecisionFilters from '../src/components/catalog-decision/CatalogDecisionFilters.vue';
import { defaultManagementFilters, managementFilterPayload } from '../src/services/catalog-management-api';
import { api } from '../src/api';
import { catalogDecisionApi } from '../src/services/catalog-decision-api';
import { ManagerFeaturesService } from '../src/client';

const brands = [{ id: 1, title: 'MDV' }, { id: 2, title: 'Gree' }];
const series = [
  { id: 10, title: 'MDSAG', brand_id: 1 },
  { id: 20, title: 'Pular', brand_id: 2 },
];
const buttonByText = (wrapper: ReturnType<typeof mount>, text: string) => (
  wrapper.findAll('button').find((button) => button.text() === text)!
);

describe('catalog management filters', () => {
  afterEach(() => vi.restoreAllMocks());

  const mountFilters = async (modelValue = defaultManagementFilters()) => {
    vi.spyOn(catalogDecisionApi, 'filterOptions').mockResolvedValue({ brands, series } as any);
    vi.spyOn(api, 'listSuppliers').mockResolvedValue({ items: [{ id: 7, name: 'Поставщик' }] } as any);
    vi.spyOn(ManagerFeaturesService, 'listManagerFeatures').mockResolvedValue({
      items: [{ id: 9, name: 'Wi-Fi', slug: 'wifi', category: { name: 'Comfort' } }], total: 1,
    } as any);
    const wrapper = mount(CatalogManagementFilters, { props: { modelValue, sort: 'recommended' } });
    await flushPromises();
    return wrapper;
  };

  it('includes drafts by default while retaining the shared all-orderable filter', () => {
    const state = defaultManagementFilters();
    expect(state).toEqual({ includeOrderable: true });
    expect(managementFilterPayload(state)).toMatchObject({
      is_published: undefined,
      availability: undefined,
    });
  });

  it('reuses the shared brand-to-series cascade', async () => {
    const wrapper = await mountFilters();
    await buttonByText(wrapper, 'MDV').trigger('click');
    expect(wrapper.emitted('update:modelValue')?.at(-1)?.[0]).toMatchObject({ brandIds: [1] });

    await wrapper.setProps({ modelValue: { ...defaultManagementFilters(), brandIds: [1] } });
    expect(wrapper.text()).toContain('MDSAG');
    expect(wrapper.text()).not.toContain('Pular');
  });

  it('clears supplier, publication and completeness filters back to unbounded values', async () => {
    const wrapper = await mountFilters({
      ...defaultManagementFilters(),
      supplierId: 7,
      isPublished: false,
      missing: 'image',
    });
    const selects = wrapper.findAll('select');
    await selects[0]!.setValue('');
    expect(wrapper.emitted('update:modelValue')?.at(-1)?.[0]).toMatchObject({ supplierId: undefined });
    await selects[1]!.setValue('');
    expect(wrapper.emitted('update:modelValue')?.at(-1)?.[0]).toMatchObject({ isPublished: undefined });
    await selects[2]!.setValue('');
    expect(wrapper.emitted('update:modelValue')?.at(-1)?.[0]).toMatchObject({ missing: undefined });
  });

  it('forwards reset requests from the shared filters', async () => {
    const wrapper = await mountFilters();
    wrapper.findComponent(CatalogDecisionFilters).vm.$emit('reset');
    await flushPromises();
    expect(wrapper.emitted('reset')).toHaveLength(1);
  });

  it('offers a reset control for management-only filters', async () => {
    const wrapper = await mountFilters();
    await buttonByText(wrapper, 'Сбросить фильтры').trigger('click');
    expect(wrapper.emitted('reset')).toHaveLength(1);
  });

  it('maps feature presence and Yandex feed controls to bounded filter values', async () => {
    const wrapper = await mountFilters();
    await wrapper.find('select[aria-label="Особенность"]').setValue('9');
    expect(wrapper.emitted('update:modelValue')?.at(-1)?.[0]).toMatchObject({ featureId: 9, hasFeature: true });
    await wrapper.setProps({ modelValue: { ...defaultManagementFilters(), featureId: 9, hasFeature: true } });
    await buttonByText(wrapper, 'Нет').trigger('click');
    expect(wrapper.emitted('update:modelValue')?.at(-1)?.[0]).toMatchObject({ hasFeature: false });
    await buttonByText(wrapper, 'В выгрузке').trigger('click');
    expect(wrapper.emitted('update:modelValue')?.at(-1)?.[0]).toMatchObject({ inYandexFeed: true });
  });
});
