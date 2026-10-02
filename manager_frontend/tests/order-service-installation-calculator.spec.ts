import { flushPromises, mount, type VueWrapper } from '@vue/test-utils';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import OrderServiceInstallationCalculator from '../src/components/orders/OrderServiceInstallationCalculator.vue';
import type { ManagerInstallationPreviewResponse } from '../src/client';
import type { StandardInstallationChoice } from '../src/services/installation-estimate-api';

const mocks = vi.hoisted(() => ({ list: vi.fn(), preview: vi.fn(), confirm: vi.fn(), attach: vi.fn() }));
vi.mock('../src/client', () => ({ ManagerInstallationEstimatesService: {
  previewManagerInstallationEstimate: mocks.preview,
  confirmManagerInstallationEstimate: mocks.confirm,
  attachManagerInstallationEstimate: mocks.attach,
} }));
vi.mock('../src/services/installation-estimate-api', async (original) => ({
  ...await original<typeof import('../src/services/installation-estimate-api')>(),
  listInstallationStandardTariffs: mocks.list,
}));
const tariff: StandardInstallationChoice = { code: 'wall.small', title: 'Монтаж до 4,2 кВт',
  description: 'Трасса 3 м; проход стены до 80 см; подключение питания', price: '600',
  product_kind: 'complete_split_system', indoor_type: 'wall', route_m: '3',
  holes_by_type: { through_thick: '1' }, bookRevision: 7 };
const fixed = { status: 'fixed', scope_ref: 'scope', preview_ref: 'a'.repeat(64), total: '730.25',
  collapsed_lines: [{ title: 'Монтаж до 4,2 кВт', description: 'Трасса 5 м; стена до 80 см; питание', price: '730.25' }],
  detailed_lines: [] } as unknown as ManagerInstallationPreviewResponse;
const deferred = <T,>() => {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => { resolve = done; });
  return { promise, resolve };
};
const mounted: VueWrapper[] = [];
const mountCalculator = (initialTariff: StandardInstallationChoice | null = tariff, quantity = 27) => {
  const wrapper = mount(OrderServiceInstallationCalculator, { props: { initialTariff, quantity } });
  mounted.push(wrapper);
  return wrapper;
};
const button = (wrapper: VueWrapper, text: string) => wrapper.findAll('button').find((item) => item.text() === text)!;
beforeEach(() => {
  vi.clearAllMocks();
  mocks.list.mockReset().mockResolvedValue({ items: [tariff], price_book_revision: 7 });
  mocks.preview.mockReset().mockResolvedValue(fixed);
  sessionStorage.clear();
});
afterEach(() => { mounted.splice(0).forEach((wrapper) => wrapper.unmount()); sessionStorage.clear(); });

