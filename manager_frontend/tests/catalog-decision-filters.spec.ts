import { mount } from '@vue/test-utils';
import { describe, expect, it } from 'vitest';

import CatalogDecisionFilters from '../src/components/catalog-decision/CatalogDecisionFilters.vue';
import { defaultCatalogDecisionFilters } from '../src/services/catalog-decision-api';

const brands = [{ id: 1, title: 'MDV' }, { id: 2, title: 'Gree' }];
const series = [{ id: 10, title: 'MDSAG', brandId: 1 }, { id: 20, title: 'Pular', brandId: 2 }];
const buttonByText = (wrapper: ReturnType<typeof mount>, text: string) => wrapper.findAll('button').find(button => button.text() === text)!;

describe('CatalogDecisionFilters', () => {
  it('shows series only for selected brands and keeps brand selection multi-value', async () => {
    const wrapper = mount(CatalogDecisionFilters, { props: { modelValue: { isPublished: true }, brands, series } });

    expect(wrapper.text()).not.toContain('Серии выбранных брендов');
    await buttonByText(wrapper, 'MDV').trigger('click');
    expect(wrapper.emitted('update:modelValue')?.at(-1)?.[0]).toMatchObject({ brandIds: [1] });

    await wrapper.setProps({ modelValue: { isPublished: true, brandIds: [1] } });
    expect(wrapper.text()).toContain('MDSAG');
    expect(wrapper.text()).not.toContain('Pular');
  });

  it('keeps BTU selection multi-value across the two compact groups', async () => {
    const wrapper = mount(CatalogDecisionFilters, { props: { modelValue: { isPublished: true, coolingBtuClasses: [9] }, brands, series } });

    await buttonByText(wrapper, '30').trigger('click');
    expect(wrapper.emitted('update:modelValue')?.at(-1)?.[0]).toMatchObject({ coolingBtuClasses: [9, 30] });
    expect(buttonByText(wrapper, '7').attributes('aria-pressed')).toBe('false');
  });

  it('uses wifi state and direct stock selection without legacy hasWifi criteria', async () => {
    const wrapper = mount(CatalogDecisionFilters, { props: { modelValue: { isPublished: true, hasWifi: true }, brands, series } });

    await buttonByText(wrapper, 'Встроенный').trigger('click');
    expect(wrapper.emitted('update:modelValue')?.at(-1)?.[0]).toMatchObject({ wifi: 'builtin', hasWifi: undefined });
    await buttonByText(wrapper, 'Все').trigger('click');
    expect(wrapper.emitted('update:modelValue')?.at(-1)?.[0]).toMatchObject({ includeOrderable: true });
  });

  it('keeps invalid budget ranges local and emits criteria after the range is valid', async () => {
    const wrapper = mount(CatalogDecisionFilters, { props: { modelValue: { isPublished: true }, brands, series } });
    const budgetInputs = wrapper.findAll('input[aria-label^="Бюджет"]');

    await budgetInputs[0]!.setValue('1000');
    const emittedBeforeInvalidMaximum = wrapper.emitted('update:modelValue')?.length;
    await budgetInputs[1]!.setValue('500');
    expect(wrapper.text()).toContain('Минимум не может быть больше максимума.');
    expect(wrapper.emitted('update:modelValue')).toHaveLength(emittedBeforeInvalidMaximum ?? 0);
    expect(wrapper.emitted('update:modelValue')?.at(-1)?.[0]).toMatchObject({ retailMinByn: 1000 });

    await wrapper.setProps({ modelValue: { isPublished: true, retailMinByn: 1000, isInverter: true } });
    expect(wrapper.text()).toContain('Минимум не может быть больше максимума.');

    await budgetInputs[1]!.setValue('1500');
    expect(wrapper.emitted('update:modelValue')?.at(-1)?.[0]).toMatchObject({ retailMinByn: 1000, retailMaxByn: 1500 });
  });

  it('selects a frost threshold and an equipment silhouette by direct click', async () => {
    const wrapper = mount(CatalogDecisionFilters, { props: { modelValue: defaultCatalogDecisionFilters(), brands, series } });

    await buttonByText(wrapper, '-25 °C').trigger('click');
    expect(wrapper.emitted('update:modelValue')?.at(-1)?.[0]).toMatchObject({ heatingMin: -25 });
    await buttonByText(wrapper, 'Консольный').trigger('click');
    expect(wrapper.emitted('update:modelValue')?.at(-1)?.[0]).toMatchObject({ indoorFormFactor: 'console' });
    expect(buttonByText(wrapper, 'Консольный').find('svg').exists()).toBe(true);
  });

  it('keeps the selected brands visible while collapsing a long brand list', async () => {
    const manyBrands = Array.from({ length: 10 }, (_, index) => ({ id: index + 1, title: `Бренд ${index + 1}` }));
    const wrapper = mount(CatalogDecisionFilters, { props: { modelValue: { isPublished: true, brandIds: [10] }, brands: manyBrands, series: [] } });

    expect(wrapper.text()).toContain('Бренд 10');
    await buttonByText(wrapper, 'Ещё 1').trigger('click');
    expect(wrapper.find('input[aria-label="Найти бренд"]').exists()).toBe(true);
  });

  it('clears an invalid local range when the parent increments resetKey', async () => {
    const wrapper = mount(CatalogDecisionFilters, { props: { modelValue: { isPublished: true }, brands, series, resetKey: 0 } });
    const budgetInputs = wrapper.findAll('input[aria-label^="Бюджет"]');

    await budgetInputs[0]!.setValue('1000');
    await budgetInputs[1]!.setValue('500');
    expect(wrapper.get('[role="alert"]').text()).toContain('Минимум не может быть больше максимума.');

    await wrapper.setProps({ resetKey: 1 });
    expect(wrapper.find('[role="alert"]').exists()).toBe(false);
    expect((budgetInputs[1]!.element as HTMLInputElement).value).toBe('');
  });
});
