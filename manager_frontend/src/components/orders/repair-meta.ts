import type { EquipmentServiceEventType } from '../../client';

export type RepairMeta = {
  repair_status: string;
  customer_approval_status: string;
  customer_approval_note: string;
  parts_status: string;
  parts_note: string;
  repair_completion_note: string;
  customer_complaint: string;
  complaint_official: string;
  complaint_text?: string;
  likely_diagnosis: string;
  fault_type: string;
  fault_location: string;
  operation_status: string;
  diagnostic_notes: string;
  equipment_name: string;
  equipment_brand: string;
  equipment_model: string;
  equipment_power: string;
  equipment_serial_number: string;
  equipment_inventory_number: string;
  equipment_commissioning_date: string;
  technical_condition: string;
  startup_check_result: string;
  compressor_check_result: string;
  measurement_result: string;
  diagnostic_result: string;
  further_use_assessment: string;
  operation_restrictions: string;
  technical_conclusion: string;
  repair_feasibility: string;
  recommended_decision: string;
  repair_recommendation: string;
  repair_possible: string;
  refrigerant_type: string;
  refrigerant_amount: string;
  refrigerant_pricing_mode: string;
  repair_not_viable: string;
  repair_not_viable_reason: string;
  repair_estimate_text: string;
  risks?: string[];
  recommended_actions?: string[];
  hidden_defects_possible?: boolean;
  structured_diagnosis?: Record<string, any>;
  defect_act_blocks?: Record<string, string>;
};

export type RepairAiDefectType = {
  value: string;
  label: string;
  hint: string;
};

export const REPAIR_WORKFLOW_STATUS_OPTIONS = [
  { value: 'new', label: 'Новая' },
  { value: 'scheduled', label: 'Запланирован' },
  { value: 'diagnostic_in_progress', label: 'Диагностика идет' },
  { value: 'awaiting_diagnostic_result', label: 'Ждем диагностику' },
  { value: 'awaiting_customer_approval', label: 'На согласовании' },
  { value: 'approved_for_repair', label: 'Ремонт согласован' },
  { value: 'repair_in_progress', label: 'Ремонт идет' },
  { value: 'awaiting_parts', label: 'Ждем запчасти' },
  { value: 'completed', label: 'Завершен' },
  { value: 'not_repairable', label: 'Не ремонтируется' },
  { value: 'cancelled', label: 'Отменен' },
];
const REPAIR_WORKFLOW_STATUS_VALUES = new Set(REPAIR_WORKFLOW_STATUS_OPTIONS.map((item) => item.value));

export const CUSTOMER_APPROVAL_STATUS_OPTIONS = [
  { value: '', label: 'Не указано' },
  { value: 'pending', label: 'Ожидает согласования' },
  { value: 'approved', label: 'Согласовано' },
  { value: 'rejected', label: 'Отказано' },
];

export const PARTS_STATUS_OPTIONS = [
  { value: '', label: 'Не указано' },
  { value: 'not_required', label: 'Не требуются' },
  { value: 'awaiting', label: 'Ожидаются' },
  { value: 'ordered', label: 'Заказаны' },
  { value: 'received', label: 'Получены' },
  { value: 'installed', label: 'Установлены' },
];

export const emptyRepairMeta = (): RepairMeta => ({
  repair_status: '',
  customer_approval_status: '',
  customer_approval_note: '',
  parts_status: '',
  parts_note: '',
  repair_completion_note: '',
  customer_complaint: '',
  complaint_official: '',
  likely_diagnosis: '',
  fault_type: '',
  fault_location: '',
  operation_status: '',
  diagnostic_notes: '',
  equipment_name: '',
  equipment_brand: '',
  equipment_model: '',
  equipment_power: '',
  equipment_serial_number: '',
  equipment_inventory_number: '',
  equipment_commissioning_date: '',
  technical_condition: '',
  startup_check_result: '',
  compressor_check_result: '',
  measurement_result: '',
  diagnostic_result: '',
  further_use_assessment: '',
  operation_restrictions: '',
  technical_conclusion: '',
  repair_feasibility: '',
  recommended_decision: '',
  repair_recommendation: '',
  repair_possible: '',
  refrigerant_type: '',
  refrigerant_amount: '',
  refrigerant_pricing_mode: '',
  repair_not_viable: '',
  repair_not_viable_reason: '',
  repair_estimate_text: '',
  risks: [],
  recommended_actions: [],
  hidden_defects_possible: false,
  structured_diagnosis: {},
  defect_act_blocks: {},
});

export const REPAIR_CHOICE_OPTIONS = ['', 'Да', 'Нет'];
export const REFRIGERANT_PRICING_MODE_OPTIONS = [
  'по фактической массе',
  'включен в стоимость ремонта',
  'отдельной строкой сметы',
  'не требуется',
];
export const EQUIPMENT_EVENT_OPTIONS: Array<{ value: EquipmentServiceEventType; label: string }> = [
  { value: 'diagnostic', label: 'Диагностика' },
  { value: 'repair', label: 'Ремонт' },
  { value: 'maintenance', label: 'Обслуживание' },
  { value: 'refrigerant_charge', label: 'Заправка хладагентом' },
  { value: 'leak', label: 'Утечка' },
  { value: 'recommendation', label: 'Рекомендация' },
  { value: 'not_repairable', label: 'Не ремонтируется' },
  { value: 'other', label: 'Другое' },
];