describe('service row installation calculator', () => {
  it('starts from published defaults, with an explicit tariff choice for a custom row', async () => {
    const wrapper = mountCalculator(null);
    await flushPromises();
    expect(wrapper.find('[data-testid="calculator-route"]').exists()).toBe(false);
    expect(wrapper.get('[data-testid="calculator-tariff"]').element).toHaveProperty('value', '');
    await wrapper.get('[data-testid="calculator-tariff"]').setValue(tariff.code);
    expect(wrapper.get('[data-testid="calculator-route"]').element).toHaveProperty('value', '3');
    expect(wrapper.get('[data-testid="calculator-thick"]').element).toHaveProperty('value', '1');
    await wrapper.get('[data-testid="calculator-calculate"]').trigger('click');
    await flushPromises();
    expect(mocks.preview).toHaveBeenCalledWith(expect.any(String), expect.objectContaining({
      expected_revision: 7, tariff_selections: { 'service-row': tariff.code },
      installations: [expect.objectContaining({ route_length_m: 3,
        holes_by_type: { through_thin: 0, through_thick: 1, through_over_80: 0 }, extras: [] })],
    }));
  });

  it('calculates a preview and applies unit price, title and description only when explicitly requested', async () => {
    const wrapper = mountCalculator();
    await flushPromises();
    await wrapper.get('[data-testid="calculator-route"]').setValue('5');
    await wrapper.get('[data-testid="calculator-calculate"]').trigger('click');
    await flushPromises();
    expect(wrapper.emitted('apply')).toBeUndefined();
    expect(mocks.confirm).not.toHaveBeenCalled();
    expect(mocks.attach).not.toHaveBeenCalled();
    expect(wrapper.text()).toContain('за 27 шт.');
    expect(wrapper.text()).toContain('730,25 BYN');
    await wrapper.get('[data-testid="calculator-apply"]').trigger('click');
    expect(wrapper.emitted('apply')).toEqual([[{ title: tariff.title,
      description: 'Трасса 5 м; стена до 80 см; питание', price: 730.25, installation_standard: tariff }]]);
    expect(wrapper.props('quantity')).toBe(27);
    expect(wrapper.emitted('update:quantity')).toBeUndefined();
    expect(wrapper.emitted('apply')?.[0]?.[0]).not.toHaveProperty('quantity');
  });

  it('keeps published power, wall and electrical defaults in the applied description when preview has no lines', async () => {
    mocks.preview.mockResolvedValue({ ...fixed, total: '600', collapsed_lines: [] });
    const wrapper = mountCalculator();
    await flushPromises();
    await wrapper.get('[data-testid="calculator-calculate"]').trigger('click');
    await flushPromises();
    await wrapper.get('[data-testid="calculator-apply"]').trigger('click');
    expect(wrapper.emitted('apply')?.[0]?.[0]).toMatchObject({
      title: 'Монтаж до 4,2 кВт', description: tariff.description, price: 600,
    });
  });

  it('does not apply a computed preview when closed', async () => {
    const wrapper = mountCalculator();
    await flushPromises();
    await wrapper.get('[data-testid="calculator-calculate"]').trigger('click');
    await flushPromises();
    await button(wrapper, 'Закрыть расчёт').trigger('click');
    expect(wrapper.emitted('close')).toEqual([[]]);
    expect(wrapper.emitted('apply')).toBeUndefined();
  });

  it('invalidates a previous preview after measurements change and allows a fresh calculation', async () => {
    const wrapper = mountCalculator();
    await flushPromises();
    await wrapper.get('[data-testid="calculator-calculate"]').trigger('click');
    await flushPromises();
    expect(wrapper.find('[data-testid="calculator-apply"]').exists()).toBe(true);
    await wrapper.get('[data-testid="calculator-route"]').setValue('8');
    expect(wrapper.find('[data-testid="calculator-apply"]').exists()).toBe(false);
    await wrapper.get('[data-testid="calculator-calculate"]').trigger('click');
    await flushPromises();
    expect(mocks.preview.mock.calls[1]![1].installations[0].route_length_m).toBe(8);
    expect(wrapper.find('[data-testid="calculator-apply"]').exists()).toBe(true);
  });

  it('keeps two row calculators independent even with a stale global estimate stored', async () => {
    sessionStorage.setItem('manager.installation-order:anonymous:8:12', JSON.stringify({
      source: 'equipment', selected: [44], work: { 'p:12:44:1': { route: 99 } },
      intent: { confirmed: { estimate_id: 31, revision: 1 } }, archived: true,
    }));
    const first = mountCalculator();
    const second = mountCalculator();
    await flushPromises();
    await first.get('[data-testid="calculator-route"]').setValue('9');
    expect(second.get('[data-testid="calculator-route"]').element).toHaveProperty('value', '3');
    await first.get('[data-testid="calculator-calculate"]').trigger('click');
    await flushPromises();
    expect(first.find('[data-testid="calculator-apply"]').exists()).toBe(true);
    expect(second.find('[data-testid="calculator-apply"]').exists()).toBe(false);
    expect(mocks.confirm).not.toHaveBeenCalled();
    expect(mocks.attach).not.toHaveBeenCalled();
  });

  it.each(['quote', 'unknown'])('does not offer Apply for a %s preview', async (status) => {
    mocks.preview.mockResolvedValue({ ...fixed, status });
    const wrapper = mountCalculator();
    await flushPromises();
    await wrapper.get('[data-testid="calculator-calculate"]').trigger('click');
    await flushPromises();
    expect(wrapper.find('[data-testid="calculator-apply"]').exists()).toBe(false);
    expect(wrapper.text()).toContain('Можно указать согласованную цену вручную');
  });

  it.each(['-1', '1001'])('reports invalid route %s without requesting a preview', async (route) => {
    const wrapper = mountCalculator();
    await flushPromises();
    await wrapper.get('[data-testid="calculator-route"]').setValue(route);
    await wrapper.get('[data-testid="calculator-calculate"]').trigger('click');
    expect(wrapper.get('[role="alert"]').text()).toContain('Проверьте длину трассы');
    expect(mocks.preview).not.toHaveBeenCalled();
  });

  it.each(['edit', 'reset', 'unmount'])('ignores an in-flight preview after %s', async (action) => {
    const pending = deferred<ManagerInstallationPreviewResponse>();
    mocks.preview.mockReturnValueOnce(pending.promise);
    const wrapper = mountCalculator();
    await flushPromises();
    await wrapper.get('[data-testid="calculator-route"]').setValue('6');
    await wrapper.get('[data-testid="calculator-calculate"]').trigger('click');
    if (action === 'edit') await wrapper.get('[data-testid="calculator-route"]').setValue('7');
    if (action === 'reset') {
      await button(wrapper, 'Сбросить к стандартному составу').trigger('click');
      expect(wrapper.get('[data-testid="calculator-route"]').element).toHaveProperty('value', '3');
    }
    if (action === 'unmount') { wrapper.unmount(); mounted.splice(mounted.indexOf(wrapper), 1); }
    pending.resolve(fixed);
    await flushPromises();
    if (action !== 'unmount') expect(wrapper.find('[data-testid="calculator-apply"]').exists()).toBe(false);
    expect(wrapper.emitted('apply')).toBeUndefined();
  });

  it('keeps manual entry available when published tariffs fail to load', async () => {
    mocks.list.mockRejectedValueOnce(new Error('Тарифы недоступны'));
    const wrapper = mountCalculator();
    await flushPromises();
    expect(wrapper.get('[role="alert"]').text()).toContain('Тарифы недоступны');
    expect(wrapper.find('[data-testid="calculator-calculate"]').exists()).toBe(false);
    await button(wrapper, 'Закрыть расчёт').trigger('click');
    expect(wrapper.emitted('close')).toEqual([[]]);
  });
});
