import type { OrderCustomerBrief } from '../../../client';

const BUSINESS_DOCUMENT_TYPES = new Set([
  'contract',
  'invoice',
  'service_act',
  'maintenance_service_act',
  'act',
  'defect_act',
  'tn2',
  'ttn1',
]);

const LEGAL_ADDRESS_DOCUMENT_TYPES = new Set([
  'contract',
  'service_act',
  'maintenance_service_act',
  'act',
  'defect_act',
  'tn2',
  'ttn1',
]);

const present = (value: unknown) => Boolean(String(value || '').trim());

export const getCustomerDocumentWarnings = (
  customer: OrderCustomerBrief | null | undefined,
  documentType: string,
): string[] => {
  if (!customer || !BUSINESS_DOCUMENT_TYPES.has(documentType)) return [];

  const isBusiness = customer.type === 'company'
    || customer.type === 'individual_entrepreneur'
    || present(customer.inn);
  if (!isBusiness) return [];

  const warnings: string[] = [];
  if (!present(customer.full_legal_name)) warnings.push('полное наименование');
  if (!present(customer.inn)) warnings.push('УНП');
  if (LEGAL_ADDRESS_DOCUMENT_TYPES.has(documentType) && !present(customer.legal_address)) {
    warnings.push('юридический адрес');
  }
  if (documentType === 'contract' && customer.type === 'company') {
    if (!present(customer.signer_name)) warnings.push('ФИО подписанта');
    if (!present(customer.signer_position)) warnings.push('должность подписанта');
    if (!present(customer.acting_basis)) warnings.push('основание полномочий');
  }
  return warnings;
};
