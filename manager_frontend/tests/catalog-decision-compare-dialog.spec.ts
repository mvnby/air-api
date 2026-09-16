import { DOMWrapper, mount } from '@vue/test-utils';
import { afterEach, describe, expect, it } from 'vitest';

import CatalogDecisionCompareDialog from '../src/components/catalog-decision/CatalogDecisionCompareDialog.vue';
import type { CatalogDecisionItem } from '../src/services/catalog-decision-api';

const first: CatalogDecisionItem = {
  id: 1, title: 'Gree Pular 12', slug: 'gree-pular-12', retail_price_byn: 1500.12,
  purchase_cost_byn: null, recommended_price_byn: null, margin_abs_byn: null, margin_pct: null,
  supplier_name: null, availability: 'in_stock', supplier_qty: 2, cooling_power_kw: 3.5,
  heating_min_c: -20, is_inverter: true, wifi: 'builtin', indoor_form_factor: 'wall', area_m2: null,
  is_published: true,
};
const second: CatalogDecisionItem = {
  ...first, id: 2, title: 'Gree Pular 09', retail_price_byn: 1200, supplier_qty: undefined,
  cooling_power_kw: 2.5, heating_min_c: null, is_inverter: false, wifi: 'none',
};

const mounts: ReturnType<typeof mount>[] = [];
afterEach(() => mounts.splice(0).forEach(wrapper => wrapper.unmount()));
const mountDialog = (items: CatalogDecisionItem[]) => {
  const wrapper = mount(CatalogDecisionCompareDialog, {
    props: { open: true, items },
    attachTo: document.body,
  });
  mounts.push(wrapper);
  return wrapper;
};
const dialog = () => new DOMWrapper(document.body.querySelector<HTMLElement>('[role="dialog"]')!);

describe('CatalogDecisionCompareDialog', () => {
  it('compares supplied values, preserving missing data as dashes', () => {
    const wrapper = mountDialog([first, second]);

    expect(dialog().attributes('aria-modal')).toBe('true');
    expect(dialog().text()).toContain('1 500,12 BYN');
    expect(dialog().text()).not.toContain('Нет в наличии');
    expect(dialog().text()).toContain('Остаток');
    expect(dialog().text()).toContain('—');
    expect(dialog().text()).toContain('До -20 °C');
  });

  it('filters equal attributes when only differences is selected', async () => {
    const wrapper = mountDialog([first, second]);
    expect(dialog().text()).toContain('Внутренний блок');

    const checkbox = dialog().get('input[type="checkbox"]');
    (checkbox.element as HTMLInputElement).checked = true;
    await checkbox.trigger('change');
    expect(dialog().text()).not.toContain('Внутренний блок');
    expect(dialog().text()).toContain('Охлаждение');
  });

  it('asks for two models when comparison selection is incomplete', () => {
    const wrapper = mountDialog([first]);

    expect(dialog().text()).toContain('Выберите от двух до четырёх моделей');
  });
});
