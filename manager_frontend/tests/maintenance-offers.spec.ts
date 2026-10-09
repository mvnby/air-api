import { flushPromises, mount } from '@vue/test-utils';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import Panel from '../src/components/maintenance-observations/MaintenanceOffersPanel.vue';
const api = vi.hoisted(() => ({ listManagerMaintenanceOffers: vi.fn(), prepareManagerMaintenanceWorkspace: vi.fn(), prepareManagerMaintenanceOffer: vi.fn(), commandManagerMaintenanceOffer: vi.fn(), resolveManagerMaintenanceObservation: vi.fn() }));
const order = vi.hoisted(() => vi.fn());
vi.mock('../src/client', async (original) => ({ ...await original<object>(), ManagerMaintenanceObservationsService: api, ManagerOrdersService: { getManagerOrderDetail: order } }));
const observations = [{ id: 3, version: 2, equipment_description: 'Блок A' }, { id: 4, version: 1, equipment_description: 'Блок B' }] as any;
const offer = { id: 10, source_order_id: 42, continuation_order_id: 66, proposal_id: 8, version: 2, state: 'send', snapshot: { proposal_name: 'Ремонт', lines: [
  { key: 'service:5', kind: 'service', observation_id: 3, purpose: 'repair', data: { title: 'Ремонт A', quantity: 1, price: '120.25' } },
  { key: 'service:6', kind: 'service', observation_id: 4, purpose: 'diagnosis', data: { title: 'Диагностика B', quantity: 1, price: '30.50' } },
] }, events: [], resolutions: [] };
beforeEach(() => {
  vi.clearAllMocks(); api.listManagerMaintenanceOffers.mockResolvedValue({ items: [], total: 0 });
  api.prepareManagerMaintenanceWorkspace.mockResolvedValue({ source_order_id: 42, continuation_order_id: 66 });
  order.mockResolvedValue({ proposals: [{ id: 8, name: 'Ремонт', is_selected: true, status: 'draft', service_lines: [{ id: 5, service_title: 'Ремонт A', quantity: 1, price: 120.25 }], product_lines: [] }] });
  api.prepareManagerMaintenanceOffer.mockResolvedValue({ ...offer, state: 'draft', version: 0 });
  api.commandManagerMaintenanceOffer.mockResolvedValue(offer); api.resolveManagerMaintenanceObservation.mockResolvedValue({ id: 1 });
});
const panel = () => mount(Panel, { props: { orderId: 42, observations } });
const button = (w: ReturnType<typeof panel>, label: string) => w.findAll('button').find(b => b.text() === label)!;
async function evidence(w: ReturnType<typeof panel>) {
  await w.get('input[placeholder="Письмо клиента, звонок, встреча…"]').setValue('Письмо 42');
  await w.findAll('textarea')[0]!.setValue('Клиент согласовал только ремонт A');
}
describe('maintenance commercial workflow requests', () => {
  it('prepares actual ordinary lines and selected finding revisions without implicit work', async () => {
    const w = panel(); await flushPromises(); expect(api.prepareManagerMaintenanceWorkspace).not.toHaveBeenCalled();
    await w.get('[data-testid="maintenance-workspace"]').trigger('click'); await flushPromises();
    expect(w.get('a').attributes('href')).toBe('/manager/orders/kanban?orderId=66');
    expect(w.get('[data-testid="prepare-offer"]').attributes('disabled')).toBeDefined();
    await w.get('select[aria-label="Замечание для Ремонт A"]').setValue(3); await w.findAll('select')[2]!.setValue('repair');
    await w.get('[data-testid="prepare-offer"]').trigger('click'); await flushPromises();
    expect(api.prepareManagerMaintenanceOffer).toHaveBeenCalledWith(42, expect.objectContaining({ proposal_id: 8, lines: [{ kind: 'service', line_id: 5, purpose: 'repair', observation_id: 3, expected_version: 2 }] }));
    expect(api.commandManagerMaintenanceOffer).not.toHaveBeenCalled();
  });
  it('partial consent sends only checked frozen line and exact version', async () => {
    api.listManagerMaintenanceOffers.mockResolvedValue({ items: [offer], total: 1 });
    const w = panel(); await flushPromises(); await evidence(w);
    await w.get('input[aria-label="Согласовать service:5"]').setValue(true);
    await button(w, 'Согласовать выбранные строки').trigger('click'); await flushPromises();
    expect(api.commandManagerMaintenanceOffer).toHaveBeenCalledWith(42, 10, expect.objectContaining({ action: 'accept', expected_version: 2, accepted_lines: ['service:5'], source: 'Письмо 42' }));
    expect(api.commandManagerMaintenanceOffer).toHaveBeenCalledTimes(1); expect(api.resolveManagerMaintenanceObservation).not.toHaveBeenCalled();
  });
  it('replays exact command after acknowledgement loss and permits return to deferred', async () => {
    api.listManagerMaintenanceOffers.mockResolvedValue({ items: [{ ...offer, state: 'defer', version: 4 }], total: 1 });
    api.commandManagerMaintenanceOffer.mockRejectedValueOnce(new Error('Lost acknowledgement'));
    const w = panel(); await flushPromises(); await evidence(w);
    await w.get('input[aria-label="Согласовать service:5"]').setValue(true);
    await button(w, 'Согласовать выбранные строки').trigger('click'); await flushPromises();
    const first = api.commandManagerMaintenanceOffer.mock.calls[0]![2]; expect(w.get('fieldset').attributes('disabled')).toBeDefined();
    await button(w, 'Повторить сохранённую команду').trigger('click'); await flushPromises();
    expect(api.commandManagerMaintenanceOffer.mock.calls[1]![2]).toEqual(first); expect(first.expected_version).toBe(4);
  });
  it('shows agreed subset and both totals after acceptance without hiding rejected lines', async () => {
    api.listManagerMaintenanceOffers.mockResolvedValue({ items: [{ ...offer, state: 'accept', version: 3, events: [{ id: 1, action: 'accept', details: { accepted_lines: ['service:5'] } }] }], total: 1 });
    const w = panel(); await flushPromises();
    expect(w.text()).toContain('Согласовано'); expect(w.text()).toContain('Не согласовано');
    expect(w.text()).toContain('Ремонт A'); expect(w.text()).toContain('Диагностика B');
    expect(w.text()).toContain('150,75'); expect(w.text()).toContain('120,25');
    expect(w.findAll('[aria-label="Нет данных"]')).toHaveLength(0);
  });
  it('resolves only an approved repair through separate evidence command', async () => {
    api.listManagerMaintenanceOffers.mockResolvedValue({ items: [{ ...offer, state: 'continue', version: 4, events: [{ id: 1, action: 'continue', actor: 'manager', details: { source: 'email', comment: 'approved', accepted_lines: ['service:5', 'service:6'] } }] }], total: 1 });
    const w = panel(); await flushPromises(); expect(w.text()).not.toContain('Подтвердить устранение #4');
    await button(w, 'Подтвердить устранение #3').trigger('click');
    expect(button(w, 'Подтвердить устранение и записать ремонт в историю').attributes('disabled')).toBeDefined();
    await w.findAll('textarea')[1]!.setValue('Изоляция заменена и проверена');
    await button(w, 'Подтвердить устранение и записать ремонт в историю').trigger('click'); await flushPromises();
    expect(api.resolveManagerMaintenanceObservation).toHaveBeenCalledWith(3, expect.objectContaining({ expected_version: 2, offer_id: 10, evidence: 'Изоляция заменена и проверена' }));
  });
});
