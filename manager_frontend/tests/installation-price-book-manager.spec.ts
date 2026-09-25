import { flushPromises, mount } from '@vue/test-utils';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  listTariffs: vi.fn(), createTariff: vi.fn(), updateTariff: vi.fn(),
  listFavorites: vi.fn(), createRule: vi.fn(), updateRule: vi.fn(),
  comparison: vi.fn(), publish: vi.fn(), confirm: vi.fn(),
}));
vi.mock('../src/api', () => ({ api: {
  listManagerTariffsByKind: mocks.listTariffs, createManagerTariff: mocks.createTariff,
  updateManagerTariff: mocks.updateTariff, listManagerFavoriteTariffRules: mocks.listFavorites,
  createManagerTariffRule: mocks.createRule, updateManagerTariffRule: mocks.updateRule,
  listManagerInstallationLegacyComparison: mocks.comparison,
  publishManagerInstallationPriceBook: mocks.publish,
} }));
vi.mock('../src/services/ui-feedback', () => ({ confirmDialog: mocks.confirm }));

import TariffEditModal from '../src/components/TariffEditModal.vue';
import TariffRuleEditModal from '../src/components/TariffRuleEditModal.vue';
import TariffsView from '../src/views/TariffsView.vue';

const tariff = {
  id: 10, service_kind: 'installation' as const, short_name: 'Настенный монтаж',
  selector_label: 'Настенный монтаж', full_description: null, estimate_template: 'Монтаж',
  category: 'Wall', power_range: '07-12', base_price: 600, included_route_meters: 3,
  installation_code: 'installation.wall.abc12345', installation_price_mode: 'fixed' as const,
  installation_match: { product_kind: 'complete_split_system', indoor_type: 'wall' as const,
    capacity_min_kw: '2', capacity_max_kw: '4', pipe_liquid: '1/4"', pipe_gas: '3/8"',
    weight_source: null, weight_min_kg: null, weight_max_kg: null },
  included_holes_by_type: { diamond: 1 }, is_active: true, sort_order: 0, comment: null,
  rules: [],
};
const mountOptions = { global: { stubs: { teleport: true } } };
const save = async (wrapper: ReturnType<typeof mount>) => {
  const button = wrapper.findAll('button').find(item => item.text().includes('Сохранить'));
  await button!.trigger('click'); await flushPromises();
};

