import { describe, expect, it } from 'vitest';

import { isB2cCustomer, isBusinessCustomer } from '../src/utils/customer-party';
import {
  buildCustomerPatchPayload,
  customerPartyTypeWarning,
  validateCustomerProfileForm,
  type CustomerForm,
} from '../src/components/customers/customer-profile-form';

const individual: CustomerForm = {
  type: 'individual', name: 'Иванов Иван Иванович', full_legal_name: '', inn: '',
  phone: '', email: '', city: '', kpp: '', legal_address: '', actual_address: '',
  bank_name: '', bic: '', iban: '', signer_position: '', signer_name: '', acting_basis: '',
  signing_mode: 'self',
};

describe('customer profile party guard', () => {
  it.each([
    [{ inn: '123456789' }, '«ИП» или «Юрлицо»'],
    [{ name: 'ИП Иванов Иван Иванович' }, 'Выберите «ИП»'],
    [{ name: 'ООО «Тест»' }, 'Выберите «Юрлицо»'],
    [{ full_legal_name: 'Частное торговое унитарное предприятие "МЭДО"' }, 'Выберите «Юрлицо»'],
  ])('blocks saving an individual with business identity %s', (fields, message) => {
    const form = { ...individual, ...fields };
    expect(customerPartyTypeWarning(form)).toContain(message);
    const validation = validateCustomerProfileForm(form, false);
    expect(validation.valid).toBe(false);
    expect(validation.fieldErrors.type).toContain(message);
    expect(validation.issues).toContain(validation.fieldErrors.type);
    expect(validateCustomerProfileForm({ ...form, type: 'company' }, false).valid).toBe(true);
    expect(validateCustomerProfileForm({ ...form, type: 'individual_entrepreneur' }, false).valid).toBe(true);
  });

  it('does not mistake a personal bank account or a substring for an organization', () => {
    expect(customerPartyTypeWarning({ ...individual, name: 'Филипп АОнов' })).toBe('');
    const form = { ...individual, bank_name: 'ОАО Банк', iban: 'BY13NBRB3600900000002Z00AB00' };
    expect(customerPartyTypeWarning(form)).toBe('');
    expect(validateCustomerProfileForm(individual, false).valid).toBe(true);
  });

  it('keeps the existing party type out of an unrelated edit and sends deliberate changes', () => {
    const form: CustomerForm = { ...individual, type: 'company', signing_mode: 'statutory_body' };
    expect(buildCustomerPatchPayload(form, { name: true })).toEqual({ name: form.name });
    expect(buildCustomerPatchPayload(form, { type: true, signing_mode: true })).toEqual({
      type: 'company', signing_mode: 'statutory_body',
    });
  });
});

describe('customer party classification', () => {
  it.each([
    ['individual', { type: 'individual', inn: '' }, false],
    ['individual entrepreneur', { type: 'individual_entrepreneur', inn: '' }, true],
    ['company', { type: 'company', inn: '' }, true],
    ['legacy requisites', { type: 'individual', inn: ' 123456789 ' }, true],
    ['missing customer', undefined, false],
  ])('classifies %s without relying on order data', (_name, customer, expectedBusiness) => {
    expect(isBusinessCustomer(customer)).toBe(expectedBusiness);
    expect(isB2cCustomer(customer)).toBe(!expectedBusiness);
  });
});

import { customerCompleteness } from '../src/components/customers/customer-completeness';
import type { ManagerCatalogCustomerItemResponse } from '../src/client';
const dossier = (extra: Record<string, unknown> = {}) => ({ id: 1, name: 'Клиент', type: 'company', signing_mode: 'statutory_body', ...extra } as ManagerCatalogCustomerItemResponse);
const group = (extra: Record<string, unknown>, id: string) => customerCompleteness(dossier(extra)).find(g => g.id === id)!;
describe('saved dossier completeness', () => {
  it.each([null, undefined, '', '  \n '])('counts empty values as absent: %s', value => {
    expect(group({ phone: value, email: value }, 'contacts').missing).toEqual(['телефон', 'email']);
    expect(group({ inn: value, full_legal_name: value }, 'identity').missing).toEqual(['полное наименование', 'УНП']);
    expect(group({ bank_name: value, bic: value, iban: value }, 'bank').missing).toEqual(['название банка', 'BIC', 'IBAN']);
  });
  it.each([['phone', ['email']], ['email', ['телефон']]])('accepts %s only', (key, missing) => {
    expect(group({ [key]: ' saved ' }, 'contacts').missing).toEqual(missing);
  });
  it('uses primary and legacy channels together without guessing from a contact name', () => {
    expect(group({ phone: '1', primary_contact: { email: 'a@b.test', is_active: true } }, 'contacts').missing).toEqual([]);
    expect(group({ primary_contact: { name: 'Анна' }, contact_count: 1 }, 'contacts').missing).toEqual(['телефон', 'email']);
  });
  it('ignores inactive contacts and snapshots belonging to another client', () => {
    expect(customerCompleteness(dossier(), { customerId: 1, items: [{ customer_id: 1, phone: '1', is_active: false }] })[0].missing).toEqual(['телефон', 'email']);
    expect(customerCompleteness(dossier(), { customerId: 2, items: [{ customer_id: 2, phone: '1', email: 'a' }] })[0].missing).toEqual(['телефон', 'email']);
  });
  it.each(['individual', 'individual_entrepreneur', 'company'])('applies fields to %s and its valid modes', type => {
    const groups = customerCompleteness(dossier({ type, signing_mode: type === 'company' ? 'statutory_body' : 'self' }));
    expect(groups.find(g => g.id === 'identity')!.applicable).toBe(type !== 'individual');
    expect(groups.find(g => g.id === 'bank')!.applicable).toBe(type !== 'individual');
    expect(groups.find(g => g.id === 'signer')!.missing).toEqual(type === 'individual' ? [] : type === 'company' ? ['ФИО подписанта', 'должность подписанта', 'основание полномочий'] : ['ФИО подписанта']);
    expect(group({ type, signing_mode: 'power_of_attorney' }, 'signer').missing).toEqual(['ФИО представителя', 'основание полномочий представителя']);
  });
  it('does not normalize incompatible or missing signing modes into saved evidence', () => {
    expect(group({ type: 'individual_entrepreneur', signing_mode: 'statutory_body' }, 'signer').missing).toContain('допустимый режим подписания');
    expect(group({ signing_mode: undefined }, 'signer').missing).toContain('допустимый режим подписания');
    const signer = group({ signer_name: 'Иванов', signer_position: 'Директор', acting_basis: 'Устав' }, 'signer');
    expect(signer.missing).toEqual([]);
    expect(signer.note).toContain('не подтверждают полномочия');
  });
  it('uses saved delivery addresses for individuals', () => {
    expect(group({ type: 'individual', last_delivery_address: 'Минск' }, 'addresses').missing).toEqual([]);
    expect(group({ type: 'individual', actual_address: '  ' }, 'addresses').missing).toEqual(['адрес объекта / доставки']);
  });
});
