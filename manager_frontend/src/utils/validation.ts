import { normalizeIban, normalizeUnp } from './legal-requisites';
import { isInternationalPhoneComplete, normalizePhoneDigits } from './phone';

export function normalizeEmail(value: string): string {
  return (value || '').trim().toLowerCase();
}

export function isValidEmail(value: string): boolean {
  const email = normalizeEmail(value);
  if (!email) return false;
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
}

export function validateOptionalEmail(value: string): string {
  const email = normalizeEmail(value);
  if (!email) return '';
  return isValidEmail(email) ? '' : 'Введите корректный email';
}

export function validateOptionalByUnp(value: string): string {
  const unp = normalizeUnp(value || '');
  if (!unp) return '';
  return unp.length === 9 ? '' : 'УНП должен содержать 9 цифр';
}

function ibanChecksumValid(iban: string): boolean {
  return /^BY\d{2}[A-Z0-9]{24}$/.test(iban);
}

export function validateOptionalByIban(value: string): string {
  const iban = normalizeIban(value || '');
  if (!iban) return '';
  if (!iban.startsWith('BY') || iban.length !== 28) return 'Введите корректный IBAN BY';
  return ibanChecksumValid(iban) ? '' : 'Введите корректный IBAN BY';
}

export function validateOptionalBelarusPhone(masked: string, isMaskComplete: boolean): string {
  const raw = (masked || '').trim();
  if (!raw) return '';
  const digits = normalizePhoneDigits(raw);
  if (digits === '375') return '';
  if (!isMaskComplete || !isInternationalPhoneComplete(raw)) {
    return 'Введите телефон в международном формате, например +375 (XX) XXX-XX-XX или +7 XXX XXX-XX-XX';
  }
  return '';
}
