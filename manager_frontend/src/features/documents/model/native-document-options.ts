import type { ManagedDocumentItem } from '../../../client';

export const BUSINESS_NATIVE_DOCUMENT_TYPES = [
  { value: 'offer', label: 'Коммерческое предложение' },
  { value: 'invoice', label: 'Счёт' },
  { value: 'contract', label: 'Договор' },
  { value: 'act', label: 'Акт' },
  { value: 'tn2', label: 'Товарная накладная ТН-2' },
  { value: 'ttn1', label: 'Товарно-транспортная ТТН-1' },
] as const;

export const CONSUMER_NATIVE_DOCUMENT_TYPES = [
  { value: 'b2c_supply_installation_act', label: 'Заказ-акт: продажа с монтажом' },
  { value: 'b2c_customer_equipment_installation_act', label: 'Заказ-акт: монтаж оборудования клиента' },
  { value: 'b2c_maintenance_repair_act', label: 'Заказ-акт: обслуживание и ремонт' },
  { value: 'b2c_route_laying_act', label: 'Заказ-акт: закладка трассы' },
] as const;

export const NATIVE_DOCUMENT_TYPES = [
  ...BUSINESS_NATIVE_DOCUMENT_TYPES,
  ...CONSUMER_NATIVE_DOCUMENT_TYPES,
] as const;

export const NUMBER_POLICY_TYPES = [
  ...NATIVE_DOCUMENT_TYPES,
  { value: 'invoice_offer', label: 'Счёт-оферта' },
] as const;

export const NUMBER_PERIODS = [
  { value: 'calendar_year', label: 'Каждый год с начала' },
  { value: 'continuous', label: 'Без сброса' },
  { value: 'per_basis', label: 'Отдельно по каждому основанию' },
] as const;

export const documentTypeName = (value: string) => (
  NUMBER_POLICY_TYPES.find((item) => item.value === value)?.label || value
);

export const managedDocumentStatus = (value: string) => ({
  draft: 'Черновик',
  issued: 'Выпущен',
  sent: 'Отправлен',
  signed: 'Подписан',
  void: 'Аннулирован',
  replaced: 'Заменён',
}[value] || value);

export const managedDocumentStatusClass = (value: string) => ({
  draft: 'bg-amber-100 text-amber-800 dark:bg-amber-950/50 dark:text-amber-300',
  issued: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-950/50 dark:text-emerald-300',
  sent: 'bg-blue-100 text-blue-800 dark:bg-blue-950/50 dark:text-blue-300',
  signed: 'bg-teal-100 text-teal-800 dark:bg-teal-950/50 dark:text-teal-300',
  void: 'bg-rose-100 text-rose-800 dark:bg-rose-950/50 dark:text-rose-300',
  replaced: 'bg-slate-200 text-slate-700 dark:bg-slate-800 dark:text-slate-300',
}[value] || 'bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300');

export const officialDocumentTitle = (document: ManagedDocumentItem) => {
  const kind = document.doc_type === 'invoice' && document.business_role === 'offer'
    ? 'Счёт-оферта'
    : documentTypeName(document.doc_type);
  return `${kind} № ${document.display_number}`;
};
