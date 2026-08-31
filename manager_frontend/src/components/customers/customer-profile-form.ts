import type { ManagerCustomerUpdatePayload } from '../../client';
import { normalizeIban, normalizeUnp } from '../../utils/legal-requisites';
import { normalizePhoneForApi } from '../../utils/phone';
import {
  normalizeEmail,
  validateOptionalBelarusPhone,
  validateOptionalByIban,
  validateOptionalByUnp,
  validateOptionalEmail,
} from '../../utils/validation';

export type CustomerPartyType = 'individual' | 'individual_entrepreneur' | 'company';
export type CustomerSigningMode = 'self' | 'statutory_body' | 'power_of_attorney';

export type CustomerForm = {
  name: string;
  phone: string;
  email: string;
  type: CustomerPartyType;
  city: string;
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
  signing_mode: CustomerSigningMode;
};

type CustomerFormDiff = Partial<Record<keyof CustomerForm, boolean>>;

export type CustomerProfileValidation = {
  valid: boolean;
  fieldErrors: Partial<Record<keyof CustomerForm, string>>;
  phoneError: string;
  emailError: string;
  innError: string;
  ibanError: string;
};

const normalizers: Partial<Record<keyof CustomerForm, (value: string) => string>> = {
  phone: normalizePhoneForApi,
  email: normalizeEmail,
  inn: normalizeUnp,
  iban: normalizeIban,
};

export const buildCustomerPatchPayload = (
  form: CustomerForm,
  diff: CustomerFormDiff,
): ManagerCustomerUpdatePayload => {
  const payload: ManagerCustomerUpdatePayload = {};

  (Object.keys(diff) as (keyof CustomerForm)[]).forEach((key) => {
    if (!diff[key]) return;
    const trimmed = String(form[key] ?? '').trim();
    Object.assign(payload, { [key]: normalizers[key]?.(trimmed) ?? trimmed });
  });

  return payload;
};

export const validateCustomerProfileForm = (
  form: CustomerForm,
  phoneMaskComplete: boolean,
): CustomerProfileValidation => {
  const fieldErrors: Partial<Record<keyof CustomerForm, string>> = {};
  const phoneError = validateOptionalBelarusPhone(form.phone || '', phoneMaskComplete);
  const emailError = validateOptionalEmail(form.email || '');
  const innError = validateOptionalByUnp(form.inn || '');
  const ibanError = validateOptionalByIban(form.iban || '');

  if (!form.name.trim()) {
    fieldErrors.name = 'Имя клиента не может быть пустым';
  }
  if (isBusinessCustomer(form.type) && !form.full_legal_name.trim()) {
    fieldErrors.full_legal_name = 'Для ИП или юрлица укажите полное наименование';
  }

  return {
    valid: !phoneError && !emailError && !innError && !ibanError && !Object.keys(fieldErrors).length,
    fieldErrors,
    phoneError,
    emailError,
    innError,
    ibanError,
  };
};

export const normalizeCustomerPartyType = (value: unknown): CustomerPartyType => {
  if (value === 'individual_entrepreneur' || value === 'company') return value;
  return 'individual';
};

export const isBusinessCustomer = (type: CustomerPartyType) => type !== 'individual';

export const customerPartyLabel = (type: CustomerPartyType) => ({
  individual: 'Физ. лицо',
  individual_entrepreneur: 'ИП',
  company: 'Юр. лицо',
}[type]);

export const defaultSigningMode = (type: CustomerPartyType): CustomerSigningMode => (
  type === 'company' ? 'statutory_body' : 'self'
);

export const normalizeCustomerSigningMode = (
  type: CustomerPartyType,
  value: unknown,
): CustomerSigningMode => {
  if (type === 'company') {
    return value === 'power_of_attorney' ? 'power_of_attorney' : 'statutory_body';
  }
  return value === 'power_of_attorney' ? 'power_of_attorney' : 'self';
};
