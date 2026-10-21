import { flushPromises, mount, type VueWrapper } from '@vue/test-utils';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import OrderWorkerAssignmentsPanel from '../src/components/orders/OrderWorkerAssignmentsPanel.vue';
import { orderWorkerAssignmentsApi as api } from '../src/services/order-worker-assignments';
import { clearManagerSession, managerSession } from '../src/services/manager-session';
vi.mock('../src/services/order-worker-assignments', () => ({ orderWorkerAssignmentsApi: { get: vi.fn(), candidates: vi.fn(), assign: vi.fn(), publish: vi.fn(), revoke: vi.fn(), collection: vi.fn() } }));
const assignment = { id: 11, staff_user_id: 3, display_name: 'Монтажник', work_stage_id: null, version: 4, title: 'Монтаж', instructions: '', source: 'manager', revoked_at: null, is_active: true, material_link_ids: [] };
const state = { order_id: 55, assignments: [assignment], materials: [{ link_id: 44, label: 'Техническая схема', file_kind: 'pdf' as const, work_stage_id: null }], collection: { version: 7, assignment_id: null, amount: null, currency: null, status: 'not_assigned' as const, updated_at: null }, balances: [{ currency: 'EUR' as const, remaining_amount: '500.00' }], financial_fingerprint: 'a'.repeat(64) };
let wrapper: VueWrapper | undefined;
const beforeAction = vi.fn();
const mountPanel = async () => { wrapper = mount(OrderWorkerAssignmentsPanel, { props: { orderId: 55, contextVersion: 'initial', workStages: [{ id: 2, name: 'Второй выезд' }], beforeAction } }); await flushPromises(); return wrapper; };
beforeEach(() => { vi.resetAllMocks(); managerSession.auth.value = { username: 'manager', status: 'authenticated', staff_user_id: 2, tenant_id: 2, storefront_id: 5, capabilities: ['crm.manage'] }; beforeAction.mockResolvedValue(true); vi.mocked(api.get).mockResolvedValue(structuredClone(state)); vi.mocked(api.candidates).mockResolvedValue({ items: [{ staff_user_id: 3, display_name: 'Монтажник' }], total: 1, page: 1, limit: 100 }); for (const method of [api.assign, api.publish, api.revoke, api.collection]) vi.mocked(method).mockResolvedValue(structuredClone(state)); });
afterEach(() => { wrapper?.unmount(); wrapper = undefined; clearManagerSession(); });
describe('manager installer workspace', () => {
  it('assigns a real selected staff person to the selected visit after pending edits flush', async () => {
    const view = await mountPanel(); await view.get('[aria-label="Исполнитель работы"]').setValue('3'); await view.get('[aria-label="Выезд или весь заказ"]').setValue('2'); await view.findAll('form')[0]!.trigger('submit'); await flushPromises(); expect(beforeAction).toHaveBeenCalledTimes(1); expect(api.assign).toHaveBeenCalledWith(55, 3, 2);
  });
  it('requires an explicit amount, accepts zero and sends currency/version/fingerprint unchanged', async () => {
    const view = await mountPanel(); await view.get('[aria-label="Получатель оплаты"]').setValue('11'); expect(view.get('[aria-label="Сумма к получению"]').element).toHaveProperty('value', '');
    await view.get('[aria-label="Сумма к получению"]').setValue('0,00'); await view.get('[aria-label="Валюта к получению"]').setValue('EUR'); await view.findAll('form').at(-1)!.trigger('submit'); await flushPromises();
    expect(api.collection).toHaveBeenCalledWith(55, { expected_version: 7, assignment_id: 11, amount: '0.00', currency: 'EUR', financial_fingerprint: 'a'.repeat(64) });
  });
  it('rejects a negative amount and clears a collection instruction explicitly with nulls', async () => {
    const view = await mountPanel(); await view.get('[aria-label="Получатель оплаты"]').setValue('11'); await view.get('[aria-label="Сумма к получению"]').setValue('-0.01'); await view.findAll('form').at(-1)!.trigger('submit'); await flushPromises(); expect(api.collection).not.toHaveBeenCalled(); expect(view.get('[role="alert"]').text()).toContain('неотрицательную');
    await view.get('[aria-label="Получатель оплаты"]').setValue(''); await view.findAll('form').at(-1)!.trigger('submit'); await flushPromises(); expect(api.collection).toHaveBeenCalledWith(55, { expected_version: 7, assignment_id: null, amount: null, currency: null, financial_fingerprint: 'a'.repeat(64) });
  });
  it('revokes only the chosen active assignment with its reviewed version', async () => {
    const view = await mountPanel(); await view.findAll('button').find(button => button.text() === 'Отозвать')!.trigger('click'); await flushPromises(); expect(api.revoke).toHaveBeenCalledWith(55, 11, 4);
  });
  it('captures the reviewed fingerprint before flush and refreshes a409 without replay', async () => {
    const view = await mountPanel(); await view.get('[aria-label="Получатель оплаты"]').setValue('11'); await view.get('[aria-label="Сумма к получению"]').setValue('15.50');
    vi.mocked(api.collection).mockRejectedValue({ status: 409 }); vi.mocked(api.get).mockResolvedValue({ ...state, financial_fingerprint: 'b'.repeat(64), collection: { ...state.collection, version: 8 } });
    await view.findAll('form').at(-1)!.trigger('submit'); await flushPromises(); expect(api.collection).toHaveBeenCalledTimes(1); expect(vi.mocked(api.collection).mock.calls[0]?.[1].expected_version).toBe(7); expect(view.get('[role="alert"]').text()).toContain('изменились'); expect(view.get('[aria-label="Получатель оплаты"]').element).toHaveProperty('value', '11'); expect(view.get('[aria-label="Сумма к получению"]').element).toHaveProperty('value', '15.50');
  });
  it('sends selected technical materials and safe instructions as a dedicated versioned publication', async () => {
    const view = await mountPanel(); await view.findAll('button').find(button => button.text() === 'Указания и материалы')!.trigger('click'); await view.get('[aria-label="Название работы"]').setValue('Безопасный заголовок'); await view.get('[aria-label="Указания исполнителю"]').setValue('Только техническая инструкция'); await view.get('input[type="checkbox"]').setValue(true); await view.findAll('form')[0]!.trigger('submit'); await flushPromises();
    expect(api.publish).toHaveBeenCalledWith(55, 11, { expected_version: 4, title: 'Безопасный заголовок', instructions: 'Только техническая инструкция', material_link_ids: [44] });
  });
  it('offers visit materials to an order-wide assignee while keeping visit-specific choices scoped', async () => {
    const materials = [{ link_id: 45, label: 'Фото второго выезда', file_kind: 'image' as const, work_stage_id: 2 }];
    vi.mocked(api.get).mockResolvedValue({ ...state, materials });
    const view = await mountPanel(); await view.findAll('button').find(button => button.text() === 'Указания и материалы')!.trigger('click');
    await view.get('input[type="checkbox"]').setValue(true); await view.findAll('form')[0]!.trigger('submit'); await flushPromises();
    expect(api.publish).toHaveBeenCalledWith(55, 11, expect.objectContaining({ material_link_ids: [45] }));
  });
  it('keeps demo controls disabled and aborts mutations when pending order edits fail', async () => {
    managerSession.auth.value = { ...managerSession.auth.value!, demo_read_only: true }; const view = await mountPanel(); expect(view.get('[aria-label="Исполнитель работы"]').attributes('disabled')).toBeDefined(); expect(api.assign).not.toHaveBeenCalled();
    managerSession.auth.value = { ...managerSession.auth.value!, demo_read_only: false }; await flushPromises(); beforeAction.mockResolvedValue(false); await view.get('[aria-label="Исполнитель работы"]').setValue('3'); await view.findAll('form')[0]!.trigger('submit'); await flushPromises(); expect(api.assign).not.toHaveBeenCalled();
  });
  it('refreshes changed context while preserving assignment editing and collection drafts', async () => {
    const view = await mountPanel();
    expect(api.get).toHaveBeenCalledOnce();
    await view.get('[aria-label="Исполнитель работы"]').setValue('3');
    await view.get('[aria-label="Выезд или весь заказ"]').setValue('2');
    await view.get('[aria-label="Получатель оплаты"]').setValue('11');
    await view.get('[aria-label="Сумма к получению"]').setValue('17,50');
    await view.get('[aria-label="Валюта к получению"]').setValue('USD');
    await view.findAll('button').find(button => button.text() === 'Указания и материалы')!.trigger('click');
    await view.get('[aria-label="Название работы"]').setValue('Локальное название');
    await view.get('[aria-label="Указания исполнителю"]').setValue('Локальные указания');
    await view.get('input[type="checkbox"]').setValue(true);
    vi.mocked(api.get).mockResolvedValue({ ...state, assignments: [{ ...assignment, title: 'Обновлённая работа' }], collection: { ...state.collection, status: 'requires_review' }, balances: [{ currency: 'EUR', remaining_amount: '700.00' }] });
    vi.mocked(api.candidates).mockResolvedValue({ items: [{ staff_user_id: 3, display_name: 'Монтажник' }, { staff_user_id: 4, display_name: 'Новый исполнитель' }], total: 2, page: 1, limit: 100 });
    await view.setProps({ contextVersion: 'changed-lines-and-payment' }); await flushPromises();
    expect(api.get).toHaveBeenCalledTimes(2);
    expect(view.text()).toContain('Обновлённая работа');
    expect(view.text()).toContain('700.00 EUR');
    expect(view.text()).toContain('Проверьте сумму');
    for (const [label, value] of [['Исполнитель работы', '3'], ['Выезд или весь заказ', '2'], ['Получатель оплаты', '11'], ['Сумма к получению', '17,50'], ['Валюта к получению', 'USD'], ['Название работы', 'Локальное название'], ['Указания исполнителю', 'Локальные указания']]) {
      expect(view.get(`[aria-label="${label}"]`).element).toHaveProperty('value', value);
    }
    expect(view.get('input[type="checkbox"]').element).toHaveProperty('checked', true);
    expect(view.get('[aria-label="Исполнитель работы"]').text()).toContain('Новый исполнитель');
    expect(api.assign).not.toHaveBeenCalled();
  });

  it('defers a context refresh through the order-save barrier and pending assignment write', async () => {
    let finishBarrier!: (value: boolean) => void, finishWrite!: (value: typeof state) => void;
    beforeAction.mockImplementationOnce(() => new Promise(resolve => { finishBarrier = resolve; }));
    vi.mocked(api.assign).mockReturnValueOnce(new Promise(resolve => { finishWrite = resolve; }));
    const view = await mountPanel();
    await view.get('[aria-label="Исполнитель работы"]').setValue('3');
    await view.findAll('form')[0]!.trigger('submit');
    await view.setProps({ contextVersion: 'saved-order' }); await flushPromises();
    expect(api.get).toHaveBeenCalledOnce();
    finishBarrier(true); await flushPromises();
    expect(api.assign).toHaveBeenCalledWith(55, 3, null);
    await view.setProps({ contextVersion: 'newer-order' }); await flushPromises();
    expect(api.get).toHaveBeenCalledOnce();
    finishWrite(structuredClone(state)); await flushPromises();
    expect(api.get).toHaveBeenCalledTimes(2);
    expect(beforeAction).toHaveBeenCalledOnce();
  });

  it('discards a context refresh response after the order scope changes', async () => {
    let finishRefresh!: (value: typeof state) => void;
    const view = await mountPanel();
    vi.mocked(api.get).mockReturnValueOnce(new Promise(resolve => { finishRefresh = resolve; }));
    await view.setProps({ contextVersion: 'changed' });
    vi.mocked(api.get).mockResolvedValueOnce({ ...state, order_id: 66, assignments: [{ ...assignment, title: 'Новая область заказа' }] });
    await view.setProps({ orderId: 66, contextVersion: 'new-scope-context' }); await flushPromises();
    expect(api.get).toHaveBeenCalledTimes(3);
    finishRefresh({ ...state, assignments: [{ ...assignment, title: 'Устаревший ответ' }] }); await flushPromises();
    expect(view.text()).toContain('Новая область заказа');
    expect(view.text()).not.toContain('Устаревший ответ');
    expect(api.assign).not.toHaveBeenCalled();
  });

  it('publishes retained instructions with the reviewed version and keeps them visible after a conflict', async () => {
    const view = await mountPanel();
    await view.findAll('button').find(button => button.text() === 'Указания и материалы')!.trigger('click');
    await view.get('[aria-label="Название работы"]').setValue('Моё название');
    await view.get('[aria-label="Указания исполнителю"]').setValue('Мои несохранённые указания');
    await view.get('input[type="checkbox"]').setValue(true);
    vi.mocked(api.get).mockResolvedValue({ ...state, assignments: [{ ...assignment, version: 5, instructions: 'Изменено другим менеджером' }] });
    await view.setProps({ contextVersion: 'external-instructions' }); await flushPromises();
    vi.mocked(api.publish).mockRejectedValueOnce({ status: 409 });
    await view.findAll('form')[0]!.trigger('submit'); await flushPromises();
    expect(api.publish).toHaveBeenCalledTimes(1);
    expect(api.publish).toHaveBeenLastCalledWith(55, 11, { expected_version: 4, title: 'Моё название', instructions: 'Мои несохранённые указания', material_link_ids: [44] });
    expect(view.get('[role="alert"]').text()).toContain('изменились');
    expect(view.get('[aria-label="Название работы"]').element).toHaveProperty('value', 'Моё название');
    expect(view.get('[aria-label="Указания исполнителю"]').element).toHaveProperty('value', 'Мои несохранённые указания');
    expect(view.get('input[type="checkbox"]').element).toHaveProperty('checked', true);
    await view.findAll('form')[0]!.trigger('submit'); await flushPromises();
    expect(api.publish).toHaveBeenCalledTimes(2);
    expect(api.publish).toHaveBeenLastCalledWith(55, 11, expect.objectContaining({ expected_version: 5, instructions: 'Мои несохранённые указания' }));
  });

  it('retains the collection draft version and fingerprint across refreshes until explicit conflict review', async () => {
    const view = await mountPanel();
    await view.get('[aria-label="Получатель оплаты"]').setValue('11');
    await view.get('[aria-label="Сумма к получению"]').setValue('15.50');
    await view.get('[aria-label="Валюта к получению"]').setValue('EUR');
    vi.mocked(api.get).mockResolvedValue({ ...state, financial_fingerprint: 'b'.repeat(64), collection: { ...state.collection, version: 8, assignment_id: 11, amount: '99.00', currency: 'USD' } });
    await view.setProps({ contextVersion: 'external-payment' }); await flushPromises();
    vi.mocked(api.get).mockResolvedValue({ ...state, financial_fingerprint: 'c'.repeat(64), collection: { ...state.collection, version: 9, assignment_id: 11, amount: '125.00', currency: 'USD' } });
    await view.setProps({ contextVersion: 'another-payment' }); await flushPromises();
    vi.mocked(api.collection).mockRejectedValueOnce({ status: 409 });
    await view.findAll('form').at(-1)!.trigger('submit'); await flushPromises();
    expect(api.collection).toHaveBeenCalledTimes(1);
    expect(api.collection).toHaveBeenLastCalledWith(55, { expected_version: 7, financial_fingerprint: 'a'.repeat(64), assignment_id: 11, amount: '15.50', currency: 'EUR' });
    expect(view.get('[role="alert"]').text()).toContain('изменились');
    expect(view.get('[aria-label="Получатель оплаты"]').element).toHaveProperty('value', '11');
    expect(view.get('[aria-label="Сумма к получению"]').element).toHaveProperty('value', '15.50');
    expect(view.get('[aria-label="Валюта к получению"]').element).toHaveProperty('value', 'EUR');
    await view.findAll('form').at(-1)!.trigger('submit'); await flushPromises();
    expect(api.collection).toHaveBeenCalledTimes(2);
    expect(api.collection).toHaveBeenLastCalledWith(55, { expected_version: 9, financial_fingerprint: 'c'.repeat(64), assignment_id: 11, amount: '15.50', currency: 'EUR' });
  });

  it('updates pristine collection fields and their reviewed version on a context refresh', async () => {
    const view = await mountPanel();
    vi.mocked(api.get).mockResolvedValue({ ...state, financial_fingerprint: 'b'.repeat(64), collection: { ...state.collection, version: 8, assignment_id: 11, amount: '33.00', currency: 'EUR' } });
    await view.setProps({ contextVersion: 'external-collection' }); await flushPromises();
    expect(view.get('[aria-label="Получатель оплаты"]').element).toHaveProperty('value', '11');
    expect(view.get('[aria-label="Сумма к получению"]').element).toHaveProperty('value', '33.00');
    expect(view.get('[aria-label="Валюта к получению"]').element).toHaveProperty('value', 'EUR');
    expect(api.collection).not.toHaveBeenCalled();
    await view.findAll('form').at(-1)!.trigger('submit'); await flushPromises();
    expect(api.collection).toHaveBeenCalledWith(55, { expected_version: 8, financial_fingerprint: 'b'.repeat(64), assignment_id: 11, amount: '33.00', currency: 'EUR' });
  });

});
