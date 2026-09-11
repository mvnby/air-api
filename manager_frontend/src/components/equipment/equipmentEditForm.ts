import type { ManagerEquipmentDetailResponse, ManagerEquipmentUpdatePayload } from '../../client';

export const dateInput = (value?: string | null) => value?.slice(0, 10) || '';
const timestamp = (value: string) => value ? `${value}T00:00:00` : null;

export function addCalendarMonths(value: string, months: number): string {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value) || !Number.isInteger(months) || months < 1) return '';
  const [year, month, day] = value.split('-').map(Number) as [number, number, number];
  const date = new Date(Date.UTC(year, month - 1 + months, 1));
  const lastDay = new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth() + 1, 0)).getUTCDate();
  date.setUTCDate(Math.min(day, lastDay));
  return date.toISOString().slice(0, 10);
}

export function equipmentEditForm(item: ManagerEquipmentDetailResponse) {
  return {
    displayName: item.display_name || '',
    brand: item.brand || '',
    model: item.model || '',
    serial: item.serial || '',
    inventoryNumber: item.inventory_number || '',
    locationHint: item.location_hint || '',
    source: item.equipment_source || 'unknown',
    installedAt: dateInput(item.installed_at),
    commissionedAt: dateInput(item.commissioned_at),
    warrantyMode: item.warranty_mode || 'auto',
    warrantyStart: dateInput(item.warranty_started_at),
    warrantyMonths: (item.warranty_duration_months ?? '') as number | string,
    warrantyTerms: item.warranty_terms || '',
    maintenanceEnabled: item.maintenance_enabled ?? false,
    maintenanceMonths: (item.maintenance_interval_months ?? 12) as number | string,
    maintenanceAnchor: dateInput(item.maintenance_anchor_at),
    notes: item.notes || '',
  };
}

export type EquipmentEditForm = ReturnType<typeof equipmentEditForm>;

export function maintenancePreview(form: EquipmentEditForm, lastService?: string | null) {
  if (!form.maintenanceEnabled) return '';
  const anchor = form.maintenanceAnchor || form.commissionedAt || form.installedAt;
  if (!anchor) return '';
  const service = dateInput(lastService);
  return addCalendarMonths(service > anchor ? service : anchor, Number(form.maintenanceMonths));
}

const warrantyChanged = (form: EquipmentEditForm, initial: EquipmentEditForm) => (
  form.warrantyMode !== initial.warrantyMode || (
    form.warrantyMode === 'manual' && (form.warrantyStart !== initial.warrantyStart
      || String(form.warrantyMonths) !== String(initial.warrantyMonths) || form.warrantyTerms !== initial.warrantyTerms)
  )
);

export function equipmentEditError(form: EquipmentEditForm, initial?: EquipmentEditForm | null) {
  if (form.warrantyMode === 'manual' && (!initial || warrantyChanged(form, initial))) {
    if (!form.warrantyStart) return 'Укажите дату начала гарантии.';
    if (!Number.isInteger(Number(form.warrantyMonths)) || Number(form.warrantyMonths) < 1 || Number(form.warrantyMonths) > 240) {
      return 'Срок гарантии — от 1 до 240 месяцев.';
    }
  }
  if (form.maintenanceEnabled) {
    if (!Number.isInteger(Number(form.maintenanceMonths)) || Number(form.maintenanceMonths) < 1 || Number(form.maintenanceMonths) > 120) {
      return 'Интервал ТО — от 1 до 120 месяцев.';
    }
    if (!form.maintenanceAnchor && !form.commissionedAt && !form.installedAt) {
      return 'Укажите дату ввода в эксплуатацию или дату отсчёта ТО.';
    }
  }
  return '';
}

export function equipmentEditPayload(form: EquipmentEditForm, initial: EquipmentEditForm): ManagerEquipmentUpdatePayload {
  const payload: ManagerEquipmentUpdatePayload = {};
  const textFields = {
    displayName: 'display_name', brand: 'brand', model: 'model', serial: 'serial',
    inventoryNumber: 'inventory_number', locationHint: 'location_hint', source: 'equipment_source', notes: 'notes',
  } as const;
  for (const [key, field] of Object.entries(textFields)) {
    const value = form[key as keyof typeof textFields];
    if (value !== initial[key as keyof typeof textFields]) payload[field] = value.trim() || null;
  }
  for (const [key, field] of [['installedAt', 'installed_at'], ['commissionedAt', 'commissioned_at']] as const) {
    if (form[key] !== initial[key]) payload[field] = timestamp(form[key]);
  }
  if (warrantyChanged(form, initial)) {
    payload.warranty_mode = form.warrantyMode;
    if (form.warrantyMode === 'manual') {
      payload.warranty_started_at = timestamp(form.warrantyStart);
      payload.warranty_duration_months = Number(form.warrantyMonths);
      payload.warranty_terms = form.warrantyTerms.trim() || null;
    }
  }
  if (form.maintenanceEnabled !== initial.maintenanceEnabled) payload.maintenance_enabled = form.maintenanceEnabled;
  const interval = Number(form.maintenanceMonths);
  if (String(form.maintenanceMonths) !== String(initial.maintenanceMonths)
    && Number.isInteger(interval) && interval >= 1 && interval <= 120) payload.maintenance_interval_months = interval;
  if (form.maintenanceAnchor !== initial.maintenanceAnchor) payload.maintenance_anchor_at = timestamp(form.maintenanceAnchor);
  return payload;
}
