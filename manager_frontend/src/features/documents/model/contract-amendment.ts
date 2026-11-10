import type { ContractAmendmentTerms_Input } from '../../../client';
export const newAmendmentTerms = (): ContractAmendmentTerms_Input => ({
  works: [{ title: '', quantity: '1', unit: 'компл.', unit_price: '' }], equipment: '',
  acceptance_terms: 'Приёмка дополнительных работ производится на условиях исходного договора.',
  payment_terms: 'Оплата дополнительных работ производится на условиях исходного договора.',
  effective_terms: 'Настоящее соглашение вступает в силу после подписания обеими сторонами.',
});
export const amendmentTermsError = (terms: ContractAmendmentTerms_Input) => {
  if (!terms.works.length || terms.works.some(w => !w.title.trim() || !w.unit.trim() || !(Number(w.quantity) > 0) || !(Number(w.unit_price) > 0))) return 'Заполните название, количество, единицу и цену дополнительных работ';
  if (!terms.payment_terms?.trim() || !terms.acceptance_terms?.trim() || !terms.effective_terms?.trim()) return 'Заполните приёмку, оплату и вступление в силу';
  return '';
};


const scaled = (value: string | number, places: number): bigint | null => {
  const text = String(value).trim();
  if (!new RegExp(`^\\d+(?:\\.\\d{0,${places}})?$`).test(text)) return null;
  const [whole = '0', fraction = ''] = text.split('.');
  return BigInt(whole + fraction.padEnd(places, '0'));
};

// The server rounds each commercial row to cents with ROUND_HALF_UP.
// Keep decimal input exact: 0.5 × 0.29 must display 0.15, including before save.
export const amendmentChangeAmount = (terms: ContractAmendmentTerms_Input): string | null => {
  let cents = 0n;
  for (const work of terms.works) {
    const quantity = scaled(work.quantity, 3);
    const price = scaled(work.unit_price, 2);
    if (quantity === null || price === null) return null;
    cents += (quantity * price + 500n) / 1000n;
  }
  return `${cents / 100n}.${String(cents % 100n).padStart(2, '0')}`;
};
