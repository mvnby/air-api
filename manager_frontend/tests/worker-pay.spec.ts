import { DOMWrapper, flushPromises, mount, type VueWrapper } from '@vue/test-utils';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import WorkerPayView from '../src/views/WorkerPayView.vue';
import OrderWorkerPayPanel from '../src/components/orders/OrderWorkerPayPanel.vue';
import { workerPayApi as api } from '../src/services/worker-pay';
import { workerMoneyApi } from '../src/services/worker-money';
import { managerSession, clearManagerSession } from '../src/services/manager-session';
import { managerStorefrontSelection } from '../src/services/manager-storefront-selection';
vi.mock('../src/services/worker-pay', () => ({ workerPayApi: { own: vi.fn(), overview: vi.fn(), worker: vi.fn(), order: vi.fn(), agree: vi.fn(), revise: vi.fn(), agreementAction: vi.fn(), payout: vi.fn(), offset: vi.fn(), reverse: vi.fn() } }));
vi.mock('../src/services/worker-money', async original => ({ ...await original<typeof import('../src/services/worker-money')>(), workerMoneyApi: { worker: vi.fn() } }));
const agreement = { id: 12, worker_profile_id: 4, order_id: 77, assignment_reference: 11, work_stage_id: null, work_key: 'w1', title: 'Монтаж блока', amount: '100.00', currency: 'BYN', status: 'accrued' as const, version: 2, paid: '20.00', owed: '80.00', created_at: '2026-10-17T10:00:00Z', cost_byn_amount: 'SECRET-COST' };
const balance = { currency: 'BYN', agreed: '100.00', accrued: '100.00', paid: '20.00', owed: '80.00' };
const entry = { id: 8, kind: 'payout' as const, status: 'recorded' as const, amount: '20.00', currency: 'BYN', method: 'cash' as const, created_at: '2026-10-17T10:00:00Z', version: 0, can_reverse: true };
const workspace = { worker_profile_id: 4, staff_user_id: 9, display_name: 'Монтажник', version: 6, can_manage: true, can_offset: true, balances: [balance], agreements: [agreement], items: [entry], total: 1, page: 1, limit: 30 };
const candidate = { assignment_id: 11, worker_profile_id: 4, staff_user_id: 9, display_name: 'Монтажник', title: 'Монтаж блока', work_stage_id: null, account_version: 6 };
let wrapper: VueWrapper | undefined;
const content = () => new DOMWrapper(document.body);
const button = (text: string) => content().findAll('button').find(item => item.text() === text)!;
beforeEach(() => {
  vi.resetAllMocks(); managerSession.isAuthenticated.value = true; managerSession.auth.value = { username: 'admin', status: 'authenticated', staff_user_id: 3, tenant_id: 2, storefront_id: 5, capabilities: ['crm.manage', 'worker.pay.read', 'worker.pay.manage'] };
  managerStorefrontSelection.selectedTenantId.value = 2; managerStorefrontSelection.selectedSlug.value = 'main';
  vi.mocked(api.own).mockResolvedValue(workspace); vi.mocked(api.worker).mockResolvedValue(workspace); vi.mocked(api.overview).mockResolvedValue({ items: [workspace], total: 1, page: 1, limit: 30, can_manage: true, can_offset: true });
  vi.mocked(api.order).mockResolvedValue({ order_id: 77, candidates: [candidate], agreements: [], can_manage: true });
  vi.mocked(workerMoneyApi.worker).mockResolvedValue({ ...workspace, balances: [{ currency: 'BYN', received: '70.00', handed_over: '0.00', held: '70.00', pending: '10.00', available: '60.00' }], items: [] });
});
afterEach(() => { wrapper?.unmount(); wrapper = undefined; clearManagerSession(); document.body.innerHTML = ''; });
const openManager = async () => { wrapper = mount(WorkerPayView, { props: { management: true }, attachTo: document.body }); await flushPromises(); await content().findAll('button').find(item => item.text().includes('Монтажник'))!.trigger('click'); await flushPromises(); };
describe('worker remuneration', () => {
  it('shows only own remuneration and separates client cash without expense or finance actions', async () => {
    wrapper = mount(WorkerPayView, { attachTo: document.body }); await flushPromises(); expect(wrapper.text()).not.toContain('SECRET-COST'); expect(wrapper.text()).not.toContain('Монтажник'); expect(wrapper.text()).toContain('Начислено: 100.00'); expect(wrapper.text()).toContain('80.00'); expect(wrapper.find('input').exists()).toBe(false); expect(workerMoneyApi.worker).not.toHaveBeenCalled(); expect(wrapper.get('a').attributes('href')).toContain('/manager/my-money?company=2&site=main');
  });
  it('confirms a partial bank payout and suppresses duplicate submission', async () => {
    let resolve!: () => void; vi.mocked(api.payout).mockReturnValue(new Promise<void>(done => { resolve = done; })); await openManager(); await content().get('[aria-label="Сумма выплаты"]').setValue('12,50'); await content().get('[aria-label="Способ выплаты"]').setValue('bank'); await content().get('form').trigger('submit'); expect(api.payout).not.toHaveBeenCalled(); expect(content().get('[role=dialog]').text()).toContain('12.50 BYN по банку'); await button('Подтверждаю').trigger('click'); await button('Сохраняем…').trigger('click'); expect(api.payout).toHaveBeenCalledTimes(1); expect(api.payout).toHaveBeenCalledWith(4, expect.objectContaining({ amount: '12.50', expected_version: 6, method: 'bank' })); resolve(); await flushPromises();
  });
  it('rejects overpayment and extra decimals without rounding', async () => {
    await openManager(); for (const amount of ['80.01', '0', '1.005']) { await content().get('[aria-label="Сумма выплаты"]').setValue(amount); await content().get('form').trigger('submit'); expect(content().find('[role=dialog]').exists()).toBe(false); } expect(api.payout).not.toHaveBeenCalled();
  });
  it('shows both balances in an explicit partial offset summary and captures version', async () => {
    vi.mocked(api.offset).mockResolvedValue({}); await openManager(); expect(wrapper!.text()).toContain('Доступно зачесть: 60.00 BYN'); await content().get('[aria-label="Сумма выплаты"]').setValue('25'); await button('Зачесть деньги клиента в вознаграждение').trigger('click'); const text = content().get('[role=dialog]').text(); expect(text).toContain('80.00 → 55.00 BYN'); expect(text).toContain('70.00 → 45.00 BYN'); expect(api.offset).not.toHaveBeenCalled(); await button('Подтверждаю').trigger('click'); await flushPromises(); expect(api.offset).toHaveBeenCalledWith(4, expect.objectContaining({ amount: '25.00', expected_version: 6 }));
  });
  it('keeps platform support read only even when remuneration history is visible', async () => {
    vi.mocked(api.worker).mockResolvedValue({ ...workspace, can_manage: false, can_offset: false }); await openManager(); expect(wrapper!.text()).toContain('80.00'); expect(wrapper!.find('input').exists()).toBe(false); expect(button('Учесть выплату')).toBeUndefined(); expect(button('Исправить ошибочную выплату')).toBeUndefined();
  });
  it('does not offer offset with only remuneration permission', async () => {
    vi.mocked(api.worker).mockResolvedValue({ ...workspace, can_offset: false }); await openManager(); expect(button('Зачесть деньги клиента в вознаграждение')).toBeUndefined(); expect(workerMoneyApi.worker).not.toHaveBeenCalled();
  });
  it('retains exact command after uncertain failure then blocks 409', async () => {
    vi.mocked(api.payout).mockRejectedValueOnce(new Error('Нет ответа')).mockRejectedValueOnce({ status: 409 }); await openManager(); await content().get('[aria-label="Сумма выплаты"]').setValue('10'); await content().get('form').trigger('submit'); await button('Подтверждаю').trigger('click'); await flushPromises(); const body = vi.mocked(api.payout).mock.calls[0]![1]; await button('Подтверждаю').trigger('click'); await flushPromises(); expect(vi.mocked(api.payout).mock.calls[1]![1]).toEqual(body); expect(button('Подтверждаю').attributes('disabled')).toBeDefined();
  });
  it('requires a reason for correcting a payout', async () => {
    vi.mocked(api.reverse).mockResolvedValue({}); await openManager(); await button('Исправить ошибочную выплату').trigger('click'); expect(content().find('[role=dialog]').exists()).toBe(false); await content().get('[aria-label="Причина исправления выплаты"]').setValue('Ошибочная выплата'); await button('Исправить ошибочную выплату').trigger('click'); await button('Подтверждаю').trigger('click'); await flushPromises(); expect(api.reverse).toHaveBeenCalledWith(4, 8, expect.objectContaining({ expected_version: 6, reason: 'Ошибочная выплата' }));
  });
  it('clears a pending offset and foreign worker data on site change', async () => {
    await openManager(); await content().get('[aria-label="Сумма выплаты"]').setValue('10'); await button('Зачесть деньги клиента в вознаграждение').trigger('click'); managerStorefrontSelection.selectedSlug.value = 'other'; await flushPromises(); expect(content().find('[role=dialog]').exists()).toBe(false); expect(api.offset).not.toHaveBeenCalled(); expect(wrapper!.text()).not.toContain('SECRET-COST');
  });
});
describe('order remuneration agreement', () => {
  it('flushes the order before creating an exact fixed agreement and refreshes margin afterward', async () => {
    const beforeAction = vi.fn().mockResolvedValue(true); vi.mocked(api.agree).mockResolvedValue({}); wrapper = mount(OrderWorkerPayPanel, { props: { orderId: 77, beforeAction }, attachTo: document.body }); await flushPromises(); await content().get('[aria-label="Работа для вознаграждения"]').setValue('11'); await content().get('[aria-label="Вознаграждение за работу"]').setValue('25,50'); await content().get('form').trigger('submit'); expect(beforeAction).not.toHaveBeenCalled(); await button('Подтверждаю').trigger('click'); await flushPromises(); expect(beforeAction).toHaveBeenCalledTimes(1); expect(api.agree).toHaveBeenCalledWith(77, expect.objectContaining({ amount: '25.50', assignment_id: 11, expected_version: 6 })); expect(vi.mocked(api.agree).mock.calls[0]![1]).not.toHaveProperty('cost_byn_amount'); expect(wrapper.emitted('changed')).toHaveLength(1);
  });
  it('requires a reviewed BYN expense for a foreign currency agreement', async () => {
    wrapper = mount(OrderWorkerPayPanel, { props: { orderId: 77, beforeAction: vi.fn().mockResolvedValue(true) }, attachTo: document.body }); await flushPromises(); await content().get('[aria-label="Работа для вознаграждения"]').setValue('11'); await content().get('[aria-label="Вознаграждение за работу"]').setValue('10'); await content().get('[aria-label="Валюта вознаграждения"]').setValue('USD'); await content().get('form').trigger('submit'); expect(content().find('[role=dialog]').exists()).toBe(false); await content().get('[aria-label="Расход вознаграждения в BYN"]').setValue('32.50'); await content().get('form').trigger('submit'); expect(content().get('[role=dialog]').text()).toContain('32.50 BYN');
  });
  it('does not send a captured agreement if the order changes during the save barrier', async () => {
    let resolve!: (value: boolean) => void; const beforeAction = vi.fn(() => new Promise<boolean>(done => { resolve = done; })); wrapper = mount(OrderWorkerPayPanel, { props: { orderId: 77, beforeAction }, attachTo: document.body }); await flushPromises(); await content().get('[aria-label="Работа для вознаграждения"]').setValue('11'); await content().get('[aria-label="Вознаграждение за работу"]').setValue('10'); await content().get('form').trigger('submit'); await button('Подтверждаю').trigger('click'); await wrapper.setProps({ orderId: 78 }); resolve(true); await flushPromises(); expect(api.agree).not.toHaveBeenCalled();
  });
  it('explicitly accrues using both current account and displayed agreement versions', async () => {
    vi.mocked(api.order).mockResolvedValue({ order_id: 77, candidates: [candidate], agreements: [{ ...agreement, status: 'agreed', paid: '0.00' }], can_manage: true }); vi.mocked(api.agreementAction).mockResolvedValue({}); wrapper = mount(OrderWorkerPayPanel, { props: { orderId: 77, beforeAction: vi.fn().mockResolvedValue(true) }, attachTo: document.body }); await flushPromises(); await button('Начислить').trigger('click'); await flushPromises(); expect(api.agreementAction).not.toHaveBeenCalled(); await button('Подтверждаю').trigger('click'); await flushPromises(); expect(api.agreementAction).toHaveBeenCalledWith(4, 12, 'accrue', expect.objectContaining({ expected_version: 6, expected_agreement_version: 2 }));
  });
});
