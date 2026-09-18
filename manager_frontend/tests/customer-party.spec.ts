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
