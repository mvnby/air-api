import { mount } from '@vue/test-utils';
import { describe, expect, it, vi } from 'vitest';

import ProductSeriesSelector from '../src/components/products/ProductSeriesSelector.vue';

const { listManagerBrandSeries } = vi.hoisted(() => ({ listManagerBrandSeries: vi.fn() }));

vi.mock('../src/api', () => ({
  api: { listManagerBrandSeries },
}));

describe('ProductSeriesSelector', () => {
  it('loads series for its selected brand and exposes draft and product count', async () => {
    listManagerBrandSeries.mockResolvedValue({
      items: [
        { id: 4, title: 'Elite', sort_order: 20, is_published: false, products_count: 3 },
        { id: 3, title: 'Breeze', sort_order: 10, is_published: true, products_count: 8 },
      ],
    });

    const wrapper = mount(ProductSeriesSelector, { props: { brandId: 12, modelValue: null } });
    await vi.waitFor(() => expect(listManagerBrandSeries).toHaveBeenCalledWith(12));

    expect(wrapper.text()).toContain('Без серии');
    expect(wrapper.text()).toContain('Breeze · 8 тов.');
    expect(wrapper.text()).toContain('Elite · черновик · 3 тов.');
  });

  it('resets the selected series when the brand is cleared', async () => {
    const wrapper = mount(ProductSeriesSelector, { props: { brandId: null, modelValue: 4 } });
    await vi.waitFor(() => expect(wrapper.emitted('update:modelValue')?.[0]).toEqual([null]));
  });

  it('shows a conflict instead of silently clearing a series from another brand', async () => {
    listManagerBrandSeries.mockResolvedValue({ items: [] });

    const wrapper = mount(ProductSeriesSelector, { props: { brandId: 12, modelValue: 99 } });
    await vi.waitFor(() => expect(wrapper.text()).toContain('Текущая серия не входит в список'));

    expect(wrapper.emitted('update:modelValue')).toBeUndefined();
  });

  it('requires an explicit choice for a legacy text-only series', async () => {
    listManagerBrandSeries.mockResolvedValue({ items: [] });
    const wrapper = mount(ProductSeriesSelector, {
      props: { brandId: 12, modelValue: null, legacySeriesTitle: 'Legacy Line' },
    });
    await vi.waitFor(() => expect(wrapper.text()).toContain('старых характеристиках'));

    await wrapper.get('select').setValue('__none__');
    expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual([null]);
  });
});
