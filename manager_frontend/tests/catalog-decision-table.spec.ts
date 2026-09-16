import { mount } from '@vue/test-utils';
import { describe, expect, it } from 'vitest';

import CatalogDecisionTable from '../src/components/catalog-decision/CatalogDecisionTable.vue';
import type { CatalogDecisionItem } from '../src/services/catalog-decision-api';

const item: CatalogDecisionItem = {
  id: 1,
  title: 'Gree Pular 12',
  slug: 'gree-pular-12',
  main_image: 'https://images.example.test/pular.png',
  brand_title: 'Gree',
  series_title: 'Pular',
  retail_price_byn: 1500.12,
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
  heating_min_c: -20,
  area_m2: 35,
  category: 'household',
  indoor_form_factor: 'wall',
  is_inverter: true,
  wifi: 'builtin',
  is_published: true,
};

describe('CatalogDecisionTable', () => {
  it('keeps commercial precision and the accessible BYN text together', () => {
    const wrapper = mount(CatalogDecisionTable, { props: { items: [item], selectedIds: [], sort: 'title', direction: 'asc' } });

    expect(wrapper.text()).toContain('1 500,12 BYN');
    expect(wrapper.find('svg[aria-hidden="true"]').exists()).toBe(true);
    expect(wrapper.find('img').classes()).toContain('object-contain');
  });

  it('marks selected items as pressed and exposes sort state', async () => {
    const wrapper = mount(CatalogDecisionTable, { props: { items: [item], selectedIds: [item.id], sort: 'title', direction: 'asc' } });

    expect(wrapper.get('th[aria-sort="ascending"]').text()).toContain('Модель');
    expect(wrapper.findAll('button[aria-pressed="true"]').some(button => button.text().includes('Выбран'))).toBe(true);
    await wrapper.get('button[aria-label="Открыть карточку Gree Pular 12"]').trigger('click');
    expect(wrapper.emitted('details')).toEqual([[item]]);
  });

  it('shows missing commercial values as dashes instead of zero', () => {
    const wrapper = mount(CatalogDecisionTable, {
      props: {
        items: [{ ...item, purchase_cost_byn: null, recommended_price_byn: null, margin_abs_byn: null, margin_pct: null, cooling_power_kw: null, heating_min_c: null, wifi: undefined }],
        selectedIds: [], sort: 'title', direction: 'asc',
      },
    });

    expect(wrapper.text()).toContain('Закупка—');
    expect(wrapper.text()).toContain('Охл.: —');
    expect(wrapper.text()).toContain('Обогрев: —');
    expect(wrapper.text()).toContain('Wi-Fi: —');
  });

  it('keeps a zero customer price distinct from missing data', () => {
    const wrapper = mount(CatalogDecisionTable, {
      props: { items: [{ ...item, retail_price_byn: 0, purchase_cost_byn: null }], selectedIds: [], sort: 'title', direction: 'asc' },
    });

    expect(wrapper.text()).toContain('Цена клиенту0 BYN');
    expect(wrapper.text()).toContain('Закупка—');
  });

  it('offers purchase and margin sorting on narrow screens', async () => {
    const wrapper = mount(CatalogDecisionTable, { props: { items: [item], selectedIds: [], sort: 'title', direction: 'asc' } });

    expect(wrapper.text()).toContain('Сортировка');
    expect(wrapper.text()).toContain('Закупка');
    expect(wrapper.text()).toContain('Маржа %');
    await wrapper.findAll('button').find(button => button.text() === 'Закупка')!.trigger('click');
    expect(wrapper.emitted('sort')?.at(-1)).toEqual(['purchase_cost']);
  });
});
