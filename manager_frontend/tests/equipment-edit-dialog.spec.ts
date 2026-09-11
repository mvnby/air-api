import { DOMWrapper, flushPromises, mount, type VueWrapper } from '@vue/test-utils';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import EquipmentEditDialog from '../src/components/equipment/EquipmentEditDialog.vue';
import EquipmentRegistryCards from '../src/components/equipment/EquipmentRegistryCards.vue';
import EquipmentRegistryTable from '../src/components/equipment/EquipmentRegistryTable.vue';
import EquipmentAttentionBadges from '../src/components/equipment/EquipmentAttentionBadges.vue';
import { addCalendarMonths, equipmentEditForm, equipmentEditPayload, maintenancePreview } from '../src/components/equipment/equipmentEditForm';
import { equipmentSubtitle, equipmentWarrantyDate } from '../src/components/equipment/registry';
import type { ManagerEquipmentDetailResponse } from '../src/client';

const { getEquipment, patchEquipment } = vi.hoisted(() => ({ getEquipment: vi.fn(), patchEquipment: vi.fn() }));
vi.mock('../src/client', () => ({ ManagerEquipmentService: { getManagerEquipment: getEquipment, patchManagerEquipment: patchEquipment } }));
const item: ManagerEquipmentDetailResponse = {
  id: 7, customer_id: 2, customer_name: 'Клиент', customer_phone: '+375291111111',
  display_name: 'MDV FOREST', brand: 'MDV', model: 'MDV FOREST', equipment_source: 'customer_owned',
  commissioned_at: '2026-09-11T15:30:00', created_at: '2026-09-11T15:30:00',
  warranty_mode: 'auto', warranty_status: 'unknown', maintenance_enabled: false, maintenance_interval_months: 12,
  coverages: [], attention_reasons: ['needs_decision'],
};
const mounted: VueWrapper[] = [];
const surface = () => new DOMWrapper(document.body);
const field = (name: string, selector = 'input') => {
  const label = surface().findAll('label').find((node) => node.text().startsWith(name));
  if (!label) throw new Error(`Missing label: ${name}`);
  return label.get(selector);
};
const button = (name: string) => {
  const found = surface().findAll('button').find((node) => node.text() === name);
  if (!found) throw new Error(`Missing button: ${name}`);
  return found;
};
const open = async (data = item) => {
  getEquipment.mockResolvedValueOnce(data);
  const wrapper = mount(EquipmentEditDialog, { props: { equipmentId: data.id }, attachTo: document.body });
  mounted.push(wrapper);
  await flushPromises();
  return wrapper;
};
beforeEach(() => { vi.resetAllMocks(); patchEquipment.mockResolvedValue(item); });
afterEach(() => { mounted.splice(0).forEach((wrapper) => wrapper.unmount()); document.body.innerHTML = ''; });

