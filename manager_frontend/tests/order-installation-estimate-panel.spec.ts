import { mount, flushPromises } from '@vue/test-utils';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import OrderInstallationEstimatePanel from '../src/components/orders/OrderInstallationEstimatePanel.vue';
import { managerSession } from '../src/services/manager-session';

const service = vi.hoisted(() => ({
  getManagerOrderDetail: vi.fn(),
  previewManagerInstallationEstimate: vi.fn(),
  confirmManagerInstallationEstimate: vi.fn(),
  attachManagerInstallationEstimate: vi.fn(),
  resolveInstallationStandard: vi.fn(),
}));
vi.mock('../src/services/installation-estimate-api', async (importOriginal) => ({
  ...await importOriginal<typeof import('../src/services/installation-estimate-api')>(),
  resolveInstallationStandard: service.resolveInstallationStandard,
}));
vi.mock('../src/client', () => ({
  ManagerOrdersService: { getManagerOrderDetail: service.getManagerOrderDetail },
  ManagerInstallationEstimatesService: {
    previewManagerInstallationEstimate: service.previewManagerInstallationEstimate,
    confirmManagerInstallationEstimate: service.confirmManagerInstallationEstimate,
    attachManagerInstallationEstimate: service.attachManagerInstallationEstimate,
  },
}));

const product = { id: 71, proposal_id: 12, product_id: 44, product_title: 'Кондиционер', quantity: 1,
  price: 1200, is_installation_included: false };
const order = { id: 8, proposals: [{ id: 12, status: 'draft', is_archived: false, product_lines: [product] }] };
const fixed = { status: 'fixed', scope_ref: 'scope', preview_ref: 'a'.repeat(64), total: '530.25',
  collapsed_lines: [{ title: 'Установка №1: монтаж.', price: '530.25' }],
  detailed_lines: [{ title: 'Установка №1: монтаж', price: '500.00' },
    { title: 'Установка №1: трасса', price: '30.25' }] };

const mountPanel = () => mount(OrderInstallationEstimatePanel, {
  props: { orderId: 8, proposalId: 12,
    beforeAction: vi.fn().mockResolvedValue(true),
    beginAttach: vi.fn().mockResolvedValue(true), afterAttach: vi.fn().mockResolvedValue(true),
    endAttach: vi.fn() },
});

const prepare = async (wrapper: ReturnType<typeof mountPanel>) => {
  await wrapper.get('[data-testid="installation-open"]').trigger('click');
  await flushPromises();
  await wrapper.get('[data-testid="installation-product"]').setValue(true);
  await flushPromises();
  await wrapper.get('[data-testid="installation-edit-work"]').trigger('click');
  await wrapper.get('[data-testid="installation-route"]').setValue('6');
  await wrapper.get('[data-testid="installation-holes"]').setValue('1');
  await wrapper.get('[data-testid="installation-thick-holes"]').setValue('0');
  await wrapper.get('[data-testid="installation-over80-holes"]').setValue('0');
};

beforeEach(() => {
  sessionStorage.clear();
  vi.clearAllMocks();
  managerSession.auth.value = null;
  service.getManagerOrderDetail.mockResolvedValue(order);
  service.resolveInstallationStandard.mockResolvedValue({ status: 'fixed', scope_ref: 'scope',
    included: { route_m: '3', holes_by_type: { shared_pass_through: '1' } } });
  service.previewManagerInstallationEstimate.mockResolvedValue(fixed);
  service.confirmManagerInstallationEstimate.mockResolvedValue({ estimate_id: 31, revision: 1, total: '530.25' });
  service.attachManagerInstallationEstimate.mockResolvedValue({ lines: [{ title: 'Установка №1: монтаж.', price: '530.25' }], total: '530.25' });
});

