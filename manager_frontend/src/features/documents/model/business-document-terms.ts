export const CONTRACT_SCENARIOS = [
  { value: 'supply', label: 'Поставка оборудования', note: 'Без монтажных работ' },
  { value: 'supply_installation', label: 'Поставка с монтажом', note: 'Оборудование и работы под ключ' },
  { value: 'installation', label: 'Монтаж', note: 'В том числе оборудования заказчика' },
  { value: 'services', label: 'Оказание услуг', note: 'Отдельные согласованные услуги' },
  { value: 'maintenance', label: 'Техническое обслуживание', note: 'Регламентные работы без ремонта' },
  { value: 'repair', label: 'Диагностика и ремонт', note: 'Ремонт и необходимые запчасти' },
  { value: 'framework', label: 'Рамочный договор', note: 'Для повторяющихся работ и поставок' },
] as const;

export type ContractScenario = typeof CONTRACT_SCENARIOS[number]['value'];
export type PaymentDueEvent = 'before_supply' | 'before_work' | 'after_supply' | 'after_work' | 'after_acceptance';
export type PaymentDayKind = 'calendar' | 'banking';

export type PaymentScheduleItem = {
  share_percent: number;
  due_event: PaymentDueEvent;
  due_days: number | null;
  due_day_kind: PaymentDayKind;
  note: string | null;
};

export type BusinessDocumentTerms = {
  contract_scenario: ContractScenario | null;
  subject: string | null;
  delivery_deadline: string | null;
  performance_deadline: string | null;
  valid_until: string | null;
  additional_conditions: string | null;
  additional_conditions_overridden: boolean;
  payment_schedule: PaymentScheduleItem[];
  goods_warranty_months: number | null;
  goods_warranty_terms: string | null;
  work_warranty_months: number | null;
  work_warranty_terms: string | null;
};

export const BUSINESS_TERMS_DOCUMENT_TYPES = new Set(['contract', 'offer', 'invoice', 'act']);

export const isBusinessTermsDocumentType = (documentType: string) => (
  BUSINESS_TERMS_DOCUMENT_TYPES.has(documentType)
);

export const createDefaultBusinessDocumentTerms = (): BusinessDocumentTerms => ({
  contract_scenario: null,
  subject: null,
  delivery_deadline: null,
  performance_deadline: null,
  valid_until: null,
  additional_conditions: null,
  additional_conditions_overridden: false,
  payment_schedule: [{ share_percent: 100, due_event: 'before_supply', due_days: null, due_day_kind: 'banking', note: null }],
  goods_warranty_months: null,
  goods_warranty_terms: null,
  work_warranty_months: null,
  work_warranty_terms: null,
});

const picked = <T extends readonly (keyof BusinessDocumentTerms)[]>(
  terms: BusinessDocumentTerms,
  keys: T,
) => Object.fromEntries(keys.map((key) => [key, terms[key]])) as Pick<BusinessDocumentTerms, T[number]>;

/**
 * The draft only carries clauses meaningful for the selected document type.
 * Other form facts stay in local state, so changing type does not discard a
 * manager's work and cannot leak an incompatible clause into a document.
 */
export const serializeBusinessTerms = (
  documentType: string,
  terms: BusinessDocumentTerms,
) => {
  if (documentType === 'contract') return { ...terms };
  if (documentType === 'offer' || documentType === 'invoice') {
    return picked(terms, [
      'subject',
      'delivery_deadline',
      'performance_deadline',
      'additional_conditions',
      'additional_conditions_overridden',
      'payment_schedule',
    ]);
  }
  if (documentType === 'act') {
    return picked(terms, [
      'additional_conditions',
      'additional_conditions_overridden',
      'goods_warranty_months',
      'goods_warranty_terms',
      'work_warranty_months',
      'work_warranty_terms',
    ]);
  }
  return undefined;
};

export const businessTermsValidationError = (
  documentType: string,
  terms: BusinessDocumentTerms,
) => {
  if (documentType === 'contract' && !terms.contract_scenario) return 'Выберите сценарий договора';
  if (documentType === 'contract' && terms.contract_scenario === 'framework' && !terms.valid_until) {
    return 'Для рамочного договора укажите срок действия';
  }
  if (['contract', 'offer', 'invoice'].includes(documentType)) {
    const total = terms.payment_schedule.reduce((sum, item) => sum + item.share_percent, 0);
    if (!terms.payment_schedule.length || Math.abs(total - 100) > 0.001) {
      return 'График оплаты должен составлять ровно 100%';
    }
    if (terms.payment_schedule.some((item) => item.share_percent <= 0 || item.share_percent > 100)) {
      return 'Доля каждого платежа должна быть больше 0 и не больше 100%';
    }
    if (terms.payment_schedule.some((item) => item.due_days !== null && (item.due_days < 1 || item.due_days > 3650))) {
      return 'Количество дней для оплаты должно быть от 1 до 3650';
    }
  }
  if (terms.goods_warranty_terms && terms.goods_warranty_months === null) {
    return 'Для гарантии на оборудование укажите срок';
  }
  if (terms.goods_warranty_months !== null && (terms.goods_warranty_months < 0 || terms.goods_warranty_months > 240)) {
    return 'Срок гарантии на оборудование должен быть от 0 до 240 месяцев';
  }
  if (terms.work_warranty_terms && terms.work_warranty_months === null) {
    return 'Для гарантии на работы укажите срок';
  }
  if (terms.work_warranty_months !== null && (terms.work_warranty_months < 0 || terms.work_warranty_months > 240)) {
    return 'Срок гарантии на работы должен быть от 0 до 240 месяцев';
  }
  return '';
};
