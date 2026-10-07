import { flushPromises, mount } from '@vue/test-utils';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import MaintenanceObservationsPanel from '../src/components/maintenance-observations/MaintenanceObservationsPanel.vue';
import { ApiError } from '../src/client';

const api = vi.hoisted(() => ({
  listManagerOrderMaintenanceObservations: vi.fn(), listManagerEquipmentMaintenanceObservations: vi.fn(),
  createManagerMaintenanceObservation: vi.fn(), getManagerMaintenanceObservation: vi.fn(),
  updateManagerMaintenanceObservation: vi.fn(), uploadManagerMaintenanceObservationPhoto: vi.fn(),
}));
const equipment = vi.hoisted(() => vi.fn());
vi.mock('../src/client', async (original) => ({ ...await original<object>(), ManagerMaintenanceObservationsService: api }));
vi.mock('../src/components/equipment/loadAllCustomerEquipment', () => ({ listAllCustomerEquipment: equipment }));
const finding = (changes = {}) => ({
  id: 1085, source_order_id: 42, customer_id: 7, customer_branch_id: 8, equipment_id: null,
  equipment_description: 'Наружный блок у входа', original_comment: 'Повреждена изоляция.',
  facts: 'Видимое повреждение теплоизоляции.', recommendation: 'Восстановить изоляцию.',
  origin: 'manager_maintenance', created_by: 'Manager', updated_by: 'Manager', version: 1,
  observed_at: '2026-10-07T11:00:00', created_at: '2026-10-07T11:01:00', updated_at: '2026-10-07T11:01:00',
  photos: [], revisions: [], ...changes,
});
const photo = { id: 99, filename: 'block.png', file_kind: 'image', created_at: '2026-10-07T11:01:00' };
beforeEach(() => {
  vi.clearAllMocks();
  api.listManagerOrderMaintenanceObservations.mockResolvedValue({ items: [], total: 0 });
  api.listManagerEquipmentMaintenanceObservations.mockResolvedValue({ items: [finding()], total: 1 });
  api.createManagerMaintenanceObservation.mockResolvedValue(finding());
  api.getManagerMaintenanceObservation.mockResolvedValue(finding());
  api.updateManagerMaintenanceObservation.mockResolvedValue(finding({ version: 2 }));
  api.uploadManagerMaintenanceObservationPhoto.mockResolvedValue(photo);
  equipment.mockResolvedValue([]);
});
const panel = (props = {}) => mount(MaintenanceObservationsPanel, {
  props: { orderId: 42, customerId: 7, customerBranchId: 8, ...props },
  global: { stubs: { ServiceAttachmentViewer: true, MaintenanceDefectActsPanel: true } },
});
async function newFinding(wrapper: ReturnType<typeof panel>) {
  await wrapper.get('[data-testid="observations-toggle"]').trigger('click'); await flushPromises();
  await wrapper.get('[data-testid="observation-new"]').trigger('click'); await flushPromises();
  for (const [selector, value] of [['original-comment', 'Повреждена изоляция.'], ['equipment-description', 'Наружный блок у входа'], ['facts', 'Видимое повреждение теплоизоляции.'], ['recommendation', 'Восстановить изоляцию.']]) {
    await wrapper.get(`[data-testid="${selector}"]`).setValue(value);
  }
}