export const REPAIR_AI_DEFECT_TYPES: RepairAiDefectType[] = [
  {
    value: 'refrigerant_leak',
    label: 'Утечка хладагента',
    hint: 'падение производительности, обмерзание, требуется поиск и устранение утечки',
  },
  {
    value: 'drainage_failure',
    label: 'Нарушение отвода конденсата',
    hint: 'протечка воды, засор или неправильный уклон дренажа',
  },
  {
    value: 'control_board_failure',
    label: 'Неисправность платы управления',
    hint: 'ошибки управления, нестабильная работа, отсутствие запуска',
  },
  {
    value: 'fan_motor_failure',
    label: 'Неисправность двигателя вентилятора',
    hint: 'шум, отсутствие вращения, перегрев, ошибка вентилятора',
  },
  {
    value: 'compressor_failure',
    label: 'Неисправность компрессора',
    hint: 'электрическая или механическая неисправность компрессора, срабатывание защиты',
  },
  {
    value: 'heat_exchanger_damage',
    label: 'Повреждение теплообменника',
    hint: 'коррозия, механические повреждения, нарушение теплообмена',
  },
  {
    value: 'contamination',
    label: 'Загрязнение оборудования',
    hint: 'загрязнение теплообменника, фильтров или внутренних узлов',
  },
  {
    value: 'poor_installation',
    label: 'Нарушение монтажа',
    hint: 'ошибки трассы, дренажа, подключения или установки блоков',
  },
  {
    value: 'unknown_fault',
    label: 'Требуется уточнение',
    hint: 'причина не подтверждена, нужна дополнительная диагностика',
  },
];

export const textValue = (value: unknown) => String(value ?? '').trim();

const normalizeRepairWorkflowStatus = (value: unknown) => {
  const raw = textValue(value);
  const normalized = raw.toLowerCase().replace(/-/g, '_').split(/\s+/).filter(Boolean).join('_');
  return REPAIR_WORKFLOW_STATUS_VALUES.has(normalized) ? normalized : '';
};

const choiceText = (value: unknown) => {
  if (typeof value === 'boolean') return value ? 'Да' : 'Нет';
  return textValue(value);
};

const isExplicitNegativeRepairText = (value: unknown) => {
  const text = textValue(value).toLowerCase();
  if (!text) return false;
  return [
    'невозмож',
    'не возмож',
    'нецелесообраз',
    'не целесообраз',
    'нерентаб',
    'не рентаб',
    'списан',
    'списани',
    'вывести из эксплуатации',
  ].some((marker) => text.includes(marker));
};

export const normalizeRepairMeta = (
  raw: Partial<RepairMeta> | Record<string, any> | null | undefined,
  options: { defaultRepairStatus?: boolean } = {},
): RepairMeta => {
  const meta = { ...emptyRepairMeta(), ...((raw || {}) as Partial<RepairMeta>) };
  meta.repair_status = normalizeRepairWorkflowStatus(meta.repair_status) || (options.defaultRepairStatus ? 'new' : '');
  meta.customer_approval_status = textValue(meta.customer_approval_status);
  meta.customer_approval_note = textValue(meta.customer_approval_note);
  meta.parts_status = textValue(meta.parts_status);
  meta.parts_note = textValue(meta.parts_note);
  meta.repair_completion_note = textValue(meta.repair_completion_note);
  if (!textValue(meta.customer_complaint)) {
    meta.customer_complaint = textValue(meta.complaint_official) || textValue(meta.complaint_text);
  }
  if (!textValue(meta.diagnostic_result)) {
    meta.diagnostic_result = textValue(meta.measurement_result);
  }
  if (!textValue(meta.repair_recommendation)) {
    meta.repair_recommendation = textValue(meta.recommended_decision) || textValue(meta.technical_conclusion);
  }
  meta.repair_possible = choiceText(meta.repair_possible);
  meta.repair_not_viable = choiceText(meta.repair_not_viable);
  const legacyFeasibility = textValue(meta.repair_feasibility);
  if (legacyFeasibility && isExplicitNegativeRepairText(legacyFeasibility)) {
    if (!textValue(meta.repair_not_viable)) meta.repair_not_viable = 'Да';
    if (!textValue(meta.repair_not_viable_reason)) meta.repair_not_viable_reason = legacyFeasibility;
  }
  return meta;
};

export const selectOptionsWithCurrent = (baseOptions: string[], current: unknown) => {
  const currentValue = textValue(current);
  if (!currentValue || baseOptions.includes(currentValue)) return baseOptions;
  return [...baseOptions, currentValue];
};

export const labeledOptionsWithCurrent = (baseOptions: Array<{ value: string; label: string }>, current: unknown) => {
  const currentValue = textValue(current);
  if (!currentValue || baseOptions.some((item) => item.value === currentValue)) return baseOptions;
  return [...baseOptions, { value: currentValue, label: currentValue }];
};
