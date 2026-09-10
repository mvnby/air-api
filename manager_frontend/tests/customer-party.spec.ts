import { describe, expect, it } from 'vitest';

import { isB2cCustomer, isBusinessCustomer } from '../src/utils/customer-party';

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