describe('equipment editing', () => {
  it('saves no warranty with an independent six-month maintenance reminder', async () => {
    const wrapper = await open();
    await button('Без гарантии').trigger('click');
    await field('Напоминать о ТО').setValue(true);
    expect(field('Интервал ТО').element).toHaveProperty('value', '12');
    await field('Интервал ТО').setValue(6);
    expect(surface().text()).toContain('11 мар. 2027');
    await surface().get('form').trigger('submit');
    await flushPromises();
    expect(patchEquipment).toHaveBeenCalledWith(7, { warranty_mode: 'none', maintenance_enabled: true, maintenance_interval_months: 6 });
    expect(wrapper.emitted('saved')).toHaveLength(1);
  });

  it('requires manual warranty dates and months, then sends explicit correction', async () => {
    await open();
    await button('Указать вручную').trigger('click');
    expect(field('Начало гарантии').element).toHaveProperty('value', '2026-09-11');
    expect(button('Сохранить').attributes('disabled')).toBeDefined();
    await field('Срок гарантии').setValue(36);
    expect(surface().text()).toContain('11 сент. 2029');
    await surface().get('form').trigger('submit');
    expect(patchEquipment).toHaveBeenCalledWith(7, {
      warranty_mode: 'manual', warranty_started_at: '2026-09-11T00:00:00', warranty_duration_months: 36, warranty_terms: null,
    });
  });

  it('requires an anchor when commissioning and installation are unknown', async () => {
    await open({ ...item, commissioned_at: null });
    await field('Напоминать о ТО').setValue(true);
    expect(button('Сохранить').attributes('disabled')).toBeDefined();
    await field('Отсчитывать ТО').setValue('2026-08-31');
    expect(button('Сохранить').attributes('disabled')).toBeUndefined();
    expect(surface().text()).toContain('31 авг. 2027');
  });

  it('preserves a custom interval when toggling reminders off and on', async () => {
    await open({ ...item, maintenance_enabled: true, maintenance_interval_months: 6 });
    await field('Напоминать о ТО').setValue(false);
    await field('Напоминать о ТО').setValue(true);
    expect(field('Интервал ТО').element).toHaveProperty('value', '6');
    expect(button('Сохранить').attributes('disabled')).toBeDefined();
  });

  it('can disable a reminder even after clearing its interval input', async () => {
    await open({ ...item, maintenance_enabled: true, maintenance_interval_months: 6 });
    await field('Интервал ТО').setValue('');
    await field('Напоминать о ТО').setValue(false);
    await surface().get('form').trigger('submit');
    expect(patchEquipment).toHaveBeenCalledWith(7, { maintenance_enabled: false });
  });

  it('changes serial without resending guarantee, plan or date fields', async () => {
    await open({ ...item, warranty_mode: 'manual', warranty_duration_months: 36, warranty_started_at: '2026-09-11T15:30:00' });
    await field('Серийный номер').setValue('ABC-123');
    await surface().get('form').trigger('submit');
    expect(patchEquipment).toHaveBeenCalledWith(7, { serial: 'ABC-123' });
  });

  it('allows maintenance edits on a legacy entry identified only by serial', async () => {
    await open({ ...item, display_name: null, model: null, brand: null, serial: 'ABC-123' });
    await field('Напоминать о ТО').setValue(true);
    expect(button('Сохранить').attributes('disabled')).toBeUndefined();
    await surface().get('form').trigger('submit');
    expect(patchEquipment).toHaveBeenCalledWith(7, { maintenance_enabled: true });
  });

  it('preserves a legacy manual warranty with an exact expiry outside whole months', async () => {
    await open({ ...item, warranty_mode: 'manual', warranty_started_at: '2026-09-11T00:00:00', warranty_expires_at: '2027-09-30T00:00:00', warranty_duration_months: null });
    await field('Серийный номер').setValue('ABC-123');
    expect(surface().text()).toContain('30 сент. 2027');
    expect(button('Сохранить').attributes('disabled')).toBeUndefined();
    await surface().get('form').trigger('submit');
    expect(patchEquipment).toHaveBeenCalledWith(7, { serial: 'ABC-123' });
  });

  it('retains edits after save fails and allows retry', async () => {
    patchEquipment.mockRejectedValueOnce(new Error('Сохранение недоступно'));
    const wrapper = await open();
    await field('Серийный номер').setValue('ABC-123');
    await surface().get('form').trigger('submit');
    await flushPromises();
    expect(surface().get('[role="alert"]').text()).toContain('Сохранение недоступно');
    expect(field('Серийный номер').element).toHaveProperty('value', 'ABC-123');
    expect(wrapper.emitted('saved')).toBeUndefined();
    await surface().get('form').trigger('submit');
    await flushPromises();
    expect(wrapper.emitted('saved')).toHaveLength(1);
  });

  it('ignores stale detail replies after another equipment is selected', async () => {
    let resolveFirst!: (data: ManagerEquipmentDetailResponse) => void;
    getEquipment.mockImplementationOnce(() => new Promise((resolve) => { resolveFirst = resolve; }));
    const wrapper = mount(EquipmentEditDialog, { props: { equipmentId: 7 }, attachTo: document.body });
    mounted.push(wrapper);
    getEquipment.mockResolvedValueOnce({ ...item, id: 8, display_name: 'Другое оборудование' });
    await wrapper.setProps({ equipmentId: 8 });
    await flushPromises();
    resolveFirst(item);
    await flushPromises();
    expect(field('Название').element).toHaveProperty('value', 'Другое оборудование');
  });

  it('opens editing from both desktop rows and mobile cards', async () => {
    for (const component of [EquipmentRegistryTable, EquipmentRegistryCards]) {
      const wrapper = mount(component, { props: { items: [item] } });
      mounted.push(wrapper);
      await wrapper.get('[aria-label="Изменить: MDV FOREST"]').trigger('click');
      expect(wrapper.emitted('edit')?.[0]?.[0]).toEqual(item);
    }
  });
});

describe('equipment presentation and dates', () => {
  it('marks explicit no warranty without asking to clarify and removes repeated titles', () => {
    const wrapper = mount(EquipmentAttentionBadges, { props: { reasons: [], warrantyStatus: 'none', warrantyMode: 'none' } });
    mounted.push(wrapper);
    expect(wrapper.text()).toBe('Без гарантии');
    expect(equipmentWarrantyDate({ ...item, warranty_mode: 'none' })).toBe('Без гарантии');
    expect(equipmentSubtitle(item)).toBe('');
  });

  it('clamps month ends and uses actual maintenance after the configured anchor', () => {
    expect(addCalendarMonths('2024-02-29', 12)).toBe('2025-02-28');
    expect(addCalendarMonths('2026-08-31', 6)).toBe('2027-02-28');
    const initial = equipmentEditForm({ ...item, maintenance_enabled: true, maintenance_interval_months: 6 });
    expect(maintenancePreview(initial, '2026-10-31T10:00:00')).toBe('2027-04-30');
    expect(maintenancePreview(initial, '2026-08-31T10:00:00')).toBe('2027-03-11');
    expect(equipmentEditPayload(initial, { ...initial })).toEqual({});
  });
});
