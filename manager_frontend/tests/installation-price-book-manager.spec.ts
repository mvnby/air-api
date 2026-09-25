import { flushPromises, mount } from '@vue/test-utils';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  listTariffs: vi.fn(), createTariff: vi.fn(), updateTariff: vi.fn(),
  deleteTariff: vi.fn(), listFavorites: vi.fn(), createRule: vi.fn(), updateRule: vi.fn(), deleteRule: vi.fn(),
  comparison: vi.fn(), publish: vi.fn(), confirm: vi.fn(),
}));
vi.mock('../src/api', () => ({ api: {
  listManagerTariffsByKind: mocks.listTariffs, createManagerTariff: mocks.createTariff,
  updateManagerTariff: mocks.updateTariff, deleteManagerTariff: mocks.deleteTariff,
  listManagerFavoriteTariffRules: mocks.listFavorites,
  createManagerTariffRule: mocks.createRule, updateManagerTariffRule: mocks.updateRule,
  deleteManagerTariffRule: mocks.deleteRule,
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
const comparisonReport = (base = '600', route = '50', revision: number | null = 2) => ({
  price_book_revision: revision,
  items: [{
    legacy_rate_id: 1, legacy_category: 'Wall', legacy_power_range: '07-12',
    legacy_base_price: '600', legacy_route_extra_price: '50',
    status: base === '600' && route === '50' ? 'price_equal_review_required' : 'price_diff_review_required',
    candidates: [{ tariff_code: tariff.installation_code, matcher: tariff.installation_match,
      mode: 'fixed', base_price: base, route_extra_price: route }],
  }],
});
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
    mocks.deleteRule.mockResolvedValue({}); mocks.deleteTariff.mockResolvedValue({});
    mocks.comparison.mockResolvedValue(comparisonReport());
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
      installation_code: expect.stringMatching(/^installation\.complete_split_system\.standard\.cassette\.[a-f0-9]{8}$/),
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
    expect(wrapper.text()).toContain('База и доп. трасса совпадают; подбор проверить');
    expect(wrapper.text()).toContain('трубы 1/4" + 3/8"');
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
    mocks.publish.mockRejectedValueOnce({ body: { detail: { code: 'missing_route_price', message: 'installation.wall.abc12345: route.extra_m is required' } } });
    const wrapper = mount(TariffsView, mountOptions);
    await flushPromises();
    expect(wrapper.text()).toContain('Нет кандидатов — требуется сопоставление');
    await wrapper.findAll('button').find(item => item.text().includes('Опубликовать книгу'))!.trigger('click');
    await flushPromises();
    expect(wrapper.text()).toContain('Добавьте правило «Трасса сверх включённой»');
    expect(wrapper.text()).toContain('Проверьте тариф: Настенный монтаж');
    expect(wrapper.text()).not.toContain('route.extra_m is required');
    mocks.publish.mockRejectedValueOnce({ status: 403, message: 'Forbidden' });
    await wrapper.findAll('button').find(item => item.text().includes('Опубликовать книгу'))!.trigger('click');
    await flushPromises();
    expect(wrapper.find('[role="alert"]').text()).toContain('Нет прав на публикацию');
  });

  it('refreshes changed draft prices before allowing publication', async () => {
    let resolveRefresh!: (value: ReturnType<typeof comparisonReport>) => void;
    mocks.comparison.mockResolvedValueOnce(comparisonReport());
    mocks.comparison.mockImplementationOnce(() => new Promise((resolve) => { resolveRefresh = resolve; }));
    mocks.comparison.mockResolvedValueOnce(comparisonReport('650', '50', 3));
    mocks.listTariffs.mockResolvedValueOnce({ items: [tariff] });
    mocks.listTariffs.mockResolvedValue({ items: [{ ...tariff, base_price: 650 }] });
    const wrapper = mount(TariffsView, mountOptions);
    await flushPromises();
    await wrapper.find('button[title="Редактировать"]').trigger('click');
    const modal = wrapper.findComponent(TariffEditModal);
    await modal.find('input[type="number"][min="0"]').setValue('650');
    await save(modal as ReturnType<typeof mount>);
    expect(mocks.updateTariff).toHaveBeenCalledWith(10, expect.objectContaining({ base_price: 650 }));
    expect(wrapper.text()).toContain('Загружаем сравнение');
    expect(wrapper.findAll('button').find((item) => item.text().includes('Опубликовать книгу'))!.attributes('disabled')).toBeDefined();
    expect(mocks.publish).not.toHaveBeenCalled();

    resolveRefresh(comparisonReport('650'));
    await flushPromises();
    expect(wrapper.text()).toContain('База 650 BYN');
    expect(wrapper.text()).toContain('Различаются: база');
    await wrapper.findAll('button').find((item) => item.text().includes('Опубликовать книгу'))!.trigger('click');
    await flushPromises();
    expect(mocks.publish).toHaveBeenCalledOnce();
  });

  it('refreshes comparison after rule edit and deletion', async () => {
    const withRule = { ...tariff, rules: [{ id: 9, component_code: 'route.extra_m', name: 'Трасса',
      rule_type: 'per_meter_over_included', line_template: '{name}', unit: 'м', unit_price: 50,
      is_optional: false, is_favorite: false, is_active: true, sort_order: 0, service_id: null }] };
    mocks.listTariffs.mockResolvedValue({ items: [withRule] });
    const wrapper = mount(TariffsView, mountOptions);
    await flushPromises();
    await wrapper.find('button[title="Редактировать правило"]').trigger('click');
    const ruleModal = wrapper.findComponent(TariffRuleEditModal);
    await ruleModal.find('[aria-label="Смысл компонента"]').setValue('pump.install');
    await save(ruleModal as ReturnType<typeof mount>);
    await flushPromises();
    expect(mocks.updateRule).toHaveBeenCalledWith(10, 9, expect.objectContaining({
      component_code: 'pump.install', rule_type: 'per_unit_manual', unit: 'шт', is_optional: true,
    }));
    expect(mocks.comparison).toHaveBeenCalledTimes(2);
    await wrapper.find('button[title="Удалить правило"]').trigger('click');
    await flushPromises();
    expect(mocks.deleteRule).toHaveBeenCalledWith(10, 9);
    expect(mocks.comparison).toHaveBeenCalledTimes(3);
  });

  it('ignores an older comparison response after a draft refresh', async () => {
    let resolveInitial!: (value: ReturnType<typeof comparisonReport>) => void;
    let resolveLatest!: (value: ReturnType<typeof comparisonReport>) => void;
    mocks.comparison.mockImplementationOnce(() => new Promise((resolve) => { resolveInitial = resolve; }));
    mocks.comparison.mockImplementationOnce(() => new Promise((resolve) => { resolveLatest = resolve; }));
    const wrapper = mount(TariffsView, mountOptions);
    await flushPromises();
    wrapper.findComponent(TariffRuleEditModal).vm.$emit('success');
    await flushPromises();
    resolveLatest(comparisonReport('650'));
    await flushPromises();
    resolveInitial(comparisonReport('600'));
    await flushPromises();
    expect(wrapper.text()).toContain('База 650 BYN');
    expect(wrapper.text()).not.toContain('База и доп. трасса совпадают');
  });

  it('keeps publication status unknown and button disabled when comparison fails', async () => {
    mocks.comparison.mockRejectedValueOnce({ status: 503, message: 'Unavailable' });
    const wrapper = mount(TariffsView, mountOptions);
    await flushPromises();
    expect(wrapper.text()).toContain('статус публикации недоступен');
    expect(wrapper.text()).not.toContain('ещё не опубликована');
    expect(wrapper.findAll('button').find((item) => item.text().includes('Опубликовать книгу'))!.attributes('disabled')).toBeDefined();
  });

  it('resets comparison pagination when returning to installation', async () => {
    const fullPage = { ...comparisonReport(), items: Array.from({ length: 100 }, (_, index) => ({
      ...comparisonReport().items[0]!, legacy_rate_id: index + 1,
    })) };
    mocks.comparison.mockResolvedValueOnce(fullPage);
    mocks.comparison.mockResolvedValueOnce(comparisonReport('650'));
    mocks.comparison.mockResolvedValueOnce(comparisonReport());
    const wrapper = mount(TariffsView, mountOptions);
    await flushPromises();
    await wrapper.findAll('button').find((item) => item.text() === 'Далее')!.trigger('click');
    await flushPromises();
    expect(mocks.comparison).toHaveBeenNthCalledWith(2, 100);
    await wrapper.find('select').setValue('repair');
    await flushPromises();
    await wrapper.find('select').setValue('installation');
    await flushPromises();
    expect(mocks.comparison).toHaveBeenNthCalledWith(3, 0);
    expect(wrapper.text()).toContain('Записи 1–1');
  });
});
