import { mount, flushPromises, type VueWrapper } from '@vue/test-utils';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import InstallerMoneyReceipt from '../src/components/installer/InstallerMoneyReceipt.vue';
import WorkerMoneyView from '../src/views/WorkerMoneyView.vue';
import { workerMoneyApi as api, exactAmount } from '../src/services/worker-money';
import { managerSession, clearManagerSession } from '../src/services/manager-session';
import { managerStorefrontSelection } from '../src/services/manager-storefront-selection';
vi.mock('../src/services/worker-money', async original => ({ ...await original<typeof import('../src/services/worker-money')>(), workerMoneyApi: { own: vi.fn(), recipients: vi.fn(), receive: vi.fn(), handover: vi.fn(), cancel: vi.fn(), overview: vi.fn(), worker: vi.fn(), action: vi.fn(), reverse: vi.fn() } }));
const balance = { currency: 'BYN' as const, received: '100.00', handed_over: '0.00', held: '100.00', pending: '0.00', available: '100.00' };
const entry = { id: 7, kind: 'handover' as const, status: 'pending' as const, amount: '20.00', currency: 'BYN' as const, created_at: '2026-10-17T10:00:00Z', recipient_staff_user_id: 3, recipient_name: 'Кассир', version: 2, can_reverse: false };
const workspace = { worker_profile_id: 4, staff_user_id: 9, display_name: 'Монтажник', version: 8, can_manage: true, balances: [balance], items: [entry], total: 1, page: 1, limit: 30 };
let wrapper: VueWrapper | undefined;
beforeEach(() => {
  vi.resetAllMocks();
  managerSession.isAuthenticated.value = true; managerSession.auth.value = { username: 'staff', status: 'authenticated', staff_user_id: 3, tenant_id: 2, storefront_id: 5, capabilities: ['crm.manage'] };
  managerStorefrontSelection.selectedTenantId.value = 2; managerStorefrontSelection.selectedSlug.value = 'main';
  vi.mocked(api.own).mockResolvedValue(workspace); vi.mocked(api.worker).mockResolvedValue(workspace);
  vi.mocked(api.overview).mockResolvedValue({ items: [workspace], can_manage: true, total: 1, page: 1, limit: 30 });
  vi.mocked(api.recipients).mockResolvedValue({ items: [{ staff_user_id: 3, display_name: 'Кассир' }], total: 1, page: 1, limit: 30 });
});
afterEach(() => { wrapper?.unmount(); wrapper = undefined; clearManagerSession(); });
const button = (text: string) => wrapper!.findAll('button').find(item => item.text() === text)!;
const receipt = () => mount(InstallerMoneyReceipt, { props: { assignmentId: 11, collection: { status: 'ready', amount: '100.00', currency: 'BYN', version: 6 } } });
describe('client money receipt', () => {
  it('requires deliberate partial confirmation and suppresses double submission', async () => {
    let resolve!: () => void; vi.mocked(api.receive).mockReturnValue(new Promise<void>(done => { resolve = done; }));
    wrapper = receipt(); await wrapper.get('input').setValue('12,30'); await button('Получил деньги').trigger('click');
    expect(api.receive).not.toHaveBeenCalled(); expect(wrapper.text()).toContain('12.30 BYN');
    await button('Подтверждаю получение').trigger('click'); await button('Сохраняем…').trigger('click');
    expect(api.receive).toHaveBeenCalledTimes(1); expect(api.receive).toHaveBeenCalledWith(11, expect.objectContaining({ amount: '12.30', currency: 'BYN', expected_version: 6 })); resolve(); await flushPromises(); expect(wrapper.emitted('saved')).toHaveLength(1);
  });
  it('rejects extra decimals, zero and exceeding instruction without rounding', async () => {
    wrapper = receipt(); for (const value of ['1.005', '0', '100.01']) { await wrapper.get('input').setValue(value); await button('Получил деньги').trigger('click'); expect(wrapper.find('[role=alert]').exists()).toBe(true); } expect(api.receive).not.toHaveBeenCalled(); expect(exactAmount('999999999999.99')).toBe('999999999999.99');
  });
  it('retains the command across uncertain retries and blocks stale instruction replay', async () => {
    vi.mocked(api.receive).mockRejectedValueOnce(new Error('Связь прервана')).mockRejectedValueOnce({ status: 409 });
    wrapper = receipt(); await wrapper.get('input').setValue('10'); await button('Получил деньги').trigger('click'); await button('Подтверждаю получение').trigger('click'); await flushPromises();
    const original = vi.mocked(api.receive).mock.calls[0]![1]; await button('Подтверждаю получение').trigger('click'); await flushPromises();
    expect(vi.mocked(api.receive).mock.calls[1]![1]).toEqual(original); expect(button('Подтверждаю получение').attributes('disabled')).toBeDefined(); expect(wrapper.text()).toContain('Поручение изменилось');
  });
  it('never offers receipt without designated positive current instructions', () => {
    for (const collection of [{ status: 'not_collector' as const, amount: '100', version: 1 }, { status: 'ready' as const, amount: '0', version: 1 }, { status: 'ready' as const, amount: '100' }]) { const item = mount(InstallerMoneyReceipt, { props: { assignmentId: 11, collection: { ...collection, currency: 'BYN' } } }); expect(item.find('button').exists()).toBe(false); item.unmount(); }
  });
});
describe('worker cash workspace', () => {
  it('records a handover only after confirming amount and recipient with account version', async () => {
    vi.mocked(api.handover).mockResolvedValue({}); wrapper = mount(WorkerMoneyView); await flushPromises();
    await button('Загрузить получателей').trigger('click'); await flushPromises(); await wrapper.get('[aria-label="Получатель денег"]').setValue('3'); await wrapper.get('[aria-label="Сумма передачи"]').setValue('20.5'); await wrapper.get('form').trigger('submit');
    expect(api.handover).not.toHaveBeenCalled(); expect(wrapper.get('[role=dialog]').text()).toContain('20.50 BYN: Кассир'); await button('Подтверждаю').trigger('click'); await flushPromises(); expect(api.handover).toHaveBeenCalledWith(expect.objectContaining({ amount: '20.50', recipient_staff_user_id: 3, expected_version: 8 }));
  });
  it('shows cash confirmations only for intended finance recipient and rejects for finance', async () => {
    wrapper = mount(WorkerMoneyView, { props: { management: true } }); await flushPromises(); await wrapper.findAll('button').find(item => item.text().includes('Монтажник'))!.trigger('click'); await flushPromises();
    expect(button('Я принял деньги')).toBeDefined(); expect(button('Отклонить')).toBeDefined(); await button('Я принял деньги').trigger('click'); await button('Подтверждаю').trigger('click'); await flushPromises(); expect(api.action).toHaveBeenCalledWith(4, 7, 'confirm', expect.objectContaining({ expected_version: 2 }));
    vi.mocked(api.worker).mockResolvedValue({ ...workspace, can_manage: false }); await button('Обновить').trigger('click'); await flushPromises(); expect(button('Я принял деньги')).toBeUndefined(); expect(button('Отклонить')).toBeUndefined();
  });
  it('does not expose confirmation to a different recipient', async () => {
    vi.mocked(api.worker).mockResolvedValue({ ...workspace, items: [{ ...entry, recipient_staff_user_id: 99 }] }); wrapper = mount(WorkerMoneyView, { props: { management: true } }); await flushPromises(); await wrapper.findAll('button').find(item => item.text().includes('Монтажник'))!.trigger('click'); await flushPromises(); expect(button('Я принял деньги')).toBeUndefined(); expect(button('Отклонить')).toBeDefined();
  });
  it('cancels a pending handover using its displayed row version', async () => {
    vi.mocked(api.cancel).mockResolvedValue({}); wrapper = mount(WorkerMoneyView); await flushPromises(); await button('Отменить передачу').trigger('click'); expect(api.cancel).not.toHaveBeenCalled(); await button('Подтверждаю').trigger('click'); await flushPromises(); expect(api.cancel).toHaveBeenCalledWith(7, expect.objectContaining({ expected_version: 2 }));
  });
  it('captures a reason and account version for a reversible original receipt', async () => {
    vi.mocked(api.worker).mockResolvedValue({ ...workspace, items: [{ ...entry, kind: 'client_receipt', status: 'recorded', can_reverse: true }] });
    wrapper = mount(WorkerMoneyView, { props: { management: true } }); await flushPromises(); await wrapper.findAll('button').find(item => item.text().includes('Монтажник'))!.trigger('click'); await flushPromises();
    await button('Исправить ошибочное получение').trigger('click'); expect(api.reverse).not.toHaveBeenCalled(); expect(wrapper.text()).toContain('Укажите причину'); await wrapper.get('[aria-label="Причина исправления"]').setValue('Ошибочная запись'); await button('Исправить ошибочное получение').trigger('click'); await button('Подтверждаю').trigger('click'); await flushPromises(); expect(api.reverse).toHaveBeenCalledWith(4, 7, expect.objectContaining({ expected_version: 8, reason: 'Ошибочная запись' }));
  });
  it('blocks conflicting handover retry without silently sending a new version', async () => {
    vi.mocked(api.cancel).mockRejectedValue({ status: 409 }); wrapper = mount(WorkerMoneyView); await flushPromises(); await button('Отменить передачу').trigger('click'); await button('Подтверждаю').trigger('click'); await flushPromises(); expect(api.cancel).toHaveBeenCalledTimes(1); expect(button('Подтверждаю').attributes('disabled')).toBeDefined();
    managerStorefrontSelection.selectedSlug.value = 'another-site'; await flushPromises(); expect(wrapper.find('[role=dialog]').exists()).toBe(false); expect(api.cancel).toHaveBeenCalledTimes(1);
  });
  it('paginates the journal and keeps historical orders as plain text', async () => {
    vi.mocked(api.own).mockResolvedValue({ ...workspace, total: 31, items: [{ ...entry, order_id: 77, title: 'Архивная работа' }] }); wrapper = mount(WorkerMoneyView); await flushPromises(); expect(wrapper.text()).toContain('Заказ №77'); expect(wrapper.find('a').exists()).toBe(false); await button('Далее').trigger('click'); await flushPromises(); expect(api.own).toHaveBeenLastCalledWith(2);
  });
  it('clears old company balance and ignores delayed responses after context changes', async () => {
    let resolve!: (value: typeof workspace) => void; vi.mocked(api.own).mockImplementationOnce(() => new Promise(done => { resolve = done; })).mockResolvedValueOnce({ ...workspace, balances: [], items: [] });
    wrapper = mount(WorkerMoneyView); await flushPromises(); managerStorefrontSelection.selectedTenantId.value = 22; await flushPromises(); resolve({ ...workspace, display_name: 'OLD', balances: [{ ...balance, held: '98765.00' }] }); await flushPromises(); expect(wrapper.text()).not.toContain('98765.00'); expect(wrapper.text()).not.toContain('OLD');
  });
});
