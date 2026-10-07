import { flushPromises, mount } from '@vue/test-utils';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import Panel from '../src/components/maintenance-observations/MaintenanceDefectActsPanel.vue';
import { ApiError } from '../src/client';
const api = vi.hoisted(() => ({ listManagerMaintenanceDefectActs: vi.fn(), prepareManagerMaintenanceDefectAct: vi.fn() }));
const entities = vi.hoisted(() => vi.fn());
const preview = vi.hoisted(() => vi.fn());
vi.mock('../src/client', async (original) => ({ ...await original<object>(),
  ManagerMaintenanceObservationsService: api, ManagerDocumentSystemService: { listManagerDocumentLegalEntities: entities } }));
vi.mock('../src/features/documents/integrations/native-document-preview', () => ({ openNativeDocumentPreview: preview }));
const act = { preparation_id: 1, source_order_id: 42, continuation_order_id: 66, document_id: 88, status: 'draft', observations: [{ observation_id: 3, expected_version: 2 }] };
beforeEach(() => {
  vi.clearAllMocks(); entities.mockResolvedValue({ items: [{ id: 9, display_name: 'Исполнитель', status: 'active', is_default: true }] });
  api.listManagerMaintenanceDefectActs.mockResolvedValue({ items: [], total: 0 });
  api.prepareManagerMaintenanceDefectAct.mockResolvedValue(act);
});
const panel = (selected = [{ observation_id: 3, expected_version: 2 }]) => mount(Panel, { props: { orderId: 42, selected } });
describe('explicit maintenance defect acts', () => {
  it('requires a selection and issuer, preserves source versions, opens ordinary continuation documents', async () => {
    const wrapper = panel([]); await flushPromises();
    expect(wrapper.get('[data-testid="prepare-act"]').attributes('disabled')).toBeDefined();
    await wrapper.setProps({ selected: [{ observation_id: 3, expected_version: 2 }, { observation_id: 4, expected_version: 1 }] });
    api.listManagerMaintenanceDefectActs.mockResolvedValue({ items: [act], total: 1 });
    await wrapper.get('[data-testid="prepare-act"]').trigger('click'); await flushPromises();
    const [order, payload] = api.prepareManagerMaintenanceDefectAct.mock.calls[0]!;
    expect(order).toBe(42); expect(payload.observations).toEqual([{ observation_id: 3, expected_version: 2 }, { observation_id: 4, expected_version: 1 }]);
    expect(payload.command_key).toMatch(/^[a-f0-9-]{36}$/);
    expect(payload.legal_entity_id).toBe(9);
    expect(wrapper.text()).toContain('Черновик дефектного акта #88 подготовлен');
    expect(wrapper.get('a').attributes('href')).toBe('/manager/orders/kanban?orderId=66');
    await wrapper.findAll('button').find((b) => b.text() === 'Предпросмотр черновика')!.trigger('click');
    expect(preview).toHaveBeenCalledWith(88);
  });
  it('retains exact command after acknowledgement loss and locks selection/input changes', async () => {
    api.prepareManagerMaintenanceDefectAct.mockRejectedValueOnce(new Error('Connection lost'));
    const wrapper = panel(); await flushPromises();
    await wrapper.get('[data-testid="prepare-act"]').trigger('click'); await flushPromises();
    const first = api.prepareManagerMaintenanceDefectAct.mock.calls[0]![1];
    expect(wrapper.get('fieldset').attributes('disabled')).toBeDefined();
    expect(wrapper.emitted('lock')?.at(-1)).toEqual([true]);
    await wrapper.setProps({ selected: [{ observation_id: 3, expected_version: 3 }] });
    await wrapper.get('[data-testid="prepare-act"]').trigger('click'); await flushPromises();
    expect(api.prepareManagerMaintenanceDefectAct.mock.calls[1]![1]).toEqual(first);
    expect(wrapper.emitted('lock')?.at(-1)).toEqual([false]);
  });
  it('exposes stale-version error and explicit reread without silently changing versions', async () => {
    api.prepareManagerMaintenanceDefectAct.mockRejectedValueOnce(new ApiError({ method: 'POST', url: '' }, { url: '', ok: false, status: 409, statusText: 'Conflict', body: { detail: 'Замечание уже изменено' } }, 'Conflict'));
    const wrapper = panel(); await flushPromises();
    await wrapper.get('[data-testid="prepare-act"]').trigger('click'); await flushPromises();
    expect(wrapper.text()).toContain('Замечание уже изменено');
    expect(wrapper.get('fieldset').attributes('disabled')).toBeUndefined();
    await wrapper.findAll('button').find((button) => button.text() === 'Обновить замечания и акты')!.trigger('click');
    expect(wrapper.emitted('refresh')).toHaveLength(1);
    expect(api.prepareManagerMaintenanceDefectAct).toHaveBeenCalledOnce();
  });
  it('ignores a late prepare response when the source order changes', async () => {
    let resolve!: (value: unknown) => void;
    api.prepareManagerMaintenanceDefectAct.mockReturnValueOnce(new Promise((r) => { resolve = r; }));
    const wrapper = panel(); await flushPromises();
    await wrapper.get('[data-testid="prepare-act"]').trigger('click');
    await wrapper.setProps({ orderId: 43, selected: [] }); await flushPromises();
    resolve(act); await flushPromises();
    expect(wrapper.text()).not.toContain('Черновик дефектного акта #88 подготовлен');
  });
});
