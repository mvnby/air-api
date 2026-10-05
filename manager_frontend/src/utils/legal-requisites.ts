type EgrRow = {
  vnaimp?: string;
  vpadres?: string;
};

type EgrResponse = {
  row?: EgrRow;
};

type BankResponse = {
  name?: string;
  address?: string;
  bic?: string;
};

const UNP_OCR_CONFUSABLES: Record<string, string> = {
  З: '3', з: '3', O: '0', o: '0', О: '0', о: '0', I: '1', i: '1', L: '1', l: '1', І: '1', і: '1',
};

// Keep unexpected characters and extra digits visible so validation can reject
// the value instead of silently turning an OCR paste into another company's UNP.
export const normalizeUnp = (value: string): string => (value || '')
  .normalize('NFKC')
  .replace(/[\s-]+/g, '')
  .replace(/[ЗзOoОоIiLlІі]/g, (character) => UNP_OCR_CONFUSABLES[character] || character);

const IBAN_CONFUSABLES: Record<string, string> = {
  А: 'A', В: 'B', Е: 'E', К: 'K', М: 'M', Н: 'H', О: 'O', Р: 'P',
  С: 'C', Т: 'T', У: 'Y', Х: 'X', І: 'I',
};

export const normalizeIban = (value: string): string => (value || '')
  .normalize('NFKC')
  .toUpperCase()
  .replace(/[АВЕКМНОРСТУХІ]/g, (letter) => IBAN_CONFUSABLES[letter] || letter)
  .replace(/[\s\u200B-\u200D\uFEFF]/g, '');

export const getCompanyFromEgr = (payload: unknown): { fullLegalName?: string; legalAddress?: string } => {
  const data = (payload || {}) as EgrResponse;
  return {
    fullLegalName: data.row?.vnaimp?.trim() || undefined,
    legalAddress: data.row?.vpadres?.trim() || undefined,
  };
};

export const getBankFromLookup = (payload: unknown): { bankName?: string; bic?: string } => {
  const data = (payload || {}) as BankResponse;
  const bankName = data.name ? [data.name, data.address].filter(Boolean).join(', ') : undefined;
  return {
    bankName,
    bic: data.bic?.trim() || undefined,
  };
};
