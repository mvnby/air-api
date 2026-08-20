import { mount } from '@vue/test-utils';
import { describe, expect, it } from 'vitest';

import CatalogDecisionFilters from '../src/components/catalog-decision/CatalogDecisionFilters.vue';

const brands = [{ id: 1, title: 'MDV' }, { id: 2, title: 'Gree' }];
const series = [{ id: 10, title: 'MDSAG', brandId: 1 }, { id: 20, title: 'Pular', brandId: 2 }];
const buttonByText = (wrapper: ReturnType<typeof mount>, text: string) => wrapper.findAll('button').find(button => button.text() === text)!;

describe('CatalogDecisionFilters', () => {
  it('shows series only for the selected brands and keeps brand selection multi-value', async () => {
    const wrapper = mount(CatalogDecisionFilters, { props: { modelValue: { isPublished: true }, brands, series } });

    expect(wrapper.text()).not.toContain('Серии выбранных брендов');
    await buttonByText(wrapper, 'MDV').trigger('click');
    const first = wrapper.emitted('update:modelValue')?.at(-1)?.[0] as { brandIds: number[] };
    expect(first.brandIds).toEqual([1]);

    await wrapper.setProps({ modelValue: { isPublished: true, brandIds: [1] } });
    expect(wrapper.text()).toContain('MDSAG');
    expect(wrapper.text()).not.toContain('Pular');
  });

  it('emits a multi-select list for nominal buttons', async () => {
    const wrapper = mount(CatalogDecisionFilters, { props: { modelValue: { isPublished: true, coolingBtuClasses: [9] }, brands, series } });

    await buttonByText(wrapper, '12').trigger('click');
    expect(wrapper.emitted('update:modelValue')?.at(-1)?.[0]).toMatchObject({ coolingBtuClasses: [9, 12] });
  });
});
