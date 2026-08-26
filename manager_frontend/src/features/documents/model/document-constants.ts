import type { DocumentRoleType } from './document-types';

export const DOCUMENT_FILE_ACCEPT = '.pdf,.doc,.docx,application/pdf,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document';
export const OPEN_CONTRACT_PREFIX = 'open:';
export const ORDER_DOCUMENT_PREFIX = 'doc:';
export const BASE_DOCUMENT_TYPES = new Set(['offer', 'contract', 'invoice']);
export const CLOSING_DOCUMENT_TYPES = new Set(['act', 'tn2', 'ttn1']);

export const DOCUMENT_TYPES = [
  { type: 'contract', label: 'Договор' },
  { type: 'invoice', label: 'Счет' },
  { type: 'retail_receipt', label: 'Товарный чек' },
  { type: 'service_act', label: 'Заказ-акт' },
  { type: 'maintenance_service_act', label: 'Заказ-акт ТО' },
  { type: 'warranty_certificate', label: 'Гарантийный талон' },
  { type: 'act', label: 'Акт' },
  { type: 'defect_act', label: 'Дефектный акт' },
  { type: 'offer', label: 'КП' },
  { type: 'tn2', label: 'ТН-2' },
  { type: 'ttn1', label: 'ТТН-1' },
] as const;

export const DOCUMENT_ROLE_OPTIONS: Array<{ value: DocumentRoleType; label: string }> = [
  { value: 'seller_buyer', label: 'Продавец / Покупатель' },
  { value: 'executor_customer', label: 'Исполнитель / Заказчик' },
  { value: 'contractor_customer', label: 'Подрядчик / Заказчик' },
];

export const DATED_DOCUMENT_TYPES = new Set([
  'contract',
  'retail_receipt',
  'service_act',
  'maintenance_service_act',
  'warranty_certificate',
  'act',
  'defect_act',
  'tn2',
  'ttn1',
]);
