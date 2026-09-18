import type { ManagerCustomerCreatePayload, ManagerCustomerUpdatePayload } from '../../client';
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
  issues: string[];
  fieldErrors: Partial<Record<keyof CustomerForm, string>>;
  phoneError: string;
  emailError: string;
  innError: string;
  ibanError: string;
};

export const customerPartyTypeWarning = (
  form: Pick<CustomerForm, 'type' | 'name' | 'full_legal_name' | 'inn'>,
): string => {
  if (form.type !== 'individual') return '';
  const identity = `${form.name} ${form.full_legal_name}`.toLocaleLowerCase();
  // Match whole Cyrillic words; JavaScript's \b only understands ASCII letters.
  const entrepreneur = /(?:^|[^а-яёіўa-z])(?:ип|индивидуальный\s+предприниматель|індывідуальны\s+прадпрымальнік)(?=$|[^а-яёіўa-z])/u.test(identity);
  const company = /(?:^|[^а-яёіўa-z])(?:ооо|одо|оао|зао|пао|ао|иооо|уп|чуп|чтуп|пуп|руп|куп|гуп|таа|тда|аат|зат)(?=$|[^а-яёіўa-z])|унитарное\s+предприятие|унітарнае\s+прадпрыемства|общество\s+с\s+(?:ограниченной|дополнительной)\s+ответственностью|акционерное\s+общество/u.test(identity);
  if (company) return 'Вы сохраняете организацию как физлицо. Выберите «Юрлицо» перед сохранением.';
  if (entrepreneur) return 'В названии указан предприниматель, но выбран тип «Физлицо». Выберите «ИП» перед сохранением.';
  if (form.inn.trim()) return 'У клиента указан УНП, но выбран тип «Физлицо». Проверьте реквизиты и выберите «ИП» или «Юрлицо» перед сохранением.';
  return '';
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

export const buildCustomerCreatePayload = (
  form: CustomerForm,
): ManagerCustomerCreatePayload => ({
  name: form.name.trim(),
  type: form.type,
  phone: normalizePhoneForApi(form.phone),
  email: normalizeEmail(form.email),
  city: form.city.trim(),
  inn: normalizeUnp(form.inn),
  kpp: form.kpp.trim(),
  full_legal_name: form.full_legal_name.trim(),
  legal_address: form.legal_address.trim(),
  actual_address: form.actual_address.trim(),
  bank_name: form.bank_name.trim(),
  bic: form.bic.trim(),
  iban: normalizeIban(form.iban),
  signer_position: form.signer_position.trim(),
  signer_name: form.signer_name.trim(),
  acting_basis: form.acting_basis.trim(),
  signing_mode: normalizeCustomerSigningMode(form.type, form.signing_mode),
});

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
  const partyWarning = customerPartyTypeWarning(form);
  if (partyWarning) fieldErrors.type = partyWarning;

  const issues = [
    fieldErrors.name && `Название — ${fieldErrors.name}`,
    fieldErrors.type,
    phoneError && `Телефон — ${phoneError}`,
    emailError && `Email — ${emailError}`,
    innError && `УНП — ${innError}`,
    ibanError && `IBAN — ${ibanError}`,
  ].filter((issue): issue is string => Boolean(issue));

  return {
    valid: issues.length === 0,
    issues,
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
