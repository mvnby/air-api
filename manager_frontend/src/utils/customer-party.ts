export type CustomerPartyIdentity = {
  type?: string | null;
  inn?: string | null;
} | null | undefined;

const hasValue = (value: unknown): boolean => Boolean(String(value || '').trim());

export const isBusinessCustomer = (customer: CustomerPartyIdentity): boolean => (
  customer?.type === 'company'
  || customer?.type === 'individual_entrepreneur'
  // Older records may have requisites without a normalized party type.
  || hasValue(customer?.inn)
);

export const isB2cCustomer = (customer: CustomerPartyIdentity): boolean => !isBusinessCustomer(customer);
