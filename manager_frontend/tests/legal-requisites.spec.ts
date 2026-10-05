import { describe, expect, it, vi } from 'vitest';
import { normalizeUnp } from '../src/utils/legal-requisites';
import { validateOptionalByUnp } from '../src/utils/validation';
import { useB2BLookup } from '../src/composables/useB2BLookup';

const api = vi.hoisted(() => ({ getCompanyByUnp: vi.fn() }));
vi.mock('../src/api', () => ({ api }));

describe('UNP OCR normalization', () => {
  it('maps the requested Latin and Cyrillic lookalikes and removes separators', () => {
    expect(normalizeUnp('Зз Oо 0 I l Іі 1-2345')).toBe('33000111112345');
    expect(normalizeUnp('IiLl')).toBe('1111');
    expect(normalizeUnp('３００２３０５６５')).toBe('300230565');
  });

  it('preserves unexpected characters and extra digits so validation rejects them', () => {
    expect(normalizeUnp('12345X789')).toBe('12345X789');
    expect(normalizeUnp('1234567890')).toBe('1234567890');
    expect(validateOptionalByUnp('12345X789')).toBe('УНП должен содержать 9 цифр');
    expect(validateOptionalByUnp('1234567890')).toBe('УНП должен содержать 9 цифр');
  });

  it('does not turn invalid input into an empty valid value', () => {
    expect(normalizeUnp('—')).toBe('—');
    expect(validateOptionalByUnp('—')).toBe('УНП должен содержать 9 цифр');
  });

  it('does not look up invalid input and sends a normalized nine digit UNP', async () => {
    api.getCompanyByUnp.mockResolvedValue({ row: { vnaimp: 'ООО Тест' } });
    const { lookupCompany } = useB2BLookup();
    expect(await lookupCompany('12345X789')).toBeNull();
    expect(await lookupCompany('1234567890')).toBeNull();
    expect(api.getCompanyByUnp).not.toHaveBeenCalled();
    await lookupCompany('ЗО1-456789');
    expect(api.getCompanyByUnp).toHaveBeenCalledWith('301456789');
  });
});
