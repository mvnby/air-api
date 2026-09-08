export type InstallationTwoStagesCalculation = {
  firstStageCents: number | null;
  remainingCents: number | null;
  error: string;
};

const DECIMAL_AMOUNT = /^(\d+)(?:[.,](\d{1,2}))?$/;

export const moneyToCents = (value: unknown): number | null => {
  if (typeof value === 'number') {
    if (!Number.isFinite(value)) return null;
    const cents = Math.round(value * 100);
    return Number.isSafeInteger(cents) ? cents : null;
  }
  const raw = String(value ?? '').trim();
  const match = raw.match(DECIMAL_AMOUNT);
  if (!match) return null;

  const whole = Number(match[1]);
  if (!Number.isSafeInteger(whole)) return null;
  const fraction = (match[2] || '').padEnd(2, '0');
  const cents = whole * 100 + Number(fraction);
  return Number.isSafeInteger(cents) ? cents : null;
};

export const centsToAmount = (cents: number) => `${Math.floor(cents / 100)}.${String(cents % 100).padStart(2, '0')}`;

export const formatByn = (cents: number | null) => {
  if (cents === null) return '—';
  return `${(cents / 100).toLocaleString('ru-RU', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })} BYN`;
};

export const proposalLineTotalCents = (proposal: {
  product_lines?: Array<{ line_total: number }>;
  service_lines?: Array<{ line_total: number }>;
} | null | undefined) => {
  if (!proposal) return null;
  const lines = [...(proposal.product_lines || []), ...(proposal.service_lines || [])];
  if (!lines.length) return null;
  let total = 0;
  for (const line of lines) {
    const cents = moneyToCents(line.line_total);
    if (cents === null) return null;
    total += cents;
  }
  return total;
};

export const calculateInstallationTwoStages = (
  rawFirstStageAmount: string | null,
  proposalTotalCents: number | null,
): InstallationTwoStagesCalculation => {
  if (proposalTotalCents === null || proposalTotalCents <= 0) {
    return { firstStageCents: null, remainingCents: null, error: 'Не удалось определить сумму выбранного предложения' };
  }
  const firstStageCents = moneyToCents(rawFirstStageAmount);
  if (firstStageCents === null) {
    return { firstStageCents: null, remainingCents: null, error: 'Введите сумму первого этапа с точностью до копеек' };
  }
  if (firstStageCents <= 0 || firstStageCents >= proposalTotalCents) {
    return {
      firstStageCents,
      remainingCents: null,
      error: 'Первый этап должен быть больше 0 и меньше полной суммы предложения',
    };
  }
  return {
    firstStageCents,
    remainingCents: proposalTotalCents - firstStageCents,
    error: '',
  };
};

export const normalizeByNAmount = (value: string | null) => {
  const cents = moneyToCents(value);
  return cents === null ? null : centsToAmount(cents);
};