describe('maintenance observations', () => {
  it('loads lazily, saves without known equipment and confirms the stable ID', async () => {
    const wrapper = panel();
    expect(api.listManagerOrderMaintenanceObservations).not.toHaveBeenCalled();
    await newFinding(wrapper);
    await wrapper.get('[data-testid="observation-save"]').trigger('click'); await flushPromises();
    expect(api.createManagerMaintenanceObservation).toHaveBeenCalledOnce();
    const [id, command] = api.createManagerMaintenanceObservation.mock.calls[0]!;
    expect(id).toBe(42); expect(command.equipment_id).toBeNull();
    expect(command.command_key).toMatch(/^[a-f0-9-]{36}$/);
    expect(command.original_comment).toBe('Повреждена изоляция.');
    expect(wrapper.text()).toContain('Замечание #1085 сохранено.');
    expect(api.updateManagerMaintenanceObservation).not.toHaveBeenCalled();
  });

  it('retries an unconfirmed create with identical command and locks draft edits', async () => {
    const wrapper = panel(); await newFinding(wrapper);
    api.createManagerMaintenanceObservation.mockRejectedValueOnce(new Error('Connection lost'));
    await wrapper.get('[data-testid="observation-save"]').trigger('click'); await flushPromises();
    expect(wrapper.get('fieldset').attributes('disabled')).toBeDefined();
    const original = api.createManagerMaintenanceObservation.mock.calls[0]![1];
    await wrapper.get('[data-testid="observation-save"]').trigger('click'); await flushPromises();
    expect(api.createManagerMaintenanceObservation.mock.calls[1]![1]).toEqual(original);
    expect(wrapper.text()).toContain('Замечание #1085 сохранено.');
  });

  it('keeps failed photo upload keys and retries without a new finding or revision', async () => {
    const wrapper = panel(); await newFinding(wrapper);
    const input = wrapper.get('[data-testid="photos"]');
    Object.defineProperty(input.element, 'files', { value: [new File(['photo'], 'block.png', { type: 'image/png' })] });
    await input.trigger('change');
    api.uploadManagerMaintenanceObservationPhoto.mockRejectedValueOnce(new Error('Photo connection lost'));
    await wrapper.get('[data-testid="observation-save"]').trigger('click'); await flushPromises();
    expect(wrapper.text()).toContain('Замечание #1085 сохранено; повторите загрузку');
    const original = api.uploadManagerMaintenanceObservationPhoto.mock.calls[0];
    await wrapper.get('[data-testid="observation-save"]').trigger('click'); await flushPromises();
    expect(api.uploadManagerMaintenanceObservationPhoto.mock.calls[1]).toEqual(original);
    expect(api.createManagerMaintenanceObservation).toHaveBeenCalledOnce();
    expect(api.updateManagerMaintenanceObservation).not.toHaveBeenCalled();
    expect(wrapper.text()).toContain('сохранено с фото');
  });

  it('uses the loaded version for correction and retains a conflicting draft', async () => {
    api.listManagerOrderMaintenanceObservations.mockResolvedValue({ items: [finding()], total: 1 });
    const wrapper = panel();
    await wrapper.get('[data-testid="observations-toggle"]').trigger('click'); await flushPromises();
    await wrapper.findAll('button').find((b) => b.text().includes('#1085 ·'))!.trigger('click'); await flushPromises();
    await wrapper.findAll('button').find((b) => b.text() === 'Уточнить замечание')!.trigger('click'); await flushPromises();
    await wrapper.get('[data-testid="facts"]').setValue('Уточнено на изгибе.');
    api.updateManagerMaintenanceObservation.mockRejectedValueOnce(new ApiError({ method: 'PATCH', url: '' }, { url: '', ok: false, status: 409, statusText: 'Conflict', body: { detail: 'Замечание уже изменено.' } }, 'Conflict'));
    await wrapper.get('[data-testid="observation-save"]').trigger('click'); await flushPromises();
    expect(api.updateManagerMaintenanceObservation.mock.calls[0]![1].expected_version).toBe(1);
    expect(api.updateManagerMaintenanceObservation.mock.calls[0]![1]).not.toHaveProperty('original_comment');
    expect((wrapper.get('[data-testid="facts"]').element as HTMLTextAreaElement).value).toBe('Уточнено на изгибе.');
    expect(wrapper.text()).toContain('Замечание уже изменено');
  });

  it('ignores a late result after the source order changes', async () => {
    let resolve!: (value: unknown) => void;
    api.listManagerOrderMaintenanceObservations.mockReturnValueOnce(new Promise((r) => { resolve = r; }));
    const wrapper = panel(); await wrapper.get('[data-testid="observations-toggle"]').trigger('click');
    await wrapper.setProps({ orderId: 43 }); await flushPromises();
    resolve({ items: [finding()], total: 1 }); await flushPromises();
    expect(wrapper.text()).not.toContain('#1085 ·');
  });
});

it.each(['moved', 'archived'])('shows %s historical equipment and permits clearing the link', async (state) => {
  api.listManagerOrderMaintenanceObservations.mockResolvedValue({items:[finding({equipment_id:17})],total:1});
  api.getManagerMaintenanceObservation.mockResolvedValue(finding({equipment_id:17,equipment_link_state:state}));
  const wrapper=panel();
  await wrapper.get('[data-testid="observations-toggle"]').trigger('click'); await flushPromises();
  await wrapper.findAll('button').find(b=>b.text().includes('#1085 ·'))!.trigger('click'); await flushPromises();
  expect(wrapper.text()).toContain(state==='moved' ? 'перенесено на другой объект' : 'архивировано');
  await wrapper.findAll('button').find(b=>b.text()==='Уточнить замечание')!.trigger('click'); await flushPromises();
  expect(wrapper.get('[data-testid="equipment-id"]').text()).toContain('историческая связь');
  await wrapper.get('[data-testid="equipment-id"]').setValue('Пока неизвестно');
  await wrapper.get('[data-testid="observation-save"]').trigger('click'); await flushPromises();
  expect(api.updateManagerMaintenanceObservation.mock.calls[0]![1].equipment_id).toBeNull();
});
