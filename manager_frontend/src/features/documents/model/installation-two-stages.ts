import type { ConsumerDocumentTerms } from './consumer-document-terms';

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

export const formatBynAmount = (cents: number | null) => {
  if (cents === null) return '—';
  return (cents / 100).toLocaleString('ru-RU', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
};

export const formatByn = (cents: number | null) => cents === null ? '—' : `${formatBynAmount(cents)} BYN`;

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
  rawRemainingAmount?: string | null,
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
  if (rawRemainingAmount != null && moneyToCents(rawRemainingAmount) !== proposalTotalCents - firstStageCents) {
    return { firstStageCents, remainingCents: null, error: 'Суммы этапов должны совпадать с полной стоимостью предложения' };
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

export const serializeInstallationTerms = (terms: ConsumerDocumentTerms): ConsumerDocumentTerms => ({
  ...terms,
  installation_first_stage_amount: terms.installation_two_stages ? normalizeByNAmount(terms.installation_first_stage_amount) : null,
  installation_remaining_amount: terms.installation_two_stages ? normalizeByNAmount(terms.installation_remaining_amount) : null,
});
export const installationStageDefaults = (outdoorInFirst: boolean) => ({
  first: outdoorInFirst
    ? 'Установка наружного блока, штробление и прокладка коммуникаций.'
    : 'Штробление и прокладка коммуникаций.',
  second: outdoorInFirst
    ? 'Установка внутреннего блока, подключение и пусконаладочные работы.'
    : 'Установка наружного и внутреннего блоков, подключение и пусконаладочные работы.',
  due: 'После завершения ремонта и готовности помещения; дата выезда согласовывается сторонами. Остаток оплачивается после выполнения и приемки второго этапа.',
});

export const installationRemainingDefault = (outdoorInFirst: boolean, count: number) => (
  (outdoorInFirst ? 10000 : 20000) * count
);

export const installationTermsError = (terms: ConsumerDocumentTerms, total: number | null) => {
  if (!Number.isInteger(terms.installation_unit_count) || terms.installation_unit_count < 1 || terms.installation_unit_count > 1000) {
    return 'Укажите количество кондиционеров от 1 до 1000';
  }
  if ([terms.installation_first_stage_works, terms.installation_second_stage_works, terms.installation_second_stage_due]
    .some((value) => value !== null && !value.trim())) {
    return 'Заполните состав работ и условия завершения этапов';
  }
  return calculateInstallationTwoStages(terms.installation_first_stage_amount, total, terms.installation_remaining_amount).error;
};
