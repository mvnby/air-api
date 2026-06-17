function normalizePhoneDigits(value: string): string {
  const digits = value.replace(/\D/g, '');
  if (!digits) return '';
  if (digits.startsWith('375') && digits.length >= 12) return digits.slice(0, 12);
  if (digits.startsWith('80') && digits.length >= 11) return `375${digits.slice(2, 11)}`;
  if (digits.startsWith('0') && digits.length >= 10) return `375${digits.slice(1, 10)}`;
  if (digits.length === 9) return `375${digits}`;
  return digits;
}

function isInternationalPhoneComplete(value: string): boolean {
  const raw = (value || '').trim();
  if (!raw || !/^\+?[\d\s().-]+$/.test(raw)) return false;
  const normalized = normalizePhoneDigits(raw);
  return normalized.length >= 7 && normalized.length <= 15;
}

export function formatPhoneForDisplay(value: string): string {
  const trimmed = (value || '').trim();
  const normalized = normalizePhoneDigits(trimmed);
  if (normalized.length === 12 && normalized.startsWith('375')) {
    return `+375 (${normalized.slice(3, 5)}) ${normalized.slice(5, 8)}-${normalized.slice(8, 10)}-${normalized.slice(10, 12)}`;
  }
  if (normalized.length === 11 && (normalized.startsWith('7') || normalized.startsWith('8'))) {
    const national = normalized.startsWith('8') ? `7${normalized.slice(1)}` : normalized;
    return `+7 (${national.slice(1, 4)}) ${national.slice(4, 7)}-${national.slice(7, 9)}-${national.slice(9, 11)}`;
  }
  return trimmed;
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

export function validateRequiredBelarusPhone(masked: string, _isMaskComplete: boolean): string {
  const raw = (masked || '').trim();
  if (!raw) return 'Введите номер телефона';
  if (!isInternationalPhoneComplete(raw)) {
    return 'Введите телефон в международном формате, например +375 (XX) XXX-XX-XX или +7 XXX XXX-XX-XX';
  }
  const digits = normalizePhoneDigits(raw);
  return digits.length >= 7 && digits.length <= 15
    ? ''
    : 'Введите телефон в международном формате, например +375 (XX) XXX-XX-XX или +7 XXX XXX-XX-XX';
}
