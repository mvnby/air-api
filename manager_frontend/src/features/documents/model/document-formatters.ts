import type { ManagerOrderDocumentItem } from '../../../client';
import { CLOSING_DOCUMENT_TYPES, DOCUMENT_ROLE_OPTIONS, DOCUMENT_TYPES } from './document-constants';
import type { DocumentRoleType } from './document-types';

export const formatMoney = (value: number | null | undefined) => `${Number(value || 0).toLocaleString('ru-RU')} BYN`;

export const normalizeRoleType = (value: unknown): DocumentRoleType => {
  const raw = String(value || '').trim();
  if (raw === 'executor_customer' || raw === 'contractor_customer') return raw;
  return 'seller_buyer';
};

export const getRoleLabel = (value?: string | null) => (
  DOCUMENT_ROLE_OPTIONS.find((option) => option.value === normalizeRoleType(value))?.label || 'Продавец / Покупатель'
);

export const isWaybillType = (type: string) => type === 'tn2' || type === 'ttn1';
export const isClosingDocumentType = (type: string) => CLOSING_DOCUMENT_TYPES.has(type);
export const documentTypeLabel = (type?: string | null) => DOCUMENT_TYPES.find((item) => item.type === type)?.label || type || 'Документ';

export const documentScopeLabel = (doc: ManagerOrderDocumentItem) => {
  const title = String(doc.scope_title || '').trim();
  const address = String(doc.scope_address || '').trim();
  return [title, address].filter(Boolean).join(' · ');
};
