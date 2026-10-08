import { flushPromises, mount } from '@vue/test-utils';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import OrderSourceEquipmentAction from '../src/components/orders/OrderSourceEquipmentAction.vue';
import OrderRequestSourceCard from '../src/components/orders/OrderRequestSourceCard.vue';

const api = vi.hoisted(() => ({ card: vi.fn(), equipment: vi.fn(), addEquipment: vi.fn(), originalAccess: vi.fn() }));
vi.mock('../src/services/order-source-review', async (importOriginal) => ({
  ...await importOriginal<typeof import('../src/services/order-source-review')>(), orderSourceReviewApi: api,
}));
const deferred = <T,>() => { let resolve!: (value: T) => void; const promise = new Promise<T>((done) => { resolve = done; }); return { promise, resolve }; };
const preview = {
  order_id: 461, proposal_id: 465, proposal_status: 'draft', preview_fingerprint: 'a'.repeat(64), warnings: [],
  items: [
    { brand: 'MDV', model: 'AB12/CD12', quantity: 9, product_id: 108, price: 2990, available_quantity: 20, existing_quantity: 0, reason: 'ready', message: 'Точное совпадение', can_add: true, can_restore: false },
    { brand: 'MDV', model: 'AB09/CD09', quantity: 5, product_id: 107, price: 2690, available_quantity: 20, existing_quantity: 5, reason: 'existing_line', message: 'Уже в предложении: 5; количество и цена сохранены.', can_add: false, can_restore: false },
  ],
};
const report = { added: [{ product_id: 108, quantity: 9, message: 'Добавлено' }], skipped: [], warnings: [] };

