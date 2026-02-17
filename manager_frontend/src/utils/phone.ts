function extractNormalizedDigits(value: string): string {
  const digits = value.replace(/\D/g, '');
  if (!digits) return '';

  if (digits.startsWith('375') && digits.length >= 12) return digits.slice(0, 12);
  if (digits.startsWith('80') && digits.length >= 11) return `375${digits.slice(2, 11)}`;
  if (digits.startsWith('0') && digits.length >= 10) return `375${digits.slice(1, 10)}`;
  if (digits.length >= 9 && !digits.startsWith('375')) return `375${digits.slice(-9)}`;
  return digits;
}

export function isBelarusPhoneComplete(masked: string): boolean {
  const normalized = extractNormalizedDigits(masked);
  return normalized.length === 12 && normalized.startsWith('375');
}

export function normalizePhoneForApi(masked: string): string {
  const trimmed = masked.trim();
  if (!trimmed) return '';

  const normalized = extractNormalizedDigits(trimmed);
  if (!(normalized.length === 12 && normalized.startsWith('375'))) {
    return trimmed;
  }

  const operator = normalized.slice(3, 5);
  const p1 = normalized.slice(5, 8);
  const p2 = normalized.slice(8, 10);
  const p3 = normalized.slice(10, 12);
  return `+375 (${operator}) ${p1}-${p2}-${p3}`;
}
