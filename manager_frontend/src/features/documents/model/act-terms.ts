export type ActClaimsStatus = 'none' | 'present';

export type ActTerms = {
  result_text: string | null;
  claims_status: ActClaimsStatus;
  claims_text: string | null;
  acceptance_deadline: string | null;
};

export const createDefaultActTerms = (): ActTerms => ({
  result_text: null,
  claims_status: 'none',
  claims_text: null,
  acceptance_deadline: null,
});

export const actTermsValidationError = (terms: ActTerms) => (
  terms.claims_status === 'present' && !terms.claims_text?.trim()
    ? 'Опишите замечания заказчика'
    : ''
);
