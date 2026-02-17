function normalizePhoneDigits(value: string): string {
  const digits = value.replace(/\D/g, '');
  if (!digits) return '';
  if (digits.startsWith('375') && digits.length >= 12) return digits.slice(0, 12);
  if (digits.startsWith('80') && digits.length >= 11) return `375${digits.slice(2, 11)}`;
  if (digits.startsWith('0') && digits.length >= 10) return `375${digits.slice(1, 10)}`;
  if (digits.length === 9) return `375${digits}`;
  return digits;
}

function isBelarusPhoneComplete(masked: string): boolean {
  const normalized = normalizePhoneDigits(masked);
  return normalized.length === 12 && normalized.startsWith('375');
}

function normalizeIban(value: string): string {
  return (value || '').replace(/\s/g, '').toUpperCase();
}

function normalizeUnp(value: string): string {
  return (value || '').replace(/\D/g, '').slice(0, 9);
}

export function normalizeEmail(value: string): string {
  return (value || '').trim().toLowerCase();
}

export function validateOptionalEmail(value: string): string {
  const email = normalizeEmail(value);
  if (!email) return '';
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email) ? '' : 'Введите корректный email';
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

export function validateRequiredBelarusPhone(masked: string, isMaskComplete: boolean): string {
  const raw = (masked || '').trim();
  if (!raw) return 'Введите номер телефона';
  if (!isMaskComplete || !isBelarusPhoneComplete(raw)) {
    return 'Введите телефон полностью в формате +375 (XX) XXX-XX-XX';
  }
  const digits = normalizePhoneDigits(raw);
  return digits.length === 12 && digits.startsWith('375')
    ? ''
    : 'Введите телефон полностью в формате +375 (XX) XXX-XX-XX';
}
