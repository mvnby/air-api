import { mount } from '@vue/test-utils';
import { describe, expect, it } from 'vitest';

import CatalogDecisionTable from '../src/components/catalog-decision/CatalogDecisionTable.vue';
import type { CatalogDecisionItem } from '../src/services/catalog-decision-api';

const item: CatalogDecisionItem = {
  id: 1,
  title: 'Gree Pular 12',
  slug: 'gree-pular-12',
  main_image: null,
  brand_title: 'Gree',
  series_title: 'Pular',
  retail_price_byn: 1500,
  purchase_cost_byn: 900,
  recommended_price_byn: 1600,
  margin_abs_byn: 600,
  margin_pct: 0.4,
  supplier_name: 'MVN',
  supplier_qty: 3,
  availability: 'in_stock',
  cooling_power_kw: 3.5,
  cooling_min_kw: 3.2,
  cooling_max_kw: 3.8,
  area_m2: 35,
  category: 'household',
  indoor_form_factor: 'wall',
  is_inverter: true,
  wifi: 'builtin',
  is_published: true,
};

describe('CatalogDecisionTable', () => {
  it('offers purchase and margin sorting on narrow screens', async () => {
    const wrapper = mount(CatalogDecisionTable, { props: { items: [item], selectedIds: [], sort: 'title', direction: 'asc' } });

    expect(wrapper.text()).toContain('Сортировка');
    expect(wrapper.text()).toContain('Закупка');
    expect(wrapper.text()).toContain('Маржа %');
    await wrapper.findAll('button').find(button => button.text() === 'Закупка')!.trigger('click');
    expect(wrapper.emitted('sort')?.at(-1)).toEqual(['purchase_cost']);
  });
});
