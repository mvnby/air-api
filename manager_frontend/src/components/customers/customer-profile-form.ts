import { normalizeIban, normalizeUnp } from '../../utils/legal-requisites';
import { normalizePhoneForApi } from '../../utils/phone';
import { normalizeEmail } from '../../utils/validation';

export type CustomerForm = {
  name: string;
  phone: string;
  email: string;
  type: 'individual' | 'company';
  inn: string;
  kpp: string;
  full_legal_name: string;
  legal_address: string;
  actual_address: string;
  bank_name: string;
  bic: string;
  iban: string;
  signer_position: string;
  signer_name: string;
  acting_basis: string;
};

type CustomerFormDiff = Partial<Record<keyof CustomerForm, boolean>>;

const normalizers: Partial<Record<keyof CustomerForm, (value: string) => string>> = {
  phone: normalizePhoneForApi,
  email: normalizeEmail,
  inn: normalizeUnp,
  iban: normalizeIban,
};

export const buildCustomerPatchPayload = (
  form: CustomerForm,
  diff: CustomerFormDiff,
): Record<string, string> => {
  const payload: Record<string, string> = {};

  (Object.keys(diff) as (keyof CustomerForm)[]).forEach((key) => {
    if (!diff[key]) return;
    const trimmed = String(form[key] ?? '').trim();
    payload[key] = normalizers[key]?.(trimmed) ?? trimmed;
  });

  return payload;
};
