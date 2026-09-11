import { DOMWrapper, flushPromises, mount, type VueWrapper } from '@vue/test-utils';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import WarrantyPolicyDialog from '../src/components/equipment/WarrantyPolicyDialog.vue';
import { warrantyDurationLabel, warrantyScopeLabel } from '../src/components/equipment/warrantyPolicyPresentation';
import type { ManagerWarrantyPolicyResponse } from '../src/client';

const { listSeries } = vi.hoisted(() => ({ listSeries: vi.fn() }));
vi.mock('../src/client', () => ({
  ManagerBrandsService: { listManagerBrandSeries: listSeries },
  ManagerService: { smartSearchProducts: vi.fn() },
}));

const legacyPolicy: ManagerWarrantyPolicyResponse = {
  id: 1, name: 'MDV iERA', coverage_type: 'supplier', supplier_id: 30,
  supplier_name: 'Биоконд', series_id: 20, series_title: 'iERA', series_brand_id: 10,
  duration_months: 48, maintenance_required: true, maintenance_interval_months: 18,
  created_at: '2026-09-11T00:00:00', updated_at: '2026-09-11T00:00:00',
};
const mounted: VueWrapper[] = [];
const surface = () => new DOMWrapper(document.body);
const field = (_wrapper: VueWrapper, text: string, selector = 'input') => {
  const label = surface().findAll('label').find((item) => item.text().startsWith(text));
  if (!label) throw new Error(`Missing field: ${text}`);
  return label.get(selector);
};
const button = (_wrapper: VueWrapper, text: string) => {
  const found = surface().findAll('button').find((item) => item.text() === text);
  if (!found) throw new Error(`Missing button: ${text}`);
  return found;
};
const open = async (policy: ManagerWarrantyPolicyResponse | null = null) => {
  const wrapper = mount(WarrantyPolicyDialog, {
    props: { open: true, policy, suppliers: [{ id: 30, name: 'Биоконд' }], brands: [{ id: 10, title: 'MDV' }, { id: 11, title: 'TCL' }], saving: false },
    attachTo: document.body,
  });
  mounted.push(wrapper);
  await flushPromises();
  await vi.waitFor(() => expect(surface().text()).not.toContain('Загружаем серии'));
  return wrapper;
};

beforeEach(() => {
  listSeries.mockReset().mockResolvedValue({ items: [
    { id: 20, brand_id: 10, title: 'iERA', products_count: 4 },
    { id: 21, brand_id: 10, title: 'INFINI', products_count: 6 },
    { id: 22, brand_id: 10, title: 'FOREST On-Off', products_count: 3 },
  ] });
});
afterEach(() => { mounted.splice(0).forEach((wrapper) => wrapper.unmount()); document.body.innerHTML = ''; });

describe('warranty rule editing', () => {
  it('adds multiple series to an existing legacy rule and saves one policy', async () => {
    const wrapper = await open(legacyPolicy);
    expect(field(wrapper, 'iERA').element).toHaveProperty('checked', true);
    await field(wrapper, 'INFINI').setValue(true);
    await surface().get('form').trigger('submit');
    expect(wrapper.emitted('save')).toHaveLength(1);
    expect(wrapper.emitted('save')?.[0]?.[0]).toMatchObject({
      supplier_id: 30, brand_id: 10, series_ids: [20, 21], duration_months: 48,
      maintenance_interval_months: 18,
    });
  });

  it('uses 12 months when enabling maintenance and preserves a custom interval across toggles', async () => {
    const wrapper = await open();
    expect(surface().text()).not.toContain('Кто проводит ТО');
    await field(wrapper, 'Для сохранения гарантии').setValue(true);
    await vi.waitFor(() => expect(surface().text()).toContain('Интервал ТО'));
    expect(field(wrapper, 'Интервал ТО').element).toHaveProperty('value', '12');
    await field(wrapper, 'Интервал ТО').setValue('18');
    await field(wrapper, 'Для сохранения гарантии').setValue(false);
    await field(wrapper, 'Для сохранения гарантии').setValue(true);
    await vi.waitFor(() => expect(surface().text()).toContain('Интервал ТО'));
    expect(field(wrapper, 'Интервал ТО').element).toHaveProperty('value', '18');
  });

  it('saves an explicit empty series list for a brand fallback and retains supplier', async () => {
    const wrapper = await open(legacyPolicy);
    await button(wrapper, 'Все серии').trigger('click');
    await field(wrapper, 'Срок гарантии').setValue('36');
    await surface().get('form').trigger('submit');
    expect(wrapper.emitted('save')?.[0]?.[0]).toMatchObject({ supplier_id: 30, brand_id: 10, series_ids: [], duration_months: 36 });
  });

  it('requires at least one selected series, never silently turning an empty selection into all series', async () => {
    const wrapper = await open(legacyPolicy);
    await surface().get('[aria-label="Убрать серию iERA"]').trigger('click');
    expect(button(wrapper, 'Сохранить правило').attributes('disabled')).toBeDefined();
    await surface().get('form').trigger('submit');
    expect(wrapper.emitted('save')).toBeUndefined();
  });

  it('keeps selected series when filtering or switching all/selected before saving', async () => {
    const wrapper = await open(legacyPolicy);
    await field(wrapper, 'Найти серию').setValue('inf');
    await field(wrapper, 'INFINI').setValue(true);
    expect(surface().get('[aria-label="Выбранные серии"]').text()).toContain('iERA');
    await button(wrapper, 'Все серии').trigger('click');
    await button(wrapper, 'Выбранные серии').trigger('click');
    await surface().get('form').trigger('submit');
    expect(wrapper.emitted('save')?.[0]?.[0]).toMatchObject({ series_ids: [20, 21] });
  });

  it('clears previous brand series and ignores a late series response', async () => {
    const wrapper = await open(legacyPolicy);
    let resolveTcl!: (value: unknown) => void;
    listSeries.mockImplementationOnce(() => new Promise((resolve) => { resolveTcl = resolve; }));
    await field(wrapper, 'Бренд', 'select').setValue(11);
    expect(button(wrapper, 'Сохранить правило').attributes('disabled')).toBeDefined();
    await field(wrapper, 'Бренд', 'select').setValue(10);
    await flushPromises();
    resolveTcl({ items: [{ id: 99, title: 'TCL Elite', products_count: 1 }] });
    await flushPromises();
    expect(surface().text()).not.toContain('TCL Elite');
    expect(field(wrapper, 'iERA').element).toHaveProperty('checked', false);
  });

  it('retains saved series and blocks saving if the series lookup fails', async () => {
    listSeries.mockRejectedValueOnce(new Error('Unavailable'));
    const wrapper = await open(legacyPolicy);
    expect(surface().get('[aria-label="Выбранные серии"]').text()).toContain('iERA');
    expect(button(wrapper, 'Сохранить правило').attributes('disabled')).toBeDefined();
  });

  it('renders every series and a readable duration in the rule summary', () => {
    expect(warrantyScopeLabel({ ...legacyPolicy, brand_id: 10, brand_title: 'MDV', series_ids: [20, 21], series_titles: ['iERA', 'INFINI'] }))
      .toBe('Биоконд · MDV · iERA, INFINI');
    expect(warrantyDurationLabel(48)).toBe('4 года');
    expect(warrantyDurationLabel(12)).toBe('1 год');
    expect(warrantyDurationLabel(84)).toBe('7 лет');
    expect(warrantyDurationLabel(18)).toBe('18 мес.');
  });
});
