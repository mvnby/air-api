import { flushPromises, mount, type VueWrapper } from '@vue/test-utils';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { ManagerOrderDetailResponse } from '../src/client';
import OrderCustomerContext from '../src/components/orders/OrderCustomerContext.vue';
const suggestAddress = vi.hoisted(() => vi.fn());
const confirmClose = vi.hoisted(() => vi.fn());
vi.mock('../src/services/ui-feedback', () => ({ confirmDialog: confirmClose }));
const api = vi.hoisted(() => ({ createManagerCustomerBranch: vi.fn(), getManagerCustomerBranches: vi.fn(), getManagerCustomers: vi.fn(), patchManagerCustomer: vi.fn(), patchManagerOrder: vi.fn() }));
vi.mock('../src/api', () => ({ api }));
vi.mock('../src/client', async original => ({ ...(await original<typeof import('../src/client')>()), ManagerSettingsService: { suggestAddress } }));
const order = { id: 42, customer: { id: 11, type: 'individual', name: 'Анна', phone: '+375291112233', email: 'anna@example.test' }, customer_branch: null, product_lines: [], service_lines: [] } as unknown as ManagerOrderDetailResponse;
const branches = [{ id: 31, name: 'Склад', delivery_address: 'Минск, Складская, 1' }, { id: 32, name: 'Офис', delivery_address: 'Минск, Офисная, 2' }];
const wrappers: VueWrapper[] = [];
const make = (extra: Record<string, unknown> = {}) => {
  const w = mount(OrderCustomerContext, { props: { order, deliveryAddress: '', customerBranchId: null, comment: '', editTarget: null,
    'onUpdate:editTarget': value => w.setProps({ editTarget: value }), 'onUpdate:deliveryAddress': value => w.setProps({ deliveryAddress: value }),
    'onUpdate:customerBranchId': value => w.setProps({ customerBranchId: value }), 'onUpdate:comment': value => w.setProps({ comment: value }), ...extra },
    global: { stubs: { AddressSuggestInput: { name: 'AddressSuggestInput', props: ['modelValue'], emits: ['update:modelValue'], template: '<input data-testid="address-input" :value="modelValue" @input="$emit(\'update:modelValue\', $event.target.value)" />' } } } });
  wrappers.push(w); return w;
};
const open = async (w: VueWrapper, target: string) => { await w.get('[data-order-usage="context-' + target + '"]').trigger('click'); await flushPromises(); };
const address = (w: VueWrapper) => w.get('[data-testid="object-address"]');
const deferred = <T,>() => { let resolve!: (v: T) => void; const promise = new Promise<T>(r => resolve = r); return { promise, resolve }; };
beforeEach(() => {
  api.getManagerCustomerBranches.mockResolvedValue({ items: branches });
  api.getManagerCustomers.mockResolvedValue({ items: [{ id: 22, name: 'Новый клиент', phone: '+375291234567', inn: '123456789' }] });
  api.patchManagerCustomer.mockResolvedValue({}); api.patchManagerOrder.mockResolvedValue({ ...order, customer: { id: 22, name: 'Новый клиент' } });
  suggestAddress.mockResolvedValue({ items: [] }); confirmClose.mockResolvedValue(false);
});
afterEach(() => { wrappers.splice(0).forEach(w => w.unmount()); vi.useRealTimers(); vi.clearAllMocks(); });
describe('inline customer and object context', () => {
  it('expands inside the selected summary and directly toggles closed', async () => {
    const w = make(); await open(w, 'customer');
    expect(w.get('#order-context-customer-editor').isVisible()).toBe(true);
    expect(w.get('#order-context-customer-editor').get('[data-testid="change-customer"]').exists()).toBe(true);
    expect(w.find('[role="dialog"]').exists()).toBe(false);
    await open(w, 'customer'); expect(w.props('editTarget')).toBe(null); expect(w.get('#order-context-customer-editor').attributes('style')).toContain('display: none');
    await open(w, 'object'); expect(w.get('#order-context-object-editor').isVisible()).toBe(true);
    expect(w.get('#order-context-customer-editor').attributes('style')).toContain('display: none');
  });
  it('keeps a saved branch when lookup has no options', async () => {
    api.getManagerCustomerBranches.mockResolvedValue({ items: [] });
    const w = make({ order: { ...order, customer_branch: branches[0] }, customerBranchId: 31, deliveryAddress: branches[0].delivery_address }); await open(w, 'object');
    expect(w.emitted('update:customerBranchId')).toBeUndefined();
    expect((w.get('[data-testid="customer-branch"]').element as HTMLSelectElement).value).toBe('31');
  });
  it('stages branch address and comment and saves them explicitly', async () => {
    const w = make(); await open(w, 'object'); await w.get('[data-testid="customer-branch"]').setValue('32');
    await w.get('[data-testid="object-comment"]').setValue('Вход со двора');
    expect(w.emitted('update:deliveryAddress')).toBeUndefined(); expect(api.patchManagerOrder).not.toHaveBeenCalled();
    await w.get('[data-testid="save-object"]').trigger('click'); await flushPromises();
    expect(api.patchManagerOrder).toHaveBeenCalledWith(42, { customer_delivery_address: 'Минск, Офисная, 2', customer_branch_id: 32, comment: 'Вход со двора' });
    expect(w.props('deliveryAddress')).toBe('Минск, Офисная, 2'); expect(w.props('editTarget')).toBe(null);
  });
  it('creates a branch explicitly and stages its link until the object is saved', async () => {
    api.createManagerCustomerBranch.mockResolvedValue({ id: 44, name: 'Новый корпус', delivery_address: 'Минск, Новая, 4' });
    const w = make(); await open(w, 'object');
    await w.findAll('button').find(b => b.text() === 'Новый филиал')!.trigger('click');
    await w.findAll('label').find(l => l.text() === 'Название филиала')!.get('input').setValue('Новый корпус');
    await w.get('input[label="Адрес филиала"]').setValue('Минск, Новая, 4');
    await w.findAll('button').find(b => b.text() === 'Создать и выбрать')!.trigger('click'); await flushPromises();
    expect(api.createManagerCustomerBranch).toHaveBeenCalledWith(11, { name: 'Новый корпус', delivery_address: 'Минск, Новая, 4', is_default: false });
    expect(w.emitted('update:customerBranchId')).toBeUndefined();
    expect((address(w).element as HTMLInputElement).value).toBe('Минск, Новая, 4');
    await w.get('[data-testid="save-object"]').trigger('click'); await flushPromises();
    expect(api.patchManagerOrder).toHaveBeenCalledWith(42, expect.objectContaining({ customer_branch_id: 44, customer_delivery_address: 'Минск, Новая, 4' }));
  });
  it('keeps draft through collapse and unrelated refresh and cancels explicitly', async () => {
    const w = make({ deliveryAddress: 'Старый адрес' }); await open(w, 'object'); await address(w).setValue('Новый адрес');
    await open(w, 'object'); await w.setProps({ order: { ...order, total_amount: 99 } }); await open(w, 'object');
    expect((address(w).element as HTMLInputElement).value).toBe('Новый адрес');
    await w.get('[data-testid="inline-object-editor"]').findAll('button').find(b => b.text() === 'Отмена')!.trigger('click'); await open(w, 'object');
    expect((address(w).element as HTMLInputElement).value).toBe('Старый адрес');
  });
  it('refreshes saved branch choices and untouched fields without overwriting the edited address', async () => {
    const w = make(); await open(w, 'object'); await address(w).setValue('Адрес менеджера');
    await w.setProps({ order: { ...order, customer_branch: branches[0] }, customerBranchId: 31, comment: 'Комментарий из источника' });
    await flushPromises();
    expect(api.getManagerCustomerBranches).toHaveBeenCalledTimes(2);
    expect((address(w).element as HTMLInputElement).value).toBe('Адрес менеджера');
    expect((w.get('[data-testid="customer-branch"]').element as HTMLSelectElement).value).toBe('31');
    expect((w.get('[data-testid="object-comment"]').element as HTMLTextAreaElement).value).toBe('Комментарий из источника');
  });
  it('keeps failed object edits open and intact', async () => {
    const persistObject = vi.fn().mockResolvedValue(false); const w = make({ persistObject, saveError: 'Нет связи' });
    await open(w, 'object'); await address(w).setValue('Новый адрес'); await w.get('[data-testid="save-object"]').trigger('click'); await flushPromises();
    expect(w.props('editTarget')).toBe('object'); expect(w.get('[role="alert"]').text()).toBe('Нет связи');
    expect((address(w).element as HTMLInputElement).value).toBe('Новый адрес');
  });
  it('keeps an object draft when the shared queue rolls its failed model update back', async () => {
    const w = make({ deliveryAddress: 'Старый адрес' });
    await w.setProps({ persistObject: async draft => {
      await w.setProps({ deliveryAddress: draft.address });
      await w.setProps({ deliveryAddress: 'Старый адрес' });
      return false;
    } });
    await open(w, 'object'); await address(w).setValue('Новый адрес');
    await w.get('[data-testid="save-object"]').trigger('click'); await flushPromises();
    expect((address(w).element as HTMLInputElement).value).toBe('Новый адрес');
    expect(w.props('deliveryAddress')).toBe('Старый адрес');
  });
  it('protects unsaved context drafts when closing the entire order', async () => {
    const w = make(); await open(w, 'object'); await address(w).setValue('Новый адрес');
    expect(await w.vm.beforeClose()).toBe(false); expect(confirmClose).toHaveBeenCalledOnce();
    confirmClose.mockResolvedValueOnce(true); expect(await w.vm.beforeClose()).toBe(true);
    expect((address(w).element as HTMLInputElement).value).toBe('Новый адрес');
  });
  it('keeps the physical object draft when correcting the customer and clears its old branch', async () => {
    const w = make({ customerBranchId: 31 }); await open(w, 'object'); await address(w).setValue('Адрес фактического объекта');
    await w.setProps({ order: { ...order, customer: { ...order.customer!, id: 22 }, customer_branch: null }, customerBranchId: null });
    await flushPromises(); expect((address(w).element as HTMLInputElement).value).toBe('Адрес фактического объекта');
    expect((w.get('[data-testid="customer-branch"]').element as HTMLSelectElement).value).toBe('');
  });
  it('collapses after customer save succeeds and retains values on error', async () => {
    const pending = deferred<{}>(); api.patchManagerCustomer.mockReturnValueOnce(pending.promise); const w = make();
    await open(w, 'customer'); await w.get('[data-testid="edit-customer"]').trigger('click'); await w.get('[data-testid="customer-name"]').setValue('Анна Иванова');
    await w.get('[data-testid="save-customer"]').trigger('click'); await flushPromises();
    expect(w.props('editTarget')).toBe('customer'); expect((w.get('[data-testid="inline-customer-editor"]').element as HTMLFieldSetElement).disabled).toBe(true);
    pending.resolve({}); await flushPromises(); expect(w.props('editTarget')).toBe(null);
    api.patchManagerCustomer.mockRejectedValueOnce(new Error('offline')); await open(w, 'customer'); await w.get('[data-testid="edit-customer"]').trigger('click');
    await w.get('[data-testid="customer-name"]').setValue('Другое имя'); await w.get('[data-testid="save-customer"]').trigger('click'); await flushPromises();
    expect(w.props('editTarget')).toBe('customer'); expect(w.get('[role="alert"]').text()).toContain('offline');
    expect((w.get('[data-testid="customer-name"]').element as HTMLTextAreaElement).value).toBe('Другое имя');
  });
  const pickCustomer = async (w: VueWrapper) => {
    await open(w, 'customer'); await w.get('[data-testid="change-customer"]').trigger('click'); await w.get('[data-testid="customer-search"]').setValue('Новый');
    await vi.advanceTimersByTimeAsync(450); await flushPromises(); expect(w.get('[data-testid="assign-customer-22"]').text()).toContain('УНП 123456789');
    await w.get('[data-testid="assign-customer-22"]').trigger('click');
  };
  it('applies selected customer explicitly after saving order edits and clears old branch', async () => {
    vi.useFakeTimers(); const beforeSave = vi.fn().mockResolvedValue(true); const w = make({ beforeSave, customerBranchId: 31 }); await pickCustomer(w);
    expect(api.patchManagerOrder).not.toHaveBeenCalled(); await w.get('[data-testid="assign-customer"]').trigger('click'); await flushPromises();
    expect(beforeSave).toHaveBeenCalledOnce(); expect(api.patchManagerOrder).toHaveBeenCalledWith(42, { customer_id: 22, customer_branch_id: null });
    expect(w.props('customerBranchId')).toBe(null); expect(w.props('editTarget')).toBe(null);
  });
  it('retains selected customer on error and supports retry', async () => {
    vi.useFakeTimers(); api.patchManagerOrder.mockRejectedValueOnce(new Error('offline')); const w = make(); await pickCustomer(w);
    await w.get('[data-testid="assign-customer"]').trigger('click'); await flushPromises(); expect(w.props('editTarget')).toBe('customer'); expect(w.text()).toContain('offline'); expect(w.text()).toContain('Новый клиент');
    await w.get('[data-testid="assign-customer"]').trigger('click'); await flushPromises(); expect(w.props('editTarget')).toBe(null);
  });
  it('offers inline selection immediately for an unassigned customer', async () => {
    const w = make({ order: { ...order, customer: null } }); await open(w, 'customer'); expect(w.get('[data-testid="customer-search"]').isVisible()).toBe(true);
  });
  it('blocks identity change if preceding order edits fail to save', async () => {
    const w = make({ beforeSave: vi.fn().mockResolvedValue(false) }); await open(w, 'customer'); await w.get('[data-testid="edit-customer"]').trigger('click'); await w.get('[data-testid="save-customer"]').trigger('click'); await flushPromises();
    expect(api.patchManagerCustomer).not.toHaveBeenCalled(); expect(w.props('editTarget')).toBe('customer');
  });
  it('honors failed navigation and allows successful deliberate unmount', async () => {
    const w = make({ beforeNavigate: vi.fn().mockResolvedValue(false) }); await open(w, 'customer'); const push = vi.spyOn(window.history, 'pushState');
    await w.get('[aria-label="Открыть полную карточку клиента"]').trigger('click'); await flushPromises(); expect(push).not.toHaveBeenCalled();
    await w.setProps({ beforeNavigate: async () => { w.unmount(); return true; } }); await w.get('[aria-label="Открыть полную карточку клиента"]').trigger('click'); await flushPromises();
    expect(push).toHaveBeenCalledWith({}, '', expect.stringContaining('customerId=11')); push.mockRestore();
  });
  it('ignores customer-save response after changing orders', async () => {
    const pending = deferred<{}>(); api.patchManagerCustomer.mockReturnValueOnce(pending.promise); const w = make();
    await open(w, 'customer'); await w.get('[data-testid="edit-customer"]').trigger('click'); await w.get('[data-testid="save-customer"]').trigger('click'); await flushPromises();
    await w.setProps({ order: { ...order, id: 43 }, editTarget: null }); pending.resolve({}); await flushPromises(); expect(w.emitted('updated')).toBeUndefined();
  });
  it('ignores stale branch choices after changing customers', async () => {
    const pending = deferred<{ items: typeof branches }>(); api.getManagerCustomerBranches.mockReturnValueOnce(pending.promise); const w = make();
    await w.setProps({ order: { ...order, customer: { ...order.customer!, id: 12 } } }); await flushPromises(); pending.resolve({ items: [{ ...branches[0], id: 99 }] }); await flushPromises(); await open(w, 'object');
    expect(w.find('option[value="99"]').exists()).toBe(false);
  });
  it('stages explicit company address suggestion without autosaving it', async () => {
    suggestAddress.mockResolvedValue({ items: [{ value: 'Минск, Победителей, 1', title: 'Минск, Победителей, 1' }] });
    const w = make({ order: { ...order, customer: { ...order.customer!, type: 'company', full_legal_name: 'ООО Альфа' } } }); await open(w, 'object'); expect(suggestAddress).not.toHaveBeenCalled();
    await w.get('[data-testid="suggest-company-address"]').trigger('click'); await flushPromises(); await w.get('[data-testid="company-address-candidate-Минск, Победителей, 1"]').trigger('click');
    expect(w.emitted('update:deliveryAddress')).toBeUndefined(); expect((address(w).element as HTMLInputElement).value).toBe('Минск, Победителей, 1');
  });
});