describe('canonical installation book manager', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.updateTariff.mockResolvedValue(tariff); mocks.createTariff.mockResolvedValue(tariff);
    mocks.listTariffs.mockResolvedValue({ items: [tariff] });
    mocks.listFavorites.mockResolvedValue({ items: [] });
    mocks.updateRule.mockResolvedValue({}); mocks.createRule.mockResolvedValue({});
    mocks.comparison.mockResolvedValue({ price_book_revision: 2, items: [{
      legacy_rate_id: 1, legacy_category: 'Wall', legacy_power_range: '07-12',
      legacy_base_price: '600', legacy_route_extra_price: '50',
      status: 'price_equal_review_required', candidates: [{ tariff_code: tariff.installation_code }],
    }] });
    mocks.publish.mockResolvedValue({ revision: 3 }); mocks.confirm.mockResolvedValue(true);
  });

  it('saves typed matcher and included work without publishing', async () => {
    const wrapper = mount(TariffEditModal, { props: { modelValue: true, tariff }, ...mountOptions });
    await wrapper.find('[aria-label="Мощность до, кВт"]').setValue('5');
    await wrapper.find('[aria-label="Включено алмазных отверстий"]').setValue('2');
    await save(wrapper);
    expect(mocks.updateTariff).toHaveBeenCalledWith(10, expect.objectContaining({
      installation_code: 'installation.wall.abc12345', installation_price_mode: 'fixed',
      installation_match: expect.objectContaining({ indoor_type: 'wall', capacity_max_kw: 5,
        pipe_liquid: '1/4"', pipe_gas: '3/8"' }),
      included_holes_by_type: { diamond: 2 }, included_route_meters: 3,
    }));
    expect(mocks.publish).not.toHaveBeenCalled();
  });

  it('retains legacy tariff outside the book unless a type is selected', async () => {
    const legacy = { ...tariff, installation_code: null, installation_match: null };
    const wrapper = mount(TariffEditModal, { props: { modelValue: true, tariff: legacy }, ...mountOptions });
    await save(wrapper);
    expect(mocks.updateTariff).toHaveBeenCalledWith(10, expect.objectContaining({ installation_code: null, installation_match: null }));
  });

  it('creates a stable internal code when a new typed tariff is saved', async () => {
    const wrapper = mount(TariffEditModal, { props: { modelValue: true, tariff: null }, ...mountOptions });
    await wrapper.find('input[placeholder="Монтаж настенного до 3.5 кВт"]').setValue('Монтаж кассетного');
    await wrapper.find('[aria-label="Тип внутреннего блока"]').setValue('cassette');
    await wrapper.find('[aria-label="Мощность до, кВт"]').setValue('7');
    await wrapper.find('[aria-label="Жидкостная труба"]').setValue('1/4"');
    await wrapper.find('[aria-label="Газовая труба"]').setValue('1/2"');
    await save(wrapper);
    expect(mocks.createTariff).toHaveBeenCalledWith(expect.objectContaining({
      installation_code: expect.stringMatching(/^installation\.cassette\.[a-f0-9]{8}$/),
      installation_match: expect.objectContaining({ indoor_type: 'cassette', capacity_max_kw: 7 }),
    }));
    expect(mocks.publish).not.toHaveBeenCalled();
  });

  it('binds route component to its stable calculation semantics', async () => {
    const wrapper = mount(TariffRuleEditModal, { props: { modelValue: true, tariffId: 10, tariff, rule: null }, ...mountOptions });
    await flushPromises();
    await wrapper.find('[aria-label="Смысл компонента"]').setValue('route.extra_m');
    await wrapper.find('input[type="number"][min="0"][step="0.01"]').setValue('50');
    await save(wrapper);
    expect(mocks.createRule).toHaveBeenCalledWith(10, expect.objectContaining({
      component_code: 'route.extra_m', rule_type: 'per_meter_over_included', unit: 'м',
      is_optional: false, unit_price: 50,
    }));
  });

  it('shows category-only comparison and publishes only after the explicit click', async () => {
    const wrapper = mount(TariffsView, mountOptions);
    await flushPromises();
    expect(wrapper.text()).toContain('соответствие требует проверки');
    expect(mocks.publish).not.toHaveBeenCalled();
    const button = wrapper.findAll('button').find(item => item.text().includes('Опубликовать книгу'))!;
    await button.trigger('click'); await flushPromises();
    expect(mocks.confirm).toHaveBeenCalledOnce();
    expect(mocks.publish).toHaveBeenCalledOnce();
    expect(wrapper.text()).toContain('ревизия 2 опубликована');
  });

  it('shows missing coverage and server validation or permission errors', async () => {
    mocks.comparison.mockResolvedValueOnce({ price_book_revision: null, items: [{
      legacy_rate_id: 2, legacy_category: 'Duct', legacy_power_range: 'all',
      legacy_base_price: '1500', legacy_route_extra_price: '85', status: 'unmapped_review_required', candidates: [],
    }] });
    mocks.publish.mockRejectedValueOnce({ body: { detail: { code: 'missing_route_price', message: 'route.extra_m is required' } } });
    const wrapper = mount(TariffsView, mountOptions);
    await flushPromises();
    expect(wrapper.text()).toContain('Нет кандидатов — требуется сопоставление');
    await wrapper.findAll('button').find(item => item.text().includes('Опубликовать книгу'))!.trigger('click');
    await flushPromises();
    expect(wrapper.text()).toContain('Добавьте правило «Трасса сверх включённой»');
    mocks.publish.mockRejectedValueOnce({ status: 403, message: 'Forbidden' });
    await wrapper.findAll('button').find(item => item.text().includes('Опубликовать книгу'))!.trigger('click');
    await flushPromises();
    expect(wrapper.find('[role="alert"]').text()).toContain('Нет прав на публикацию');
  });
});
