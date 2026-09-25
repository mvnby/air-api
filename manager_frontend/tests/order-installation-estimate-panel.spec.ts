import { mount, flushPromises } from '@vue/test-utils';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import OrderInstallationEstimatePanel from '../src/components/orders/OrderInstallationEstimatePanel.vue';

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
    beforeAction: vi.fn().mockResolvedValue(true), afterAttach: vi.fn().mockResolvedValue(undefined) },
});

const prepare = async (wrapper: ReturnType<typeof mountPanel>) => {
  await wrapper.get('[data-testid="installation-open"]').trigger('click');
  await flushPromises();
  await wrapper.get('[data-testid="installation-product"]').setValue(true);
  await wrapper.get('[data-testid="installation-route"]').setValue('6');
  await wrapper.get('[data-testid="installation-holes"]').setValue('1');
};

beforeEach(() => {
  sessionStorage.clear();
  vi.clearAllMocks();
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
      holes_by_type: { diamond: 1 } }]);
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
});
