import type { DashboardKpi, DashboardMarketing, DashboardPeriod } from '../client';

export type DashboardMode = 'manager' | 'owner';
export type DashboardKpiKey = 'revenue' | 'new_leads' | 'sales' | 'installations' | 'active_tasks' | 'receivables';

export const DASHBOARD_MODE_STORAGE_KEY = 'manager:dashboard:mode:v1';

export const dashboardKpiOrder: Record<DashboardMode, DashboardKpiKey[]> = {
  manager: ['new_leads', 'active_tasks', 'sales', 'installations', 'revenue', 'receivables'],
  owner: ['revenue', 'sales', 'receivables', 'new_leads', 'installations', 'active_tasks'],
};

export const dashboardKpiLabels: Record<DashboardKpiKey, string> = {
  revenue: 'Оплаты за месяц',
  new_leads: 'Новые заявки',
  sales: 'Продажи',
  installations: 'Монтажи',
  active_tasks: 'Активные касания',
  receivables: 'Дебиторская задолженность',
};

export const loadDashboardMode = (): DashboardMode => {
  try {
    return window.localStorage.getItem(DASHBOARD_MODE_STORAGE_KEY) === 'owner' ? 'owner' : 'manager';
  } catch {
    return 'manager';
  }
};

export const saveDashboardMode = (mode: DashboardMode) => {
  try {
    window.localStorage.setItem(DASHBOARD_MODE_STORAGE_KEY, mode);
  } catch {
    // Dashboard remains usable where local storage is unavailable.
  }
};

export const formatDashboardNumber = (value: number | null | undefined) => (
  value == null ? '—' : new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 1 }).format(value)
);

export const formatDashboardCurrency = (value: number | null | undefined) => (
  value == null
    ? '—'
    : new Intl.NumberFormat('ru-RU', { style: 'currency', currency: 'BYN', maximumFractionDigits: 0 }).format(value)
);

const inclusivePeriodEnd = (endExclusive: string) => new Date(new Date(endExclusive).getTime() - 1);
const dashboardDateParts = (value: Date) => Object.fromEntries(
  new Intl.DateTimeFormat('ru-RU', {
    day: 'numeric', month: 'numeric', year: 'numeric', timeZone: 'Europe/Minsk',
  }).formatToParts(value).map(part => [part.type, part.value]),
);
const formatPeriodRange = (start: string, endExclusive: string) => {
  const startDate = new Date(start);
  const endDate = inclusivePeriodEnd(endExclusive);
  const startParts = dashboardDateParts(startDate);
  const endParts = dashboardDateParts(endDate);
  const dateFormatter = new Intl.DateTimeFormat('ru-RU', { day: 'numeric', month: 'short', timeZone: 'Europe/Minsk' });
  const endLabel = dateFormatter.format(endDate);
  return startParts.month === endParts.month && startParts.year === endParts.year
    ? `${Number(startParts.day)}–${endLabel}`
    : `${dateFormatter.format(startDate)}–${endLabel}`;
};

export const formatDashboardComparisonPeriod = (period: DashboardPeriod) => (
  `${formatPeriodRange(period.current.start, period.current.end)} · сравнение: ${formatPeriodRange(period.previous.start, period.previous.end)}`
);

export const formatDashboardKpi = (key: DashboardKpiKey, kpi: DashboardKpi) => (
  kpi.unit === 'byn' || key === 'revenue' || key === 'receivables'
    ? formatDashboardCurrency(kpi.current)
    : formatDashboardNumber(kpi.current)
);

export type DashboardTrend = { label: string; tone: 'positive' | 'negative' | 'neutral' };

export const getDashboardTrend = (key: DashboardKpiKey, kpi: DashboardKpi): DashboardTrend => {
  if (kpi.previous == null || kpi.trend === 'unavailable' || kpi.delta_pct == null) {
    return { label: 'Срез на сейчас', tone: 'neutral' };
  }
  if (kpi.trend === 'flat') return { label: 'Без изменений', tone: 'neutral' };

  const prefix = kpi.delta_pct > 0 ? '+' : '';
  const label = `${prefix}${new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 1 }).format(kpi.delta_pct)}% к тому же периоду`;
  if (key === 'receivables') {
    return { label, tone: kpi.trend === 'down' ? 'positive' : 'negative' };
  }
  return { label, tone: kpi.trend === 'up' ? 'positive' : 'negative' };
};

export const dashboardMarketingStatus = (marketing: Pick<DashboardMarketing, 'status'>) => {
  const messages = {
    fresh: 'Данные аналитики обновлены и готовы к работе.',
    stale: 'Данные аналитики обновлялись давно и могут быть неактуальны.',
    error: 'Интеграция аналитики временно недоступна. CRM-данные продолжают работать.',
    unconfigured: 'Подключите Яндекс Метрику, чтобы видеть визиты и источники.',
  } as const;
  const labels = {
    fresh: 'Данные актуальны',
    stale: 'Данные устарели',
    error: 'Ошибка интеграции',
    unconfigured: 'Не подключено',
  } as const;
  return { label: labels[marketing.status], message: messages[marketing.status], tone: marketing.status };
};

export const formatMarketingProvider = (provider: string | null | undefined) => {
  if (provider === 'integrated') return 'Сводка по подключённым источникам';
  if (provider === 'yandex_metrika') return 'Яндекс Метрика';
  if (provider === 'yandex_direct') return 'Яндекс Директ';
  if (provider === 'google_analytics') return 'Google Analytics 4';
  if (provider === 'google_ads') return 'Google Ads';
  return provider || 'Веб-аналитика и реклама';
};

export const formatSearchDemandProvider = (provider: string) => {
  if (provider === 'yandex_webmaster') return 'Яндекс Вебмастер';
  if (provider === 'google_search_console') return 'Google Search Console';
  return provider;
};

export const formatMarketingValue = (
  value: number | null | undefined,
  kind: 'count' | 'currency' | 'percent' = 'count',
) => {
  if (value == null) return '—';
  if (kind === 'currency') return formatDashboardCurrency(value);
  if (kind === 'percent') return `${new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 2 }).format(value)}%`;
  return formatDashboardNumber(value);
};

export const formatMarketingCurrency = (
  value: number | null | undefined,
  currency: string | null | undefined,
) => {
  if (value == null) return '—';
  if (!currency) return formatDashboardNumber(value);
  try {
    return new Intl.NumberFormat('ru-RU', {
      style: 'currency',
      currency,
      maximumFractionDigits: 2,
    }).format(value);
  } catch {
    return `${formatDashboardNumber(value)} ${currency}`;
  }
};

export const formatDurationSeconds = (value: number | null | undefined) => {
  if (value == null) return '—';
  const totalSeconds = Math.max(0, Math.round(value));
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return minutes ? `${minutes} мин ${seconds.toString().padStart(2, '0')} с` : `${seconds} с`;
};
