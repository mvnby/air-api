import { normalizeRepairMeta } from '../../../components/orders/repair-meta';
import type { ManagerOrderDetailResponse, RepairDefect } from '../../../client';

export const REPAIR_DEFECT_DOCUMENT = { value: 'repair_defect_act', label: 'Дефектный акт ремонта' } as const;

export const repairVerdicts = [
  { value: 'repairable', label: 'Подлежит ремонту' },
  { value: 'uneconomical', label: 'Ремонт нецелесообразен' },
  { value: 'not_repairable', label: 'Не подлежит ремонту' },
  { value: 'needs_diagnostics', label: 'Нужна доп. диагностика' },
  { value: 'operational', label: 'Оборудование исправно' },
] as const satisfies ReadonlyArray<{ value: RepairDefect['verdict']; label: string }>;

export type RepairDefectForm = Omit<RepairDefect, 'verdict'> & { verdict: RepairDefect['verdict'] | '' };

const text = (raw: unknown) => typeof raw === 'string' ? raw.trim() : '';
const joined = (items: unknown[]) => [...new Set(items.map(text).filter(Boolean))].join(' ');
const facts = (raw: unknown) => Array.isArray(raw) ? raw.map(text).filter(Boolean) : [];

export function repairOrderSuggestions(order?: ManagerOrderDetailResponse) {
  const meta = normalizeRepairMeta(order?.repair_meta);
  const models = facts(meta.equipment_models);
  const equipment = joined([
    meta.equipment_name, meta.equipment_brand, meta.equipment_model || (models.length === 1 ? models[0] : ''),
    text(meta.equipment_serial_number) && `S/N ${text(meta.equipment_serial_number)}`,
    text(meta.equipment_inventory_number) && `инв. № ${text(meta.equipment_inventory_number)}`,
  ]);
  // Legacy templates and bot-assisted notes may contain unverified prose. Only an
  // explicit manager action can copy those excerpts into the customer document.
  const savedFinding = [text(meta.diagnostic_result), ...facts(meta.confirmed_facts), ...facts(meta.structured_diagnosis?.confirmed_facts)]
    .find(item => item && item.length <= 320) || '';
  const multipleUnits = models.length > 1 || (order?.linked_equipment_count || 0) > 1;
  return {
    equipment: multipleUnits ? '' : equipment,
    savedFinding: multipleUnits ? '' : savedFinding,
    savedRecommendation: multipleUnits ? '' : text(meta.repair_recommendation),
  };
}

export function newRepairDefectForm(order?: ManagerOrderDetailResponse): RepairDefectForm {
  const defaults = repairOrderSuggestions(order);
  return {
    verdict: '', equipment: defaults.equipment,
    finding: '',
    recommendation: '', cost: null, term: null, restriction: null,
  };
}

export function repairDefectFormError(form: RepairDefectForm) {
  if (!form.verdict) return 'Выберите вывод по оборудованию';
  if (!form.equipment.trim()) return 'Укажите оборудование для акта';
  if (!form.finding.trim()) return 'Кратко укажите, что установлено';
  if (!form.recommendation.trim()) return 'Укажите, что делать дальше';
  if (form.equipment.length > 250 || form.finding.length > 320 || form.recommendation.length > 320
    || (form.cost?.length || 0) > 120 || (form.term?.length || 0) > 120 || (form.restriction?.length || 0) > 180)
    return 'Сократите название до 250 символов, вывод и рекомендацию до 320, цену и срок до 120, ограничение до 180';
  return '';
}

export const repairDefectPayload = (form: RepairDefectForm) => form.verdict ? {
  verdict: form.verdict,
  equipment: form.equipment.trim(), finding: form.finding.trim(), recommendation: form.recommendation.trim(),
  cost: form.cost?.trim() || null, term: form.term?.trim() || null, restriction: form.restriction?.trim() || null,
} : undefined;
