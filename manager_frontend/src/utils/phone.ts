function extractNormalizedDigits(value: string): string {
  const digits = value.replace(/\D/g, '');
  if (!digits) return '';

  if (digits.startsWith('375') && digits.length >= 12) return digits.slice(0, 12);
  if (digits.startsWith('80') && digits.length >= 11) return `375${digits.slice(2, 11)}`;
  if (digits.startsWith('0') && digits.length >= 10) return `375${digits.slice(1, 10)}`;
  if (digits.length === 9) return `375${digits}`;
  return digits;
}

export function normalizePhoneDigits(value: string): string {
  return extractNormalizedDigits(value);
}

export function isInternationalPhoneComplete(value: string): boolean {
  const raw = (value || '').trim();
  if (!raw || !/^\+?[\d\s().-]+$/.test(raw)) return false;
  const normalized = extractNormalizedDigits(raw);
  return normalized.length >= 7 && normalized.length <= 15;
}

export function formatPhoneForDisplay(value: string): string {
  const trimmed = value.trim();
  const normalized = extractNormalizedDigits(trimmed);
  if (normalized.length === 12 && normalized.startsWith('375')) {
    const operator = normalized.slice(3, 5);
    const p1 = normalized.slice(5, 8);
    const p2 = normalized.slice(8, 10);
    const p3 = normalized.slice(10, 12);
    return `+375 (${operator}) ${p1}-${p2}-${p3}`;
  }

  if (normalized.length === 11 && (normalized.startsWith('7') || normalized.startsWith('8'))) {
    const national = normalized.startsWith('8') ? `7${normalized.slice(1)}` : normalized;
    const operator = national.slice(1, 4);
    const p1 = national.slice(4, 7);
    const p2 = national.slice(7, 9);
    const p3 = national.slice(9, 11);
    return `+7 (${operator}) ${p1}-${p2}-${p3}`;
  }

  return trimmed;
}

export function normalizePhoneForApi(masked: string): string {
  const trimmed = masked.trim();
  if (!trimmed) return '';

  const normalized = extractNormalizedDigits(trimmed);
  if (normalized.length < 7) return '';
  return formatPhoneForDisplay(trimmed);
}
