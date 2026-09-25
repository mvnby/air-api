import { mount, flushPromises } from '@vue/test-utils';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import OrderInstallationEstimatePanel from '../src/components/orders/OrderInstallationEstimatePanel.vue';
import { managerSession } from '../src/services/manager-session';

const service = vi.hoisted(() => ({
  getManagerOrderDetail: vi.fn(),
  previewManagerInstallationEstimate: vi.fn(),
  confirmManagerInstallationEstimate: vi.fn(),
  attachManagerInstallationEstimate: vi.fn(),
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
  service.previewManagerInstallationEstimate.mockResolvedValue(fixed);
  service.confirmManagerInstallationEstimate.mockResolvedValue({ estimate_id: 31, revision: 1, total: '530.25' });
  service.attachManagerInstallationEstimate.mockResolvedValue({ lines: [{ title: 'Установка №1: монтаж.', price: '530.25' }], total: '530.25' });
});

describe('OrderInstallationEstimatePanel', () => {
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
    expect(wrapper.get('[data-testid="installation-confirm"]').attributes('disabled')).toBeDefined();
    await wrapper.get('[data-testid="installation-consent"]').setValue(true);
    await wrapper.get('[data-testid="installation-confirm"]').trigger('click');
    await flushPromises();
    expect(service.confirmManagerInstallationEstimate).toHaveBeenCalledWith(expect.any(String), {
      preview_ref: 'a'.repeat(64), order_id: 8, proposal_id: 12, verified_service_only_keys: [],
    });
    await wrapper.get('[data-testid="installation-attach"]').trigger('click');
    await flushPromises();
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
    expect(wrapper.find('[data-testid="installation-confirm"]').exists()).toBe(false);
    service.previewManagerInstallationEstimate.mockResolvedValueOnce(fixed);
    await wrapper.get('[data-testid="installation-preview"]').trigger('click');
    await flushPromises();
    expect(wrapper.find('[data-testid="installation-confirm"]').exists()).toBe(true);
    await wrapper.get('[data-testid="installation-route"]').setValue('7');
    expect(wrapper.find('[data-testid="installation-confirm"]').exists()).toBe(false);
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
    expect(wrapper.find('[data-testid="installation-confirm"]').exists()).toBe(false);
    await wrapper.get('[data-testid="scaffold-actual"]').setValue('125');
    await wrapper.get('[data-testid="scaffold-scope"]').setValue('Леса на фасаде первого этажа');
    await wrapper.get('[data-testid="installation-preview"]').trigger('click');
    await flushPromises();
    const input = service.previewManagerInstallationEstimate.mock.calls[1][1];
    expect(input.approved_site_access).toEqual([{ code: 'access.scaffold', actual_total: 125,
      scope_note: 'Леса на фасаде первого этажа' }]);
    expect(wrapper.find('[data-testid="installation-confirm"]').exists()).toBe(true);
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
    await wrapper.get('[data-testid="installation-consent"]').setValue(true);
    await wrapper.get('[data-testid="installation-confirm"]').trigger('click');
    await flushPromises();
    expect(service.confirmManagerInstallationEstimate.mock.calls[0][1].verified_service_only_keys).toEqual([payload.installations[0].key]);
    expect(wrapper.text()).toContain('подтвердите его заново');
    expect(wrapper.find('[data-testid="installation-confirm"]').exists()).toBe(false);
    await wrapper.get('[data-testid="installation-preview"]').trigger('click');
    await flushPromises();
    expect(service.previewManagerInstallationEstimate.mock.calls[1][0]).not.toBe(service.previewManagerInstallationEstimate.mock.calls[0][0]);
  });

  it('ignores an attach response after switching proposals and retains the old retry key', async () => {
    const wrapper = mountPanel();
    await prepare(wrapper);
    await wrapper.get('[data-testid="installation-preview"]').trigger('click');
    await flushPromises();
    await wrapper.get('[data-testid="installation-consent"]').setValue(true);
    await wrapper.get('[data-testid="installation-confirm"]').trigger('click');
    await flushPromises();
    let finish!: (value: unknown) => void;
    service.attachManagerInstallationEstimate.mockImplementationOnce(() => new Promise((resolve) => { finish = resolve; }));
    await wrapper.get('[data-testid="installation-attach"]').trigger('click');
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
    expect(wrapper.find('[data-testid="installation-confirm"]').exists()).toBe(false);
  });

  it('ignores a confirmation completed after the account changes', async () => {
    managerSession.auth.value = { tenant_id: 1, staff_user_id: 9, username: 'first' } as any;
    const wrapper = mountPanel();
    await prepare(wrapper);
    await wrapper.get('[data-testid="installation-preview"]').trigger('click');
    await flushPromises();
    await wrapper.get('[data-testid="installation-consent"]').setValue(true);
    let finish!: (value: unknown) => void;
    service.confirmManagerInstallationEstimate.mockImplementationOnce(() => new Promise((resolve) => { finish = resolve; }));
    await wrapper.get('[data-testid="installation-confirm"]').trigger('click');
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
    await wrapper.get('[data-testid="installation-consent"]').setValue(true);
    await wrapper.get('[data-testid="installation-confirm"]').trigger('click');
    await flushPromises();
    service.attachManagerInstallationEstimate.mockRejectedValueOnce(new Error('Connection lost'));
    await wrapper.get('[data-testid="installation-attach"]').trigger('click');
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
    await wrapper.get('[data-testid="installation-consent"]').setValue(true);
    await wrapper.get('[data-testid="installation-confirm"]').trigger('click');
    await flushPromises();
    await wrapper.setProps({ proposalId: 13 });
    service.getManagerOrderDetail.mockResolvedValueOnce({ id: 8, proposals: [{
      id: 12, status: 'draft', is_archived: false,
      product_lines: [{ ...product, is_installation_included: true }],
    }] });
    await wrapper.setProps({ proposalId: 12 });
    await wrapper.get('[data-testid="installation-open"]').trigger('click');
    await flushPromises();
    expect(wrapper.find('[data-testid="installation-confirm"]').exists()).toBe(false);
    expect(wrapper.get('[data-testid="installation-start-new"]').exists()).toBe(true);
    await wrapper.get('[data-testid="installation-start-new"]').trigger('click');
    expect(wrapper.get('[data-testid="installation-preview"]').attributes('disabled')).toBeUndefined();
  });
});