describe('OrderInstallationEstimatePanel', () => {
  it('adds standard installation to the remaining ready-to-send proposal after the active proposal is archived', async () => {
    const wrapper = mountPanel();
    service.getManagerOrderDetail.mockResolvedValue({ ...order, proposals: [
      { ...order.proposals[0], is_archived: true },
      { id: 13, status: 'ready_to_send', is_archived: false, is_selected: true,
        product_lines: [{ ...product, proposal_id: 13 }] },
    ] });
    await wrapper.setProps({ proposalId: 13 });
    await wrapper.get('[data-testid="installation-standard-add"]').trigger('click');
    await flushPromises();

    expect(service.previewManagerInstallationEstimate.mock.calls[0][1].installations[0].key).toBe('p:13:71:1');
    expect(service.attachManagerInstallationEstimate).toHaveBeenCalledWith(31, 8, 13, expect.any(String), { revision: 1, mode: 'collapsed' });
    expect(wrapper.text()).toContain('Смета прикреплена');
    wrapper.unmount();
  });

  it.each(['ready_to_send', 'rejected'])('opens installation settings for an editable %s proposal', async (status) => {
    service.getManagerOrderDetail.mockResolvedValue({ ...order, proposals: [{ ...order.proposals[0], status }] });
    const wrapper = mountPanel();
    await wrapper.get('[data-testid="installation-open"]').trigger('click');
    await flushPromises();
    expect(wrapper.get('[data-testid="installation-product"]').exists()).toBe(true);
    expect(wrapper.find('[role="alert"]').exists()).toBe(false);
    wrapper.unmount();
  });

  it('adds a service-only standard tariff to a ready-to-send proposal', async () => {
    service.getManagerOrderDetail.mockResolvedValue({ ...order, proposals: [{ ...order.proposals[0], status: 'ready_to_send' }] });
    service.previewManagerInstallationEstimate.mockResolvedValueOnce({ ...fixed, total: '600' });
    const wrapper = mountPanel();
    await (wrapper.vm as any).selectStandardTariff({ code: 'wall.small', title: 'Монтаж настенного кондиционера до 4,2 кВт',
      price: '600', description: 'Стандарт', route_m: '3', holes_by_type: { shared_pass_through: '1' },
      product_kind: 'complete_split_system', indoor_type: 'wall', bookRevision: 7 });
    await flushPromises();
    expect(service.attachManagerInstallationEstimate).toHaveBeenCalledWith(31, 8, 12, expect.any(String), { revision: 1, mode: 'collapsed' });
    expect(wrapper.text()).toContain('Смета прикреплена');
    wrapper.unmount();
  });

  it.each(['sent', 'approved'])('keeps installation changes blocked for a %s proposal', async (status) => {
    service.getManagerOrderDetail.mockResolvedValue({ ...order, proposals: [{ ...order.proposals[0], status }] });
    const wrapper = mountPanel();
    await wrapper.get('[data-testid="installation-standard-add"]').trigger('click');
    await flushPromises();
    expect(wrapper.text()).toContain('Верните его в черновик либо создайте копию');
    expect(service.resolveInstallationStandard).not.toHaveBeenCalled();
    expect(service.previewManagerInstallationEstimate).not.toHaveBeenCalled();
    expect(service.attachManagerInstallationEstimate).not.toHaveBeenCalled();
    wrapper.unmount();
  });

  it.each(['archived', 'missing'])('does not use a %s active proposal', async (state) => {
    service.getManagerOrderDetail.mockResolvedValue({ ...order, proposals: state === 'archived'
      ? [{ ...order.proposals[0], is_archived: true }] : [] });
    const wrapper = mountPanel();
    await wrapper.get('[data-testid="installation-standard-add"]').trigger('click');
    await flushPromises();
    expect(wrapper.text()).toContain('Активное предложение больше недоступно');
    expect(service.attachManagerInstallationEstimate).not.toHaveBeenCalled();
    wrapper.unmount();
  });

  it('keeps each selected composition inline and retains independent values when deselected', async () => {
    service.getManagerOrderDetail.mockResolvedValue({ ...order, proposals: [{ ...order.proposals[0],
      product_lines: [{ ...product, quantity: 2 }] }] });
    const wrapper = mountPanel();
    await wrapper.get('[data-testid="installation-open"]').trigger('click');
    await flushPromises();
    const cards = wrapper.findAll('[data-testid="installation-card"]');
    expect(cards).toHaveLength(2);
    expect(cards[0]!.text()).toContain('шт. 1');
    expect(cards[1]!.text()).toContain('шт. 2');
    expect(wrapper.find('[data-testid="installation-card-work"]').exists()).toBe(false);
    await cards[0]!.get('[data-testid="installation-product"]').setValue(true);
    await flushPromises();
    expect(cards[0]!.get('[data-testid="installation-standard-summary"]').text()).toContain('стены до 80 см: 1');
    expect(cards[1]!.find('[data-testid="installation-card-work"]').exists()).toBe(false);
    await cards[0]!.get('[data-testid="installation-edit-work"]').trigger('click');
    expect(cards[0]!.get('[data-testid="installation-extra-work"]').attributes('open')).toBeUndefined();
    await cards[0]!.get('[data-testid="installation-route"]').setValue('7');
    await cards[0]!.get('[data-testid="installation-holes"]').setValue('2');
    await cards[0]!.get('[data-testid="installation-pump"]').setValue(true);
    expect(cards[0]!.get('[data-testid="installation-extra-work"]').attributes('open')).toBeDefined();
    await cards[0]!.get('[data-testid="installation-product"]').setValue(false);
    expect(cards[0]!.find('[data-testid="installation-card-work"]').exists()).toBe(false);
    await cards[1]!.get('[data-testid="installation-product"]').setValue(true);
    await flushPromises();
    expect(cards[1]!.get('[data-testid="installation-standard-summary"]').text()).toContain('Трасса 3 м');
    await cards[0]!.get('[data-testid="installation-product"]').setValue(true);
    await flushPromises();
    expect((cards[0]!.get('[data-testid="installation-route"]').element as HTMLInputElement).value).toBe('7');
    expect((cards[0]!.get('[data-testid="installation-holes"]').element as HTMLInputElement).value).toBe('2');
    expect((cards[0]!.get('[data-testid="installation-pump"]').element as HTMLInputElement).checked).toBe(true);
    expect(service.resolveInstallationStandard).toHaveBeenCalledTimes(2);
    await wrapper.get('[data-testid="installation-preview"]').trigger('click');
    await flushPromises();
    expect(service.previewManagerInstallationEstimate.mock.calls[0][1].installations).toEqual([
      expect.objectContaining({ route_length_m: 3 }),
      expect.objectContaining({ route_length_m: 7, holes_by_type: { through_thin: 2, through_thick: 1, through_over_80: 0 },
        extras: [{ code: 'pump.package', quantity: 1 }] }),
    ]);
    wrapper.unmount();
  });

  it('exposes unknown work inputs without replacing them with zeros when the standard is unavailable', async () => {
    service.resolveInstallationStandard.mockRejectedValue(new Error('Тариф недоступен'));
    const wrapper = mountPanel();
    await wrapper.get('[data-testid="installation-open"]').trigger('click');
    await flushPromises();
    await wrapper.get('[data-testid="installation-product"]').setValue(true);
    await flushPromises();
    const card = wrapper.get('[data-testid="installation-card"]');
    expect(card.get('[data-testid="installation-extra-work"]').attributes('open')).toBeDefined();
    for (const field of ['installation-route', 'installation-holes', 'installation-thick-holes', 'installation-over80-holes']) {
      expect((card.get(`[data-testid="${field}"]`).element as HTMLInputElement).value).toBe('');
    }
    await wrapper.get('[data-testid="installation-preview"]').trigger('click');
    await flushPromises();
    expect(service.previewManagerInstallationEstimate).not.toHaveBeenCalled();
    expect(wrapper.text()).toContain('укажите новую трассу и проходы стен');
    wrapper.unmount();
  });

  it('brings a calculation opened from the shared toolbar into view', async () => {
    const wrapper = mountPanel();
    await wrapper.setProps({ hideActions: true });
    const scrollIntoView = vi.fn();
    (wrapper.element as HTMLElement).scrollIntoView = scrollIntoView;
    await (wrapper.vm as any).openPanel();
    await flushPromises();
    expect(wrapper.get('[data-testid="installation-product"]').exists()).toBe(true);
    expect(scrollIntoView).toHaveBeenCalledWith({ block: 'start' });
    wrapper.unmount();
  });

  it('adds a published service-only standard without inventing equipment capacity or opening the profile form', async () => {
    service.previewManagerInstallationEstimate.mockResolvedValueOnce({ ...fixed, total: '600' });
    const wrapper = mountPanel();
    const tariff = { code: 'wall.small', title: 'Монтаж настенного кондиционера до 4,2 кВт',
      price: '600', description: 'Стандарт', route_m: '3', holes_by_type: { shared_pass_through: '1' },
      product_kind: 'complete_split_system', indoor_type: 'wall', bookRevision: 7 };
    await (wrapper.vm as any).selectStandardTariff(tariff);
    await flushPromises();
    const payload = service.previewManagerInstallationEstimate.mock.calls[0][1];
    expect(payload.installations[0].typed_profile).toEqual({ product_kind: 'complete_split_system', indoor_type: 'wall', confirmed: true });
    expect(payload.tariff_selections).toEqual({ [payload.installations[0].key]: 'wall.small' });
    expect(payload.expected_revision).toBe(7);
    expect(payload.installations[0].holes_by_type).toEqual({ through_thin: 0, through_thick: 1, through_over_80: 0 });
    expect(service.attachManagerInstallationEstimate).toHaveBeenCalledOnce();
  });

  it('does not automatically attach when an old catalogue choice has a different current price', async () => {
    const wrapper = mountPanel();
    await (wrapper.vm as any).selectStandardTariff({ code: 'wall.small', title: 'Малый настенный',
      price: '600', description: 'Стандарт', route_m: '3', holes_by_type: { shared_pass_through: '1' },
      product_kind: 'complete_split_system', indoor_type: 'wall' });
    await flushPromises();
    expect(wrapper.text()).toContain('Цена тарифа изменилась');
    expect(service.confirmManagerInstallationEstimate).not.toHaveBeenCalled();
    expect(service.attachManagerInstallationEstimate).not.toHaveBeenCalled();
    expect(wrapper.get('[data-testid="installation-add"]').exists()).toBe(true);
  });

  it('opens only work options for editing a selected service-only base tariff', async () => {
    const wrapper = mountPanel();
    await (wrapper.vm as any).selectStandardTariff({ code: 'wall.small', title: 'Малый настенный',
      price: '600', description: 'Стандарт', route_m: '3', holes_by_type: { shared_pass_through: '1' },
      product_kind: 'complete_split_system', indoor_type: 'wall' }, true);
    await flushPromises();
    expect(wrapper.findAll('select')).toHaveLength(0);
    expect(wrapper.get('[data-testid="installation-route"]').exists()).toBe(true);
    expect(service.confirmManagerInstallationEstimate).not.toHaveBeenCalled();
    await wrapper.get('[data-testid="installation-route"]').setValue('5');
    await wrapper.get('[data-testid="installation-preview"]').trigger('click');
    await flushPromises();
    expect(service.previewManagerInstallationEstimate.mock.calls[1][1].tariff_selections).toEqual(expect.objectContaining({
      [service.previewManagerInstallationEstimate.mock.calls[1][1].installations[0].key]: 'wall.small',
    }));
  });
  it('adds canonical standard installation in one click without entering measurements', async () => {
    service.resolveInstallationStandard.mockResolvedValueOnce({ status: 'fixed', scope_ref: 'scope',
      included: { route_m: '4.5', holes_by_type: { shared_pass_through: '2', through_thick: '1' } } });
    const wrapper = mountPanel();
    await wrapper.get('[data-testid="installation-standard-add"]').trigger('click');
    await flushPromises();
    expect(service.resolveInstallationStandard).toHaveBeenCalledWith({ product_id: 44, work_kind: 'standard' });
    expect(service.previewManagerInstallationEstimate.mock.calls[0][1].installations[0]).toMatchObject({
      route_length_m: 4.5, holes_by_type: { through_thin: 0, through_thick: 3, through_over_80: 0 }, extras: [],
    });
    expect(service.confirmManagerInstallationEstimate).toHaveBeenCalledOnce();
    expect(service.attachManagerInstallationEstimate).toHaveBeenCalledOnce();
    expect(wrapper.text()).toContain('Смета прикреплена');
  });

  it('starts selected equipment at canonical base and allows extra metres and a pump before adding', async () => {
    const wrapper = mountPanel();
    await wrapper.get('[data-testid="installation-open"]').trigger('click');
    await flushPromises();
    await wrapper.get('[data-testid="installation-product"]').setValue(true);
    await flushPromises();
    expect(wrapper.get('[data-testid="installation-standard-summary"]').text()).toContain('Трасса 3 м');
    await wrapper.get('[data-testid="installation-edit-work"]').trigger('click');
    expect((wrapper.get('[data-testid="installation-holes"]').element as HTMLInputElement).value).toBe('0');
    await wrapper.get('[data-testid="installation-route"]').setValue('5');
    const pump = wrapper.findAll('input[type="checkbox"]').find((input) => input.element.parentElement?.textContent?.includes('Насос с установкой'));
    await pump?.setValue(true);
    await wrapper.get('[data-testid="installation-preview"]').trigger('click');
    await flushPromises();
    expect(service.previewManagerInstallationEstimate.mock.calls[0][1].installations[0]).toMatchObject({
      route_length_m: 5, extras: [{ code: 'pump.package', quantity: 1 }],
    });
    await wrapper.get('[data-testid="installation-add"]').trigger('click');
    await flushPromises();
    expect(service.attachManagerInstallationEstimate).toHaveBeenCalledOnce();
  });

  it.each([[21], [11, 10]])('does not silently add a partial standard estimate for quantities %j', async (...quantities: number[]) => {
    service.getManagerOrderDetail.mockResolvedValue({ ...order, proposals: [{
      ...order.proposals[0], product_lines: quantities.map((quantity, index) => ({ ...product, id: 71 + index, quantity })),
    }] });
    const wrapper = mountPanel();
    await wrapper.get('[data-testid="installation-standard-add"]').trigger('click');
    await flushPromises();
    expect(wrapper.text()).toContain('до 20 установок');
    expect(service.resolveInstallationStandard).not.toHaveBeenCalled();
    expect(service.previewManagerInstallationEstimate).not.toHaveBeenCalled();
    expect(service.attachManagerInstallationEstimate).not.toHaveBeenCalled();
  });

  it('keeps an existing custom draft when the standard shortcut is clicked', async () => {
    const wrapper = mountPanel();
    await prepare(wrapper);
    await wrapper.get('[data-testid="installation-standard-add"]').trigger('click');
    await flushPromises();
    expect(service.previewManagerInstallationEstimate.mock.calls[0][1].installations[0].route_length_m).toBe(6);
    expect(service.attachManagerInstallationEstimate).not.toHaveBeenCalled();
    expect(wrapper.text()).toContain('Сохранён состав');
  });

  it('does not add a standard estimate when its price is a quote', async () => {
    service.previewManagerInstallationEstimate.mockResolvedValueOnce({ status: 'quote', scope_ref: 'scope', reason_code: 'no_match' });
    const wrapper = mountPanel();
    await wrapper.get('[data-testid="installation-standard-add"]').trigger('click');
    await flushPromises();
    expect(service.confirmManagerInstallationEstimate).not.toHaveBeenCalled();
    expect(service.attachManagerInstallationEstimate).not.toHaveBeenCalled();
    expect(wrapper.text()).toContain('индивидуальная смета');
  });

  it('does not apply a tariff resolved for a proposal that was switched away from', async () => {
    let finish!: (value: unknown) => void;
    service.resolveInstallationStandard.mockImplementationOnce(() => new Promise((resolve) => { finish = resolve; }));
    const wrapper = mountPanel();
    await wrapper.get('[data-testid="installation-standard-add"]').trigger('click');
    await flushPromises();
    await wrapper.setProps({ proposalId: 13 });
    finish({ status: 'fixed', scope_ref: 'old', included: { route_m: '3', holes_by_type: { shared_pass_through: '1' } } });
    await flushPromises();
    expect(service.previewManagerInstallationEstimate).not.toHaveBeenCalled();
    expect(service.attachManagerInstallationEstimate).not.toHaveBeenCalled();
  });

  it('stops the shortcut on a price change and requires a new calculation', async () => {
    service.confirmManagerInstallationEstimate.mockRejectedValueOnce({ body: { detail: {
      code: 'price_changed', fresh_preview: { ...fixed, total: '540.25' },
    } } });
    const wrapper = mountPanel();
    await wrapper.get('[data-testid="installation-standard-add"]').trigger('click');
    await flushPromises();
    expect(service.attachManagerInstallationEstimate).not.toHaveBeenCalled();
    expect(wrapper.text()).toContain('подтвердите его заново');
    expect(wrapper.find('[data-testid="installation-add"]').exists()).toBe(false);
  });

  it('reuses the same attachment key when the shortcut had an uncertain response', async () => {
    service.attachManagerInstallationEstimate.mockRejectedValueOnce(new Error('Connection lost'));
    const wrapper = mountPanel();
    await wrapper.get('[data-testid="installation-standard-add"]').trigger('click');
    await flushPromises();
    const key = service.attachManagerInstallationEstimate.mock.calls[0][3];
    await wrapper.get('[data-testid="installation-standard-add"]').trigger('click');
    await flushPromises();
    expect(service.attachManagerInstallationEstimate.mock.calls[1][3]).toBe(key);
    expect(service.confirmManagerInstallationEstimate).toHaveBeenCalledOnce();
  });
  it('uses persisted proposal equipment, previews exact server lines, then confirms and attaches once', async () => {
    const wrapper = mountPanel();
    await prepare(wrapper);
    await wrapper.get('[data-testid="installation-preview"]').trigger('click');
    await flushPromises();
    const payload = service.previewManagerInstallationEstimate.mock.calls[0][1];
    expect(payload.installations).toMatchObject([{ product_id: 44, display_label: '№1', route_length_m: 6,
      holes_by_type: { through_thin: 1, through_thick: 0, through_over_80: 0 } }]);
    expect(wrapper.text()).toContain('Установка №1: монтаж.');
    expect(wrapper.text()).toContain('530,25');
    await wrapper.get('[data-testid="installation-add"]').trigger('click');
    await flushPromises();
    expect(service.confirmManagerInstallationEstimate).toHaveBeenCalledWith(expect.any(String), {
      preview_ref: 'a'.repeat(64), order_id: 8, proposal_id: 12, verified_service_only_keys: [],
    });
    expect(service.attachManagerInstallationEstimate).toHaveBeenCalledWith(31, 8, 12,
      expect.any(String), { revision: 1, mode: 'collapsed' });
    expect(wrapper.props('afterAttach')).toHaveBeenCalledOnce();
  });

  it('does not allow confirmation for a quote or a changed input', async () => {
    service.previewManagerInstallationEstimate.mockResolvedValueOnce({ status: 'quote', scope_ref: 'scope', reason_code: 'no_match' });
    const wrapper = mountPanel();
    await prepare(wrapper);
    await wrapper.get('[data-testid="installation-preview"]').trigger('click');
    await flushPromises();
    expect(wrapper.find('[data-testid="installation-add"]').exists()).toBe(false);
    service.previewManagerInstallationEstimate.mockResolvedValueOnce(fixed);
    await wrapper.get('[data-testid="installation-preview"]').trigger('click');
    await flushPromises();
    expect(wrapper.find('[data-testid="installation-add"]').exists()).toBe(true);
    await wrapper.get('[data-testid="installation-route"]').setValue('7');
    expect(wrapper.find('[data-testid="installation-add"]').exists()).toBe(false);
  });

  it('sends one confirmed multi system with shared work inputs', async () => {
    const wrapper = mountPanel();
    await wrapper.get('[data-testid="installation-open"]').trigger('click');
    await flushPromises();
    await wrapper.findAll('button').find((button) => button.text() === 'Без товара')?.trigger('click');
    await wrapper.findAll('select')[0].setValue('multi_split_system');
    const count = wrapper.findAll('input[type="number"]').find((input) => input.attributes('min') === '2');
    await count?.setValue('2');
    await wrapper.find('textarea').setValue('Два внутренних блока и один наружный');
    const verified = wrapper.findAll('input[type="checkbox"]').find((input) => input.element.parentElement?.textContent?.includes('Параметры оборудования проверены'));
    await verified?.setValue(true);
    await wrapper.get('[data-testid="installation-route"]').setValue('8');
    await wrapper.get('[data-testid="installation-holes"]').setValue('1');
    await wrapper.get('[data-testid="installation-thick-holes"]').setValue('1');
    await wrapper.get('[data-testid="installation-over80-holes"]').setValue('0');
    await wrapper.findAll('input[type="checkbox"]').find((input) => input.element.parentElement?.textContent?.includes('Насос с установкой'))?.setValue(true);
    await wrapper.get('[data-testid="installation-preview"]').trigger('click');
    await flushPromises();
    const input = service.previewManagerInstallationEstimate.mock.calls[0][1];
    expect(input.installations).toHaveLength(1);
    expect(input.installations[0]).toMatchObject({
      typed_profile: { product_kind: 'multi_split_system', indoor_unit_count: 2,
        composition_note: 'Два внутренних блока и один наружный', confirmed: true },
      route_length_m: 8, holes_by_type: { through_thin: 1, through_thick: 1 },
      extras: [{ code: 'pump.package', quantity: 1 }],
    });
    expect(input.installations[0].typed_profile.indoor_type).toBeUndefined();
    await wrapper.findAll('select')[0].setValue('complete_split_system');
    await wrapper.findAll('select')[1].setValue('wall');
    await wrapper.find('input[min="0.001"]').setValue('2.5');
    await wrapper.get('[data-testid="installation-preview"]').trigger('click');
    await flushPromises();
    const single = service.previewManagerInstallationEstimate.mock.calls[1][1].installations[0].typed_profile;
    expect(single.product_kind).toBe('complete_split_system');
    expect(single.indoor_unit_count).toBeUndefined();
    expect(single.composition_note).toBeUndefined();
  });

  it('keeps access provisional until an actual amount and scope are entered', async () => {
    service.previewManagerInstallationEstimate.mockResolvedValueOnce({
      status: 'provisional', reason_code: 'site_access_requires_approval', scope_ref: 'scope',
      total: '630.25', preview_ref: 'b'.repeat(64),
    });
    const wrapper = mountPanel();
    await prepare(wrapper);
    await wrapper.findAll('input[type="checkbox"]').find((input) => input.element.parentElement?.textContent?.includes('Леса на объекте'))?.setValue(true);
    await wrapper.get('[data-testid="installation-preview"]').trigger('click');
    await flushPromises();
    expect(wrapper.text()).toContain('Ориентировочная сумма');
    expect(wrapper.find('[data-testid="installation-add"]').exists()).toBe(false);
    await wrapper.get('[data-testid="scaffold-actual"]').setValue('125');
    await wrapper.get('[data-testid="scaffold-scope"]').setValue('Леса на фасаде первого этажа');
    await wrapper.get('[data-testid="installation-preview"]').trigger('click');
    await flushPromises();
    const input = service.previewManagerInstallationEstimate.mock.calls[1][1];
    expect(input.approved_site_access).toEqual([{ code: 'access.scaffold', actual_total: 125,
      scope_note: 'Леса на фасаде первого этажа' }]);
    expect(wrapper.find('[data-testid="installation-add"]').exists()).toBe(true);
  });

  it('does not offer installation for a product whose price includes it', async () => {
    service.getManagerOrderDetail.mockResolvedValueOnce({ id: 8, proposals: [{
      id: 12, status: 'draft', is_archived: false,
      product_lines: [{ ...product, is_installation_included: true }],
    }] });
    const wrapper = mountPanel();
    await wrapper.get('[data-testid="installation-open"]').trigger('click');
    await flushPromises();
    expect(wrapper.find('[data-testid="installation-product"]').exists()).toBe(false);
    expect(wrapper.text()).toContain('Нет оплачиваемого оборудования');
  });

  it('requires explicit service-only profile proof and starts new consent after a price change', async () => {
    const wrapper = mountPanel();
    await wrapper.get('[data-testid="installation-open"]').trigger('click');
    await flushPromises();
    await wrapper.findAll('button').find((button) => button.text() === 'Без товара')?.trigger('click');
    const selects = wrapper.findAll('select');
    await selects[0].setValue('complete_split_system');
    await selects[1].setValue('wall');
    const manualInputs = wrapper.findAll('input');
    await manualInputs.find((input) => input.attributes('type') === 'number')?.setValue('2.5');
    const pipes = manualInputs.filter((input) => input.attributes('class') === 'field-input' && !input.attributes('type'));
    await pipes[0].setValue('1/4"');
    await pipes[1].setValue('3/8"');
    await wrapper.get('[data-testid="installation-route"]').setValue('3');
    await wrapper.get('[data-testid="installation-holes"]').setValue('0');
    await wrapper.get('[data-testid="installation-thick-holes"]').setValue('0');
    await wrapper.get('[data-testid="installation-over80-holes"]').setValue('0');
    await wrapper.get('[data-testid="installation-preview"]').trigger('click');
    await flushPromises();
    expect(service.previewManagerInstallationEstimate).not.toHaveBeenCalled();
    expect(wrapper.text()).toContain('Подтвердите параметры оборудования');
    const verified = wrapper.findAll('input[type="checkbox"]').find((input) => input.element.parentElement?.textContent?.includes('Параметры оборудования проверены'));
    await verified?.setValue(true);
    await wrapper.get('[data-testid="installation-preview"]').trigger('click');
    await flushPromises();
    const payload = service.previewManagerInstallationEstimate.mock.calls[0][1];
    expect(payload.installations[0].typed_profile).toMatchObject({ product_kind: 'complete_split_system', indoor_type: 'wall', confirmed: true });
    expect(payload.installations[0].product_id).toBeUndefined();
    service.confirmManagerInstallationEstimate.mockRejectedValueOnce({ body: { detail: {
      code: 'price_changed', fresh_preview: { ...fixed, total: '540.25' },
    } } });
    await wrapper.get('[data-testid="installation-add"]').trigger('click');
    await flushPromises();
    expect(service.confirmManagerInstallationEstimate.mock.calls[0][1].verified_service_only_keys).toEqual([payload.installations[0].key]);
    expect(wrapper.text()).toContain('подтвердите его заново');
    expect(wrapper.find('[data-testid="installation-add"]').exists()).toBe(false);
    await wrapper.get('[data-testid="installation-preview"]').trigger('click');
    await flushPromises();
    expect(service.previewManagerInstallationEstimate.mock.calls[1][0]).not.toBe(service.previewManagerInstallationEstimate.mock.calls[0][0]);
  });

  it('ignores an attach response after switching proposals and retains the old retry key', async () => {
    const wrapper = mountPanel();
    await prepare(wrapper);
    await wrapper.get('[data-testid="installation-preview"]').trigger('click');
    await flushPromises();
    let finish!: (value: unknown) => void;
    service.attachManagerInstallationEstimate.mockImplementationOnce(() => new Promise((resolve) => { finish = resolve; }));
    await wrapper.get('[data-testid="installation-add"]').trigger('click');
    await flushPromises();
    const oldKey = service.attachManagerInstallationEstimate.mock.calls[0][3];
    await wrapper.setProps({ proposalId: 13 });
    await flushPromises();
    await wrapper.setProps({ proposalId: 12 });
    await flushPromises();
    await wrapper.get('[data-testid="installation-open"]').trigger('click');
    await flushPromises();
    finish({ lines: [{ title: 'Old proposal', price: '530.25' }], total: '530.25' });
    await flushPromises();
    expect(wrapper.props('afterAttach')).not.toHaveBeenCalled();
    expect(wrapper.text()).not.toContain('Смета прикреплена');
    expect(wrapper.get('[data-testid="installation-attach"]').text()).toContain('Повторить');
    await wrapper.get('[data-testid="installation-attach"]').trigger('click');
    await flushPromises();
    expect(service.attachManagerInstallationEstimate.mock.calls[1][3]).toBe(oldKey);
  });

  it('ignores an order load and preview completed for another proposal', async () => {
    let finishLoad!: (value: unknown) => void;
    service.getManagerOrderDetail.mockImplementationOnce(() => new Promise((resolve) => { finishLoad = resolve; }));
    const wrapper = mountPanel();
    await wrapper.get('[data-testid="installation-open"]').trigger('click');
    await flushPromises();
    await wrapper.setProps({ proposalId: 13 });
    finishLoad(order);
    await flushPromises();
    expect(wrapper.find('[data-testid="installation-product"]').exists()).toBe(false);
    await wrapper.setProps({ proposalId: 12 });
    await prepare(wrapper);
    let finishPreview!: (value: unknown) => void;
    service.previewManagerInstallationEstimate.mockImplementationOnce(() => new Promise((resolve) => { finishPreview = resolve; }));
    await wrapper.get('[data-testid="installation-preview"]').trigger('click');
    await flushPromises();
    await wrapper.setProps({ proposalId: 13 });
    finishPreview(fixed);
    await flushPromises();
    expect(wrapper.text()).not.toContain('530,25');
    expect(wrapper.find('[data-testid="installation-add"]').exists()).toBe(false);
  });

  it('ignores a confirmation completed after the account changes', async () => {
    managerSession.auth.value = { tenant_id: 1, staff_user_id: 9, username: 'first' } as any;
    const wrapper = mountPanel();
    await prepare(wrapper);
    await wrapper.get('[data-testid="installation-preview"]').trigger('click');
    await flushPromises();
    let finish!: (value: unknown) => void;
    service.confirmManagerInstallationEstimate.mockImplementationOnce(() => new Promise((resolve) => { finish = resolve; }));
    await wrapper.get('[data-testid="installation-add"]').trigger('click');
    await flushPromises();
    managerSession.auth.value = { tenant_id: 2, staff_user_id: 9, username: 'second' } as any;
    await flushPromises();
    finish({ estimate_id: 31, revision: 1, total: '530.25' });
    await flushPromises();
    expect(wrapper.find('[data-testid="installation-attach"]').exists()).toBe(false);
    expect(wrapper.text()).not.toContain('Цена подтверждена');
    wrapper.unmount();
    managerSession.auth.value = null;
  });

  it('keeps the same attach key after an uncertain response and allows a new calculation after a definite rejection', async () => {
    const wrapper = mountPanel();
    await prepare(wrapper);
    await wrapper.get('[data-testid="installation-preview"]').trigger('click');
    await flushPromises();
    service.attachManagerInstallationEstimate.mockRejectedValueOnce(new Error('Connection lost'));
    await wrapper.get('[data-testid="installation-add"]').trigger('click');
    await flushPromises();
    expect(wrapper.get('[data-testid="installation-start-new"]').attributes('disabled')).toBeDefined();
    const key = service.attachManagerInstallationEstimate.mock.calls[0][3];
    service.attachManagerInstallationEstimate.mockRejectedValueOnce({ body: { detail: { code: 'equipment_not_in_proposal' } } });
    await wrapper.get('[data-testid="installation-attach"]').trigger('click');
    await flushPromises();
    expect(service.attachManagerInstallationEstimate.mock.calls[1][3]).toBe(key);
    expect(wrapper.get('[data-testid="installation-start-new"]').attributes('disabled')).toBeUndefined();
    await wrapper.get('[data-testid="installation-start-new"]').trigger('click');
    expect(wrapper.find('[data-testid="installation-attach"]').exists()).toBe(false);
    expect(wrapper.get('[data-testid="installation-route"]').attributes('disabled')).toBeUndefined();
  });

  it('offers a new calculation when a restored confirmation no longer has eligible equipment', async () => {
    const wrapper = mountPanel();
    await prepare(wrapper);
    await wrapper.get('[data-testid="installation-preview"]').trigger('click');
    await flushPromises();
    service.attachManagerInstallationEstimate.mockRejectedValueOnce({ body: { detail: { code: 'equipment_not_in_proposal' } } });
    await wrapper.get('[data-testid="installation-add"]').trigger('click');
    await flushPromises();
    await wrapper.setProps({ proposalId: 13 });
    service.getManagerOrderDetail.mockResolvedValueOnce({ id: 8, proposals: [{
      id: 12, status: 'draft', is_archived: false,
      product_lines: [{ ...product, is_installation_included: true }],
    }] });
    await wrapper.setProps({ proposalId: 12 });
    await wrapper.get('[data-testid="installation-open"]').trigger('click');
    await flushPromises();
    expect(wrapper.find('[data-testid="installation-add"]').exists()).toBe(false);
    expect(wrapper.get('[data-testid="installation-start-new"]').exists()).toBe(true);
    await wrapper.get('[data-testid="installation-start-new"]').trigger('click');
    expect(wrapper.get('[data-testid="installation-preview"]').attributes('disabled')).toBeUndefined();
  });
});