describe('Order source actions', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.equipment.mockResolvedValue(preview); api.addEquipment.mockResolvedValue(report);
    api.card.mockResolvedValue({ order_id: 461, source: 'goszakupki_by', external_id: 'T1', title: 'Поставка',
      objects: [{ address: '', equipment: preview.items.map(({ brand, model, quantity }) => ({ brand, model, quantity })) }],
      originals: [{ attachment_id: 126, name: 'Техническое задание.pdf', mime_type: 'application/pdf' }],
      installation_facts: [{ text: 'Длина коммуникаций: 5 м, 8 м, 10 м', source: 'reviewed_equipment_details', needs_review: true }],
      submission: { method: 'email', email: 'offers@example.test', source: 'Техническое задание', evidence: 'Предложения направить на offers@example.test' },
      work_summary: 'Условия и сроки поставки сохранены полностью',
    });
    api.originalAccess.mockResolvedValue({ url: 'https://signed.test/original' });
  });

  it('previews current exact rows and adds only ready models after flush and awaited reload', async () => {
    const before = deferred<boolean>(); const after = deferred<boolean>();
    const beforeAction = vi.fn(() => before.promise); const afterAction = vi.fn(() => after.promise); const endAction = vi.fn();
    const wrapper = mount(OrderSourceEquipmentAction, { props: { orderId: 461, proposalId: 465, beforeAction, afterAction, endAction } });
    await wrapper.get('button').trigger('click'); await flushPromises();
    expect(wrapper.text()).toContain('Уже в предложении: 5');
    expect(wrapper.text()).toContain('20 шт. доступно');
    await wrapper.get('button.btn-mini').trigger('click'); await flushPromises();
    expect(api.addEquipment).not.toHaveBeenCalled(); before.resolve(true); await flushPromises();
    expect(api.addEquipment).toHaveBeenCalledWith(461, expect.objectContaining({ proposal_id: 465, product_ids: [108], restore_removed_product_ids: [] }));
    expect(wrapper.emitted('applied')).toBeUndefined(); expect(endAction).not.toHaveBeenCalled();
    after.resolve(true); await flushPromises();
    expect(wrapper.emitted('applied')?.[0]).toEqual([461]); expect(endAction).toHaveBeenCalledTimes(1);
  });

  it('does not release another action when flush rejects the command', async () => {
    const endAction = vi.fn();
    const wrapper = mount(OrderSourceEquipmentAction, { props: { orderId: 461, proposalId: 465, beforeAction: vi.fn().mockResolvedValue(false), endAction } });
    await wrapper.get('button').trigger('click'); await flushPromises();
    await wrapper.get('button.btn-mini').trigger('click'); await flushPromises();
    expect(api.addEquipment).not.toHaveBeenCalled(); expect(endAction).not.toHaveBeenCalled();
  });

  it('requires a separate deliberate checkbox to restore removed equipment', async () => {
    api.equipment.mockResolvedValue({ ...preview, items: [{ ...preview.items[0], can_add: false, can_restore: true, reason: 'previously_removed', message: 'Ранее удалено' }] });
    const wrapper = mount(OrderSourceEquipmentAction, { props: { orderId: 461, proposalId: 465 } });
    await wrapper.get('button').trigger('click'); await flushPromises();
    expect(wrapper.get('button.btn-mini').attributes('disabled')).toBeDefined();
    await wrapper.get('input[type="checkbox"]').setValue(true);
    await wrapper.get('button.btn-mini').trigger('click'); await flushPromises();
    expect(api.addEquipment).toHaveBeenCalledWith(461, expect.objectContaining({ product_ids: [108], restore_removed_product_ids: [108] }));
  });

  it('drops stale scope results and releases its command hook', async () => {
    const pending = deferred<typeof report>(); api.addEquipment.mockReturnValue(pending.promise);
    const afterAction = vi.fn(); const endAction = vi.fn();
    const wrapper = mount(OrderSourceEquipmentAction, { props: { orderId: 461, proposalId: 465, afterAction, endAction } });
    await wrapper.get('button').trigger('click'); await flushPromises();
    await wrapper.get('button.btn-mini').trigger('click'); await flushPromises();
    await wrapper.setProps({ orderId: 462, proposalId: 466 }); pending.resolve(report); await flushPromises();
    expect(wrapper.emitted('applied')).toBeUndefined(); expect(afterAction).not.toHaveBeenCalled(); expect(endAction).toHaveBeenCalledTimes(1);
  });

  it('reuses the command intent when the server applied rows but refreshing the order failed', async () => {
    const afterAction = vi.fn().mockRejectedValueOnce(new Error('read timeout')).mockResolvedValueOnce(true);
    const wrapper = mount(OrderSourceEquipmentAction, { props: { orderId: 461, proposalId: 465, afterAction } });
    await wrapper.get('button').trigger('click'); await flushPromises();
    await wrapper.get('button.btn-mini').trigger('click'); await flushPromises();
    expect(wrapper.text()).toContain('Товары добавлены, но карточку не удалось обновить');
    const first = api.addEquipment.mock.calls[0]![1];
    await wrapper.get('button.btn-mini').trigger('click'); await flushPromises();
    expect(api.addEquipment.mock.calls[1]![1].command_id).toBe(first.command_id);
    expect(wrapper.emitted('applied')).toHaveLength(1);
  });

  it('keeps source details collapsed and opens files through authenticated attachment access', async () => {
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined);
    const wrapper = mount(OrderRequestSourceCard, { props: { orderId: 461 } }); await flushPromises();
    expect(wrapper.text()).toContain('14 шт.'); expect(wrapper.text()).not.toContain('Техническое задание.pdf');
    expect(wrapper.text()).toContain('Подача по email · offers@example.test');
    expect(wrapper.text()).toContain('Предложения направить на offers@example.test');
    await wrapper.get('button[aria-expanded]').trigger('click');
    expect(wrapper.findAll('th').map((th) => th.text())).toEqual(['Модель', 'Шт.']);
    expect(wrapper.text()).toContain('Длина коммуникаций: 5 м, 8 м, 10 м');
    expect(wrapper.find('details').attributes('open')).toBeUndefined();
    await wrapper.findAll('button').find((button) => button.text() === 'Техническое задание.pdf')!.trigger('click'); await flushPromises();
    expect(api.originalAccess).toHaveBeenCalledWith(126); expect(click).toHaveBeenCalledTimes(1);
    await wrapper.findAll('button').find((button) => button.text() === 'Проработать')!.trigger('click');
    expect(wrapper.emitted('review')).toHaveLength(1); click.mockRestore();
  });
});


describe('source equipment price display', () => {
  it.each([null, undefined, NaN, Infinity, "125", 0, -12.345, 12.345, 123456789.12])('preserves ru-RU source precision for %s', async (price) => {
    api.equipment.mockResolvedValue({ ...preview, items: [{ ...preview.items[0], price }] });
    const wrapper = mount(OrderSourceEquipmentAction, { props: { orderId: 461, proposalId: 465 } });
    await wrapper.get('button').trigger('click'); await flushPromises();
    const money = wrapper.findComponent({ name: 'MoneyAmount' });
    const valid = typeof price === 'number' && Number.isFinite(price);
    expect(money.text()).toBe(valid ? `${price.toLocaleString('ru-RU')} BYN` : '—');
    expect(money.find('svg').exists()).toBe(valid);
    expect(wrapper.get('input[type="checkbox"]').element.checked).toBe(true);
    wrapper.unmount();
  });
});
